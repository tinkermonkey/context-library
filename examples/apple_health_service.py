#!/usr/bin/env python3
"""Launch Apple Health adapter as HTTP service for remote access.

This standalone service script exposes Apple HealthKit data as an HTTP endpoint,
enabling remote systems to fetch health and fitness data without copying the
service code.

The service communicates with a local macOS helper service (running on
127.0.0.1:7124) that provides access to Apple HealthKit data.

Usage:
    python apple_health_service.py

Configuration:
    Edit the helper_url, bind address, port, and api_key in the __main__ block.

Example:
    # Start service on all interfaces (remote access)
    python apple_health_service.py
    # Service will be available at http://mac.local:8003

    # Test from remote machine
    curl http://mac.local:8003/health
    curl -X POST http://mac.local:8003/fetch \\
        -H "Authorization: Bearer your-secure-api-key-here" \\
        -H "Content-Type: application/json" \\
        -d '{"source_ref": ""}'
"""

import sys
import logging


def main():
    """Start the Apple Health adapter HTTP service."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Import here to provide better error messages if dependencies are missing
    try:
        from context_library.adapters import AppleHealthAdapter
        from context_library.adapters.serve import serve_adapter
    except ImportError as e:
        print(
            f"Error: Failed to import required modules: {e}",
            file=sys.stderr,
        )
        print(
            "Install with: pip install context-library[apple-health]",
            file=sys.stderr,
        )
        sys.exit(1)

    # Configuration
    # ============
    # Update these values to match your environment

    # URL of the local macOS helper service that provides access to Apple HealthKit
    HELPER_URL = "http://127.0.0.1:7124"

    # Device identifier for the adapter
    DEVICE_ID = "default"

    # Optional: Filter to a specific activity type
    # Examples: "running", "cycling", "yoga", "mindfulness", etc.
    ACTIVITY_TYPE = None  # Set to filter by activity type

    BIND_HOST = "0.0.0.0"  # Accept remote connections
    BIND_PORT = 8003
    API_KEY = "your-secure-api-key-here"  # Change to a strong secret

    # Initialize adapter
    try:
        adapter = AppleHealthAdapter(
            api_url=HELPER_URL,
            device_id=DEVICE_ID,
            activity_type=ACTIVITY_TYPE,
        )
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to initialize AppleHealthAdapter: {e}", file=sys.stderr)
        sys.exit(1)

    # Start service
    print(f"Starting Apple Health adapter service...")
    print(f"Helper service: {HELPER_URL}")
    print(f"Device: {DEVICE_ID}")
    if ACTIVITY_TYPE:
        print(f"Filter: Activity type = {ACTIVITY_TYPE}")
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
