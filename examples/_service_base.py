"""Shared utilities for Mac-side adapter service scripts.

This module provides common setup and server startup logic for all adapter service
scripts, reducing code duplication while maintaining clear, independent examples.
"""

import sys
import os
import logging
from typing import Any


def setup_logging() -> None:
    """Configure logging for the service."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def get_api_key(placeholder: str = "your-secure-api-key-here") -> str:
    """Read and validate API key from environment or configuration.

    Args:
        placeholder: The placeholder value to detect (e.g., "your-secure-api-key-here")

    Returns:
        The API key string

    Raises:
        SystemExit: If API key is unset, is the placeholder, or is invalid
    """
    api_key = os.environ.get("ADAPTER_API_KEY", placeholder)

    if api_key == placeholder or not api_key:
        print(
            "Error: ADAPTER_API_KEY environment variable is not set or is the "
            "placeholder value.",
            file=sys.stderr,
        )
        print(
            "Set a strong API key via: export ADAPTER_API_KEY='<your-key-here>'",
            file=sys.stderr,
        )
        sys.exit(1)

    return api_key


def print_startup_info(
    service_name: str,
    bind_host: str,
    bind_port: int,
    api_key_enabled: bool,
    extra_info: dict[str, str] | None = None,
) -> None:
    """Print startup information for the service.

    Args:
        service_name: Name of the service (e.g., "Obsidian adapter service")
        bind_host: The host being bound to
        bind_port: The port being bound to
        api_key_enabled: Whether API authentication is enabled
        extra_info: Additional key-value pairs to display
    """
    print(f"Starting {service_name}...")
    if extra_info:
        for key, value in extra_info.items():
            print(f"{key}: {value}")
    print(f"Binding to: {bind_host}:{bind_port}")
    print(f"API authentication: {'Enabled' if api_key_enabled else 'Disabled'}")
    print("Starting server...")


def print_running_message(
    bind_port: int,
    api_key: str,
) -> None:
    """Print message indicating server is starting and show usage examples.

    Args:
        bind_port: The port the service will run on
        api_key: The API key for authentication
    """
    print()
    print("=" * 60)
    print("Service is starting. Press Ctrl+C to stop.")
    print("=" * 60)
    print(f"Health check: curl http://localhost:{bind_port}/health")
    print(
        f"Fetch endpoint: curl -X POST http://localhost:{bind_port}/fetch "
        f"-H 'Authorization: Bearer {api_key}' "
        f"-H 'Content-Type: application/json' "
        f"-d '{{\"source_ref\": \"<your-source-ref>\"}}'"
    )
    print()


def run_service(
    adapter: Any,
    host: str,
    port: int,
    api_key: str,
) -> None:
    """Run the adapter service with error handling.

    Note: This function blocks indefinitely while the server is running.

    Args:
        adapter: The initialized adapter instance
        host: Host to bind to
        port: Port to bind to
        api_key: API key for authentication

    Raises:
        SystemExit: On error or keyboard interrupt
    """
    try:
        from context_library.adapters.serve import serve_adapter
    except ImportError as e:
        print(f"Error: Failed to import serve_adapter: {e}", file=sys.stderr)
        sys.exit(1)

    print_running_message(port, api_key)

    try:
        serve_adapter(
            adapter,
            host=host,
            port=port,
            api_key=api_key,
        )
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
