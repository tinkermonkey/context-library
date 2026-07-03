"""Telemetry subsystem for OTLP instrumentation.

Provides setup_telemetry() and shutdown_telemetry() for programmatic SDK initialization
with gRPC as the default transport. Auto-instruments FastAPI, httpx, and sqlite3.
Bridges Python logging into OTLP log events with trace context injection.

Public API:
  get_tracer(name)         — Returns an OTel tracer (no-op if OTel not installed)
  get_meter(name)          — Returns an OTel meter (no-op if OTel not installed)
  capture_context()        — Snapshot OTel context for cross-thread propagation
  run_in_context(ctx)      — Context manager to re-attach a captured context
  setup_telemetry(...)     — Initialize providers and wire auto-instrumentation
  shutdown_telemetry()     — Flush and shut down all providers
"""

import contextlib
import importlib.metadata
import logging
from typing import TYPE_CHECKING, Any, Generator, Optional

from context_library.telemetry.config import TelemetryConfig
from context_library.telemetry.tracer import get_tracer as get_tracer, NoOpTracer as NoOpTracer, NoOpSpan as NoOpSpan

if TYPE_CHECKING:
    from fastapi import FastAPI

_tracer_provider: Optional[Any] = None
_logger_provider: Optional[Any] = None
_logging_handler: Optional[Any] = None
_meter_provider: Optional[Any] = None


# ---------------------------------------------------------------------------
# No-op meter (fallback when opentelemetry-api is not installed)
# ---------------------------------------------------------------------------

class _NoOpInstrument:
    def add(self, amount: float, attributes: Optional[dict] = None) -> None:
        pass

    def record(self, amount: float, attributes: Optional[dict] = None) -> None:
        pass


class _NoOpMeter:
    def create_counter(self, name: str, **kwargs: Any) -> _NoOpInstrument:
        return _NoOpInstrument()

    def create_histogram(self, name: str, **kwargs: Any) -> _NoOpInstrument:
        return _NoOpInstrument()

    def create_up_down_counter(self, name: str, **kwargs: Any) -> _NoOpInstrument:
        return _NoOpInstrument()

    def create_observable_gauge(self, name: str, **kwargs: Any) -> _NoOpInstrument:
        return _NoOpInstrument()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_meter(name: str) -> Any:
    """Get a meter for the given module name.

    Uses the OTel API's proxy mechanism so meters obtained before
    setup_telemetry() is called are automatically upgraded once
    set_meter_provider() is invoked.  Falls back to _NoOpMeter if
    opentelemetry-api is not installed.
    """
    try:
        from opentelemetry import metrics as _metrics
        return _metrics.get_meter(name)
    except ImportError:
        return _NoOpMeter()


def capture_context() -> Any:
    """Snapshot the current OTel context for propagation to a background thread."""
    try:
        from opentelemetry import context as _ctx
        return _ctx.get_current()
    except ImportError:
        return None


@contextlib.contextmanager
def run_in_context(ctx: Any) -> Generator[None, None, None]:
    """Re-attach a captured OTel context inside a background thread."""
    if ctx is None:
        yield
        return
    try:
        from opentelemetry import context as _ctx
        token = _ctx.attach(ctx)
        try:
            yield
        finally:
            _ctx.detach(token)
    except ImportError:
        yield


# ---------------------------------------------------------------------------
# SDK setup / teardown
# ---------------------------------------------------------------------------

def setup_telemetry(
    config: Optional[TelemetryConfig] = None,
    app: Optional["FastAPI"] = None,
) -> tuple[Optional[Any], Optional[Any]]:
    """Initialize the telemetry subsystem.

    Sets up TracerProvider, LoggerProvider, and MeterProvider with OTLP exporters
    (gRPC by default, HTTP/protobuf if configured).  Wires FastAPI, httpx, and
    sqlite3 auto-instrumentation and attaches the Python logging bridge.

    Returns early (no-op) if CTX_OTEL_ENABLED is falsy or CTX_OTLP_ENDPOINT is unset.
    Safe to call multiple times — subsequent calls are no-ops (guarded by
    _tracer_provider sentinel).

    Args:
        config: TelemetryConfig instance. If None, loads from environment.
        app: FastAPI app instance. If provided, FastAPIInstrumentor is wired.

    Returns:
        Tuple of (tracer_provider, logger_provider). Both are None if disabled.
    """
    global _tracer_provider, _logger_provider, _logging_handler, _meter_provider

    if _tracer_provider is not None:
        return _tracer_provider, _logger_provider

    if config is None:
        config = TelemetryConfig()

    if not config.otel_enabled or not config.otlp_endpoint:
        return None, None

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
    from opentelemetry.sdk._logs import LoggerProvider as OtelLoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, LogRecordExporter
    from opentelemetry.sdk._logs import LoggingHandler

    # Service version: config override or package metadata
    if config.otel_service_version:
        service_version = config.otel_service_version
    else:
        try:
            service_version = importlib.metadata.version("context-library")
        except importlib.metadata.PackageNotFoundError:
            service_version = "unknown"

    resource = Resource.create({
        "service.name": config.otel_service_name,
        "service.version": service_version,
        "deployment.environment": config.otel_environment,
    })

    # --- Traces ---
    span_exporter: SpanExporter
    if config.otlp_protocol == "http/protobuf":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as HTTPOTLPSpanExporter
        span_exporter = HTTPOTLPSpanExporter(endpoint=config.otlp_endpoint)
    else:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as gRPCOTLPSpanExporter
        span_exporter = gRPCOTLPSpanExporter(endpoint=config.otlp_endpoint)

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))

    # --- Logs ---
    log_exporter: LogRecordExporter
    if config.otlp_protocol == "http/protobuf":
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter as HTTPOTLPLogExporter
        log_exporter = HTTPOTLPLogExporter(endpoint=config.otlp_endpoint)
    else:
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter as gRPCOTLPLogExporter
        log_exporter = gRPCOTLPLogExporter(endpoint=config.otlp_endpoint)

    logger_provider = OtelLoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

    logging_handler = LoggingHandler(logger_provider=logger_provider)
    logging_handler.setLevel(logging.INFO)

    # --- Metrics ---
    from opentelemetry import metrics as _otel_metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    if config.otlp_protocol == "http/protobuf":
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter as HTTPOTLPMetricExporter
        metric_exporter = HTTPOTLPMetricExporter(endpoint=config.otlp_endpoint)
    else:
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter as gRPCOTLPMetricExporter
        metric_exporter = gRPCOTLPMetricExporter(endpoint=config.otlp_endpoint)

    reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=15000)
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])

    # Commit to globals before wiring instrumentation so that any
    # re-entrant get_tracer()/get_meter() calls during instrumentation see
    # the providers already in place.
    _tracer_provider = tracer_provider
    _logger_provider = logger_provider
    _logging_handler = logging_handler
    _meter_provider = meter_provider

    trace.set_tracer_provider(_tracer_provider)
    _otel_metrics.set_meter_provider(_meter_provider)
    from opentelemetry._logs import set_logger_provider as _set_logger_provider
    _set_logger_provider(_logger_provider)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if _logging_handler not in root_logger.handlers:
        root_logger.addHandler(_logging_handler)

    # Uvicorn's dictConfig sets propagate=False on its own loggers, so records
    # from uvicorn never reach the root handler.  Attach directly to survive that.
    for _uvi_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        _uvi_logger = logging.getLogger(_uvi_name)
        if _logging_handler not in _uvi_logger.handlers:
            _uvi_logger.addHandler(_logging_handler)

    # --- FastAPI instrumentation ---
    if app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        def _auth_request_hook(span: Any, scope: Any) -> None:
            if span is not None and hasattr(span, "is_recording") and span.is_recording():
                headers = {k: v for k, v in scope.get("headers", [])}
                span.set_attribute("auth.present", b"authorization" in headers)

        FastAPIInstrumentor().instrument_app(app, server_request_hook=_auth_request_hook)

    # --- httpx instrumentation ---
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    HTTPXClientInstrumentor().instrument()

    # --- sqlite3 instrumentation ---
    try:
        from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor
        SQLite3Instrumentor().instrument()
    except ImportError:
        pass

    return _tracer_provider, _logger_provider


def shutdown_telemetry() -> None:
    """Flush pending spans, logs, and metrics, then shut down all providers.

    Safe to call even if setup_telemetry() was never called.
    Exceptions during shutdown are logged but do not propagate.
    """
    global _tracer_provider, _logger_provider, _logging_handler, _meter_provider

    if _tracer_provider is not None:
        try:
            _tracer_provider.force_flush(timeout_millis=5000)
        except Exception as e:
            logging.getLogger(__name__).warning(
                "TracerProvider.force_flush() failed during shutdown: %s", e
            )
        try:
            _tracer_provider.shutdown()
        except Exception as e:
            logging.getLogger(__name__).warning(
                "TracerProvider.shutdown() failed during shutdown: %s", e
            )
        _tracer_provider = None

    if _logger_provider is not None:
        try:
            _logger_provider.force_flush(timeout_millis=5000)
        except Exception as e:
            logging.getLogger(__name__).warning(
                "LoggerProvider.force_flush() failed during shutdown: %s", e
            )
        try:
            _logger_provider.shutdown()
        except Exception as e:
            logging.getLogger(__name__).warning(
                "LoggerProvider.shutdown() failed during shutdown: %s", e
            )
        _logger_provider = None

    if _logging_handler is not None:
        try:
            _logging_handler.close()
        except Exception as e:
            logging.getLogger(__name__).warning(
                "LoggingHandler.close() failed during shutdown: %s", e
            )
        try:
            logging.getLogger().removeHandler(_logging_handler)
        except Exception as e:
            logging.getLogger(__name__).warning(
                "Failed to remove LoggingHandler during shutdown: %s", e
            )
        _logging_handler = None

    if _meter_provider is not None:
        try:
            _meter_provider.force_flush(timeout_millis=5000)
        except Exception as e:
            logging.getLogger(__name__).warning(
                "MeterProvider.force_flush() failed during shutdown: %s", e
            )
        try:
            _meter_provider.shutdown()
        except Exception as e:
            logging.getLogger(__name__).warning(
                "MeterProvider.shutdown() failed during shutdown: %s", e
            )
        _meter_provider = None
