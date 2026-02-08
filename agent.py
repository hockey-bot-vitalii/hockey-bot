import os
import re
import json
import time
import logging
from datetime import datetime, timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from dotenv import load_dotenv


# -------------------- настройки --------------------
DEFAULT_POLL_MINUTES = 10          # как часто обновлять (мин)
DEFAULT_LIMIT_PER_CHAT = 30        # сколько последних сообщений брать за проход
MAX_CHATS_TO_SCAN = 200            # сколько чатов/каналов просматривать в списке диалогов

# ключевые слова для авто-отбора хоккейных источников
HOCKEY_KEYWORDS = [
    "хоккей", "кхл", "вхл", "мхл", "нхл", "nhl", "khl", "vhl", "mhl",
    "hockey", "transfer", "трансфер", "инсайд", "состав", "звено", "вратар",
    "powerplay", "буллит", "плей-офф", "playoff", "регулярка", "матч", "ставк", "коэфф"
]

# слова/паттерны "похоже на ставку/прогноз"
BET_HINTS = [
    "ставк", "прогноз", "коэфф", "кф", "тотал", "фора", "победа", "п1", "п2", "х2", "1х",
    "itb", "it", "tb", "tm", "over", "under"
]

OUTPUT_JSON = "posts.json"
LOG_FILE = "agent.log"
SESSION_NAME = "hockey_agent"  # будет использовать hockey_agent.session


# -------------------- утилиты --------------------
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler()
        ],
    )

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def normalize_text(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()

def looks_hockeyish(title: str, username: str, about: str) -> bool:
    blob = " ".join([title or "", username or "", about or ""]).lower()
    return any(k in blob for k in HOCKEY_KEYWORDS)

def looks_like_bet(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in BET_HINTS)

def load_json(path: str):
    if not os.path.exists(path):
        return {"meta": {}, "items": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"meta": {}, "items": []}

def save_json(path: str, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def get_env_int(name: str, default: int) -> int:
    v = os.getenv(name, "").strip()
    if not v:
        return default
    try:
        return int(v)
    except ValueError:
        return default


# -------------------- основной сборщик --------------------
async def collect_once(client: TelegramClient, limit_per_chat: int):
    """
    1) Берём список диалогов (каналы/группы/чаты)
    2) Фильтруем "похоже на хоккей"
    3) Забираем последние N сообщений
    4) Складываем в posts.json (без дублей)
    """
    data = load_json(OUTPUT_JSON)
    seen_keys = set()

    # ключи уже сохранённых записей (чтобы не дублировать)
    for it in data.get("items", []):
        seen_keys.add(f"{it.get('chat_id')}:{it.get('msg_id')}")

    logging.info("Сканирую список диалогов...")
    dialogs = []
    async for d in client.iter_dialogs(limit=MAX_CHATS_TO_SCAN):
        dialogs.append(d)

    hockey_dialogs = []
    for d in dialogs:
        ent = d.entity
        title = getattr(ent, "title", "") or ""
        username = getattr(ent, "username", "") or ""
        # about у диалогов напрямую часто нет — попробуем получить через get_entity позже при необходимости
        if looks_hockeyish(title, username, ""):
            hockey_dialogs.append(d)

    logging.info(f"Найдено диалогов всего: {len(dialogs)}")
    logging.info(f"Похоже на хоккей: {len(hockey_dialogs)}")

    added = 0
    for d in hockey_dialogs:
        ent = d.entity
        chat_id = getattr(ent, "id", None)
        title = getattr(ent, "title", "") or ""
        username = getattr(ent, "username", "") or ""

        if chat_id is None:
            continue

        logging.info(f"Читаю: {title} @{username}".strip())

        try:
            async for msg in client.iter_messages(ent, limit=limit_per_chat):
                if not msg:
                    continue
                msg_id = msg.id
                key = f"{chat_id}:{msg_id}"
                if key in seen_keys:
                    continue

                text = ""
                if msg.message:
                    text = normalize_text(msg.message)

                item = {
                    "ts_utc": now_iso(),
                    "chat_id": chat_id,
                    "chat_title": title,
                    "chat_username": username,
                    "msg_id": msg_id,
                    "msg_date_utc": msg.date.replace(tzinfo=timezone.utc).isoformat() if msg.date else None,
                    "text": text,
                    "has_media": bool(msg.media),
                    "looks_like_bet": looks_like_bet(text),
                    "link": None,
                }

                # попытка собрать ссылку на сообщение (если публичный канал)
                if username:
                    item["link"] = f"https://t.me/{username}/{msg_id}"

                data.setdefault("items", []).append(item)
                seen_keys.add(key)
                added += 1

        except FloodWaitError as e:
            logging.warning(f"FloodWait {e.seconds}s — сплю...")
            time.sleep(min(e.seconds, 120))
        except Exception as e:
            logging.warning(f"RPC error: {e}")
        except Exception as e:
            logging.exception(f"Ошибка чтения {title}: {e}")

    data["meta"] = {
        "updated_utc": now_iso(),
        "total_items": len(data.get("items", [])),
        "added_this_run": added,
        "limit_per_chat": limit_per_chat,
        "poll_minutes": None,
    }
    save_json(OUTPUT_JSON, data)
    logging.info(f"Готово. Добавлено новых сообщений: {added}. Всего в posts.json: {len(data.get('items', []))}")


async def main():
    load_dotenv()
    setup_logging()

    api_id = os.getenv("API_ID", "").strip()
    api_hash = os.getenv("API_HASH", "").strip()

    if not api_id or not api_hash:
        logging.error("Нет API_ID / API_HASH. Создай .env в папке и добавь API_ID=... API_HASH=...")
        return

    api_id_int = int(api_id)

    # режим запуска
    once = "--once" in os.sys.argv
    poll_minutes = get_env_int("POLL_MINUTES", DEFAULT_POLL_MINUTES)
    limit_per_chat = get_env_int("LIMIT_PER_CHAT", DEFAULT_LIMIT_PER_CHAT)

    logging.info("Запуск TelegramClient...")
    client = TelegramClient(SESSION_NAME, api_id_int, api_hash)

    async with client:
        me = await client.get_me()
        logging.info(f"Вошли как: @{getattr(me, 'username', '')} id={getattr(me, 'id', '')}")

        if once:
            await collect_once(client, limit_per_chat=limit_per_chat)
            return

        logging.info(f"Режим: цикл. Каждые {poll_minutes} мин. LIMIT_PER_CHAT={limit_per_chat}")
        while True:
            try:
                await collect_once(client, limit_per_chat=limit_per_chat)
            except Exception as e:
                logging.exception(f"Ошибка цикла: {e}")
            time.sleep(max(60, poll_minutes * 60))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
