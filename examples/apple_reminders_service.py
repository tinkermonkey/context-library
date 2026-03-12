#!/usr/bin/env python3
"""Launch Apple Reminders adapter as HTTP service for remote access.

This standalone service script exposes Apple Reminders as an HTTP endpoint,
enabling remote systems to fetch reminders without copying the service code.

The service communicates with a local macOS helper service (running on
127.0.0.1:7123) that provides access to Apple EventKit Reminders data.

Usage:
    python apple_reminders_service.py

Configuration:
    Edit the helper_url, bind address, port, and api_key in the __main__ block.

Example:
    # Start service on all interfaces (remote access)
    python apple_reminders_service.py
    # Service will be available at http://mac.local:8002

    # Test from remote machine
    curl http://mac.local:8002/health
    curl -X POST http://mac.local:8002/fetch \\
        -H "Authorization: Bearer your-secure-api-key-here" \\
        -H "Content-Type: application/json" \\
        -d '{"source_ref": ""}'
"""

import sys
import logging


def main():
    """Start the Apple Reminders adapter HTTP service."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Import here to provide better error messages if dependencies are missing
    try:
        from context_library.adapters import AppleRemindersAdapter
        from context_library.adapters.serve import serve_adapter
    except ImportError as e:
        print(
            f"Error: Failed to import required modules: {e}",
            file=sys.stderr,
        )
        print(
            "Install with: pip install context-library[apple-reminders]",
            file=sys.stderr,
        )
        sys.exit(1)

    # Configuration
    # ============
    # Update these values to match your environment

    # URL of the local macOS helper service that provides access to Apple EventKit
    HELPER_URL = "http://127.0.0.1:7123"

    # Account identifier for the adapter
    ACCOUNT_ID = "default"

    # Optional: Filter to a specific Reminders list
    LIST_NAME = None  # Set to a list name to filter (e.g., "Inbox")

    BIND_HOST = "0.0.0.0"  # Accept remote connections
    BIND_PORT = 8002
    API_KEY = "your-secure-api-key-here"  # Change to a strong secret

    # Initialize adapter
    try:
        adapter = AppleRemindersAdapter(
            api_url=HELPER_URL,
            account_id=ACCOUNT_ID,
            list_name=LIST_NAME,
        )
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to initialize AppleRemindersAdapter: {e}", file=sys.stderr)
        sys.exit(1)

    # Start service
    print(f"Starting Apple Reminders adapter service...")
    print(f"Helper service: {HELPER_URL}")
    print(f"Account: {ACCOUNT_ID}")
    if LIST_NAME:
        print(f"Filter: List = {LIST_NAME}")
    print(f"Binding to: {BIND_HOST}:{BIND_PORT}")
    print(f"API authentication: {'Enabled' if API_KEY else 'Disabled'}")
    print(f"\nService ready. Press Ctrl+C to stop.")
    print(f"Health check: curl http://localhost:{BIND_PORT}/health")
    print(
        f"Fetch endpoint: curl -X POST http://localhost:{BIND_PORT}/fetch "
        f"-H 'Authorization: Bearer {API_KEY}' "
        f"-H 'Content-Type: application/json' "
        f"-d '{{\"source_ref\": \"\"}}'"
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
