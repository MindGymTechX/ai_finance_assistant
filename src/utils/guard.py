"""Input guard (NFR10): blocks prompt-injection attempts before any LLM sees the text."""
from __future__ import annotations

import re

PATTERNS: dict[str, str] = {
    "ignore_instructions": r"\b(ignore|disregard|forget|override)\b.{0,30}\b(previous|prior|above|earlier|all|your|the)\b.{0,20}\b(instructions?|rules?|prompts?|guidelines?|polic(y|ies))",
    "new_instructions": r"\b(new|updated|real)\s+(instructions?|rules?|system prompt)\s*[:\-]",
    "role_switch": r"\byou are (now|no longer)\b|\bact as (an?|my) (unrestricted|unfiltered|licensed|registered|sebi)",
    "pretend": r"\b(pretend|imagine|roleplay|role-play)\b.{0,40}\b(no (rules|restrictions|limits)|financial advis[eo]r|without (rules|restrictions))",
    "dan_mode": r"\b(DAN|do anything now|developer mode|jailbreak|god mode)\b",
    "system_tag": r"(<\|?(system|im_start|im_end)\|?>|\[/?(INST|SYS)\]|^\s*system\s*:)",
    "prompt_leak": r"\b(reveal|show|print|repeat|leak|output)\b.{0,30}\b(system prompt|your (prompt|instructions|rules)|hidden (prompt|instructions))",
    "disable_safety": r"\b(disable|turn off|bypass|remove|skip)\b.{0,25}\b(safety|guardrails?|filters?|disclaimers?|compliance|restrictions)",
    "no_disclaimer": r"\bwithout (any )?(disclaimers?|warnings?|caveats?)\b",
    "fake_authority": r"\b(i am|i'm) (your|the) (developer|admin|administrator|creator|owner)\b",
    "conversation_injection": r"(^|\n)\s*(assistant|ai|finai)\s*:\s",
    "encoded_payload": r"\b(base64|rot13)\b.{0,30}\b(decode|instructions?)",
}
_COMPILED = {k: re.compile(v, re.IGNORECASE | re.MULTILINE) for k, v in PATTERNS.items()}

REFUSAL = ("I can't follow instructions that try to change how I work. I'm an educational "
           "finance assistant: I can explain concepts, analyse your entered portfolio, show market "
           "data and help plan goals. What would you like to learn about?")


def scan(text: str) -> list[str]:
    """Names of matched injection patterns (empty list = clean)."""
    return [name for name, rx in _COMPILED.items() if rx.search(text or "")]
