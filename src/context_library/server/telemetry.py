"""
OpenTelemetry setup for context-library.

Call setup(default_service_name) once at startup before handling any requests.
If OTEL_EXPORTER_OTLP_ENDPOINT is not set or OTEL_SDK_DISABLED=true, this is a
no-op and all tracing calls become no-ops via the OTEL API's built-in null provider.

Environment variables (standard OTEL):
  OTEL_EXPORTER_OTLP_ENDPOINT  — OTLP HTTP base URL (e.g. http://otel-collector:4318)
  OTEL_EXPORTER_OTLP_HEADERS   — Comma-separated auth headers (e.g. api-key=secret)
  OTEL_SERVICE_NAME             — Override the per-service default passed to setup()
  OTEL_RESOURCE_ATTRIBUTES      — Extra resource attrs (key=val,key=val)
  OTEL_SDK_DISABLED             — Set to "true" to disable all telemetry
"""

import logging
import os

log = logging.getLogger(__name__)

_configured = False


def setup(default_service_name: str) -> bool:
    """
    Initialize OTEL providers for traces, metrics, and logs.

    Returns True if telemetry was configured, False if disabled or endpoint missing.
    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _configured
    if _configured:
        return True

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint or os.getenv("OTEL_SDK_DISABLED", "").lower() == "true":
        return False

    # Set service name before Resource.create() so it picks up our default.
    if not os.getenv("OTEL_SERVICE_NAME"):
        os.environ["OTEL_SERVICE_NAME"] = default_service_name

    try:
        from opentelemetry import metrics, trace
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
    except ImportError as exc:
        log.warning("opentelemetry packages not installed — telemetry disabled: %s", exc)
        return False

    try:
        # Resource picks up OTEL_SERVICE_NAME and OTEL_RESOURCE_ATTRIBUTES from env.
        resource = Resource.create()

        # Traces — OTLPSpanExporter reads OTEL_EXPORTER_OTLP_ENDPOINT/HEADERS from env.
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(tracer_provider)

        # Metrics
        metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
        metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))

        # Logs — export Python logging records to the OTEL log backend.
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
        set_logger_provider(logger_provider)
        LoggingInstrumentor().instrument(set_logging_format=False, logger_provider=logger_provider)
    except Exception as exc:
        log.warning("OTEL SDK initialisation failed — telemetry disabled: %s", exc)
        return False

    _configured = True
    log.info(
        "OTEL telemetry configured: service=%s endpoint=%s",
        os.getenv("OTEL_SERVICE_NAME"),
        endpoint,
    )
    return True


def instrument_fastapi(app) -> None:
    """Auto-instrument a FastAPI app to create spans for each HTTP request."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        pass


def instrument_httpx() -> None:
    """Auto-instrument httpx to create spans for outbound HTTP calls."""
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
    except ImportError:
        pass
