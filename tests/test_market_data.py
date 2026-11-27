from datetime import datetime, timedelta

import pytest

from src.utils import market_hours as mh
from src.utils.cache import SqliteCache
from src.utils.market_data import MarketData

IST = mh.IST
OPEN_TIME = datetime(2026, 11, 18, 11, 0, tzinfo=IST)     # Wednesday, market open
CLOSED_TIME = datetime(2026, 11, 21, 12, 0, tzinfo=IST)   # Saturday


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class Fetcher:
    def __init__(self):
        self.calls, self.fail = 0, False

    def __call__(self, ticker):
        self.calls += 1
        if self.fail:
            raise ConnectionError("yahoo down")
        return {"price": 100.0 + self.calls, "previous_close": 100.0, "currency": "INR"}


@pytest.fixture
def md(tmp_path):
    clock, fetch = Clock(OPEN_TIME), Fetcher()
    m = MarketData(SqliteCache(tmp_path / "c.db"), 5, 60, fetch_quote=fetch,
                   fetch_history=lambda t, p: [{"date": "2026-11-01", "close": 90.0}, {"date": "2026-11-18", "close": 99.0}],
                   now=clock, retry_sleep=lambda s: None)
    return m, clock, fetch


def test_market_hours():
    assert mh.is_market_open(OPEN_TIME)
    assert not mh.is_market_open(CLOSED_TIME)
    assert not mh.is_market_open(datetime(2026, 11, 18, 15, 30, tzinfo=IST))
    assert mh.next_open(CLOSED_TIME).weekday() == 0
    assert mh.last_close(CLOSED_TIME) == datetime(2026, 11, 20, 15, 30, tzinfo=IST)
    assert mh.last_close(datetime(2026, 11, 18, 10, 0, tzinfo=IST)).day == 17


def test_quote_is_cached_within_ttl_and_refreshed_after(md):
    m, clock, fetch = md
    q1 = m.get_quote("INFY.NS")
    assert q1["status"] == "ok" and q1["price"] == 101.0 and q1["as_of"]
    clock.t = OPEN_TIME + timedelta(minutes=4)
    assert m.get_quote("INFY.NS")["price"] == 101.0 and fetch.calls == 1
    clock.t = OPEN_TIME + timedelta(minutes=6)
    assert m.get_quote("INFY.NS")["price"] == 102.0 and fetch.calls == 2


def test_change_pct(md):
    m, _, _ = md
    q = m.get_quote("X.NS")
    assert q["change"] == 1.0 and q["change_pct"] == 1.0


def test_source_down_delayed_then_unavailable(md):
    m, clock, fetch = md
    m.get_quote("INFY.NS")
    fetch.fail = True
    clock.t = OPEN_TIME + timedelta(minutes=30)
    q = m.get_quote("INFY.NS")
    assert q["status"] == "delayed" and q["price"] == 101.0
    clock.t = OPEN_TIME + timedelta(minutes=90)
    q = m.get_quote("INFY.NS")
    assert q["status"] == "unavailable" and "not as current" in q["note"]


def test_no_cache_and_source_down_is_error(md):
    m, _, fetch = md
    fetch.fail = True
    q = m.get_quote("NEW.NS")
    assert q["status"] == "error" and "price" not in q


def test_market_closed_uses_closing_price_without_refetch(md):
    m, clock, fetch = md
    clock.t = CLOSED_TIME
    q = m.get_quote("INFY.NS")
    assert q["status"] == "closed" and "closing" in q["note"]
    clock.t = CLOSED_TIME + timedelta(hours=20)  # Sunday
    m.get_quote("INFY.NS")
    assert fetch.calls == 1


def test_history_change_pct(md):
    m, _, _ = md
    h = m.get_history("INFY.NS", "1mo")
    assert h["change_pct"] == 10.0 and len(h["points"]) == 2
