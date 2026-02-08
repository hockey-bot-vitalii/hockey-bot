import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
import datetime as dt

DB_PATH = Path("data") / "bot.db"

def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH.as_posix())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db() -> None:
    with connect() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL,
            min_confidence INTEGER,
            leagues TEXT,
            daily_time TEXT
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            league TEXT NOT NULL,
            game_id TEXT,
            match TEXT NOT NULL,
            pick TEXT NOT NULL,
            confidence INTEGER NOT NULL,
            why_json TEXT NOT NULL,
            risks_json TEXT NOT NULL,
            sources_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            final_score TEXT,
            closed_at TEXT
        );
        """)
        conn.commit()

def upsert_user(chat_id: int, created_at_iso: str) -> None:
    with connect() as conn:
        conn.execute("""
        INSERT INTO users (chat_id, created_at, min_confidence, leagues, daily_time)
        VALUES (?, ?, NULL, NULL, NULL)
        ON CONFLICT(chat_id) DO UPDATE SET chat_id=excluded.chat_id;
        """, (chat_id, created_at_iso))
        conn.commit()

def get_user(chat_id: int) -> Optional[dict]:
    with connect() as conn:
        cur = conn.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,))
        row = cur.fetchone()
        return dict(row) if row else None

def get_all_chat_ids() -> List[int]:
    with connect() as conn:
        cur = conn.execute("SELECT chat_id FROM users")
        return [r[0] for r in cur.fetchall()]

def set_min_confidence(chat_id: int, value: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE users SET min_confidence=? WHERE chat_id=?", (value, chat_id))
        conn.commit()

def set_leagues(chat_id: int, leagues_csv: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE users SET leagues=? WHERE chat_id=?", (leagues_csv, chat_id))
        conn.commit()

def set_daily_time(chat_id: int, hhmm: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE users SET daily_time=? WHERE chat_id=?", (hhmm, chat_id))
        conn.commit()

def insert_signal(payload: Dict[str, Any]) -> int:
    with connect() as conn:
        cur = conn.execute("""
        INSERT INTO signals (created_at, league, game_id, match, pick, confidence, why_json, risks_json, sources_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            payload["created_at"], payload["league"], payload.get("game_id"),
            payload["match"], payload["pick"], int(payload["confidence"]),
            payload["why_json"], payload["risks_json"], payload["sources_json"]
        ))
        conn.commit()
        return int(cur.lastrowid)

def list_recent_signals(limit: int = 20) -> List[dict]:
    with connect() as conn:
        cur = conn.execute("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]

def list_pending_signals() -> List[dict]:
    with connect() as conn:
        cur = conn.execute("SELECT * FROM signals WHERE status='PENDING' ORDER BY id DESC")
        return [dict(r) for r in cur.fetchall()]

def close_signal(signal_id: int, status: str, final_score: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE signals SET status=?, final_score=?, closed_at=? WHERE id=?",
            (status, final_score, dt.datetime.utcnow().isoformat(), signal_id)
        )
        conn.commit()
