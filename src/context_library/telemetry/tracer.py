"""Lazy OpenTelemetry tracer initialization with no-op fallback.

Provides get_tracer() function that safely returns a tracer even if opentelemetry-api
is not installed. This allows core modules to conditionally use telemetry without
making it a hard dependency.
"""

from contextlib import contextmanager
from enum import Enum
from typing import Any, Generator

_tracer_cache: dict[str, Any] = {}


class StatusCode(Enum):
    """No-op StatusCode for when OpenTelemetry is unavailable."""

    UNSET = 0
    OK = 1
    ERROR = 2


class NoOpSpan:
    """No-op context manager for when OpenTelemetry is unavailable."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __enter__(self) -> "NoOpSpan":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass

    def record_exception(self, exception: Exception) -> None:
        pass


class NoOpTracer:
    """No-op tracer that provides the minimal span interface."""

    def __init__(self, name: str) -> None:
        self.name = name

    @contextmanager
    def start_as_current_span(self, name: str) -> Generator[NoOpSpan, None, None]:
        """Context manager that yields a no-op span."""
        yield NoOpSpan(name)


def get_tracer(name: str) -> Any:
    """Get a tracer for the given module name.

    Returns an OpenTelemetry tracer if opentelemetry-api is installed,
    otherwise returns a no-op tracer that safely ignores all span operations.

    Args:
        name: Module name for the tracer (typically __name__).

    Returns:
        A tracer object with start_as_current_span() context manager support.
    """
    if name in _tracer_cache:
        return _tracer_cache[name]

    try:
        from opentelemetry import trace
        tracer: Any = trace.get_tracer(name)
    except ImportError:
        tracer = NoOpTracer(name)

    _tracer_cache[name] = tracer
    return tracer


def get_status_code() -> Any:
    """Get the StatusCode enum (real or no-op version).

    Returns the OpenTelemetry StatusCode if available, otherwise returns
    the no-op StatusCode defined in this module.
    """
    try:
        from opentelemetry.trace import StatusCode as OTLPStatusCode
        return OTLPStatusCode
    except ImportError:
        return StatusCode
