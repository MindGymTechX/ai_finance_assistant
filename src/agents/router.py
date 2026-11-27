"""Router: one small structured-output LLM call (a classifier, not an agent)."""
from __future__ import annotations

from langchain_core.messages import SystemMessage

from src.agents import prompts
from src.core.logging_setup import get_logger
from src.core.schemas import RouterDecision

log = get_logger("finai.router")
MAX_TASKS = 3


def route(llm, history: list, profile: dict) -> RouterDecision:
    system = prompts.ROUTER + "\n\n" + prompts.profile_block(profile)
    try:
        decision = llm.with_structured_output(RouterDecision, method="function_calling").invoke([SystemMessage(content=system), *history])
    except Exception:  # noqa: BLE001 - structured output occasionally fails; never crash the turn
        log.exception("router failed; defaulting to finance_qa")
        last = history[-1].content if history else ""
        return RouterDecision.model_validate({"tasks": [{"agent": "finance_qa", "query": str(last)}]})
    seen, tasks = set(), []
    for t in decision.tasks:
        if t.agent not in seen:
            seen.add(t.agent)
            tasks.append(t)
    decision.tasks = tasks[:MAX_TASKS]
    if not decision.tasks and not decision.direct_reply.strip():
        last = history[-1].content if history else ""
        decision = RouterDecision.model_validate({"tasks": [{"agent": "finance_qa", "query": str(last)}]})
    return decision
