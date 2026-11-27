import pytest

from src.core.config import get_config
from src.data.profile_store import ProfileStore
from src.utils import tickers
from src.utils.retry import with_retry


def test_config_loads_and_env_override(monkeypatch):
    cfg = get_config()
    assert cfg["market"]["ttl_open_minutes"] == 5
    assert set(cfg["agents"]["budgets"]) == {"finance_qa", "tax_education", "portfolio", "market", "goal_planning", "news"}


@pytest.mark.parametrize("q,ticker", [("Infosys", "INFY.NS"), ("INFY", "INFY.NS"), ("nifty", "^NSEI"),
                                      ("hdfc bank", "HDFCBANK.NS"), ("sensex", "^BSESN"), ("ZZZQ", "ZZZQ.NS")])
def test_resolve(q, ticker):
    r = tickers.resolve(q)
    assert r["status"] == "ok" and r["ticker"] == ticker


def test_resolve_ambiguous_and_not_found():
    r = tickers.resolve("tata")
    assert r["status"] == "ambiguous" and len(r["candidates"]) >= 3
    assert tickers.resolve("some random words")["status"] == "not_found"
    assert tickers.sector_of("TCS.NS") == "IT" and tickers.name_of("INFY") == "Infosys"


def test_profile_store_roundtrip_and_threads(tmp_path):
    s = ProfileStore(tmp_path / "p.db")
    uid = s.normalize_user_id("  Meena K!! ")
    assert uid == "meenak"
    profile, holdings = s.load(uid)
    assert profile["knowledge_level"] == "beginner" and holdings == []
    s.save(uid, {**profile, "risk_appetite": "cautious"}, [{"symbol": "INFY", "quantity": 1, "avg_price": 1}])
    p2, h2 = s.load(uid)
    assert p2["risk_appetite"] == "cautious" and h2[0]["symbol"] == "INFY"
    t1 = s.new_thread(uid)
    t2 = s.new_thread(uid)
    s.rename_thread(t1, "College plan")
    threads = s.list_threads(uid)
    assert {t["thread_id"] for t in threads} == {t1, t2} and t1 != t2
    assert s.list_threads("someone-else") == []


def test_retry_succeeds_after_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise IOError("x")
        return "ok"
    assert with_retry(flaky, attempts=3, sleep=lambda s: None) == "ok"
    with pytest.raises(IOError):
        with_retry(lambda: (_ for _ in ()).throw(IOError("y")), attempts=2, sleep=lambda s: None)


def test_analyze_holdings_resolves_names_and_uses_cached_prices(monkeypatch, tmp_path):
    from src.core import services
    from src.utils.cache import SqliteCache
    from src.utils.market_data import MarketData

    prices = {"INFY.NS": 1500.0, "TCS.NS": 3500.0}

    def fetch(t):
        if t not in prices:
            raise ConnectionError("no data")
        return {"price": prices[t], "previous_close": prices[t], "currency": "INR"}
    md = MarketData(SqliteCache(tmp_path / "c.db"), fetch_quote=fetch, retry_sleep=lambda s: None)
    monkeypatch.setattr(services, "get_market", lambda: md)
    a = services.analyze_holdings([
        {"symbol": "Infosys", "quantity": 10, "avg_price": 1000},
        {"symbol": "TCS", "quantity": 2, "avg_price": 3000},
        {"symbol": "UNKNOWNCO", "quantity": 1, "avg_price": 100},
        {"symbol": "Some Fund", "quantity": 100, "avg_price": 10, "asset_type": "mutual_fund", "current_price": 12},
        {"symbol": float("nan"), "quantity": 1, "avg_price": 1},
    ])
    syms = {h["symbol"] for h in a["holdings"]}
    assert {"INFY.NS", "TCS.NS", "UNKNOWNCO.NS", "Some Fund"} == syms
    assert a["prices_unavailable_for"] == ["UNKNOWNCO.NS"]
    assert a["sector_allocation"]["IT"] > 90 - 5
    assert a["price_source"]["statuses"]["UNKNOWNCO.NS"] == "error"
