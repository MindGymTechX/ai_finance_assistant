"""Long-term memory per user (FR8a/FR8b): profile, holdings and the list of chat threads.
Conversation content itself lives in the LangGraph checkpointer, keyed by thread_id."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path

DEFAULT_PROFILE = {"name": "", "age": None, "monthly_income": None, "knowledge_level": "beginner",
                   "risk_appetite": "moderate", "goals": ""}


class ProfileStore:
    def __init__(self, path: str | Path):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, profile TEXT, holdings TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS threads (thread_id TEXT PRIMARY KEY, user_id TEXT, title TEXT, created_at TEXT);
        """)
        self._db.commit()

    @staticmethod
    def normalize_user_id(user_id: str) -> str:
        return "".join(ch for ch in user_id.strip().lower() if ch.isalnum() or ch in "-_.")[:40]

    def load(self, user_id: str) -> tuple[dict, list[dict]]:
        with self._lock:
            row = self._db.execute("SELECT profile, holdings FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            return dict(DEFAULT_PROFILE), []
        return {**DEFAULT_PROFILE, **json.loads(row[0] or "{}")}, json.loads(row[1] or "[]")

    def save(self, user_id: str, profile: dict, holdings: list[dict]) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?)",
                             (user_id, json.dumps(profile), json.dumps(holdings), datetime.now().isoformat()))
            self._db.commit()

    def new_thread(self, user_id: str, title: str = "New chat") -> str:
        tid = f"{user_id}-{uuid.uuid4().hex[:8]}"
        with self._lock:
            self._db.execute("INSERT INTO threads VALUES (?,?,?,?)", (tid, user_id, title, datetime.now().isoformat()))
            self._db.commit()
        return tid

    def rename_thread(self, thread_id: str, title: str) -> None:
        with self._lock:
            self._db.execute("UPDATE threads SET title=? WHERE thread_id=?", (title[:60], thread_id))
            self._db.commit()

    def list_threads(self, user_id: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT thread_id, title, created_at FROM threads WHERE user_id=? "
                                    "ORDER BY created_at DESC", (user_id,)).fetchall()
        return [{"thread_id": r[0], "title": r[1], "created_at": r[2]} for r in rows]
