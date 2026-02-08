import os
import json
import asyncio
import logging
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import FloodWaitError

# -------------------- ENV --------------------
load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
TZ = os.getenv("TZ", "UTC")

# ВАЖНО: BOT_TOKEN НЕ ИСПОЛЬЗУЕМ ДЛЯ СКАНА (боту нельзя get_dialogs)
# BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Настройки
MAX_CHATS_TO_SCAN = int(os.getenv("MAX_CHATS_TO_SCAN", "200"))
MESSAGES_PER_CHAT = int(os.getenv("MESSAGES_PER_CHAT", "50"))
OUTPUT_JSON = os.getenv("OUTPUT_JSON", "posts.json")
POLL_MINUTES = int(os.getenv("POLL_MINUTES", "10"))

# Имя сессии (должен существовать файл hockey_agent.session)
SESSION_BASENAME = os.getenv("SESSION_BASENAME", "hockey_agent")
SESSION_FILE_LOCAL = f"./{SESSION_BASENAME}.session"
SESSION_FILE_SECRET = f"/etc/secrets/{SESSION_BASENAME}.session"

# Ключевые слова
HOCKEY_KEYWORDS = [
    "хоккей", "кхл", "вхл", "мхл", "нхл",
    "hockey", "khl", "vhl", "nhl", "mhl",
    "ставк", "коэфф", "прогноз", "линия", "тотал", "фора"
]

# -------------------- LOGGING --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("agent")


def ensure_session_file():
    """
    На Render secret file лежит в /etc/secrets/...
    Мы копируем его в рабочую папку, чтобы Telethon спокойно его увидел.
    """
    if os.path.exists(SESSION_FILE_SECRET):
        if (not os.path.exists(SESSION_FILE_LOCAL)) or (os.path.getsize(SESSION_FILE_LOCAL) != os.path.getsize(SESSION_FILE_SECRET)):
            shutil.copyfile(SESSION_FILE_SECRET, SESSION_FILE_LOCAL)
            log.info(f"Session copied from secrets: {SESSION_FILE_SECRET} -> {SESSION_FILE_LOCAL}")
    else:
        log.warning(f"Secret session file not found: {SESSION_FILE_SECRET} (если будет EOFError — значит не залил session)")


def looks_hockey(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in HOCKEY_KEYWORDS)


async def scan_once(client: TelegramClient):
    tzinfo = ZoneInfo(TZ)
    now = datetime.now(tzinfo).isoformat()

    results = {
        "generated_at": now,
        "chats_scanned": 0,
        "matches": []
    }

    dialogs = await client.get_dialogs(limit=MAX_CHATS_TO_SCAN)
    results["chats_scanned"] = len(dialogs)

    for d in dialogs:
        entity = d.entity
        title = getattr(entity, "title", None) or getattr(entity, "username", None) or str(getattr(entity, "id", "unknown"))

        # берём последние сообщения
        try:
            async for msg in client.iter_messages(entity, limit=MESSAGES_PER_CHAT):
                text = msg.message or ""
                if looks_hockey(text):
                    results["matches"].append({
                        "chat": title,
                        "chat_id": getattr(entity, "id", None),
                        "date": msg.date.isoformat() if msg.date else None,
                        "message_id": msg.id,
                        "text": text[:2000]
                    })
        except FloodWaitError as e:
            log.warning(f"FloodWait {e.seconds}s on {title} — sleeping...")
            await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            log.warning(f"Skip chat {title}: {e}")

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    log.info(f"Scan done. chats={results['chats_scanned']} matches={len(results['matches'])} -> {OUTPUT_JSON}")


async def main():
    if API_ID == 0 or not API_HASH:
        raise RuntimeError("Нет API_ID/API_HASH в Render Environment Variables")

    ensure_session_file()

    # ВАЖНО: используем user-session (SQLite session file)
    client = TelegramClient(SESSION_BASENAME, API_ID, API_HASH)

    await client.connect()

    # Если нет авторизации — значит session не тот / не залит / не авторизован
    if not await client.is_user_authorized():
        raise RuntimeError(
            "Сессия НЕ авторизована. Нужно залить правильный hockey_agent.session в Render Secret Files "
            "и убедиться, что он был получен на компе после входа в аккаунт."
        )

    log.info("Telegram user-agent connected OK (session authorized)")

    # цикл
    while True:
        try:
            await scan_once(client)
        except Exception as e:
            log.exception(f"Scan failed: {e}")
        await asyncio.sleep(POLL_MINUTES * 60)


if __name__ == "__main__":
    asyncio.run(main())
