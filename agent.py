import os
import json
import asyncio
import logging
from datetime import datetime, timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
TZ = os.getenv("TZ", "Asia/Krasnoyarsk")

if not API_ID or not API_HASH or not BOT_TOKEN:
    raise RuntimeError("Нужно указать переменные окружения: API_ID, API_HASH, BOT_TOKEN")

API_ID = int(API_ID)

OUTPUT_JSON = "posts.json"
DEFAULT_POLL_MINUTES = int(os.getenv("POLL_MINUTES", "10"))

async def run_once(client: TelegramClient):
    """
    ТУТ твоя логика: читать апдейты/сообщения, сохранять в JSON и т.д.
    Пока просто пинг, чтобы убедиться что Telethon стартует на Render без ввода.
    """
    me = await client.get_me()
    logging.info(f"Telethon BOT запущен: @{me.username} (id={me.id})")

    data = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "bot_username": me.username,
        "note": "bot is alive"
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def main():
    # ВАЖНО: session имя любое, Telethon сам создаст локальную сессию без вопросов,
    # потому что мы логинимся как BOT по BOT_TOKEN.
    client = TelegramClient("bot_session", API_ID, API_HASH)

    await client.start(bot_token=BOT_TOKEN)  # <-- КЛЮЧЕВОЕ: никаких телефонов/кодов
    logging.info("Client started OK")

    while True:
        try:
            await run_once(client)
        except FloodWaitError as e:
            logging.warning(f"FloodWait {e.seconds}s")
            await asyncio.sleep(e.seconds + 2)
        except Exception as e:
            logging.exception(e)
            await asyncio.sleep(10)

        await asyncio.sleep(DEFAULT_POLL_MINUTES * 60)

if __name__ == "__main__":
    asyncio.run(main())
