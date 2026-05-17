"""Tests for the telemetry subsystem."""

import logging

import pytest

from context_library.telemetry import setup_telemetry, shutdown_telemetry
from context_library.telemetry.config import TelemetryConfig


@pytest.fixture(autouse=True)
def reset_telemetry_state():
    """Reset telemetry module state before and after each test."""
    import context_library.telemetry as tel_module

    tel_module._tracer_provider = None
    tel_module._logger_provider = None
    tel_module._logging_handler = None
    yield
    tel_module._tracer_provider = None
    tel_module._logger_provider = None
    tel_module._logging_handler = None


def test_setup_telemetry_disabled_by_default():
    """When CTX_OTEL_ENABLED is unset, setup_telemetry returns (None, None)."""
    config = TelemetryConfig(otel_enabled=False)
    tp, lp = setup_telemetry(config=config)
    assert tp is None
    assert lp is None


def test_setup_telemetry_no_op_without_endpoint():
    """When CTX_OTLP_ENDPOINT is unset, setup_telemetry returns (None, None) even if enabled."""
    config = TelemetryConfig(otel_enabled=True, otlp_endpoint="")
    tp, lp = setup_telemetry(config=config)
    assert tp is None
    assert lp is None


def test_setup_telemetry_idempotent():
    """Calling setup_telemetry twice returns the same providers (guard against double init)."""
    import context_library.telemetry as tel_module
    from unittest.mock import MagicMock

    # Simulate a provider already being initialized by setting it directly
    mock_provider = MagicMock()
    mock_logger_provider = MagicMock()
    tel_module._tracer_provider = mock_provider
    tel_module._logger_provider = mock_logger_provider

    config = TelemetryConfig(
        otel_enabled=True,
        otlp_endpoint="http://localhost:4317",
    )

    # Call setup_telemetry when providers already exist
    tp, lp = setup_telemetry(config=config)

    # Should return the existing providers without re-initializing
    assert tp is mock_provider
    assert lp is mock_logger_provider

    shutdown_telemetry()


def test_shutdown_telemetry_safe_when_not_initialized():
    """shutdown_telemetry is safe to call even if setup_telemetry was never called."""
    # Should not raise
    shutdown_telemetry()
