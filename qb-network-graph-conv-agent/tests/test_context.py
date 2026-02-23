"""Tests for ContextWindow."""
import pytest


class TestContextWindow:
    def test_assemble_empty_session(self, context_window, mock_db):
        mock_db.create_session("s-1", "user-1")
        session = mock_db.get_session("s-1")
        history = context_window.assemble_context(session, "Hello")
        assert history == []

    def test_assemble_with_messages(self, context_window, mock_db):
        mock_db.create_session("s-1", "user-1")
        mock_db.add_message("m1", "s-1", "user", "Hi")
        mock_db.add_message("m2", "s-1", "assistant", "Hello!")
        mock_db.add_message("m3", "s-1", "user", "How are you?")

        session = mock_db.get_session("s-1")
        history = context_window.assemble_context(session, "New msg")

        assert len(history) == 3  # keep_recent=3
        assert history[0]["role"] == "user"
        assert history[0]["parts"] == ["Hi"]
        assert history[1]["role"] == "model"
        assert history[2]["role"] == "user"

    def test_assemble_with_summary(self, context_window, mock_db):
        mock_db.create_session("s-1", "user-1")
        mock_db.update_session("s-1", context_summary="Previous: discussed entity gr-001")
        mock_db.add_message("m1", "s-1", "user", "Latest question")

        session = mock_db.get_session("s-1")
        history = context_window.assemble_context(session, "New msg")

        # Should have summary pair + 1 message = 3
        assert len(history) == 3
        assert "Previous conversation summary" in history[0]["parts"][0]
        assert history[1]["role"] == "model"
        assert history[2]["parts"] == ["Latest question"]

    def test_assemble_respects_keep_recent(self, context_window, mock_db):
        mock_db.create_session("s-1", "user-1")
        for i in range(10):
            role = "user" if i % 2 == 0 else "assistant"
            mock_db.add_message(f"m{i}", "s-1", role, f"msg {i}")

        session = mock_db.get_session("s-1")
        history = context_window.assemble_context(session, "New msg")

        # keep_recent=3 so only last 3 messages
        assert len(history) == 3

    def test_no_compression_below_threshold(self, context_window, mock_db):
        mock_db.create_session("s-1", "user-1")
        for i in range(5):
            mock_db.add_message(f"m{i}", "s-1", "user", f"msg {i}")
        mock_db._sessions["s-1"]["message_count"] = 5

        session = mock_db.get_session("s-1")
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            context_window.maybe_compress(session, "gemini-2.5-flash")
        )
        assert result is False

    def test_estimate_tokens(self):
        from chat.context import ContextWindow
        assert ContextWindow.estimate_tokens("a" * 100) == 25
        assert ContextWindow.estimate_tokens("") == 0
