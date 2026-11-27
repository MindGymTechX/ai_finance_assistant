"""A minimal hand-built ReAct loop: reason -> act (tool) -> observe -> repeat, with a tool budget.
Kept explicit (instead of a prebuilt agent) so the loop, budget and metadata capture are visible."""
from __future__ import annotations

import json

from langchain_core.messages import SystemMessage, ToolMessage

BUDGET_MSG = ("Tool budget reached. Do not call more tools. Answer now with the information you "
              "already have and say clearly what you could not check.")


def message_text(msg) -> str:
    c = getattr(msg, "content", "")
    if isinstance(c, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in c)
    return str(c or "")


def _parse(out) -> dict:
    if isinstance(out, dict):
        return out
    try:
        v = json.loads(out)
        return v if isinstance(v, dict) else {"value": v}
    except (TypeError, ValueError):
        return {"value": str(out)}


def run_react(llm, system_prompt: str, messages: list, tools: list, budget: int) -> dict:
    """Returns {"answer", "tool_results": [parsed tool outputs], "tool_calls": n, "budget_hit": bool}."""
    by_name = {t.name: t for t in tools}
    bound = llm.bind_tools(tools) if tools else llm
    convo = [SystemMessage(content=system_prompt), *messages]
    results: list[dict] = []
    calls = 0
    while True:
        resp = bound.invoke(convo)
        convo.append(resp)
        tool_calls = getattr(resp, "tool_calls", None) or []
        if not tool_calls:
            return {"answer": message_text(resp), "tool_results": results, "tool_calls": calls, "budget_hit": False}
        if calls >= budget:
            for tc in tool_calls:
                convo.append(ToolMessage(content=BUDGET_MSG, tool_call_id=tc["id"], name=tc["name"]))
            final = llm.bind_tools(tools, tool_choice="none").invoke(convo) if tools else llm.invoke(convo)
            return {"answer": message_text(final), "tool_results": results, "tool_calls": calls, "budget_hit": True}
        for tc in tool_calls:
            calls += 1
            tool = by_name.get(tc["name"])
            try:
                out = tool.invoke(tc.get("args", {})) if tool else json.dumps({"status": "error", "error": "unknown tool"})
            except Exception as e:  # noqa: BLE001 - tool errors are reported to the LLM, not raised
                out = json.dumps({"status": "error", "error": f"{type(e).__name__}: {e}"})
            out_str = out if isinstance(out, str) else json.dumps(out, default=str)
            results.append(_parse(out_str))
            convo.append(ToolMessage(content=out_str, tool_call_id=tc["id"], name=tc["name"]))
