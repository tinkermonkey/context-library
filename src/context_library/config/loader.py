"""Configuration loader for adapter instantiation from YAML/TOML/JSON files.

This module provides functions to load adapter configurations from files
and instantiate BaseAdapter objects from declarative configuration.

Example usage:

    from context_library.config.loader import load_adapters_from_file

    adapters = load_adapters_from_file("config/adapters.yaml")
    for adapter in adapters:
        print(f"Loaded: {adapter.adapter_id}")
"""

import importlib
import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from context_library.adapters.base import BaseAdapter
from context_library.config.models import (
    AdaptersConfig,
    LocalAdapterConfig,
    RemoteAdapterConfig,
)

logger = logging.getLogger(__name__)

# Try to import optional YAML support
HAS_YAML = False
_YAML_IMPORT_ERROR: str | None = None

try:
    import yaml

    HAS_YAML = True
except ImportError as e:
    _YAML_IMPORT_ERROR = str(e)

# Try to import optional TOML support
HAS_TOML = False
_TOML_IMPORT_ERROR: str | None = None

try:
    import tomllib  # type: ignore[import-not-found]
    HAS_TOML = True
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[import-not-found]
        HAS_TOML = True
    except ImportError as e:
        _TOML_IMPORT_ERROR = str(e)


def load_adapters_from_file(config_path: str | Path) -> list[BaseAdapter]:
    """Load and instantiate adapters from a configuration file.

    Parses a YAML, TOML, or JSON configuration file and instantiates
    BaseAdapter objects according to the declarative configuration.

    Supports:
    - Remote adapters via RemoteAdapterConfig (instantiates RemoteAdapter)
    - Local adapters via LocalAdapterConfig (dynamically imports and instantiates)

    Args:
        config_path: Path to the configuration file (YAML, TOML, or JSON)

    Returns:
        List of instantiated BaseAdapter objects (RemoteAdapter and/or local adapters)

    Raises:
        FileNotFoundError: If config_path does not exist
        ValueError: If file format is not supported or config is invalid
        ValidationError: If configuration does not match expected schema
        ImportError: If required dependencies (httpx for RemoteAdapter) are missing
        Exception: If adapter instantiation fails

    Example:
        >>> adapters = load_adapters_from_file("config/adapters.yaml")
        >>> len(adapters)
        2
        >>> adapters[0].adapter_id
        'obsidian:vault'
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    # Determine file format and parse
    suffix = config_path.suffix.lower()

    if suffix in (".yaml", ".yml"):
        config_data = _parse_yaml(config_path)
    elif suffix == ".toml":
        config_data = _parse_toml(config_path)
    elif suffix == ".json":
        config_data = _parse_json(config_path)
    else:
        raise ValueError(
            f"Unsupported configuration file format: {suffix}. "
            "Supported formats: .yaml, .yml, .toml, .json"
        )

    # Parse and validate configuration
    try:
        config = AdaptersConfig(**config_data)
    except ValidationError as e:
        raise ValueError(
            f"Configuration validation failed: {e.error_count()} error(s)\n"
            f"{e}"
        ) from e

    # Instantiate adapters
    adapters = []

    # Instantiate remote adapters
    for remote_config in config.remote_adapters:
        adapter = _instantiate_remote_adapter(remote_config)
        adapters.append(adapter)
        logger.debug(
            f"Loaded RemoteAdapter: {adapter.adapter_id} -> {remote_config.service_url}"
        )

    # Instantiate local adapters
    for local_config in config.local_adapters:
        adapter = _instantiate_local_adapter(local_config)
        adapters.append(adapter)
        logger.debug(f"Loaded {local_config.adapter_type}: {adapter.adapter_id}")

    return adapters


def _parse_yaml(config_path: Path) -> dict[str, Any]:
    """Parse YAML configuration file.

    Args:
        config_path: Path to YAML file

    Returns:
        Parsed configuration as dict

    Raises:
        ImportError: If PyYAML is not installed
        Exception: If YAML parsing fails
    """
    if not HAS_YAML:
        raise ImportError(
            f"PyYAML is required to parse YAML files. "
            f"Install it with: pip install pyyaml. "
            f"Original error: {_YAML_IMPORT_ERROR}"
        )

    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)
            if data is None:
                return {}
            if not isinstance(data, dict):
                raise ValueError("YAML root must be a dict/object")
            return data
    except Exception as e:
        raise ValueError(f"Failed to parse YAML file {config_path}: {e}") from e


def _parse_toml(config_path: Path) -> dict[str, Any]:
    """Parse TOML configuration file.

    Args:
        config_path: Path to TOML file

    Returns:
        Parsed configuration as dict

    Raises:
        ImportError: If TOML parser is not available
        Exception: If TOML parsing fails
    """
    if not HAS_TOML:
        raise ImportError(
            f"tomllib (Python 3.11+) or tomli is required to parse TOML files. "
            f"For Python <3.11, install tomli with: pip install tomli. "
            f"Original error: {_TOML_IMPORT_ERROR}"
        )

    try:
        with open(config_path, "rb") as f:
            data: dict[str, Any] = tomllib.load(f)  # type: ignore[attr-defined]
            return data
    except Exception as e:
        raise ValueError(f"Failed to parse TOML file {config_path}: {e}") from e


def _parse_json(config_path: Path) -> dict[str, Any]:
    """Parse JSON configuration file.

    Args:
        config_path: Path to JSON file

    Returns:
        Parsed configuration as dict

    Raises:
        Exception: If JSON parsing fails
    """
    try:
        with open(config_path) as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("JSON root must be an object")
            return data
    except Exception as e:
        raise ValueError(f"Failed to parse JSON file {config_path}: {e}") from e


def _instantiate_remote_adapter(config: RemoteAdapterConfig) -> BaseAdapter:
    """Instantiate a RemoteAdapter from configuration.

    Args:
        config: RemoteAdapterConfig with service URL and parameters

    Returns:
        Instantiated RemoteAdapter

    Raises:
        ImportError: If httpx is not installed or RemoteAdapter cannot be imported
        Exception: If RemoteAdapter instantiation fails
    """
    try:
        from context_library.adapters.remote import RemoteAdapter
    except ImportError as e:
        raise ImportError(
            f"RemoteAdapter requires httpx. "
            f"Install it with: pip install httpx. "
            f"Original error: {e}"
        ) from e

    return RemoteAdapter(
        service_url=config.service_url,
        domain=config.domain,
        adapter_id=config.adapter_id,
        normalizer_version=config.normalizer_version,
        api_key=config.api_key,
        timeout=config.timeout,
    )


def _instantiate_local_adapter(config: LocalAdapterConfig) -> BaseAdapter:
    """Instantiate a local adapter from configuration.

    Dynamically imports the adapter class based on adapter_type and
    instantiates it with the provided configuration.

    Supported adapter_type values map to classes:
    - "filesystem" -> FilesystemAdapter
    - "obsidian" -> ObsidianAdapter
    - "obsidian_tasks" -> ObsidianTasksAdapter
    - "email" -> EmailAdapter
    - "caldav" -> CalDAVAdapter
    - "apple_reminders" -> AppleRemindersAdapter
    - "apple_health" -> AppleHealthAdapter
    - "apple_music_library" -> AppleMusicLibraryAdapter

    Args:
        config: LocalAdapterConfig with adapter type and parameters

    Returns:
        Instantiated adapter instance

    Raises:
        ValueError: If adapter_type is unknown or config format is invalid
        ImportError: If adapter class cannot be imported or dependencies are missing
        RuntimeError: If adapter instantiation fails

    Note:
        LocalAdapterConfig.domain and adapter_id are used for validation and
        identification within the configuration file. However, most local adapters
        derive their actual domain and adapter_id from their own configuration or
        hardcoded values (e.g., FilesystemAdapter hardcodes domain=DOCUMENTS).
        The config fields are not passed to the adapter constructor.
    """
    # Map adapter types to module paths and class names
    adapter_registry = {
        "filesystem": ("context_library.adapters.filesystem", "FilesystemAdapter"),
        "obsidian": ("context_library.adapters.obsidian", "ObsidianAdapter"),
        "obsidian_tasks": (
            "context_library.adapters.obsidian_tasks",
            "ObsidianTasksAdapter",
        ),
        "email": ("context_library.adapters.email", "EmailAdapter"),
        "caldav": ("context_library.adapters.caldav", "CalDAVAdapter"),
        "apple_reminders": (
            "context_library.adapters.apple_reminders",
            "AppleRemindersAdapter",
        ),
        "apple_health": (
            "context_library.adapters.apple_health",
            "AppleHealthAdapter",
        ),
        "apple_music": (
            "context_library.adapters.apple_music",
            "AppleMusicAdapter",
        ),
        "apple_music_library": (
            "context_library.adapters.apple_music_library",
            "AppleMusicLibraryAdapter",
        ),
    }

    if config.adapter_type not in adapter_registry:
        raise ValueError(
            f"Unknown adapter_type: {config.adapter_type!r}. "
            f"Supported types: {sorted(adapter_registry.keys())}"
        )

    module_path, class_name = adapter_registry[config.adapter_type]

    # Dynamically import the adapter class
    try:
        module = importlib.import_module(module_path)
        adapter_class = getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        raise ImportError(
            f"Failed to import {class_name} from {module_path}: {e}"
        ) from e

    # Pass only adapter-specific config parameters from config.config dict
    # Domain and adapter_id are typically properties of the adapter, not constructor args
    config_dict = config.config or {}

    try:
        adapter: BaseAdapter = adapter_class(**config_dict)
        logger.debug(
            f"Instantiated {class_name} with adapter_id={config.adapter_id} "
            f"(domain={config.domain})"
        )
        return adapter
    except Exception as e:
        raise RuntimeError(
            f"Failed to instantiate {class_name} with adapter_id={config.adapter_id}: {e}"
        ) from e
