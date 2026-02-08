import os
import json
import asyncio
import logging
from datetime import datetime, timezone

from telethon import TelegramClient
from telethon.tl.types import Channel
from telethon.errors import FloodWaitError
from dotenv import load_dotenv

# ================== ENV ==================
load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TZ = os.getenv("TZ", "UTC")

# ================== НАСТРОЙКИ ==================
DEFAULT_POLL_MINUTES = 10          # как часто запускать (мин)
MAX_CHATS_TO_SCAN = 200            # сколько каналов/чатов просматривать
MESSAGES_PER_CHAT = 50             # сколько сообщений брать из каждого

OUTPUT_JSON = "posts.json"
LOG_FILE = "agent.log"
SESSION_NAME = "hockey_agent"

# ключевые слова хоккея
HOCKEY_KEYWORDS = [
    "хоккей", "кхл", "вхл", "мхл", "нхл",
    "hockey", "khl", "vhl", "nhl",
    "буллит", "плей-офф", "playoff",
    "вратарь", "звено", "состав", "матч"
]

# слова, похожие на ставки / прогнозы
BET_HINTS = [
    "ставк", "прогноз", "коэф", "кф",
    "тотал", "фора", "победа",
    "1х", "2х", "x2", "over", "under"
]

# ================== ЛОГИ ==================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

log = logging.getLogger("agent")

# ================== УТИЛИТЫ ==================
def contains_any(text: str, words: list[str]) -> bool:
    text = text.lower()
    return any(w in text for w in words)

def load_posts() -> list:
    if not os.path.exists(OUTPUT_JSON):
        return []
    with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
        return json.load(f)

def save_posts(posts: list):
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)

# ================== ОСНОВНАЯ ЛОГИКА ==================
async def scan(client: TelegramClient):
    log.info("Начинаем сканирование Telegram")

    posts = load_posts()
    seen_ids = {p["id"] for p in posts}

    dialogs = await client.get_dialogs(limit=MAX_CHATS_TO_SCAN)

    for dialog in dialogs:
        if not isinstance(dialog.entity, Channel):
            continue

        try:
            async for msg in client.iter_messages(
                dialog.entity,
                limit=MESSAGES_PER_CHAT
            ):
                if not msg.text:
                    continue

                if msg.id in seen_ids:
                    continue

                text = msg.text.lower()

                # фильтры
                if not contains_any(text, HOCKEY_KEYWORDS):
                    continue
                if not contains_any(text, BET_HINTS):
                    continue

                post = {
                    "id": msg.id,
                    "chat": dialog.name,
                    "date": msg.date.astimezone(timezone.utc).isoformat(),
                    "text": msg.text
                }

                posts.append(post)
                seen_ids.add(msg.id)

                log.info(f"Найден прогноз: {dialog.name} | {msg.id}")

        except FloodWaitError as e:
            log.warning(f"FloodWait {e.seconds}s")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            log.error(f"Ошибка в {dialog.name}: {e}")

    save_posts(posts)
    log.info(f"Сохранено постов: {len(posts)}")

# ================== ЦИКЛ ==================
async def main():
    if not API_ID or not API_HASH or not BOT_TOKEN:
        raise RuntimeError("API_ID / API_HASH / BOT_TOKEN не заданы")

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start(bot_token=BOT_TOKEN)

    log.info("Telegram BOT запущен")

    while True:
        await scan(client)
        await asyncio.sleep(DEFAULT_POLL_MINUTES * 60)

# ================== START ==================
if __name__ == "__main__":
    asyncio.run(main())
