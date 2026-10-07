import os,re,asyncio,logging,requests
from decimal import Decimal
from telethon import TelegramClient,events
from telethon.sessions import StringSession
logging.basicConfig(level=logging.INFO,format='%(asctime)s | %(levelname)s | %(message)s'); log=logging.getLogger('mexc_auto_trader')
API_ID=int(os.getenv('TG_API_ID','0')); API_HASH=os.getenv('TG_API_HASH',''); TG_SESSION=os.getenv('TG_SESSION',''); CHANNEL=os.getenv('TELEGRAM_CHANNEL','skrenner_r').lstrip('@'); TOKEN=os.getenv('TELEGRAM_BOT_TOKEN',''); CHAT=os.getenv('TELEGRAM_CHAT_ID','')
MARGIN=Decimal(os.getenv('MARGIN_USDT','25')); LEVERAGE=int(os.getenv('LEVERAGE','30')); TP=Decimal(os.getenv('TP_PCT','0.0067')); SL=Decimal(os.getenv('SL_PCT','0.04')); POLL=int(os.getenv('POLL_SECONDS','3')); LIVE=os.getenv('LIVE_TRADING','false').lower()=='true'
def notify(s):
 try:
  r=requests.post(f'https://api.telegram.org/bot{TOKEN}/sendMessage',data={'chat_id':CHAT,'text':s},timeout=10); d=r.json()
  if r.ok and d.get('ok'): log.info('TELEGRAM SEND OK | message_id=%s',d['result']['message_id']); return True
  log.error('TELEGRAM SEND FAILED | status=%s | response=%s',r.status_code,d)
 except Exception: log.exception('TELEGRAM SEND EXCEPTION')
 return False
def parse(t):
 t=(t or '').upper(); direction='LONG' if re.search(r'\b(LONG|PUMP)\b',t) or '🟢' in t else ('SHORT' if re.search(r'\b(SHORT|DUMP)\b',t) or '🔴' in t else None)
 if not direction:return None
 for p in [r'\b([A-Z0-9]{2,20})USDT\b',r'[$#]\s*([A-Z0-9]{2,20})\b',r'\b([A-Z0-9]{2,20})\s*/\s*USDT\b']:
  m=re.search(p,t)
  if m:return direction,m.group(1)+'USDT'
 return direction,None
async def handle(m,src):
 mid=getattr(m,'id',None); text=getattr(m,'raw_text','') or ''; log.info('SOURCE MESSAGE | source=%s | id=%s | text=%s',src,mid,text[:1500].replace('\n',' | ')); p=parse(text)
 if not p: log.info('SOURCE MESSAGE IGNORED | no supported signal pattern'); return
 direction,symbol=p; log.info('SIGNAL PARSED | direction=%s | symbol=%s',direction,symbol or 'UNKNOWN')
 notify(('⚠️ СИГНАЛ ОТРИМАНИЙ, АЛЕ МОНЕТУ НЕ РОЗІЗНАНО\n' if not symbol else '🧪 SIGNAL TEST — отримано з джерела\n')+f'Напрямок: {direction}\n'+(f'Монета: {symbol}\n' if symbol else '')+f'Margin: {MARGIN} USDT\nLeverage: {LEVERAGE}x\nTP рух ціни: {TP*100}%\nSL рух ціни: {SL*100}%\nLIVE_TRADING={LIVE}\nSource: @{CHANNEL}\nMessage ID: {mid}')
async def poll(client,entity,seen):
 last=0
 latest=await client.get_messages(entity,limit=1)
 if latest:last=latest[0].id; log.info('POLL BASELINE | id=%s',last)
 while True:
  try:
   msgs=await client.get_messages(entity,limit=20); fresh=[m for m in reversed(msgs) if m.id>last]
   for m in fresh:
    last=max(last,m.id)
    if m.id not in seen:seen.add(m.id); await handle(m,'POLL')
   if fresh:log.info('POLL FOUND %s NEW MESSAGE(S)',len(fresh))
  except Exception:log.exception('POLL ERROR')
  await asyncio.sleep(POLL)
async def main():
 if not API_ID or not API_HASH or not TG_SESSION:raise RuntimeError('TG_API_ID, TG_API_HASH and TG_SESSION are required')
 client=TelegramClient(StringSession(TG_SESSION),API_ID,API_HASH); await client.start(); me=await client.get_me(); log.info('TELEGRAM AUTH OK | user=%s',getattr(me,'username',None) or getattr(me,'id',None))
 entity=await client.get_entity(CHANNEL); log.info('SOURCE RESOLVED | @%s | id=%s | type=%s',CHANNEL,getattr(entity,'id',None),type(entity).__name__)
 latest=await client.get_messages(entity,limit=1); log.info('SOURCE READ TEST OK | latest_message_id=%s',latest[0].id if latest else 'NONE')
 notify(f'✅ MEXC AUTO TRADER ONLINE\nSource: @{CHANNEL}\n30x | TP {TP*100}% price move | SL {SL*100}%\nLIVE_TRADING={LIVE}\nEVENT + POLLING active.')
 seen=set()
 @client.on(events.NewMessage())
 async def h(e):
  try:
   c=await e.get_chat(); cid=getattr(c,'id',None); u=(getattr(c,'username',None) or '').lstrip('@'); tid=getattr(entity,'id',None); log.info('TELEGRAM EVENT | chat_id=%s | username=%s | target_id=%s',cid,u or '@',tid)
   if cid!=tid and u.lower()!=CHANNEL.lower():return
   mid=getattr(e.message,'id',None)
   if mid in seen:return
   seen.add(mid); await handle(e.message,'EVENT')
  except Exception:log.exception('GLOBAL EVENT ERROR')
 log.info('EVENT LISTENER ACTIVE'); log.info('POLLING LISTENER ACTIVE | interval=%ss',POLL); task=asyncio.create_task(poll(client,entity,seen));
 try:await client.run_until_disconnected()
 finally:task.cancel()
if __name__=='__main__':asyncio.run(main())
