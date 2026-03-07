"""
OTEL Telemetry — traces and metrics for the Backend API.

Pipeline:
  BE (Python OTEL SDK)
    -> OTLP gRPC at localhost:4317
    -> OTEL Collector
    -> traces: Elasticsearch -> Kibana
    -> metrics: Prometheus :8889
"""
from __future__ import annotations
import os
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

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

_initialized = False
_tracer = None
_meter = None

# Metrics instruments
_request_duration = None
_query_counter = None
_error_counter = None


def setup(
    service_name: str = "qb-backend-api",
    otlp_endpoint: str | None = None,
    export_interval_ms: int = 15000,
) -> bool:
    global _initialized, _tracer, _meter
    global _request_duration, _query_counter, _error_counter

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

        # Tracing
        span_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)
        _tracer = trace.get_tracer(service_name, "1.0.0")

        # Metrics
        metric_exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
        metric_reader = PeriodicExportingMetricReader(
            metric_exporter, export_interval_millis=export_interval_ms,
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)
        _meter = metrics.get_meter(service_name, "1.0.0")

        # Logs — bridge Python logging to OTLP
        log_exporter = OTLPLogExporter(endpoint=endpoint, insecure=True)
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        set_logger_provider(logger_provider)
        otel_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
        logging.getLogger().addHandler(otel_handler)

        # Instruments
        _request_duration = _meter.create_histogram(
            name="be.request_duration_ms",
            description="API request duration in ms",
            unit="ms",
        )
        _query_counter = _meter.create_counter(
            name="be.queries",
            description="Database queries by type",
            unit="queries",
        )
        _error_counter = _meter.create_counter(
            name="be.errors",
            description="API errors by type",
            unit="errors",
        )

        _initialized = True
        logger.info(f"OTEL telemetry initialized -> {endpoint}")
        return True

    except Exception as e:
        logger.warning(f"OTEL setup failed ({e}) — telemetry disabled")
        _initialized = True
        return False


def instrument_app(app):
    """Instrument a FastAPI app with OTEL auto-instrumentation."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI OTEL instrumentation active")
    except ImportError:
        logger.debug("opentelemetry-instrumentation-fastapi not installed")


class _NoOpSpan:
    def set_attribute(self, key, value): pass
    def set_status(self, status): pass
    def record_exception(self, exc): pass
    def add_event(self, name, attributes=None): pass


@contextmanager
def span(name: str, attributes: dict | None = None):
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


def record_query(query_type: str, target: str = ""):
    if _query_counter:
        _query_counter.add(1, {"query_type": query_type, "target": target})


def record_error(error_type: str, endpoint: str = ""):
    if _error_counter:
        _error_counter.add(1, {"error_type": error_type, "endpoint": endpoint})
