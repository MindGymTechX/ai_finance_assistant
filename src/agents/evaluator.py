"""Evaluator: rules first (regex), then an optional small LLM check for subtle advice (NFR1)."""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents import prompts
from src.core.logging_setup import get_logger
from src.core.schemas import AdviceCheck
from src.utils.compliance import advice_violations

log = get_logger("finai.evaluator")


def evaluate(llm, draft: str, use_llm: bool = True) -> tuple[bool, str]:
    """Returns (passed, feedback)."""
    hits = advice_violations(draft)
    if hits:
        return False, f"Advice-like language detected ({', '.join(hits)})."
    if not use_llm or not draft.strip():
        return True, ""
    try:
        verdict = llm.with_structured_output(AdviceCheck, method="function_calling").invoke(
            [SystemMessage(content=prompts.ADVICE_JUDGE), HumanMessage(content=draft)])
    except Exception:  # noqa: BLE001 - rules already passed; don't block on a judge failure
        log.exception("LLM advice check failed; rules passed, allowing")
        return True, ""
    return (False, f"Subtle advice: {verdict.reason}") if verdict.is_advice else (True, "")
