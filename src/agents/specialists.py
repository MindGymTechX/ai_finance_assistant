"""The six specialist agents. Each = system prompt + tools + budget, run by the ReAct loop.
Output contract (written to shared state): {agent, answer, sources, unavailable, status}."""
from __future__ import annotations

import time

from langchain_core.messages import HumanMessage

from src.agents import prompts, tools
from src.agents.react import run_react
from src.core.config import get_config
from src.core.llm import get_chat_model
from src.core.logging_setup import get_logger, log_event

log = get_logger("finai.agents")

AGENT_LABELS = {
    "finance_qa": "Finance Q&A", "tax_education": "Tax education", "portfolio": "Portfolio analysis",
    "market": "Market analysis", "goal_planning": "Goal planning", "news": "News synthesizer",
}


def _collect_meta(tool_results: list[dict]) -> tuple[list[dict], list[str]]:
    sources, unavailable = [], []
    for r in tool_results:
        m = r.get("_meta") or {}
        sources.extend(m.get("sources", []))
        unavailable.extend(m.get("unavailable", []))
    return sources, unavailable


def run_news(request: str, tickers: list[str], sectors: list[str], days: int = 7, llm=None) -> dict:
    """News agent, callable as a tool by other agents. Returns the structured NewsResponse contract:
    {status: ok|no_news|error, summary, items[], _meta}. Status and items are decided by code."""
    llm = llm or get_chat_model()
    budget = get_config()["agents"]["budgets"]["news"]
    ask = request
    if tickers or sectors:
        ask += f"\nTickers: {', '.join(tickers) or '-'}; sectors: {', '.join(sectors) or '-'}; last {days} days."
    res = run_react(llm, prompts.NEWS, [HumanMessage(content=ask)], [tools.fetch_news], budget)
    fetched = [r for r in res["tool_results"] if "items" in r]
    items, seen = [], set()
    for r in fetched:
        for it in r["items"]:
            if it["headline"] not in seen:
                seen.add(it["headline"])
                items.append(it)
    if not fetched or all(r.get("status") == "error" for r in fetched):
        status = "error"
    else:
        status = "ok" if items else "no_news"
    sources, unavailable = _collect_meta(res["tool_results"])
    return {"status": status, "summary": res["answer"], "items": items[:8],
            "_meta": {"sources": sources, "unavailable": unavailable or (["recent news"] if status == "error" else [])}}


def _tools_for(agent: str, holdings: list[dict]) -> list:
    news_tool = tools.make_news_agent_tool(run_news)
    return {
        "finance_qa": [tools.make_retrieve_tool(None)],
        "tax_education": [tools.make_retrieve_tool("tax")],
        "portfolio": [tools.make_portfolio_tool(holdings), tools.get_history, news_tool],
        "market": [tools.resolve_ticker, tools.get_quote, tools.get_history, news_tool],
        "goal_planning": [tools.project_goal],
        "news": [tools.fetch_news],
    }[agent]


PROMPTS = {
    "finance_qa": prompts.FINANCE_QA, "tax_education": prompts.TAX_EDUCATION,
    "portfolio": prompts.PORTFOLIO, "market": prompts.MARKET,
    "goal_planning": prompts.GOAL_PLANNING, "news": prompts.NEWS,
}


def run_agent(agent: str, query: str, profile: dict, holdings: list[dict], history: list, llm=None) -> dict:
    start = time.perf_counter()
    llm = llm or get_chat_model()
    budget = get_config()["agents"]["budgets"][agent]
    system = PROMPTS[agent] + "\n\n" + prompts.profile_block(profile)
    messages = [*history, HumanMessage(content=query)]
    try:
        res = run_react(llm, system, messages, _tools_for(agent, holdings), budget)
        sources, unavailable = _collect_meta(res["tool_results"])
        out = {"agent": agent, "answer": res["answer"], "sources": sources,
               "unavailable": unavailable, "status": "ok", "tool_calls": res["tool_calls"]}
    except Exception as e:  # noqa: BLE001 - one failing agent must not sink the whole reply
        log.exception("agent %s failed", agent)
        out = {"agent": agent, "answer": "", "sources": [], "status": "error",
               "unavailable": [f"{AGENT_LABELS[agent]} (temporarily unavailable)"], "error": str(e)}
    log_event(log, "agent_done", agent=agent, status=out["status"], tool_calls=out.get("tool_calls"),
              latency_ms=round(1000 * (time.perf_counter() - start)))
    return out
