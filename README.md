# MEXC Auto Trader — polling diagnostic

Тестова збірка для перевірки сигналів з @skrenner_r.

Паралельно використовує Telegram events та polling останніх повідомлень кожні 5 секунд.
LIVE_TRADING=false — реальні MEXC ордери не відкриваються.

Railway Variables:
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
POLL_SECONDS=5

ВАЖЛИВО: це diagnostic ZIP, не live-trading build.
