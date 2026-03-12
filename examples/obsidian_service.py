#!/usr/bin/env python3
"""Launch Obsidian adapter as HTTP service for remote access.

This standalone service script exposes an Obsidian vault as an HTTP endpoint,
enabling remote systems to fetch notes without copying the service code.

Usage:
    export ADAPTER_API_KEY='your-strong-api-key'
    python obsidian_service.py

Configuration:
    Edit VAULT_PATH, BIND_HOST, and BIND_PORT below. Set ADAPTER_API_KEY via
    environment variable for security.

Example:
    export ADAPTER_API_KEY='my-secret-key'
    python obsidian_service.py
    # Service will be available at http://mac.local:8001

    # Test from remote machine
    curl http://mac.local:8001/health
    curl -X POST http://mac.local:8001/fetch \\
        -H "Authorization: Bearer my-secret-key" \\
        -H "Content-Type: application/json" \\
        -d '{"source_ref": "Note Title"}'
"""

import sys
from pathlib import Path

# Add parent directory to path to import shared utilities
sys.path.insert(0, str(Path(__file__).parent))
from _service_base import (
    setup_logging,
    get_api_key,
    print_startup_info,
    run_service,
)


def main():
    """Start the Obsidian adapter HTTP service."""
    setup_logging()

    # Import here to provide better error messages if dependencies are missing
    try:
        from context_library.adapters import ObsidianAdapter
    except ImportError as e:
        print(
            f"Error: Failed to import ObsidianAdapter: {e}",
            file=sys.stderr,
        )
        print("Install with: pip install context-library[obsidian]", file=sys.stderr)
        sys.exit(1)

    # Configuration
    VAULT_PATH = "/Users/me/Documents/Obsidian"
    BIND_HOST = "0.0.0.0"  # Accept remote connections
    BIND_PORT = 8001

    # Get API key from environment variable
    api_key = get_api_key()

    # Validate vault path exists
    vault_path = Path(VAULT_PATH).expanduser()
    if not vault_path.exists():
        print(
            f"Error: Vault path does not exist: {VAULT_PATH}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not vault_path.is_dir():
        print(
            f"Error: Vault path is not a directory: {VAULT_PATH}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Initialize adapter
    try:
        adapter = ObsidianAdapter(vault_path=str(vault_path))
    except Exception as e:
        print(f"Error: Failed to initialize ObsidianAdapter: {e}", file=sys.stderr)
        sys.exit(1)

    # Print startup info before attempting to start server
    print_startup_info(
        "Obsidian adapter service",
        BIND_HOST,
        BIND_PORT,
        bool(api_key),
        {"Vault": str(vault_path)},
    )

    # Run the service
    run_service(adapter, BIND_HOST, BIND_PORT, api_key)


if __name__ == "__main__":
    main()
