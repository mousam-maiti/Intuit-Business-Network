"""
MySQL client for chat_sessions + chat_messages tables.
Falls back to in-memory storage when MySQL is unavailable.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

CREATE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    title VARCHAR(255),
    context_summary TEXT,
    compressed_up_to INT DEFAULT 0,
    message_count INT DEFAULT 0,
    status ENUM('active', 'archived') DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_sessions (user_id, status, updated_at DESC)
)
"""

CREATE_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS chat_messages (
    message_id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL,
    role ENUM('user', 'assistant', 'system') NOT NULL,
    content TEXT NOT NULL,
    metadata JSON,
    token_estimate INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
    INDEX idx_session_messages (session_id, created_at)
)
"""


class ChatDB:
    """MySQL-backed chat persistence."""

    def __init__(self, host: str, port: int, user: str, password: str, database: str,
                 pool_size: int = 5):
        self._config = dict(host=host, port=port, user=user, password=password,
                            database=database, pool_size=pool_size)
        self._pool = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self):
        """Connect to MySQL and ensure tables exist."""
        try:
            import mysql.connector.pooling
            self._pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name="chat_pool",
                pool_size=self._config["pool_size"],
                host=self._config["host"],
                port=self._config["port"],
                user=self._config["user"],
                password=self._config["password"],
                database=self._config["database"],
            )
            conn = self._pool.get_connection()
            cursor = conn.cursor()
            cursor.execute(CREATE_SESSIONS_TABLE)
            cursor.execute(CREATE_MESSAGES_TABLE)
            conn.commit()
            cursor.close()
            conn.close()
            self._connected = True
            logger.info("ChatDB connected to MySQL")
        except Exception as e:
            logger.warning(f"ChatDB MySQL connection failed: {e} — using in-memory fallback")
            self._connected = False

    def _get_conn(self):
        return self._pool.get_connection()

    # ── Sessions ─────────────────────────────────────────────

    def get_session(self, session_id: str) -> dict | None:
        conn = self._get_conn()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM chat_sessions WHERE session_id = %s", (session_id,))
            row = cursor.fetchone()
            cursor.close()
            return row
        finally:
            conn.close()

    def create_session(self, session_id: str, user_id: str, title: str | None = None) -> dict:
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO chat_sessions (session_id, user_id, title) VALUES (%s, %s, %s)",
                (session_id, user_id, title),
            )
            conn.commit()
            cursor.close()
        finally:
            conn.close()
        return self.get_session(session_id)

    def update_session(self, session_id: str, **fields) -> dict:
        conn = self._get_conn()
        try:
            sets = ", ".join(f"{k} = %s" for k in fields)
            vals = list(fields.values()) + [session_id]
            cursor = conn.cursor()
            cursor.execute(f"UPDATE chat_sessions SET {sets} WHERE session_id = %s", vals)
            conn.commit()
            cursor.close()
        finally:
            conn.close()
        return self.get_session(session_id)

    def list_sessions(self, user_id: str) -> list[dict]:
        conn = self._get_conn()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT session_id, user_id, title, message_count, status, created_at, updated_at "
                "FROM chat_sessions WHERE user_id = %s AND status = 'active' "
                "ORDER BY updated_at DESC",
                (user_id,),
            )
            rows = cursor.fetchall()
            cursor.close()
            return rows
        finally:
            conn.close()

    # ── Messages ─────────────────────────────────────────────

    def add_message(self, message_id: str, session_id: str, role: str, content: str,
                    metadata: dict | None = None, token_estimate: int = 0):
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO chat_messages (message_id, session_id, role, content, metadata, token_estimate) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (message_id, session_id, role, content,
                 json.dumps(metadata) if metadata else None, token_estimate),
            )
            cursor.execute(
                "UPDATE chat_sessions SET message_count = message_count + 1 WHERE session_id = %s",
                (session_id,),
            )
            conn.commit()
            cursor.close()
        finally:
            conn.close()

    def get_messages(self, session_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
        conn = self._get_conn()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM chat_messages WHERE session_id = %s "
                "ORDER BY created_at ASC LIMIT %s OFFSET %s",
                (session_id, limit, offset),
            )
            rows = cursor.fetchall()
            cursor.close()
            for row in rows:
                if row.get("metadata") and isinstance(row["metadata"], str):
                    row["metadata"] = json.loads(row["metadata"])
            return rows
        finally:
            conn.close()

    def get_recent_messages(self, session_id: str, limit: int = 10) -> list[dict]:
        conn = self._get_conn()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM chat_messages WHERE session_id = %s "
                "ORDER BY created_at DESC LIMIT %s",
                (session_id, limit),
            )
            rows = list(reversed(cursor.fetchall()))
            cursor.close()
            for row in rows:
                if row.get("metadata") and isinstance(row["metadata"], str):
                    row["metadata"] = json.loads(row["metadata"])
            return rows
        finally:
            conn.close()

    def delete_messages_before(self, session_id: str, before_message_id: str) -> int:
        """Delete messages older than the given message (by created_at)."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM chat_messages WHERE session_id = %s AND created_at < "
                "(SELECT created_at FROM (SELECT created_at FROM chat_messages WHERE message_id = %s) t)",
                (session_id, before_message_id),
            )
            deleted = cursor.rowcount
            conn.commit()
            cursor.close()
            return deleted
        finally:
            conn.close()

    def clear_messages(self, session_id: str):
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chat_messages WHERE session_id = %s", (session_id,))
            cursor.execute(
                "UPDATE chat_sessions SET message_count = 0, context_summary = NULL, "
                "compressed_up_to = 0 WHERE session_id = %s",
                (session_id,),
            )
            conn.commit()
            cursor.close()
        finally:
            conn.close()

    async def close(self):
        # mysql-connector pool doesn't need explicit close
        self._connected = False


class MockChatDB:
    """In-memory fallback for testing / when MySQL is unavailable."""

    def __init__(self):
        self._sessions: dict[str, dict] = {}
        self._messages: dict[str, list[dict]] = {}
        self._connected = True

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self):
        self._connected = True

    def get_session(self, session_id: str) -> dict | None:
        return self._sessions.get(session_id)

    def create_session(self, session_id: str, user_id: str, title: str | None = None) -> dict:
        now = datetime.now(timezone.utc)
        session = {
            "session_id": session_id, "user_id": user_id, "title": title,
            "context_summary": None, "compressed_up_to": 0, "message_count": 0,
            "status": "active", "created_at": now, "updated_at": now,
        }
        self._sessions[session_id] = session
        self._messages[session_id] = []
        return session

    def update_session(self, session_id: str, **fields) -> dict:
        session = self._sessions[session_id]
        session.update(fields)
        session["updated_at"] = datetime.now(timezone.utc)
        return session

    def list_sessions(self, user_id: str) -> list[dict]:
        return sorted(
            [s for s in self._sessions.values() if s["user_id"] == user_id and s["status"] == "active"],
            key=lambda s: s["updated_at"], reverse=True,
        )

    def add_message(self, message_id: str, session_id: str, role: str, content: str,
                    metadata: dict | None = None, token_estimate: int = 0):
        now = datetime.now(timezone.utc)
        msg = {
            "message_id": message_id, "session_id": session_id, "role": role,
            "content": content, "metadata": metadata, "token_estimate": token_estimate,
            "created_at": now,
        }
        self._messages.setdefault(session_id, []).append(msg)
        if session_id in self._sessions:
            self._sessions[session_id]["message_count"] += 1
            self._sessions[session_id]["updated_at"] = now

    def get_messages(self, session_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
        msgs = self._messages.get(session_id, [])
        return msgs[offset:offset + limit]

    def get_recent_messages(self, session_id: str, limit: int = 10) -> list[dict]:
        msgs = self._messages.get(session_id, [])
        return msgs[-limit:]

    def delete_messages_before(self, session_id: str, before_message_id: str) -> int:
        msgs = self._messages.get(session_id, [])
        idx = next((i for i, m in enumerate(msgs) if m["message_id"] == before_message_id), None)
        if idx is None:
            return 0
        deleted = msgs[:idx]
        self._messages[session_id] = msgs[idx:]
        return len(deleted)

    def clear_messages(self, session_id: str):
        self._messages[session_id] = []
        if session_id in self._sessions:
            self._sessions[session_id]["message_count"] = 0
            self._sessions[session_id]["context_summary"] = None
            self._sessions[session_id]["compressed_up_to"] = 0

    async def close(self):
        self._connected = False
