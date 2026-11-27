"""Tiny SQLite key-value cache with fetch timestamps (price cache, NFR4)."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class SqliteCache:
    def __init__(self, path: str | Path):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT, fetched_at TEXT)")
        self._conn.commit()

    def get(self, key: str) -> tuple[Any, datetime] | None:
        with self._lock:
            row = self._conn.execute("SELECT v, fetched_at FROM cache WHERE k=?", (key,)).fetchone()
        if not row:
            return None
        return json.loads(row[0]), datetime.fromisoformat(row[1])

    def set(self, key: str, value: Any, fetched_at: datetime) -> None:
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)",
                               (key, json.dumps(value, default=str), fetched_at.isoformat()))
            self._conn.commit()
