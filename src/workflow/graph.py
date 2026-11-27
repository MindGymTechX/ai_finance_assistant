"""The multi-agent LangGraph workflow.

START -> guard -> router -> (Send to 1-3 agents in parallel) -> synthesizer -> evaluator -> finalize -> END
Shortcuts: guard blocked -> finalize; router direct reply (greeting/off-topic) -> evaluator.
Evaluator fail -> synthesizer (rewrite, max N) -> else safe fallback."""
from __future__ import annotations

import time
from typing import Callable, TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from src.agents.evaluator import evaluate
from src.agents.router import route
from src.agents.specialists import run_agent
from src.agents.synthesizer import synthesize
from src.core.config import get_config
from src.core.logging_setup import get_logger, log_event
from src.core.state import RESET, FinState
from src.utils import guard as guard_rules
from src.utils.compliance import DISCLAIMER, SAFE_FALLBACK, build_footer

log = get_logger("finai.graph")
class AgentTask(TypedDict, total=False):
    """Private input of an agent node (sent with Send); declared so LangGraph keeps these keys."""
    task: dict
    profile: dict
    holdings: list[dict]
    history: list


AGENTS = ["finance_qa", "tax_education", "portfolio", "market", "goal_planning", "news"]


def _last_user_text(state: FinState) -> str:
    for m in reversed(state.get("messages", [])):
        if isinstance(m, HumanMessage):
            return str(m.content)
    return ""


def _recent(state: FinState, n: int) -> list:
    """Recent conversation, only human/AI text messages."""
    msgs = [m for m in state.get("messages", []) if isinstance(m, (HumanMessage, AIMessage))]
    return msgs[-n:]


def build_graph(llm=None, checkpointer=None, agent_runner: Callable = run_agent):
    cfg = get_config()
    n_hist = cfg["agents"]["history_turns"]
    max_retries = cfg["evaluator"]["max_retries"]

    def _llm():
        if llm is not None:
            return llm
        from src.core.llm import get_chat_model
        return get_chat_model()

    def guard(state: FinState) -> dict:
        hits = guard_rules.scan(_last_user_text(state))
        reset = {"agent_outputs": RESET, "tasks": [], "draft": "", "eval_attempts": 0, "eval_feedback": "", "final": ""}
        if hits:
            log_event(log, "guard_blocked", patterns=hits)
            return {**reset, "blocked": True, "final": guard_rules.REFUSAL}
        return {**reset, "blocked": False}

    def router(state: FinState) -> dict:
        d = route(_llm(), _recent(state, n_hist), state.get("profile", {}))
        tasks = [t.model_dump() for t in d.tasks]
        log_event(log, "routed", agents=[t["agent"] for t in tasks], direct=bool(d.direct_reply))
        return {"tasks": tasks, "draft": d.direct_reply if not tasks else ""}

    def dispatch(state: FinState):
        tasks = state.get("tasks") or []
        if not tasks:
            return "evaluator"
        history = _recent(state, n_hist)[:-1]  # the current question is passed as the task query
        return [Send(t["agent"], {"task": t, "profile": state.get("profile", {}),
                                  "holdings": state.get("holdings", []), "history": history}) for t in tasks]

    def make_agent_node(name: str):
        def node(payload: AgentTask) -> dict:
            t = payload["task"]
            out = agent_runner(name, t["query"], payload.get("profile", {}), payload.get("holdings", []),
                               payload.get("history", []), llm=llm)
            return {"agent_outputs": [out]}
        return node

    def synthesizer(state: FinState) -> dict:
        draft = synthesize(_llm(), _last_user_text(state), state.get("agent_outputs", []),
                           state.get("draft", ""), state.get("eval_feedback", ""))
        return {"draft": draft, "eval_feedback": ""}

    def evaluator(state: FinState) -> dict:
        ok, feedback = evaluate(_llm(), state.get("draft", ""), cfg["evaluator"]["llm_check"])
        attempts = state.get("eval_attempts", 0)
        log_event(log, "evaluated", passed=ok, attempts=attempts, feedback=feedback)
        if ok:
            return {"eval_feedback": ""}
        if attempts < max_retries:
            return {"eval_feedback": feedback, "eval_attempts": attempts + 1}
        return {"eval_feedback": "", "final": SAFE_FALLBACK}

    def after_eval(state: FinState) -> str:
        return "synthesizer" if state.get("eval_feedback") else "finalize"

    def finalize(state: FinState) -> dict:
        if state.get("blocked"):
            text = state["final"]
        elif state.get("final"):  # safe fallback
            text = f"{state['final']}\n\n_{DISCLAIMER}_"
        else:
            text = f"{state.get('draft', '').strip()}\n\n---\n{build_footer(state.get('agent_outputs', []))}"
        return {"final": text, "messages": [AIMessage(content=text)]}

    g = StateGraph(FinState)
    g.add_node("guard", guard)
    g.add_node("router", router)
    for a in AGENTS:
        g.add_node(a, make_agent_node(a))
    g.add_node("synthesizer", synthesizer)
    g.add_node("evaluator", evaluator)
    g.add_node("finalize", finalize)

    g.add_edge(START, "guard")
    g.add_conditional_edges("guard", lambda s: "finalize" if s.get("blocked") else "router", ["router", "finalize"])
    g.add_conditional_edges("router", dispatch, [*AGENTS, "evaluator"])
    for a in AGENTS:
        g.add_edge(a, "synthesizer")
    g.add_edge("synthesizer", "evaluator")
    g.add_conditional_edges("evaluator", after_eval, ["synthesizer", "finalize"])
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)


PROGRESS = {
    "guard": "Checking your message", "router": "Choosing the right specialists",
    "finance_qa": "Finance Q&A agent finished", "tax_education": "Tax agent finished",
    "portfolio": "Portfolio agent finished", "market": "Market agent finished",
    "goal_planning": "Goal agent finished", "news": "News agent finished",
    "synthesizer": "Writing your answer", "evaluator": "Compliance check done", "finalize": "Done",
}


def run_turn(graph, thread_id: str, user_id: str, message: str, profile: dict, holdings: list[dict]):
    """Streams progress events, then the final answer: yields ("progress", text) and ("answer", text)."""
    start = time.perf_counter()
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 40}
    inputs = {"messages": [HumanMessage(content=message)], "user_id": user_id,
              "profile": profile, "holdings": holdings}
    final = ""
    for update in graph.stream(inputs, config, stream_mode="updates"):
        for node, out in update.items():
            if node in PROGRESS:
                yield "progress", PROGRESS[node]
            if node == "finalize" and out:
                final = out.get("final", "")
    log_event(log, "turn_done", thread=thread_id, latency_ms=round(1000 * (time.perf_counter() - start)))
    yield "answer", final
