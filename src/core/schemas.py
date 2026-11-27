"""Typed contracts (validated LLM output and agent-to-agent messages)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AgentName = Literal["finance_qa", "tax_education", "portfolio", "market", "goal_planning", "news"]


class Task(BaseModel):
    agent: AgentName
    query: str = Field(description="The part of the user's question this agent should handle, self-contained")


class RouterDecision(BaseModel):
    tasks: list[Task] = Field(default_factory=list, description="Agents to run; empty for greetings/off-topic")
    direct_reply: str = Field(default="", description="Short reply when no agent is needed (greeting, off-topic redirect)")


class AdviceCheck(BaseModel):
    is_advice: bool = Field(description="True if the text recommends buying, selling, holding or timing a specific security")
    reason: str = ""


class NewsRequest(BaseModel):
    request: str = Field(description="What news is needed and why")
    tickers: list[str] = Field(default_factory=list, description="Tickers only, never quantities or values")
    sectors: list[str] = Field(default_factory=list)
    days: int = 7
