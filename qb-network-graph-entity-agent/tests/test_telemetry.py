"""
Tests for utils/telemetry.py — no-op mode when OTEL not configured.
"""
import pytest
from utils.telemetry import (
    span, _NoOpSpan,
    record_resolution_duration, record_step_duration,
    record_candidate_count, record_llm_call,
    record_embedding_call, record_error,
    inc_active, dec_active,
    traced_tool,
)


# ══════════════════════════════════════════════════════════════
# TestNoOpMode
# ══════════════════════════════════════════════════════════════

class TestNoOpMode:
    def test_span_yields_noop(self):
        with span("test_span") as s:
            assert isinstance(s, _NoOpSpan)

    def test_set_attribute_noop(self):
        s = _NoOpSpan()
        s.set_attribute("key", "value")  # Should not raise

    def test_set_status_noop(self):
        s = _NoOpSpan()
        s.set_status("OK")  # Should not raise

    def test_record_exception_noop(self):
        s = _NoOpSpan()
        s.record_exception(RuntimeError("test"))  # Should not raise


# ══════════════════════════════════════════════════════════════
# TestMetricHelpers
# ══════════════════════════════════════════════════════════════

class TestMetricHelpers:
    def test_record_resolution_duration_noop(self):
        record_resolution_duration(100.0, "MERGE", "DETERMINISTIC")

    def test_record_step_duration_noop(self):
        record_step_duration("find_candidates", 50.0, "candidate_evaluator")

    def test_record_candidate_count_noop(self):
        record_candidate_count(5)

    def test_record_llm_call_noop(self):
        record_llm_call("gemini-2.5-pro", True)

    def test_record_embedding_call_noop(self):
        record_embedding_call("text-embedding-004", True)

    def test_record_error_noop(self):
        record_error("TimeoutError", "llm_reasoning")


# ══════════════════════════════════════════════════════════════
# TestTracedTool
# ══════════════════════════════════════════════════════════════

class TestTracedTool:
    def test_decorated_function_returns_result(self):
        @traced_tool("test_tool")
        def my_func(x, y):
            return x + y

        assert my_func(3, 4) == 7

    def test_exceptions_propagated(self):
        @traced_tool("failing_tool")
        def failing_func():
            raise ValueError("intentional error")

        with pytest.raises(ValueError, match="intentional error"):
            failing_func()
