import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class AppConfig:
    bot_token: str
    timezone: str
    default_min_confidence: int
    default_daily_time: str
    log_level: str

def get_config() -> AppConfig:
    return AppConfig(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        timezone=os.getenv("TIMEZONE", "Europe/Amsterdam"),
        default_min_confidence=int(os.getenv("DEFAULT_MIN_CONFIDENCE", "65")),
        default_daily_time=os.getenv("DEFAULT_DAILY_TIME", "10:30"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
