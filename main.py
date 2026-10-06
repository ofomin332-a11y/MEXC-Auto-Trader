import os, re, json, time, hmac, hashlib, uuid, math, logging, asyncio
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Dict, Any

import requests
from telethon import TelegramClient, events
from telethon.sessions import StringSession

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
log = logging.getLogger('mexc-auto-trader')

BASE_URL = os.getenv('MEXC_BASE_URL', 'https://api.mexc.com').rstrip('/')
API_KEY = os.environ['MEXC_API_KEY']
API_SECRET = os.environ['MEXC_API_SECRET']
TG_API_ID = int(os.environ['TG_API_ID'])
TG_API_HASH = os.environ['TG_API_HASH']
TG_SESSION = os.environ['TG_SESSION']
CHANNEL = os.getenv('TELEGRAM_CHANNEL', 'skrenner_r').lstrip('@')
NOTIFY_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
NOTIFY_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
MARGIN_USDT = Decimal(os.getenv('MARGIN_USDT', '25'))
LEVERAGE = int(os.getenv('LEVERAGE', '15'))
TP_PCT = Decimal(os.getenv('TP_PCT', '0.02'))
SL_PCT = Decimal(os.getenv('SL_PCT', '0.04'))
POSITION_MODE = int(os.getenv('POSITION_MODE', '2'))
LIVE_TRADING = os.getenv('LIVE_TRADING', 'false').lower() == 'true'
MAX_OPEN_POSITIONS = int(os.getenv('MAX_OPEN_POSITIONS', '1'))

if MARGIN_USDT <= 0 or LEVERAGE <= 0 or TP_PCT <= 0 or SL_PCT <= 0:
    raise ValueError('Invalid trading parameters')

session = requests.Session()
session.headers.update({'Content-Type': 'application/json', 'ApiKey': API_KEY, 'Recv-Window': '5000'})

_contracts: Dict[str, Dict[str, Any]] = {}
_seen = set()
_seen_order = []
MAX_SEEN = 500


def _json_compact(data):
    return json.dumps(data, separators=(',', ':'), ensure_ascii=False)


def _sign(method: str, path: str, params: Optional[dict] = None):
    ts = str(int(time.time() * 1000))
    params = params or {}
    if method.upper() == 'GET':
        items = [(k, v) for k, v in params.items() if v is not None]
        query = '&'.join(f'{k}={v}' for k, v in sorted(items))
        target = API_KEY + ts + query
        url = BASE_URL + path
        if query:
            url += '?' + query
        return url, {'ApiKey': API_KEY, 'Request-Time': ts, 'Signature': hmac.new(API_SECRET.encode(), target.encode(), hashlib.sha256).hexdigest(), 'Recv-Window': '5000'}
    body = _json_compact(params)
    target = API_KEY + ts + body
    return BASE_URL + path, {'ApiKey': API_KEY, 'Request-Time': ts, 'Signature': hmac.new(API_SECRET.encode(), target.encode(), hashlib.sha256).hexdigest(), 'Recv-Window': '5000', 'Content-Type': 'application/json'}


def request(method: str, path: str, params=None, private=False):
    method = method.upper()
    if private:
        url, headers = _sign(method, path, params or {})
    else:
        url = BASE_URL + path
        headers = {'Content-Type': 'application/json'}
    if method == 'POST':
        body = _json_compact(params or {})
        r = session.request(method, url, headers=headers, data=body, timeout=15)
    else:
        r = session.request(method, url, headers=headers, params=(params or {}) if method == 'GET' else None, timeout=15)
    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f'MEXC HTTP {r.status_code}: {r.text[:500]}')
    if r.status_code >= 400 or data.get('success') is False:
        raise RuntimeError(f'MEXC error HTTP={r.status_code} response={data}')
    return data


def load_contracts():
    global _contracts
    data = request('GET', '/api/v1/contract/detail')
    rows = data.get('data') or []
    _contracts = {str(x.get('symbol', '')).upper(): x for x in rows if x.get('symbol')}
    log.info('Loaded %d MEXC futures contracts', len(_contracts))


def normalize_symbol(raw: str) -> Optional[str]:
    s = raw.upper().strip().replace('/', '').replace('-', '').replace('_', '')
    if not s:
        return None
    if s.endswith('USDT'):
        base = s[:-4]
        candidates = [f'{base}_USDT', f'{base}_USDT'.upper()]
    elif s.endswith('USDC'):
        base = s[:-4]
        candidates = [f'{base}_USDC']
    else:
        candidates = [f'{s}_USDT']
    for c in candidates:
        if c in _contracts:
            return c
    # exact baseCoin match fallback
    for name, c in _contracts.items():
        if name.replace('_', '') == s:
            return name
    return None


def parse_signal(text: str):
    t = text.upper()
    # Prefer explicit direction words. PUMP=LONG, DUMP=SHORT.
    long_words = bool(re.search(r'\b(LONG|PUMP|BULLISH|BUY)\b', t))
    short_words = bool(re.search(r'\b(SHORT|DUMP|BEARISH|SELL)\b', t))
    if long_words == short_words:
        return None
    direction = 'LONG' if long_words else 'SHORT'
    # Common ticker forms: BTCUSDT, BTC/USDT, BTC_USDT, BTC
    matches = re.findall(r'(?<![A-Z0-9])([A-Z][A-Z0-9]{1,19}(?:[_/-]?USDT|[_/-]?USDC))(?![A-Z0-9])', t)
    symbol = None
    for m in matches:
        symbol = normalize_symbol(m)
        if symbol:
            break
    if not symbol:
        # fallback to known contract base symbols mentioned in text
        for name, c in _contracts.items():
            base = name.split('_')[0]
            if re.search(rf'(?<![A-Z0-9]){re.escape(base)}(?![A-Z0-9])', t):
                symbol = name
                break
    if not symbol:
        return None
    return direction, symbol


def decimalize(v, default='0'):
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(default)


def quantize_down(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    units = (value / step).to_integral_value(rounding=ROUND_DOWN)
    return units * step


def current_price(symbol: str) -> Decimal:
    # Public fair-price endpoint. If unavailable, fall back to ticker endpoint.
    try:
        d = request('GET', '/api/v1/contract/fair_price/' + symbol)
        p = (d.get('data') or {}).get('fairPrice') if isinstance(d.get('data'), dict) else d.get('data')
        if p:
            return decimalize(p)
    except Exception as e:
        log.warning('Fair price lookup failed for %s: %s', symbol, e)
    d = request('GET', '/api/v1/contract/ticker', {'symbol': symbol})
    data = d.get('data') or {}
    return decimalize(data.get('lastPrice') or data.get('fairPrice') or data.get('bid1'))


def calc_volume(symbol: str, price: Decimal) -> Decimal:
    c = _contracts[symbol]
    contract_size = decimalize(c.get('contractSize'), '1')
    vol_unit = decimalize(c.get('volUnit'), '1')
    min_vol = decimalize(c.get('minVol'), '1')
    max_vol = decimalize(c.get('maxVol'), '1000000000')
    notional = MARGIN_USDT * Decimal(LEVERAGE)
    raw = notional / (price * contract_size)
    vol = quantize_down(raw, vol_unit)
    if vol < min_vol:
        vol = min_vol
    if vol > max_vol:
        vol = max_vol
    if vol <= 0:
        raise RuntimeError(f'Calculated volume is invalid: {vol}')
    return vol


def open_positions_count():
    try:
        d = request('GET', '/api/v1/private/position/open_positions', private=True)
        rows = d.get('data') or []
        return len(rows)
    except Exception as e:
        log.warning('Could not read open positions: %s', e)
        return 0


def place_order(direction: str, symbol: str):
    price = current_price(symbol)
    c = _contracts[symbol]
    vol = calc_volume(symbol, price)
    price_scale = int(c.get('priceScale', 8) or 8)
    q = Decimal('1').scaleb(-price_scale)
    if direction == 'LONG':
        tp = price * (Decimal('1') + TP_PCT)
        sl = price * (Decimal('1') - SL_PCT)
        side = 1
    else:
        tp = price * (Decimal('1') - TP_PCT)
        sl = price * (Decimal('1') + SL_PCT)
        side = 3
    tp = tp.quantize(q, rounding=ROUND_DOWN)
    sl = sl.quantize(q, rounding=ROUND_DOWN)
    ext = ('AT' + uuid.uuid4().hex[:28]).upper()
    order = {
        'symbol': symbol,
        'price': 0,
        'vol': float(vol) if vol % 1 else int(vol),
        'leverage': LEVERAGE,
        'side': side,
        'type': 5,
        'openType': 1,
        'externalOid': ext,
        'positionMode': POSITION_MODE,
        'stopLossPrice': float(sl),
        'takeProfitPrice': float(tp),
        'lossTrend': 1,
        'profitTrend': 1,
    }
    log.info('%s %s | price=%s vol=%s notional≈%s TP=%s SL=%s LIVE=%s', direction, symbol, price, vol, (vol*decimalize(c.get('contractSize'), '1')*price).quantize(Decimal('0.01')), tp, sl, LIVE_TRADING)
    if not LIVE_TRADING:
        return {'dry_run': True, 'order': order, 'price': str(price), 'tp': str(tp), 'sl': str(sl)}
    result = request('POST', '/api/v1/private/order/create', order, private=True)
    return {'dry_run': False, 'result': result, 'price': str(price), 'tp': str(tp), 'sl': str(sl), 'volume': str(vol), 'externalOid': ext}


def notify(message: str):
    if not NOTIFY_TOKEN or not NOTIFY_CHAT_ID:
        return
    try:
        requests.post(f'https://api.telegram.org/bot{NOTIFY_TOKEN}/sendMessage', data={'chat_id': NOTIFY_CHAT_ID, 'text': message}, timeout=10)
    except Exception as e:
        log.warning('Telegram notification failed: %s', e)


def format_trade(direction, symbol, result):
    if result.get('dry_run'):
        return f'🧪 DRY RUN\n{direction} {symbol}\nEntry≈ {result["price"]}\nTP {result["tp"]}\nSL {result["sl"]}\n25 USDT × 15x'
    d = result.get('result', {}).get('data', {})
    oid = d.get('orderId', '?')
    return f'🤖 MEXC AUTO TRADE\n{direction} {symbol}\nEntry≈ {result["price"]}\nTP {result["tp"]}\nSL {result["sl"]}\nMargin 25 USDT | 15x\nOrder: {oid}'


async def main():
    load_contracts()
    client = TelegramClient(StringSession(TG_SESSION), TG_API_ID, TG_API_HASH)
    await client.start()
    me = await client.get_me()
    log.info('Telegram session authorized as %s', getattr(me, 'username', None) or getattr(me, 'first_name', 'user'))
    log.info('Monitoring Telegram channel @%s | LIVE_TRADING=%s', CHANNEL, LIVE_TRADING)

    @client.on(events.NewMessage(chats=CHANNEL))
    async def handler(event):
        text = event.raw_text or ''
        msg_id = event.id
        key = f'{CHANNEL}:{msg_id}'
        if key in _seen:
            return
        _seen.add(key); _seen_order.append(key)
        if len(_seen_order) > MAX_SEEN:
            _seen.discard(_seen_order.pop(0))
        parsed = parse_signal(text)
        if not parsed:
            log.info('Ignored message %s: no unambiguous LONG/SHORT + supported symbol', msg_id)
            return
        direction, symbol = parsed
        if MAX_OPEN_POSITIONS > 0 and open_positions_count() >= MAX_OPEN_POSITIONS:
            log.warning('Skipped %s %s: max open positions reached', direction, symbol)
            notify(f'⚠️ SKIPPED {direction} {symbol}\nMax open positions reached.')
            return
        try:
            result = place_order(direction, symbol)
            message = format_trade(direction, symbol, result)
            log.info(message.replace('\n', ' | '))
            notify(message)
        except Exception as e:
            log.exception('Trade failed for %s %s', direction, symbol)
            notify(f'❌ TRADE ERROR\n{direction} {symbol}\n{e}')

    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
