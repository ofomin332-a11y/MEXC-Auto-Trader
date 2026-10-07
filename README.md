# MEXC Auto Trader — Telegram monitoring diagnostic fix

Ця збірка виправляє моніторинг Telegram.

## Що змінено

- Прибрано старий `get_messages()` polling, який викликав `GetHistoryRequest` і не працював для Telegram bot accounts.
- Додано точний `NewMessage(chats=channel_entity)` listener для `@skrenner_r`.
- Додано `MessageEdited`, тому бот також побачить сигнал, якщо повідомлення спочатку створюється, а потім редагується.
- Додано глобальний діагностичний `NewMessage` listener. Він записує в Railway chat_id, username, title і message_id кожної події, яку бачить Telegram-сесія.
- При старті логуються `user_id` та `is_bot`, щоб одразу було видно, чи `TG_SESSION` є звичайною користувацькою сесією.
- `LIVE_TRADING=false` залишається безпечним режимом: реальні ордери не відкриваються.
- `TP_PCT=0.0083` залишається без змін.

## Railway variables

```text
TG_API_ID
TG_API_HASH
TG_SESSION
TELEGRAM_CHANNEL=skrenner_r
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
MARGIN_USDT=25
LEVERAGE=30
TP_PCT=0.0083
SL_PCT=0.04
LIVE_TRADING=false
```

## Важливо про TG_SESSION

`TG_SESSION` має бути StringSession звичайного Telegram USER-акаунта, який має доступ до `@skrenner_r`.

`TELEGRAM_BOT_TOKEN` використовується тільки для відправки повідомлень у чат сповіщень.

Після запуску шукай у Railway:

```text
Telegram session authorized as ... | user_id=... | is_bot=False
Targeted NewMessage listener registered successfully.
Targeted MessageEdited listener registered successfully.
Global diagnostic NewMessage listener registered successfully.
Waiting for new source messages from @skrenner_r ...
```

Коли сигнал з'явиться, має бути:

```text
TELEGRAM EVENT RECEIVED ...
NEW SOURCE MESSAGE ...
PARSED SIGNAL | direction=LONG/SHORT | symbol=...
```

і повідомлення у `TELEGRAM_CHAT_ID`:

```text
🧪 TEST SIGNAL RECEIVED
...
LIVE_TRADING=False
```

Реальні MEXC ордери ця діагностична збірка не відкриває.


## Monitoring fix v3
Fixed Telegram channel matching to support Telethon marked peer IDs (-100...). TELEGRAM_CHANNEL remains skrenner_r. LIVE_TRADING remains false by default.
