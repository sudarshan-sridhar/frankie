"""Chat session persistence backed by SQLite.

Each (robot_id, session_id) is a conversation thread. Messages are stored
in insertion order with a monotonically increasing turn_index so the
AURA app can render the scrollback in deterministic order. Reads and
writes run in the asyncio default executor to avoid blocking the loop.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import structlog
from pydantic import BaseModel

from frankie.config import get_settings

log = structlog.get_logger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    robot_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    turn_index INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    model_used TEXT,
    action_taken TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(robot_id, session_id, turn_index);
"""


class Message(BaseModel):
    """One persisted chat message."""

    id: int
    robot_id: str
    session_id: str
    turn_index: int
    role: str
    content: str
    model_used: str | None = None
    action_taken: str | None = None
    created_at: str


class SessionSummary(BaseModel):
    """Per-session summary returned by list_sessions."""

    session_id: str
    first_user_message: str | None
    last_update: str
    message_count: int


def _db_path() -> Path:
    return get_settings().data_dir / "chat_sessions.sqlite"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _record_message_sync(
    robot_id: str,
    session_id: str,
    role: str,
    content: str,
    model_used: str | None,
    action_taken: str | None,
) -> int:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(MAX(turn_index), -1) FROM chat_messages "
            "WHERE robot_id = ? AND session_id = ?",
            (robot_id, session_id),
        )
        next_turn = int(cur.fetchone()[0]) + 1
        cur.execute(
            "INSERT INTO chat_messages "
            "(robot_id, session_id, turn_index, role, content, "
            " model_used, action_taken, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                robot_id,
                session_id,
                next_turn,
                role,
                content,
                model_used,
                action_taken,
                _now_iso(),
            ),
        )
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        conn.close()


async def record_message(
    robot_id: str,
    session_id: str,
    role: str,
    content: str,
    model_used: str | None = None,
    action_taken: str | None = None,
) -> int:
    """Insert one chat message, returning its row id."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        _record_message_sync,
        robot_id,
        session_id,
        role,
        content,
        model_used,
        action_taken,
    )


def _get_session_sync(robot_id: str, session_id: str) -> list[Message]:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, robot_id, session_id, turn_index, role, content, "
            "model_used, action_taken, created_at "
            "FROM chat_messages WHERE robot_id = ? AND session_id = ? "
            "ORDER BY turn_index ASC",
            (robot_id, session_id),
        )
        return [Message(**dict(row)) for row in cur.fetchall()]
    finally:
        conn.close()


async def get_session(robot_id: str, session_id: str) -> list[Message]:
    """Return all messages in the given session, in turn order."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_session_sync, robot_id, session_id)


def _list_sessions_sync(robot_id: str) -> list[SessionSummary]:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT session_id, "
            "       MAX(created_at) AS last_update, "
            "       COUNT(*) AS message_count "
            "FROM chat_messages WHERE robot_id = ? "
            "GROUP BY session_id "
            "ORDER BY last_update DESC",
            (robot_id,),
        )
        rows = cur.fetchall()

        summaries: list[SessionSummary] = []
        for row in rows:
            sid = row["session_id"]
            cur.execute(
                "SELECT content FROM chat_messages "
                "WHERE robot_id = ? AND session_id = ? AND role = 'user' "
                "ORDER BY turn_index ASC LIMIT 1",
                (robot_id, sid),
            )
            first_row = cur.fetchone()
            summaries.append(
                SessionSummary(
                    session_id=sid,
                    first_user_message=first_row["content"] if first_row else None,
                    last_update=row["last_update"],
                    message_count=int(row["message_count"]),
                )
            )
        return summaries
    finally:
        conn.close()


async def list_sessions(robot_id: str) -> list[SessionSummary]:
    """List sessions for a robot, newest first, with a short summary each."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _list_sessions_sync, robot_id)
