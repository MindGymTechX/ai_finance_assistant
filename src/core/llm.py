"""LLM factory. Model, key, base URL and temperature come from config/env (NFR12).
ChatOpenAI's max_retries gives exponential backoff on every call (NFR11)."""
from __future__ import annotations

from functools import lru_cache

from src.core.config import get_config


@lru_cache(maxsize=4)
def get_chat_model(temperature: float | None = None):
    from langchain_openai import ChatOpenAI

    c = get_config()["llm"]
    return ChatOpenAI(
        model=c["chat_model"],
        temperature=c["temperature"] if temperature is None else temperature,
        max_retries=c["max_retries"],
        timeout=c["timeout_seconds"],
        base_url=c["base_url"],
    )


@lru_cache(maxsize=1)
def get_embedder():
    """Returns a function list[str] -> list[list[float]]."""
    from langchain_openai import OpenAIEmbeddings

    c = get_config()["llm"]
    emb = OpenAIEmbeddings(model=c["embed_model"], base_url=c["base_url"],
                           max_retries=c["max_retries"])
    return emb.embed_documents
