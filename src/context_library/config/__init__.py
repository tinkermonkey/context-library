"""Configuration layer for declarative adapter configuration.

This package provides Pydantic models and loaders for configuring adapters
via YAML/TOML/JSON files instead of direct Python instantiation.

Example usage:

    from context_library.config import load_adapters_from_file

    adapters = load_adapters_from_file("config/adapters.yaml")

Main exports:
- load_adapters_from_file(): Load and instantiate adapters from config file
- AdaptersConfig: Pydantic model for complete adapter configuration
- RemoteAdapterConfig: Pydantic model for remote adapter configuration
- LocalAdapterConfig: Pydantic model for local adapter configuration
"""

from context_library.config.loader import load_adapters_from_file
from context_library.config.models import (
    AdaptersConfig,
    LocalAdapterConfig,
    RemoteAdapterConfig,
)

__all__ = [
    "load_adapters_from_file",
    "AdaptersConfig",
    "RemoteAdapterConfig",
    "LocalAdapterConfig",
]
