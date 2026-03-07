"""
ContextWindow — context assembly + compression for multi-turn chat.

Builds the message history from summary + recent messages, and triggers
compression when the session exceeds the message threshold.
"""
from __future__ import annotations

import json
import logging

from chat.prompts import COMPRESSION_PROMPT

logger = logging.getLogger(__name__)


class ContextWindow:
    """Assembles and compresses conversation context."""

    def __init__(self, db, config, llm=None):
        """
        Args:
            db: ChatDB or MockChatDB instance
            config: ContextConfig dataclass
            llm: LLMProvider instance for compression
        """
        self.db = db
        self.max_messages = config.max_messages
        self.keep_recent = config.keep_recent
        self._llm = llm

    def assemble_context(self, session: dict, new_message: str) -> list[dict]:
        """Build Gemini message history from summary + recent messages + new message.

        Returns list of {"role": "user"|"model", "parts": [text]} dicts
        suitable for genai chat history.
        """
        history = []

        # Include context summary if available
        summary = session.get("context_summary")
        if summary:
            history.append({
                "role": "user",
                "parts": [f"[Previous conversation summary]\n{summary}"],
            })
            history.append({
                "role": "model",
                "parts": ["Understood. I have the context from our previous conversation."],
            })

        # Add recent messages
        recent = self.db.get_recent_messages(session["session_id"], limit=self.keep_recent)
        for msg in recent:
            role = "user" if msg["role"] == "user" else "model"
            history.append({"role": role, "parts": [msg["content"]]})

        return history

    async def maybe_compress(self, session: dict) -> bool:
        """Trigger compression if message_count >= threshold.

        Returns True if compression was performed.
        """
        message_count = session.get("message_count", 0)
        if message_count < self.max_messages:
            return False

        if not self._llm or not self._llm.available:
            logger.warning("LLM unavailable — skipping compression")
            return False

        session_id = session["session_id"]
        logger.info(f"Compressing session {session_id} ({message_count} messages)")

        try:
            # Get all messages
            all_messages = self.db.get_messages(session_id, limit=1000)
            if len(all_messages) <= self.keep_recent:
                return False

            # Split: older (compress) + recent (keep)
            older = all_messages[:-self.keep_recent]
            keep_boundary = all_messages[-self.keep_recent]

            # Format older messages as conversation text
            conversation_text = self._format_conversation(older)

            # Existing summary to subsume
            existing_summary = session.get("context_summary")
            if existing_summary:
                conversation_text = f"[Previous summary]\n{existing_summary}\n\n[New messages]\n{conversation_text}"

            # Call LLM for compression
            prompt = COMPRESSION_PROMPT.format(conversation=conversation_text)
            summary = self._llm.generate(prompt).strip()

            # Update session with new summary
            self.db.update_session(
                session_id,
                context_summary=summary,
                compressed_up_to=session.get("compressed_up_to", 0) + len(older),
            )

            # Delete older messages
            deleted = self.db.delete_messages_before(session_id, keep_boundary["message_id"])
            logger.info(f"Compressed {deleted} messages into summary for session {session_id}")
            return True

        except Exception as e:
            logger.warning(f"Compression failed for session {session_id}: {e} — will retry next message")
            return False

    @staticmethod
    def _format_conversation(messages: list[dict]) -> str:
        """Format messages as readable conversation text."""
        lines = []
        for msg in messages:
            role = msg["role"].upper()
            content = msg["content"]
            # Truncate very long messages
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough token estimate: ~4 chars per token."""
        return len(text) // 4
