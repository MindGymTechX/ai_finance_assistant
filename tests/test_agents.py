import json

import pytest

pytest.importorskip("langgraph")
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402

from src.agents import specialists, tools  # noqa: E402
from src.agents.evaluator import evaluate  # noqa: E402
from src.agents.react import BUDGET_MSG, run_react  # noqa: E402
from src.agents.router import route  # noqa: E402
from src.agents.synthesizer import synthesize  # noqa: E402
from tests.fakes import FakeLLM, tool_call  # noqa: E402


@tool
def echo(x: str) -> str:
    """Echo."""
    return json.dumps({"status": "ok", "x": x, "_meta": {"sources": [{"label": "echo"}], "unavailable": []}})


def test_react_loop_calls_tool_then_answers():
    llm = FakeLLM([tool_call("echo", {"x": "hi"}), AIMessage(content="done")])
    r = run_react(llm, "sys", [HumanMessage(content="q")], [echo], budget=3)
    assert r["answer"] == "done" and r["tool_calls"] == 1 and r["tool_results"][0]["x"] == "hi"


def test_react_budget_stops_loop():
    llm = FakeLLM([tool_call("echo", {"x": "1"}), tool_call("echo", {"x": "2"}, "c2"), AIMessage(content="partial")])
    r = run_react(llm, "sys", [HumanMessage(content="q")], [echo], budget=1)
    assert r["budget_hit"] and r["answer"] == "partial"
    assert any(getattr(m, "content", "") == BUDGET_MSG for m in llm.calls[-1])


def test_react_tool_error_is_reported_not_raised():
    llm = FakeLLM([tool_call("nope", {}), AIMessage(content="ok")])
    r = run_react(llm, "sys", [HumanMessage(content="q")], [echo], budget=2)
    assert r["tool_results"][0]["status"] == "error"


def test_router_dedupes_caps_and_falls_back():
    llm = FakeLLM(structured={"RouterDecision": [{"tasks": [
        {"agent": "market", "query": "a"}, {"agent": "market", "query": "b"}, {"agent": "news", "query": "c"},
        {"agent": "tax_education", "query": "d"}, {"agent": "portfolio", "query": "e"}]}]})
    d = route(llm, [HumanMessage(content="x")], {})
    assert [t.agent for t in d.tasks] == ["market", "news", "tax_education"]
    d2 = route(FakeLLM(), [HumanMessage(content="what is an etf")], {})  # structured output fails
    assert d2.tasks[0].agent == "finance_qa"


def test_synthesizer_skips_llm_for_single_output():
    llm = FakeLLM()
    assert synthesize(llm, "q", [{"agent": "market", "answer": "A"}]) == "A" and not llm.calls
    merged = synthesize(FakeLLM([AIMessage(content="merged")]), "q",
                        [{"agent": "market", "answer": "A"}, {"agent": "news", "answer": "B"}])
    assert merged == "merged"
    assert synthesize(FakeLLM(), "q", [], draft="Hello!") == "Hello!"


def test_evaluator_rules_then_llm():
    ok, fb = evaluate(FakeLLM(), "You should buy Infosys now.")
    assert not ok and "recommend_action" in fb
    llm = FakeLLM(structured={"AdviceCheck": [{"is_advice": True, "reason": "timing"}]})
    assert evaluate(llm, "Markets look ripe for adding IT exposure.")[0] is False
    assert evaluate(FakeLLM(), "PPF has a 15-year term.", use_llm=False) == (True, "")


def test_portfolio_tool_empty_and_goal_tool():
    out = json.loads(tools.make_portfolio_tool([]).invoke({}))
    assert out["status"] == "empty"
    g = json.loads(tools.project_goal.invoke({"target_amount": 2500000, "years": 8, "current_savings": 300000,
                                              "risk": "moderate"}))
    assert g["status"] == "ok" and g["monthly_sip"] > 0 and g["_meta"]["sources"]


def test_news_agent_contract_error_vs_no_news(monkeypatch):
    monkeypatch.setattr(tools, "_fetch_news", lambda q, days, max_items: {
        "status": "error", "items": [], "query": q, "source": "Yahoo Finance"})
    llm = FakeLLM([tool_call("fetch_news", {"query": "INFY.NS"}), AIMessage(content="Could not check news.")])
    r = specialists.run_news("news on infy", ["INFY.NS"], [], llm=llm)
    assert r["status"] == "error" and r["_meta"]["unavailable"]
    monkeypatch.setattr(tools, "_fetch_news", lambda q, days, max_items: {
        "status": "no_news", "items": [], "query": q, "source": "Yahoo Finance"})
    llm = FakeLLM([tool_call("fetch_news", {"query": "INFY.NS"}), AIMessage(content="Nothing new.")])
    assert specialists.run_news("news", ["INFY.NS"], [], llm=llm)["status"] == "no_news"


def test_run_agent_collects_sources_and_survives_errors():
    llm = FakeLLM([tool_call("project_goal", {"target_amount": 1e6, "years": 5, "current_savings": 0,
                                              "risk": "cautious"}), AIMessage(content="You need about ...")])
    out = specialists.run_agent("goal_planning", "plan 10 lakh in 5 years", {}, [], [], llm=llm)
    assert out["status"] == "ok" and out["sources"][0]["label"] == "FinAI goal assumptions"

    class Boom(FakeLLM):
        def invoke(self, messages):
            raise RuntimeError("api down")
    bad = specialists.run_agent("market", "price of infy", {}, [], [], llm=Boom())
    assert bad["status"] == "error" and bad["unavailable"]
