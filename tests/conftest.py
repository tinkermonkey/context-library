"""Root pytest configuration and fixtures."""

import gc
import time
import pytest


@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Ensure proper cleanup after each test to prevent resource leaks.

    Particularly important for:
    - FileSystemWatcher instances that hold inotify watches
    - Temporary directories that may hold open file handles
    """
    yield
    # Force garbage collection to ensure file handles and inotify watches are released
    # This helps prevent "inotify watch limit reached" errors in test_watching.py
    gc.collect()

    # Give the system time to release inotify resources
    time.sleep(0.02)
