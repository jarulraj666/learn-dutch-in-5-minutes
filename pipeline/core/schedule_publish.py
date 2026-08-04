from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pipeline import settings
from pipeline.core.db import get_connection


def _get_last_scheduled_time() -> datetime | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT scheduled_at FROM publish_jobs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return datetime.fromisoformat(row["scheduled_at"])


def next_publish_slot() -> datetime:
    config = settings.SCHEDULING_CONFIG.get("publish", {})
    cadence_days = int(config.get("cadence_days", 2))
    hour = int(config.get("preferred_hour_24", 18))
    minute = int(config.get("preferred_minute", 0))
    tz = ZoneInfo(config.get("timezone", settings.CHANNEL_TIMEZONE))

    last = _get_last_scheduled_time()
    now_local = datetime.now(tz)

    if last is None:
        candidate = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now_local:
            candidate = candidate + timedelta(days=cadence_days)
        return candidate

    return (last + timedelta(days=cadence_days)).astimezone(tz)
