from datetime import datetime, timezone, timedelta

# Malaysia Standard Time (MYT) is permanently UTC+8 with no daylight saving time
MYT = timezone(timedelta(hours=8))

def now_myt() -> datetime:
    """Returns timezone-aware datetime in Malaysia Time (UTC+8)."""
    return datetime.now(MYT)

def now_myt_naive() -> datetime:
    """Returns naive datetime in Malaysia Time (UTC+8) for local DB storage."""
    return datetime.now(MYT).replace(tzinfo=None)

def to_myt_iso(dt: datetime) -> str:
    """Formats datetime as ISO 8601 with +08:00 offset."""
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")

def to_myt_str(dt: datetime) -> str:
    """Formats datetime as human-readable string in Malaysia Time."""
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")

