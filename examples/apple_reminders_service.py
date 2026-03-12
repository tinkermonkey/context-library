#!/usr/bin/env python3
"""Launch Apple Reminders adapter as HTTP service for remote access.

This standalone service script exposes Apple Reminders as an HTTP endpoint,
enabling remote systems to fetch reminders without copying the service code.

The service communicates with a local macOS helper service (running on
127.0.0.1:7123) that provides access to Apple EventKit Reminders data.

Usage:
    export ADAPTER_API_KEY='your-strong-api-key'
    python apple_reminders_service.py

Configuration:
    Edit HELPER_URL, ACCOUNT_ID, BIND_HOST, and BIND_PORT below. Set
    ADAPTER_API_KEY via environment variable for security.

Example:
    export ADAPTER_API_KEY='my-secret-key'
    python apple_reminders_service.py
    # Service will be available at http://mac.local:8002

    # Test from remote machine
    curl http://mac.local:8002/health
    curl -X POST http://mac.local:8002/fetch \\
        -H "Authorization: Bearer my-secret-key" \\
        -H "Content-Type: application/json" \\
        -d '{"source_ref": ""}'
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
    """Start the Apple Reminders adapter HTTP service."""
    setup_logging()

    # Import here to provide better error messages if dependencies are missing
    try:
        from context_library.adapters import AppleRemindersAdapter
    except ImportError as e:
        print(
            f"Error: Failed to import AppleRemindersAdapter: {e}",
            file=sys.stderr,
        )
        print(
            "Install with: pip install context-library[apple-reminders]",
            file=sys.stderr,
        )
        sys.exit(1)

    # Configuration
    HELPER_URL = "http://127.0.0.1:7123"
    ACCOUNT_ID = "default"
    LIST_NAME = None  # Set to a list name to filter (e.g., "Inbox")
    BIND_HOST = "0.0.0.0"  # Accept remote connections
    BIND_PORT = 8002

    # Get API key from environment variable
    api_key = get_api_key()

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

    # Build extra info dict
    extra_info = {
        "Helper service": HELPER_URL,
        "Account": ACCOUNT_ID,
    }
    if LIST_NAME:
        extra_info["Filter"] = f"List = {LIST_NAME}"

    # Print startup info before attempting to start server
    print_startup_info(
        "Apple Reminders adapter service",
        BIND_HOST,
        BIND_PORT,
        bool(api_key),
        extra_info,
    )

    # Run the service
    run_service(adapter, BIND_HOST, BIND_PORT, api_key)


if __name__ == "__main__":
    main()
