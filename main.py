import os
import re
import logging
import requests
from decimal import Decimal
from telethon import TelegramClient, events
from telethon.sessions import StringSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("mexc_auto_trader")

API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
TG_SESSION = os.getenv("TG_SESSION", "")
CHANNEL = os.getenv("TELEGRAM_CHANNEL", "skrenner_r").lstrip("@")
NOTIFY_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
NOTIFY_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
MARGIN_USDT = Decimal(os.getenv("MARGIN_USDT", "25"))
LEVERAGE = int(os.getenv("LEVERAGE", "30"))
TP_PCT = Decimal(os.getenv("TP_PCT", "0.0083"))
SL_PCT = Decimal(os.getenv("SL_PCT", "0.04"))
LIVE_TRADING = os.getenv("LIVE_TRADING", "false").lower() == "true"

def notify(message: str):
    if not NOTIFY_TOKEN or not NOTIFY_CHAT_ID:
        log.error("Telegram notification skipped: token/chat_id missing")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{NOTIFY_TOKEN}/sendMessage",
            data={"chat_id": NOTIFY_CHAT_ID, "text": message},
            timeout=10,
        )
        data = r.json()
        if r.ok and data.get("ok"):
            log.info("Telegram notification SENT successfully | chat_id=%s", NOTIFY_CHAT_ID)
            return True
        log.error("Telegram notification FAILED | status=%s | response=%s", r.status_code, data)
    except Exception as e:
        log.exception("Telegram notification exception: %s", e)
    return False

def parse_signal(text: str):
    t = text.upper()
    if any(x in t for x in ("LONG", "PUMP", "🟢", "GREEN")):
        direction = "LONG"
    elif any(x in t for x in ("SHORT", "DUMP", "🔴", "RED")):
        direction = "SHORT"
    else:
        return None
    m = re.search(r"\b([A-Z0-9]{2,20})USDT\b", t)
    if m:
        return {"direction": direction, "symbol": m.group(1) + "USDT"}
    m = re.search(r"[$#]\s*([A-Z0-9]{2,20})", t) or re.search(r"\b([A-Z0-9]{2,20})\s*/\s*USDT\b", t)
    return {"direction": direction, "symbol": (m.group(1) + "USDT") if m else None}

async def main():
    if not API_ID or not API_HASH or not TG_SESSION:
        raise RuntimeError("TG_API_ID, TG_API_HASH and TG_SESSION are required")

    client = TelegramClient(StringSession(TG_SESSION), API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    log.info("Telegram session authorized as %s", getattr(me, "username", None) or getattr(me, "id", None))

    channel_entity = await client.get_entity(CHANNEL)
    log.info("Telegram source resolved: @%s | entity_id=%s | entity_type=%s",
             CHANNEL, getattr(channel_entity, "id", None), type(channel_entity).__name__)
    log.info("Monitoring Telegram channel @%s | LIVE_TRADING=%s | LEVERAGE=%sx | TP=%.4f%% | SL=%.2f%%",
             CHANNEL, LIVE_TRADING, LEVERAGE, TP_PCT * 100, SL_PCT * 100)

    notify("✅ MEXC AUTO TRADER ONLINE\n"
           f"Channel: @{CHANNEL}\nLIVE_TRADING={LIVE_TRADING}\n"
           f"Leverage: {LEVERAGE}x\nTP: {TP_PCT * 100}%\nSL: {SL_PCT * 100}%\n"
           "Listener diagnostics: ENABLED")

    @client.on(events.NewMessage(chats=channel_entity))
    async def handler(event):
        text = event.raw_text or ""
        log.info("NEW SOURCE MESSAGE | chat_id=%s | message_id=%s | text=%s",
                 getattr(event.chat, "id", None), getattr(event.message, "id", None),
                 text[:2000].replace("\n", " | "))
        parsed = parse_signal(text)
        if not parsed:
            log.info("MESSAGE IGNORED | no LONG/SHORT/PUMP/DUMP direction detected")
            return
        direction, symbol = parsed["direction"], parsed["symbol"]
        log.info("PARSED SIGNAL | direction=%s | symbol=%s", direction, symbol or "UNKNOWN")
        if not symbol:
            notify("⚠️ SIGNAL RECEIVED BUT SYMBOL NOT PARSED\n"
                   f"Direction: {direction}\nSource: @{CHANNEL}\nText: {text[:1200]}")
            return
        notify("🧪 TEST SIGNAL RECEIVED\n"
               f"Direction: {direction}\nSymbol: {symbol}\n"
               f"Margin: {MARGIN_USDT} USDT\nLeverage: {LEVERAGE}x\n"
               f"TP: {TP_PCT * 100}% price move\nSL: {SL_PCT * 100}% price move\n"
               f"LIVE_TRADING={LIVE_TRADING}\n"
               "No real order will be placed while LIVE_TRADING=false.")

    log.info("Listener registered successfully. Waiting for NEW SOURCE MESSAGE...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
