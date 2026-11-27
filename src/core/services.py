"""Process-wide singletons: market data, vector store, profile store, checkpointer."""
from __future__ import annotations

from functools import lru_cache

from src.core.config import KB_DIR, data_dir, get_config
from src.core.logging_setup import get_logger

log = get_logger("finai.services")


@lru_cache(maxsize=1)
def get_market():
    from src.utils.cache import SqliteCache
    from src.utils.market_data import MarketData

    m = get_config()["market"]
    return MarketData(SqliteCache(data_dir() / "cache.db"), m["ttl_open_minutes"], m["stale_limit_minutes"])


@lru_cache(maxsize=1)
def get_profiles():
    from src.data.profile_store import ProfileStore

    return ProfileStore(data_dir() / "profiles.db")


@lru_cache(maxsize=1)
def get_vector_store():
    """Loads the index, building it on first run (needs OPENAI_API_KEY)."""
    from src.core.llm import get_embedder
    from src.rag.chunker import chunk_documents
    from src.rag.loader import load_documents
    from src.rag.store import VectorStore

    idx = data_dir() / "index"
    store = VectorStore.load(idx)
    if store is None:
        r = get_config()["rag"]
        chunks = chunk_documents(load_documents(KB_DIR), r["chunk_size"], r["chunk_overlap"])
        log.info("building vector index from %d chunks", len(chunks))
        store = VectorStore.build(chunks, get_embedder())
        store.save(idx)
    return store


def retrieve(query: str, category: str | None = None) -> list[dict]:
    from src.core.llm import get_embedder

    r = get_config()["rag"]
    qvec = get_embedder()([query])[0]
    return get_vector_store().search(qvec, k=r["top_k"], category=category, min_score=r["min_score"])


@lru_cache(maxsize=1)
def get_checkpointer():
    """SQLite checkpointer (conversation memory per thread_id); in-memory fallback."""
    try:
        import sqlite3

        from langgraph.checkpoint.sqlite import SqliteSaver
        return SqliteSaver(sqlite3.connect(str(data_dir() / "checkpoints.db"), check_same_thread=False))
    except ImportError:
        from langgraph.checkpoint.memory import InMemorySaver
        log.warning("langgraph-checkpoint-sqlite not installed: chats won't survive a restart")
        return InMemorySaver()


def _clean(v, lower: bool = True) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return ""
    s = str(v).strip()
    return s.lower() if lower else s


def analyze_holdings(holdings: list[dict]) -> dict:
    """Resolves names to tickers, fetches live prices (cached), and runs the portfolio maths.
    Shared by the Portfolio agent tool, the Portfolio tab and the MCP server."""
    from src.utils import tickers
    from src.utils.finance_math import analyze_portfolio

    cfg = get_config()
    market, suffix = get_market(), cfg["market"]["exchange_suffix"]
    prices, sectors, quotes, resolved = {}, {}, [], []
    for h in holdings:
        h = dict(h)
        atype = _clean(h.get("asset_type")) or "stock"
        sym = _clean(h.get("symbol"), lower=False)
        if not sym:
            continue
        if atype in ("stock", "etf", "gold"):
            r = tickers.resolve(sym, suffix)
            if r["status"] == "ok":
                sym = r["ticker"]
            q = market.get_quote(sym)
            quotes.append(q)
            # 'unavailable' prices are never treated as current (NFR4)
            prices[sym] = q.get("price") if q["status"] in ("ok", "closed", "delayed") else None
            sectors[sym] = tickers.sector_of(sym)
        h["symbol"] = sym
        resolved.append(h)
    p = cfg["portfolio"]
    analysis = analyze_portfolio(resolved, prices, sectors, p["single_stock_limit_pct"], p["single_sector_limit_pct"])
    as_of = next((q["as_of"] for q in quotes if q.get("as_of")), None)
    analysis["price_source"] = {"source": "Yahoo Finance", "as_of": as_of,
                                "statuses": {q["ticker"]: q["status"] for q in quotes}}
    return analysis
