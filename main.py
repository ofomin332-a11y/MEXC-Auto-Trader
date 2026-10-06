import os
import re
import asyncio
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

    m = re.search(r"[$#]\s*([A-Z0-9]{2,20})", t)
    if not m:
        m = re.search(r"\b([A-Z0-9]{2,20})\s*/\s*USDT\b", t)

    return {"direction": direction, "symbol": (m.group(1) + "USDT") if m else None}


async def process_source_message(message_id, text, source="EVENT"):
    clean = (text or "").strip()
    log.info(
        "NEW SOURCE MESSAGE | source=%s | message_id=%s | text=%s",
        source,
        message_id,
        clean[:2000].replace("\n", " | "),
    )

    parsed = parse_signal(clean)
    if not parsed:
        log.info("MESSAGE IGNORED | no LONG/SHORT/PUMP/DUMP direction detected")
        return

    direction, symbol = parsed["direction"], parsed["symbol"]
    log.info("PARSED SIGNAL | direction=%s | symbol=%s", direction, symbol or "UNKNOWN")

    if not symbol:
        notify(
            "⚠️ SIGNAL RECEIVED BUT SYMBOL NOT PARSED\n"
            f"Direction: {direction}\nSource: @{CHANNEL}\n"
            f"Message ID: {message_id}\nText: {clean[:1200]}"
        )
        return

    notify(
        "🧪 TEST SIGNAL RECEIVED\n"
        f"Direction: {direction}\nSymbol: {symbol}\n"
        f"Margin: {MARGIN_USDT} USDT\nLeverage: {LEVERAGE}x\n"
        f"TP: {TP_PCT * 100}% price move\nSL: {SL_PCT * 100}% price move\n"
        f"LIVE_TRADING={LIVE_TRADING}\nSource: @{CHANNEL}\n"
        f"Message ID: {message_id}\n"
        "No real order will be placed while LIVE_TRADING=false."
    )


async def main():
    if not API_ID or not API_HASH or not TG_SESSION:
        raise RuntimeError("TG_API_ID, TG_API_HASH and TG_SESSION are required")

    # This must be a Telegram user StringSession, not a BotFather token/session,
    # for reliable monitoring of a channel/group the account can access.
    client = TelegramClient(StringSession(TG_SESSION), API_ID, API_HASH)
    await client.start()

    me = await client.get_me()
    me_username = getattr(me, "username", None)
    me_id = getattr(me, "id", None)
    is_bot = bool(getattr(me, "bot", False))
    log.info(
        "Telegram session authorized as %s | user_id=%s | is_bot=%s",
        me_username or me_id,
        me_id,
        is_bot,
    )
    if is_bot:
        log.warning(
            "TG_SESSION belongs to a Telegram BOT account. "
            "For reliable channel monitoring, use a normal Telegram USER StringSession."
        )
        notify(
            "⚠️ TELEGRAM SESSION WARNING\n"
            "TG_SESSION is authorized as a BOT account. "
            "Use a normal Telegram USER StringSession for channel monitoring."
        )

    channel_entity = await client.get_entity(CHANNEL)
    channel_id = getattr(channel_entity, "id", None)
    channel_username = (getattr(channel_entity, "username", None) or CHANNEL).lstrip("@")
    log.info(
        "Telegram source resolved: @%s | entity_id=%s | entity_type=%s",
        channel_username,
        channel_id,
        type(channel_entity).__name__,
    )

    log.info(
        "Monitoring Telegram channel @%s | LIVE_TRADING=%s | LEVERAGE=%sx | "
        "TP=%.4f%% | SL=%.2f%%",
        channel_username,
        LIVE_TRADING,
        LEVERAGE,
        TP_PCT * 100,
        SL_PCT * 100,
    )

    notify(
        "✅ MEXC AUTO TRADER ONLINE\n"
        f"Channel: @{channel_username}\n"
        f"Telegram session: {'BOT' if is_bot else 'USER'}\n"
        f"LIVE_TRADING={LIVE_TRADING}\n"
        f"Leverage: {LEVERAGE}x\nTP: {TP_PCT * 100}%\nSL: {SL_PCT * 100}%\n"
        "Monitoring: TARGETED EVENT + GLOBAL DIAGNOSTIC\n"
        "No real orders are placed while LIVE_TRADING=false."
    )

    seen_messages = set()

    async def handle_event(event, source):
        try:
            message = event.message
            message_id = getattr(message, "id", None)
            message_text = message.raw_text or ""
            dedupe_key = (message_id, message_text)
            if dedupe_key in seen_messages:
                return

            chat = await event.get_chat()
            chat_id = getattr(chat, "id", None)
            username = (getattr(chat, "username", None) or "").lstrip("@")
            title = getattr(chat, "title", None)

            log.info(
                "TELEGRAM EVENT RECEIVED | source=%s | chat_id=%s | username=@%s | title=%s | message_id=%s",
                source,
                chat_id,
                username or "",
                title or "",
                message_id,
            )

            # Target check is deliberately tolerant: channel username, entity id,
            # and event chat id can differ in how Telegram exposes peer metadata.
            if chat_id != channel_id and username.lower() != channel_username.lower():
                log.info("EVENT IGNORED | not target channel")
                return

            seen_messages.add(dedupe_key)
            await process_source_message(message_id, message_text, source=source)
        except Exception as e:
            log.exception("Event handler error: %s", e)

    # Targeted listener: Telethon filters events before our handler.
    @client.on(events.NewMessage(chats=channel_entity))
    async def targeted_new_message(event):
        await handle_event(event, "TARGETED_NEW_MESSAGE")

    # Some signal systems publish a placeholder and then edit it. Listen for edits too.
    @client.on(events.MessageEdited(chats=channel_entity))
    async def targeted_message_edited(event):
        await handle_event(event, "TARGETED_MESSAGE_EDITED")

    # Global diagnostic listener: if the targeted filter fails, this shows exactly
    # what Telegram is delivering to the session, without hiding it behind filters.
    @client.on(events.NewMessage())
    async def global_new_message(event):
        await handle_event(event, "GLOBAL_NEW_MESSAGE")

    log.info("Targeted NewMessage listener registered successfully.")
    log.info("Targeted MessageEdited listener registered successfully.")
    log.info("Global diagnostic NewMessage listener registered successfully.")
    log.info("Waiting for new source messages from @%s ...", channel_username)

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
