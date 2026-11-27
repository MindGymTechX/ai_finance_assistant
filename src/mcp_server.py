"""MCP server (FR13): exposes FinAI's tools to Claude Desktop or any MCP client.

Run:  python -m src.mcp_server        (stdio transport)
Claude Desktop config (claude_desktop_config.json):
  "finai": {"command": "/path/to/.venv/bin/python", "args": ["-m", "src.mcp_server"],
            "cwd": "/path/to/ai_finance_assistant"}
"""
from __future__ import annotations

import uuid

from mcp.server.fastmcp import FastMCP

from src.core import services
from src.core.config import get_config
from src.utils import tickers
from src.utils.finance_math import project_goal as _project_goal

mcp = FastMCP("finai")


@mcp.tool()
def get_quote(name_or_ticker: str) -> dict:
    """Latest NSE price for a company/index name or ticker, with as_of time and status (educational)."""
    r = tickers.resolve(name_or_ticker, get_config()["market"]["exchange_suffix"])
    if r["status"] != "ok":
        return r
    return services.get_market().get_quote(r["ticker"])


@mcp.tool()
def analyze_portfolio(holdings: list[dict]) -> dict:
    """Analyse holdings: [{symbol, quantity, avg_price, asset_type?, sector?, expense_ratio?, plan?, current_price?}]."""
    return services.analyze_holdings(holdings)


@mcp.tool()
def project_goal(target_amount: float, years: float, current_savings: float, risk: str = "moderate") -> dict:
    """Monthly SIP needed for a goal (target in today's rupees), with inflation and stated assumptions."""
    g = get_config()["goals"]
    return _project_goal(target_amount, years, current_savings, risk, g["inflation_pct"],
                         g["expected_return_pct"], g["assumptions_as_of"])


@mcp.tool()
def ask_finai(question: str) -> str:
    """Ask the full FinAI multi-agent assistant an educational finance question (India)."""
    from src.workflow.graph import build_graph, run_turn

    graph = build_graph(checkpointer=services.get_checkpointer())
    answer = ""
    for kind, text in run_turn(graph, f"mcp-{uuid.uuid4().hex[:8]}", "mcp", question, {}, []):
        if kind == "answer":
            answer = text
    return answer


if __name__ == "__main__":
    mcp.run()
