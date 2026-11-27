"""Shared graph State (one dict for the whole multi-agent graph)."""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages

RESET = "__reset__"


def outputs_reducer(old: list | None, new: Any) -> list:
    """Parallel agents append their outputs in the same super-step (needs a reducer).
    The guard writes RESET at the start of every turn so last turn's outputs never leak."""
    if new == RESET:
        return []
    return (old or []) + (new or [])


class FinState(TypedDict, total=False):
    messages: Annotated[list, add_messages]   # conversation, checkpointed per thread_id
    user_id: str
    profile: dict                             # knowledge level, risk, goals... (set by UI)
    holdings: list[dict]                      # set by UI, never parsed from chat text
    blocked: bool
    tasks: list[dict]                         # router output [{agent, query}]
    agent_outputs: Annotated[list[dict], outputs_reducer]
    draft: str
    eval_attempts: int
    eval_feedback: str
    final: str
