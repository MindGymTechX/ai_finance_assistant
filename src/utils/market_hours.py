"""NSE market hours (Mon-Fri 09:15-15:30 IST). Exchange holidays are not modelled:
on a holiday the 'open' TTL is used, which is harmless (prices simply don't change)."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
OPEN, CLOSE = time(9, 15), time(15, 30)


def now_ist() -> datetime:
    return datetime.now(IST)


def is_market_open(t: datetime) -> bool:
    t = t.astimezone(IST)
    return t.weekday() < 5 and OPEN <= t.time() < CLOSE


def next_open(t: datetime) -> datetime:
    t = t.astimezone(IST)
    d = t
    if t.time() >= OPEN:
        d = t + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.replace(hour=OPEN.hour, minute=OPEN.minute, second=0, microsecond=0)


def last_close(t: datetime) -> datetime:
    """Most recent market close at or before t."""
    t = t.astimezone(IST)
    d = t
    if t.weekday() >= 5 or t.time() < CLOSE:
        d = t - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
    return d.replace(hour=CLOSE.hour, minute=CLOSE.minute, second=0, microsecond=0)
