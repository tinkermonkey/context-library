"""Root pytest configuration and fixtures."""

import gc
import pytest


@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Ensure proper cleanup after each test to prevent resource leaks."""
    yield
    gc.collect()
