"""Synthesizer: merges agent outputs. Skips the LLM when there is nothing to merge (cost NFR5)."""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents import prompts
from src.agents.react import message_text


def synthesize(llm, question: str, outputs: list[dict], draft: str = "", feedback: str = "") -> str:
    if feedback and draft:  # retry after a failed compliance check
        msgs = [SystemMessage(content=prompts.REWRITE.format(feedback=feedback)), HumanMessage(content=draft)]
        return message_text(llm.invoke(msgs))
    answers = [o for o in outputs if o.get("answer")]
    if not answers:
        if draft:
            return draft  # router's direct reply
        failed = [o["agent"] for o in outputs if o.get("status") == "error"]
        return ("Sorry, I couldn't complete that right now" +
                (f" ({', '.join(failed)} unavailable)" if failed else "") + ". Please try again shortly.")
    if len(answers) == 1:
        return answers[0]["answer"]
    body = "\n\n".join(f"### From the {o['agent']} agent\n{o['answer']}" for o in answers)
    msgs = [SystemMessage(content=prompts.SYNTHESIZER),
            HumanMessage(content=f"User question: {question}\n\nAgent answers:\n{body}")]
    return message_text(llm.invoke(msgs))
