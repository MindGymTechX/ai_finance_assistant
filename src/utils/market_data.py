"""Market data with a market-aware cache and staleness policy (FR5, FR10, NFR4).

Every result carries source, as_of and status so the reply footer can be built by code.
status: ok | closed | delayed | unavailable | error
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from src.utils import market_hours as mh
from src.utils.cache import SqliteCache
from src.utils.retry import with_retry

SOURCE = "Yahoo Finance"


def _yf_quote(ticker: str) -> dict:
    import yfinance as yf

    t = yf.Ticker(ticker)
    hist = t.history(period="5d", interval="1d")
    if hist is None or hist.empty:
        raise ValueError(f"no data for {ticker}")
    closes = hist["Close"].dropna()
    price = float(closes.iloc[-1])
    prev = float(closes.iloc[-2]) if len(closes) > 1 else price
    try:  # intraday last price when the market is open
        lp = t.fast_info.last_price
        if lp and lp == lp:  # not NaN
            price = float(lp)
    except Exception:  # noqa: BLE001
        pass
    currency = "INR"
    try:
        currency = t.fast_info.currency or "INR"
    except Exception:  # noqa: BLE001
        pass
    return {"price": round(price, 2), "previous_close": round(prev, 2), "currency": currency}


def _yf_history(ticker: str, period: str) -> list[dict]:
    import yfinance as yf

    hist = yf.Ticker(ticker).history(period=period, interval="1d")
    if hist is None or hist.empty:
        raise ValueError(f"no history for {ticker}")
    return [{"date": idx.strftime("%Y-%m-%d"), "close": round(float(c), 2)}
            for idx, c in hist["Close"].dropna().items()]


class MarketData:
    def __init__(self, cache: SqliteCache, ttl_open_minutes: int = 5, stale_limit_minutes: int = 60,
                 fetch_quote: Callable[[str], dict] = _yf_quote,
                 fetch_history: Callable[[str, str], list[dict]] = _yf_history,
                 now: Callable[[], datetime] = mh.now_ist, retry_sleep=None):
        self.cache = cache
        self.ttl = timedelta(minutes=ttl_open_minutes)
        self.stale_limit = timedelta(minutes=stale_limit_minutes)
        self.fetch_quote = fetch_quote
        self.fetch_history = fetch_history
        self.now = now
        self._retry_kwargs = {"sleep": retry_sleep} if retry_sleep else {}

    # -- freshness policy ---------------------------------------------------
    def _is_fresh(self, fetched_at: datetime, t: datetime) -> bool:
        if mh.is_market_open(t):
            return t - fetched_at <= self.ttl
        return fetched_at >= mh.last_close(t)  # closing price stays valid until next open

    def _get(self, key: str, fetch: Callable[[], object]) -> dict:
        t = self.now()
        cached = self.cache.get(key)
        if cached and self._is_fresh(cached[1], t):
            return {"data": cached[0], "fetched_at": cached[1], "status": self._ok_status(t), "from_cache": True}
        try:
            data = with_retry(fetch, **self._retry_kwargs)
            self.cache.set(key, data, t)
            return {"data": data, "fetched_at": t, "status": self._ok_status(t), "from_cache": False}
        except Exception as e:  # noqa: BLE001
            if cached:
                age = t - cached[1]
                open_ = mh.is_market_open(t)
                status = "delayed" if (open_ and age <= self.stale_limit) else "unavailable"
                return {"data": cached[0], "fetched_at": cached[1], "status": status,
                        "from_cache": True, "error": str(e)}
            return {"data": None, "fetched_at": None, "status": "error", "error": str(e)}

    @staticmethod
    def _ok_status(t: datetime) -> str:
        return "ok" if mh.is_market_open(t) else "closed"

    # -- public API -----------------------------------------------------------
    def get_quote(self, ticker: str) -> dict:
        r = self._get(f"q:{ticker}", lambda: self.fetch_quote(ticker))
        out = {"ticker": ticker, "status": r["status"], "source": SOURCE}
        if r["data"]:
            d = r["data"]
            change = round(d["price"] - d["previous_close"], 2)
            pct = round(100 * change / d["previous_close"], 2) if d["previous_close"] else 0.0
            out.update(price=d["price"], previous_close=d["previous_close"], change=change,
                       change_pct=pct, currency=d.get("currency", "INR"),
                       as_of=r["fetched_at"].strftime("%d-%b-%Y %H:%M IST"))
        out["note"] = {
            "ok": "Live price (refreshed at most every few minutes).",
            "closed": "Market closed: this is the latest closing price.",
            "delayed": "Live data unavailable: showing a delayed price.",
            "unavailable": "Live data unavailable. Last known price shown only for reference, not as current.",
            "error": "Price data is unavailable right now.",
        }[r["status"]]
        return out

    def get_history(self, ticker: str, period: str = "1mo") -> dict:
        r = self._get(f"h:{ticker}:{period}", lambda: self.fetch_history(ticker, period))
        out = {"ticker": ticker, "period": period, "status": r["status"], "source": SOURCE, "points": r["data"] or []}
        if r["fetched_at"]:
            out["as_of"] = r["fetched_at"].strftime("%d-%b-%Y %H:%M IST")
        if out["points"]:
            first, last = out["points"][0]["close"], out["points"][-1]["close"]
            out["change_pct"] = round(100 * (last - first) / first, 2) if first else 0.0
        return out
