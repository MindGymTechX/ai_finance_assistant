"""Structured logging (NFR14). Never logs keys, income or holdings (NFR6)."""
from __future__ import annotations

import json
import logging

_configured = False


def get_logger(name: str) -> logging.Logger:
    global _configured
    if not _configured:
        from src.core.config import get_config
        logging.basicConfig(level=get_config().get("log_level", "INFO"),
                            format="%(asctime)s %(levelname)s %(name)s %(message)s")
        _configured = True
    return logging.getLogger(name)


def log_event(logger: logging.Logger, event: str, **fields) -> None:
    """One JSON line per event: route, agents, latency, evaluator result."""
    logger.info("%s %s", event, json.dumps(fields, default=str))
