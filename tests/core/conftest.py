"""Shared fixtures for core tests."""

import sys
from unittest.mock import MagicMock

import pytest

# Mock html2text at session level before any imports
@pytest.fixture(scope="session", autouse=True)
def mock_html2text_module():
    """Mock html2text module to allow tests to run without the dependency."""
    if "html2text" not in sys.modules:
        mock_module = MagicMock()
        mock_module.HTML2Text = MagicMock
        sys.modules["html2text"] = mock_module
