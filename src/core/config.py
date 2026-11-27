"""Configuration: config.yaml + environment variables (NFR12: nothing hard-coded)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
KB_DIR = ROOT / "src" / "data" / "knowledge_base"
SAMPLE_DIR = ROOT / "src" / "data" / "sample_portfolios"


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:  # python-dotenv is optional at runtime
        pass


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    _load_dotenv()
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    llm = cfg["llm"]
    llm["chat_model"] = os.getenv("FINAI_CHAT_MODEL", llm["chat_model"])
    llm["embed_model"] = os.getenv("FINAI_EMBED_MODEL", llm["embed_model"])
    llm["temperature"] = float(os.getenv("FINAI_TEMPERATURE", llm["temperature"]))
    llm["base_url"] = os.getenv("OPENAI_BASE_URL") or None
    cfg["storage"]["data_dir"] = os.getenv("FINAI_DATA_DIR", cfg["storage"]["data_dir"])
    cfg["log_level"] = os.getenv("FINAI_LOG_LEVEL", "INFO")
    return cfg


def data_dir() -> Path:
    d = Path(get_config()["storage"]["data_dir"])
    if not d.is_absolute():
        d = ROOT / d
    d.mkdir(parents=True, exist_ok=True)
    return d
