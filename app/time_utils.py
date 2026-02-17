from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import Settings


def now_local(settings: Settings) -> datetime:
    return datetime.now(ZoneInfo(settings.app_timezone))


def format_local_timestamp(settings: Settings) -> str:
    dt = now_local(settings)
    return f"{dt.month}/{dt.day}/{dt.year} {dt:%H:%M:%S}"
