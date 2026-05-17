"""Telemetry subsystem for OTLP instrumentation.

Provides setup_telemetry() and shutdown_telemetry() for programmatic SDK initialization
with gRPC as the default transport. Auto-instruments FastAPI and httpx.
Bridges Python logging into OTLP log events with trace context injection.
"""

import importlib.metadata
import logging
from typing import TYPE_CHECKING, Any, Optional

from context_library.telemetry.config import TelemetryConfig

if TYPE_CHECKING:
    from fastapi import FastAPI

_tracer_provider: Optional[Any] = None
_logger_provider: Optional[Any] = None
_logging_handler: Optional[Any] = None


def setup_telemetry(
    config: Optional[TelemetryConfig] = None,
    app: Optional["FastAPI"] = None,
) -> tuple[Optional[Any], Optional[Any]]:
    """Initialize the telemetry subsystem with TracerProvider and LoggerProvider.

    Sets up OTLP exporters (gRPC by default, HTTP/protobuf if configured),
    wires FastAPI and httpx auto-instrumentation, and attaches the Python logging bridge.

    Returns early (no-op) if CTX_OTEL_ENABLED is falsy or CTX_OTLP_ENDPOINT is unset.

    Args:
        config: TelemetryConfig instance. If None, loads from environment.
        app: FastAPI app instance to instrument. If provided, instrument_app() is called.

    Returns:
        Tuple of (tracer_provider, logger_provider). Both are None if telemetry is disabled.
    """
    global _tracer_provider, _logger_provider, _logging_handler

    # Guard against double initialization
    if _tracer_provider is not None:
        return _tracer_provider, _logger_provider

    if config is None:
        config = TelemetryConfig()

    # No-op: telemetry disabled or no endpoint configured
    if not config.otel_enabled or not config.otlp_endpoint:
        return None, None

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk._logs import LoggerProvider as OtelLoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk._logs import LoggingHandler

    # Get service version: use config override if provided, otherwise read from package metadata
    if config.otel_service_version:
        service_version = config.otel_service_version
    else:
        try:
            service_version = importlib.metadata.version("context-library")
        except importlib.metadata.PackageNotFoundError:
            service_version = "unknown"

    # Create OTLP Resource with service metadata
    resource = Resource.create({
        "service.name": config.otel_service_name,
        "service.version": service_version,
        "deployment.environment": config.otel_environment,
    })

    # Create OTLP span exporter based on protocol
    if config.otlp_protocol == "http/protobuf":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as HTTPOTLPSpanExporter
        span_exporter = HTTPOTLPSpanExporter(endpoint=config.otlp_endpoint)
    else:  # default: grpc
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as gRPCOTLPSpanExporter
        span_exporter = gRPCOTLPSpanExporter(endpoint=config.otlp_endpoint)

    # Create TracerProvider with BatchSpanProcessor
    _tracer_provider = TracerProvider(resource=resource)
    _tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(_tracer_provider)

    # Create OTLP log exporter based on protocol
    if config.otlp_protocol == "http/protobuf":
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter as HTTPOTLPLogExporter
        log_exporter = HTTPOTLPLogExporter(endpoint=config.otlp_endpoint)
    else:  # default: grpc
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter as gRPCOTLPLogExporter
        log_exporter = gRPCOTLPLogExporter(endpoint=config.otlp_endpoint)

    # Create LoggerProvider with BatchLogRecordProcessor
    _logger_provider = OtelLoggerProvider(resource=resource)
    _logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

    # Attach LoggingHandler to the context_library root logger
    # This bridges Python logging into OTLP log events with trace context injection
    _logging_handler = LoggingHandler(logger_provider=_logger_provider)
    context_library_logger = logging.getLogger("context_library")
    context_library_logger.addHandler(_logging_handler)

    # Wire FastAPI auto-instrumentation for the specific app instance
    if app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor().instrument_app(app)

    # Wire httpx auto-instrumentation with W3C Traceparent propagation (global)
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    HTTPXClientInstrumentor().instrument()

    return _tracer_provider, _logger_provider


def shutdown_telemetry() -> None:
    """Flush pending spans and logs, then shut down providers.

    Call this on server shutdown to ensure all telemetry is exported.
    Safe to call even if setup_telemetry() was never called.
    Exceptions during shutdown are logged but do not crash the shutdown sequence.
    """
    global _tracer_provider, _logger_provider, _logging_handler

    if _tracer_provider is not None:
        try:
            _tracer_provider.force_flush(timeout_millis=5000)
        except Exception as e:
            logging.getLogger(__name__).warning(
                "TracerProvider.force_flush() failed during shutdown (telemetry may be incomplete): %s",
                e
            )
        try:
            _tracer_provider.shutdown()
        except Exception as e:
            logging.getLogger(__name__).warning(
                "TracerProvider.shutdown() failed during shutdown: %s",
                e
            )
        _tracer_provider = None

    if _logger_provider is not None:
        try:
            _logger_provider.force_flush(timeout_millis=5000)
        except Exception as e:
            logging.getLogger(__name__).warning(
                "LoggerProvider.force_flush() failed during shutdown (telemetry may be incomplete): %s",
                e
            )
        try:
            _logger_provider.shutdown()
        except Exception as e:
            logging.getLogger(__name__).warning(
                "LoggerProvider.shutdown() failed during shutdown: %s",
                e
            )
        _logger_provider = None

    if _logging_handler is not None:
        try:
            _logging_handler.close()
        except Exception as e:
            logging.getLogger(__name__).warning(
                "LoggingHandler.close() failed during shutdown: %s",
                e
            )
        try:
            logging.getLogger("context_library").removeHandler(_logging_handler)
        except Exception as e:
            logging.getLogger(__name__).warning(
                "Failed to remove LoggingHandler during shutdown: %s",
                e
            )
        _logging_handler = None
