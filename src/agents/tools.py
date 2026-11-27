"""Tools given to agents. Each returns JSON including `_meta` (sources / unavailable), which the
code uses to build the reply footer (NFR2, NFR4). Context such as holdings is bound by closure,
so the LLM never has to copy holdings around (data minimisation)."""
from __future__ import annotations

import json
from typing import Callable

from langchain_core.tools import tool

from src.core import services
from src.core.config import get_config
from src.utils import tickers
from src.utils.finance_math import project_goal as _project_goal
from src.utils.news import fetch_news as _fetch_news


def _dump(d: dict) -> str:
    return json.dumps(d, default=str)


def _quote_meta(q: dict) -> dict:
    label = f"Yahoo Finance price {q['ticker']}"
    if q["status"] in ("ok", "closed", "delayed"):
        tag = {"closed": " (closing)", "delayed": " (delayed)"}.get(q["status"], "")
        return {"sources": [{"label": label + tag, "as_of": q.get("as_of")}], "unavailable": []}
    return {"sources": [], "unavailable": [f"live price for {q['ticker']}"]}


def make_retrieve_tool(category: str | None = None):
    @tool
    def retrieve(query: str) -> str:
        """Search the FinAI knowledge base. Input: a focused search query. Returns relevant passages
        with title, source and relevance score; an empty list means nothing relevant was found."""
        try:
            hits = services.retrieve(query, category=category)
        except Exception as e:  # noqa: BLE001
            return _dump({"status": "error", "error": str(e),
                          "_meta": {"sources": [], "unavailable": ["knowledge base search"]}})
        passages = [{"title": h["title"], "category": h["category"], "source": h["source"],
                     "score": h["score"], "text": h["text"]} for h in hits]
        meta = {"sources": [{"label": f"KB: \"{h['title']}\""} for h in hits], "unavailable": []}
        return _dump({"status": "ok" if hits else "no_results", "passages": passages, "_meta": meta})
    return retrieve


@tool
def resolve_ticker(name: str) -> str:
    """Resolve a company or index name (e.g. 'Infosys', 'Nifty') to its NSE ticker.
    Returns status ok with ticker, ambiguous with candidates, or not_found."""
    return _dump(tickers.resolve(name, get_config()["market"]["exchange_suffix"]))


@tool
def get_quote(ticker: str) -> str:
    """Latest price for an NSE ticker (e.g. INFY.NS) or index (e.g. ^NSEI), with change, as_of and status."""
    q = services.get_market().get_quote(ticker)
    return _dump({**q, "_meta": _quote_meta(q)})


@tool
def get_history(ticker: str, period: str = "1mo") -> str:
    """Daily closing prices for a ticker. period: 5d, 1mo, 3mo, 6mo, 1y, 5y. Returns change_pct over the period."""
    h = services.get_market().get_history(ticker, period)
    pts = h["points"]
    summary = {k: v for k, v in h.items() if k != "points"}
    summary["first"], summary["last"] = (pts[0], pts[-1]) if pts else (None, None)
    summary["points_sample"] = pts[:: max(1, len(pts) // 10)]
    ok = h["status"] != "error"
    meta = {"sources": [{"label": f"Yahoo Finance history {ticker} {period}", "as_of": h.get("as_of")}] if ok else [],
            "unavailable": [] if ok else [f"price history for {ticker}"]}
    return _dump({**summary, "_meta": meta})


@tool
def fetch_news(query: str, days: int = 7) -> str:
    """Recent news headlines. query: an NSE ticker like 'HDFCBANK.NS' or a topic like 'Indian IT sector'.
    Returns status ok/no_news/error and items with headline, published_at, source and url."""
    n = get_config()["news"]
    r = _fetch_news(query, days=days or n["days"], max_items=n["max_items"])
    ok = r["status"] != "error"
    meta = {"sources": [{"label": f"{r['source']} news: {query}"}] if r["status"] == "ok" else [],
            "unavailable": [] if ok else [f"recent news for {query}"]}
    return _dump({**r, "_meta": meta})


def make_portfolio_tool(holdings: list[dict]):
    @tool
    def analyze_portfolio() -> str:
        """Analyse the user's saved holdings with live prices: value, P&L, allocation by holding,
        sector and asset type, diversification score, risk level, concentration flags, expense ratios."""
        if not holdings:
            return _dump({"status": "empty", "message": "No holdings saved. Ask the user to add them in the Portfolio tab.",
                          "_meta": {"sources": [], "unavailable": []}})
        a = services.analyze_holdings(holdings)
        ps = a.get("price_source", {})
        missing = a.get("prices_unavailable_for") or []
        meta = {"sources": [{"label": "Yahoo Finance prices for your holdings", "as_of": ps.get("as_of")}] if ps.get("as_of") else [],
                "unavailable": [f"live prices for {', '.join(missing)} (buy price used)"] if missing else []}
        return _dump({**a, "_meta": meta})
    return analyze_portfolio


@tool
def project_goal(target_amount: float, years: float, current_savings: float, risk: str) -> str:
    """Goal calculator. target_amount in today's rupees; years to the goal; current_savings already set
    aside for this goal; risk: cautious, moderate or aggressive. Returns monthly SIP needed, inflation-
    adjusted target, scenarios for each risk level, a yearly projection and the assumptions used."""
    g = get_config()["goals"]
    r = _project_goal(target_amount, years, current_savings, risk, g["inflation_pct"],
                      g["expected_return_pct"], g["assumptions_as_of"])
    r["_meta"] = {"sources": [{"label": "FinAI goal assumptions", "as_of": g["assumptions_as_of"]}], "unavailable": []}
    return _dump(r)


def make_news_agent_tool(run_news: Callable[..., dict]):
    """Agent-as-tool: Portfolio and Market delegate to the News agent and get a structured digest."""
    @tool
    def ask_news_agent(request: str, tickers: list[str] | None = None, sectors: list[str] | None = None,
                       days: int = 7) -> str:
        """Ask the News Synthesizer agent for recent news context. request: what you need and why.
        tickers: NSE tickers only (never quantities or values). sectors: optional sector names."""
        resp = run_news(request=request, tickers=tickers or [], sectors=sectors or [], days=days)
        return _dump(resp)
    return ask_news_agent
