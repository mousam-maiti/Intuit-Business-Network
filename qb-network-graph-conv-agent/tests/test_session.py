"""Tests for SessionManager."""
import pytest


class TestSessionManager:
    def test_create_session(self, session_mgr):
        session = session_mgr.get_or_create_session("s-1", "user-1")
        assert session["session_id"] == "s-1"
        assert session["user_id"] == "user-1"
        assert session["status"] == "active"
        assert session["message_count"] == 0

    def test_get_existing_session(self, session_mgr):
        session_mgr.get_or_create_session("s-1", "user-1")
        session = session_mgr.get_or_create_session("s-1", "user-1")
        assert session["session_id"] == "s-1"

    def test_save_user_message(self, session_mgr):
        session_mgr.get_or_create_session("s-1", "user-1")
        msg_id = session_mgr.save_user_message("s-1", "Hello")
        assert msg_id  # UUID string
        messages = session_mgr.get_session_messages("s-1")
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"

    def test_save_assistant_message(self, session_mgr):
        session_mgr.get_or_create_session("s-1", "user-1")
        msg_id = session_mgr.save_assistant_message("s-1", "Hi there!", {"tool_count": 2})
        assert msg_id
        messages = session_mgr.get_session_messages("s-1")
        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"

    def test_message_count_increments(self, session_mgr):
        session_mgr.get_or_create_session("s-1", "user-1")
        session_mgr.save_user_message("s-1", "msg 1")
        session_mgr.save_assistant_message("s-1", "reply 1")
        session_mgr.save_user_message("s-1", "msg 2")
        session = session_mgr.get_session("s-1")
        assert session["message_count"] == 3

    def test_clear_session_context(self, session_mgr):
        session_mgr.get_or_create_session("s-1", "user-1")
        session_mgr.save_user_message("s-1", "msg")
        session_mgr.save_assistant_message("s-1", "reply")
        session_mgr.clear_session_context("s-1")
        session = session_mgr.get_session("s-1")
        assert session["message_count"] == 0
        assert session_mgr.get_session_messages("s-1") == []

    def test_archive_session(self, session_mgr):
        session_mgr.get_or_create_session("s-1", "user-1")
        session_mgr.archive_session("s-1")
        session = session_mgr.get_session("s-1")
        assert session["status"] == "archived"

    def test_list_user_sessions(self, session_mgr):
        session_mgr.get_or_create_session("s-1", "user-1")
        session_mgr.get_or_create_session("s-2", "user-1")
        session_mgr.get_or_create_session("s-3", "user-2")
        sessions = session_mgr.list_user_sessions("user-1")
        assert len(sessions) == 2
        assert all(s["user_id"] == "user-1" for s in sessions)

    def test_list_excludes_archived(self, session_mgr):
        session_mgr.get_or_create_session("s-1", "user-1")
        session_mgr.get_or_create_session("s-2", "user-1")
        session_mgr.archive_session("s-1")
        sessions = session_mgr.list_user_sessions("user-1")
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "s-2"

    def test_update_title(self, session_mgr):
        session_mgr.get_or_create_session("s-1", "user-1")
        session_mgr.update_title("s-1", "My Chat")
        session = session_mgr.get_session("s-1")
        assert session["title"] == "My Chat"

    def test_get_recent_messages(self, session_mgr):
        session_mgr.get_or_create_session("s-1", "user-1")
        for i in range(10):
            session_mgr.save_user_message("s-1", f"msg {i}")
        recent = session_mgr.get_recent_messages("s-1", limit=3)
        assert len(recent) == 3
        assert recent[0]["content"] == "msg 7"
        assert recent[2]["content"] == "msg 9"
