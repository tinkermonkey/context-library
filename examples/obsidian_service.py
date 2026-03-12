#!/usr/bin/env python3
"""Launch Obsidian adapter as HTTP service for remote access.

This standalone service script exposes an Obsidian vault as an HTTP endpoint,
enabling remote systems to fetch notes without copying the service code.

Usage:
    python obsidian_service.py

Configuration:
    Edit the vault_path, bind address, port, and api_key in the __main__ block.

Example:
    # Start service on all interfaces (remote access)
    python obsidian_service.py
    # Service will be available at http://mac.local:8001

    # Test from remote machine
    curl http://mac.local:8001/health
    curl -X POST http://mac.local:8001/fetch \\
        -H "Authorization: Bearer your-secure-api-key-here" \\
        -H "Content-Type: application/json" \\
        -d '{"source_ref": "Note Title"}'
"""

import sys
import logging
from pathlib import Path


def main():
    """Start the Obsidian adapter HTTP service."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Import here to provide better error messages if dependencies are missing
    try:
        from context_library.adapters import ObsidianAdapter
        from context_library.adapters.serve import serve_adapter
    except ImportError as e:
        print(
            f"Error: Failed to import required modules: {e}",
            file=sys.stderr,
        )
        print("Install with: pip install context-library[obsidian]", file=sys.stderr)
        sys.exit(1)

    # Configuration
    # ============
    # Update these values to match your environment

    VAULT_PATH = "/Users/me/Documents/Obsidian"
    BIND_HOST = "0.0.0.0"  # Accept remote connections
    BIND_PORT = 8001
    API_KEY = "your-secure-api-key-here"  # Change to a strong secret

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

    # Start service
    print(f"Starting Obsidian adapter service...")
    print(f"Vault: {vault_path}")
    print(f"Binding to: {BIND_HOST}:{BIND_PORT}")
    print(f"API authentication: {'Enabled' if API_KEY else 'Disabled'}")
    print(f"\nService ready. Press Ctrl+C to stop.")
    print(f"Health check: curl http://localhost:{BIND_PORT}/health")
    print(
        f"Fetch endpoint: curl -X POST http://localhost:{BIND_PORT}/fetch "
        f"-H 'Authorization: Bearer {API_KEY}' "
        f"-H 'Content-Type: application/json' "
        f"-d '{{\"source_ref\": \"Note Title\"}}'"
    )

    try:
        serve_adapter(
            adapter,
            host=BIND_HOST,
            port=BIND_PORT,
            api_key=API_KEY,
        )
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
