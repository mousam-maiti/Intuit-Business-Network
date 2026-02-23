"""
SessionManager — thin CRUD layer over ChatDB for session/message lifecycle.
"""
from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages chat sessions and messages."""

    def __init__(self, db):
        self.db = db

    def get_or_create_session(self, session_id: str, user_id: str) -> dict:
        """Get an existing session or create a new one."""
        session = self.db.get_session(session_id)
        if session:
            return session
        return self.db.create_session(session_id, user_id)

    def save_user_message(self, session_id: str, content: str,
                          context: dict | None = None) -> str:
        """Save a user message and return its message_id."""
        message_id = str(uuid.uuid4())
        token_estimate = len(content) // 4
        self.db.add_message(
            message_id=message_id,
            session_id=session_id,
            role="user",
            content=content,
            metadata={"context": context} if context else None,
            token_estimate=token_estimate,
        )
        return message_id

    def save_assistant_message(self, session_id: str, content: str,
                               metadata: dict | None = None) -> str:
        """Save an assistant response and return its message_id."""
        message_id = str(uuid.uuid4())
        token_estimate = len(content) // 4
        self.db.add_message(
            message_id=message_id,
            session_id=session_id,
            role="assistant",
            content=content,
            metadata=metadata,
            token_estimate=token_estimate,
        )
        return message_id

    def get_session_messages(self, session_id: str, limit: int = 100) -> list[dict]:
        """Get all messages in a session, ordered by creation time."""
        return self.db.get_messages(session_id, limit=limit)

    def get_recent_messages(self, session_id: str, limit: int = 10) -> list[dict]:
        """Get the most recent messages for context assembly."""
        return self.db.get_recent_messages(session_id, limit=limit)

    def clear_session_context(self, session_id: str):
        """Clear all messages and summary for a session."""
        self.db.clear_messages(session_id)
        logger.info(f"Cleared context for session {session_id}")

    def archive_session(self, session_id: str):
        """Archive a session (soft delete)."""
        self.db.update_session(session_id, status="archived")
        logger.info(f"Archived session {session_id}")

    def update_title(self, session_id: str, title: str):
        """Update the session title."""
        self.db.update_session(session_id, title=title)

    def list_user_sessions(self, user_id: str) -> list[dict]:
        """List all active sessions for a user."""
        return self.db.list_sessions(user_id)

    def get_session(self, session_id: str) -> dict | None:
        """Get session by ID."""
        return self.db.get_session(session_id)
