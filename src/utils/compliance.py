"""Compliance helpers (FR9, NFR1): rule-based advice detection, disclaimer and the
code-built sources & freshness footer."""
from __future__ import annotations

import re

DISCLAIMER = "Educational information only, not investment advice."

SAFE_FALLBACK = ("I couldn't produce an answer that meets my education-only rules, so I'm not "
                 "showing it. I can explain the concepts involved, for example how to evaluate a "
                 "stock or fund, what diversification means, or how risk relates to time horizon.")

ADVICE_PATTERNS = {
    "recommend_action": r"\b(you should|you must|i (would )?recommend|i'd recommend|we recommend|i suggest|my advice is)\b[^.\n]{0,50}\b(buy|sell|hold|exit|invest in|switch to|add more|book profits?|accumulate|avoid)\b",
    "imperative_trade": r"\b(buy|sell|exit|accumulate|short)\s+(now|today|immediately|this stock|these shares|it now)\b",
    "rating_language": r"\b(strong buy|strong sell|target price|stop[- ]loss|price target|multibagger|sure[- ]shot)\b",
    "timing": r"\b(good|great|right|best|perfect) (time|moment|opportunity) to (buy|sell|invest|exit|enter|add)\b",
    "guarantee": r"\b(guaranteed|risk[- ]free|can'?t lose|assured) (returns?|profits?|gains?)\b",
}
_COMPILED = {k: re.compile(v, re.IGNORECASE) for k, v in ADVICE_PATTERNS.items()}


def advice_violations(text: str) -> list[str]:
    return [name for name, rx in _COMPILED.items() if rx.search(text or "")]


def build_footer(outputs: list[dict]) -> str:
    """Sources and freshness, assembled from tool metadata. Never written by the LLM."""
    sources, missing = [], []
    for o in outputs:
        for s in o.get("sources", []):
            label = s.get("label", "")
            if s.get("as_of"):
                label += f" (as of {s['as_of']})"
            if label and label not in sources:
                sources.append(label)
        for m in o.get("unavailable", []):
            if m not in missing:
                missing.append(m)
    lines = []
    if sources:
        lines.append("**Sources:** " + " · ".join(sources[:10]))
    if missing:
        lines.append("**Not available:** " + "; ".join(missing) + ". This answer does not include it.")
    lines.append(f"_{DISCLAIMER}_")
    return "\n\n".join(lines)
