"""Small exponential-backoff helper for non-LLM calls (yfinance, RSS)."""
from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def with_retry(fn: Callable[[], T], attempts: int = 3, base_delay: float = 0.5,
               sleep: Callable[[float], None] = time.sleep) -> T:
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - we re-raise the last one
            last = e
            if i < attempts - 1:
                sleep(base_delay * (2 ** i))
    assert last is not None
    raise last
