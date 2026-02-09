import os
import asyncio
import logging

from telethon import TelegramClient
from telethon.sessions import StringSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

API_ID = os.getenv("TG_API_ID")
API_HASH = os.getenv("TG_API_HASH")
SESSION = os.getenv("TG_SESSION")  # строковая сессия (мы сделаем её следующим шагом)

async def main():
    if not API_ID or not API_HASH or not SESSION:
        logging.error("TG_API_ID / TG_API_HASH / TG_SESSION не заданы. Агент пока не запущен.")
        return

    client = TelegramClient(StringSession(SESSION), int(API_ID), API_HASH)
    await client.connect()

    me = await client.get_me()
    logging.info(f"✅ Agent logged in as: {me.id} @{getattr(me, 'username', None)}")

    # просто проверка: покажем первые ~50 диалогов (каналы/чаты)
    count = 0
    async for d in client.iter_dialogs(limit=50):
        if d.is_channel:
            logging.info(f"CHANNEL: {d.name}")
            count += 1

    logging.info(f"✅ Found channels (in first 50 dialogs): {count}")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
