"""
OTEL Telemetry — traces, metrics, and instrumentation for the agent service.

Pipeline:
  Agent (Python OTEL SDK)
    → OTLP gRPC at localhost:4317
    → OTEL Collector (same one as CDC)
    → traces: Elasticsearch → Kibana
    → metrics: Prometheus :8889

Instruments:
  - Every POST /resolve gets a root span with child spans per MCP tool call
  - Histograms: resolution_duration_ms, step_duration_ms, candidate_count
  - Counters: resolution_decisions (MERGE/NEW/REVIEW), llm_calls, embedding_calls
  - Gauges: golden_record_count, pending_review_count
"""
from __future__ import annotations
import os
import logging
import time
from typing import Callable, Any
from functools import wraps
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# ── Try imports — graceful fallback if OTEL not installed ───
try:
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.trace import StatusCode, Status
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry._logs import set_logger_provider
    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False


# ── Singleton state ─────────────────────────────────────────
_initialized = False
_tracer = None
_meter = None

# Metrics instruments (initialized in setup())
_resolution_duration = None
_step_duration = None
_candidate_count_hist = None
_decision_counter = None
_llm_call_counter = None
_embedding_call_counter = None
_error_counter = None
_active_resolutions = None


def setup(
    service_name: str = "qb-entity-resolution-agent",
    otlp_endpoint: str | None = None,
    export_interval_ms: int = 15000,
) -> bool:
    """Initialize OTEL tracing + metrics. Call once at startup.

    Returns True if OTEL is active, False if falling back to no-op.
    """
    global _initialized, _tracer, _meter
    global _resolution_duration, _step_duration, _candidate_count_hist
    global _decision_counter, _llm_call_counter, _embedding_call_counter
    global _error_counter, _active_resolutions

    if _initialized:
        return HAS_OTEL

    endpoint = otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    if not HAS_OTEL:
        logger.warning("OTEL SDK not installed — telemetry disabled")
        _initialized = True
        return False

    try:
        resource = Resource.create({
            "service.name": service_name,
            "service.version": "1.0.0",
            "deployment.environment": os.environ.get("DEPLOYMENT_ENV", "local-dev"),
        })

        # ── Tracing ─────────────────────────────────────────
        span_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)
        _tracer = trace.get_tracer(service_name, "1.0.0")

        # ── Metrics ─────────────────────────────────────────
        metric_exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
        metric_reader = PeriodicExportingMetricReader(
            metric_exporter,
            export_interval_millis=export_interval_ms,
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)
        _meter = metrics.get_meter(service_name, "1.0.0")

        # ── Logs — bridge Python logging to OTLP ────────────
        log_exporter = OTLPLogExporter(endpoint=endpoint, insecure=True)
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        set_logger_provider(logger_provider)
        otel_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
        logging.getLogger().addHandler(otel_handler)

        # ── Create instruments ──────────────────────────────

        # Histograms
        _resolution_duration = _meter.create_histogram(
            name="resolution.duration_ms",
            description="Total resolution request duration in ms",
            unit="ms",
        )
        _step_duration = _meter.create_histogram(
            name="resolution.step_duration_ms",
            description="Per-step duration within resolution pipeline",
            unit="ms",
        )
        _candidate_count_hist = _meter.create_histogram(
            name="resolution.candidate_count",
            description="Number of candidates found per resolution",
            unit="candidates",
        )

        # Counters
        _decision_counter = _meter.create_counter(
            name="resolution.decisions",
            description="Resolution decisions by type",
            unit="decisions",
        )
        _llm_call_counter = _meter.create_counter(
            name="resolution.llm_calls",
            description="LLM API calls made",
            unit="calls",
        )
        _embedding_call_counter = _meter.create_counter(
            name="resolution.embedding_calls",
            description="Embedding API calls made",
            unit="calls",
        )
        _error_counter = _meter.create_counter(
            name="resolution.errors",
            description="Resolution errors by type",
            unit="errors",
        )

        # UpDown counter (gauge-like)
        _active_resolutions = _meter.create_up_down_counter(
            name="resolution.active",
            description="Currently active resolution requests",
            unit="requests",
        )

        _initialized = True
        logger.info(f"OTEL telemetry initialized → {endpoint}")
        return True

    except Exception as e:
        logger.warning(f"OTEL setup failed ({e}) — telemetry disabled")
        _initialized = True
        return False


# ── Tracer access ───────────────────────────────────────────

def get_tracer():
    """Get the OTEL tracer (or None if not available)."""
    return _tracer


@contextmanager
def span(name: str, attributes: dict | None = None):
    """Context manager for creating a traced span.

    Usage:
        with telemetry.span("find_candidates", {"buckets": 7}) as s:
            result = do_work()
            s.set_attribute("candidates_found", len(result))
    """
    if _tracer is None:
        yield _NoOpSpan()
        return

    with _tracer.start_as_current_span(name, attributes=attributes or {}) as s:
        try:
            yield s
        except Exception as e:
            s.set_status(Status(StatusCode.ERROR, str(e)))
            s.record_exception(e)
            raise


class _NoOpSpan:
    """No-op span when OTEL is not available."""
    def set_attribute(self, key, value): pass
    def set_status(self, status): pass
    def record_exception(self, exc): pass
    def add_event(self, name, attributes=None): pass


# ── Metric recording helpers ────────────────────────────────

def record_resolution_duration(duration_ms: float, decision: str, match_level: str = ""):
    """Record total resolution duration + increment decision counter."""
    attrs = {"decision": decision}
    if match_level:
        attrs["match_level"] = match_level

    if _resolution_duration:
        _resolution_duration.record(duration_ms, attrs)
    if _decision_counter:
        _decision_counter.add(1, attrs)


def record_step_duration(step_name: str, duration_ms: float, tool: str = ""):
    """Record per-step duration within the pipeline."""
    if _step_duration:
        _step_duration.record(duration_ms, {"step": step_name, "tool": tool})


def record_candidate_count(count: int):
    """Record how many candidates were found."""
    if _candidate_count_hist:
        _candidate_count_hist.record(count)


def record_llm_call(model: str = "", success: bool = True):
    if _llm_call_counter:
        _llm_call_counter.add(1, {"model": model, "success": str(success)})


def record_embedding_call(model: str = "", success: bool = True):
    if _embedding_call_counter:
        _embedding_call_counter.add(1, {"model": model, "success": str(success)})


def record_error(error_type: str, step: str = ""):
    if _error_counter:
        _error_counter.add(1, {"error_type": error_type, "step": step})


def inc_active():
    if _active_resolutions:
        _active_resolutions.add(1)


def dec_active():
    if _active_resolutions:
        _active_resolutions.add(-1)


# ── Decorator for MCP tool instrumentation ──────────────────

def traced_tool(tool_name: str):
    """Decorator that wraps an MCP tool call with a child span + step metric.

    Usage:
        @traced_tool("find_candidates")
        def find_candidates(self, ...):
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs) -> Any:
            start = time.time()
            with span(f"mcp.{tool_name}") as s:
                try:
                    result = fn(*args, **kwargs)
                    elapsed = int((time.time() - start) * 1000)
                    s.set_attribute("duration_ms", elapsed)
                    record_step_duration(tool_name, elapsed, tool=tool_name)
                    return result
                except Exception as e:
                    elapsed = int((time.time() - start) * 1000)
                    record_step_duration(tool_name, elapsed, tool=tool_name)
                    record_error(type(e).__name__, step=tool_name)
                    raise
        return wrapper
    return decorator
