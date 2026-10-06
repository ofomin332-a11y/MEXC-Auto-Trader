import os
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

api_id = int(input('Telegram API ID: ').strip())
api_hash = input('Telegram API HASH: ').strip()
phone = input('Telegram phone (+380...): ').strip()
with TelegramClient(StringSession(), api_id, api_hash) as client:
    client.start(phone=phone)
    print('\nTG_SESSION=')
    print(client.session.save())
    print('\nCopy the TG_SESSION value to Railway Variables. Never publish it.')
