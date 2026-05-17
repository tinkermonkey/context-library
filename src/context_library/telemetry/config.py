"""Telemetry configuration loaded from environment variables."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class TelemetryConfig(BaseSettings):
    """Configuration for the OTLP telemetry subsystem.

    All settings can be overridden via environment variables prefixed with CTX_.
    For example, CTX_OTEL_ENABLED=true.
    """

    model_config = SettingsConfigDict(env_prefix="CTX_", env_file=".env", env_file_encoding="utf-8")

    # Master kill switch: if false, no providers are created, no exporters are initialized
    otel_enabled: bool = False

    # OTLP collector endpoint (e.g., http://localhost:4317)
    # If unset, setup_telemetry() returns early (no-op)
    otlp_endpoint: str = ""

    # OTLP transport protocol: "grpc" (default) or "http/protobuf"
    otlp_protocol: Literal["grpc", "http/protobuf"] = "grpc"

    # Service name exported in the OTLP Resource
    otel_service_name: str = "context-library"

    # Deployment environment exported in the OTLP Resource
    otel_environment: str = "production"
