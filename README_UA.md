# MEXC Telegram Auto Trader

Автоматичний MEXC Futures трейдер, який читає нові повідомлення з Telegram-каналу та відкриває позицію за напрямком сигналу.

## Параметри
- Margin: 25 USDT fixed
- Leverage: 15x
- TP: 2% від ціни входу
- SL: 4% від ціни входу
- Isolated margin
- One-way mode by default
- MAX_OPEN_POSITIONS=1

## Важливо
MEXC API працює з live trading; sandbox у MEXC зараз немає. Спочатку запускайте з `LIVE_TRADING=false`.

## Railway Variables
Скопіюйте змінні з `.env.example`. Для live:
`LIVE_TRADING=true`

Не додавайте MEXC API secret або TG_SESSION у GitHub.

## Telegram session
Звичайний Telegram Bot API не гарантує читання довільного публічного каналу. Цей бот використовує Telegram user session через Telethon.

1. Отримайте Telegram API ID та API HASH через https://my.telegram.org
2. Локально встановіть залежності: `pip install -r requirements.txt`
3. Запустіть: `python make_session.py`
4. Авторизуйте свій Telegram-акаунт.
5. Скопіюйте отриманий `TG_SESSION` у Railway Variables.

## Signal parser
Підтримуються явні напрямки LONG/PUMP/BUY та SHORT/DUMP/SELL. Символ повинен бути присутнім у повідомленні як, наприклад, `BTCUSDT`, `BTC/USDT` або `BTC_USDT`.

## MEXC
Використовується офіційний Futures API через `https://api.mexc.com`.
