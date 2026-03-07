"""Fixtures and configuration for adapter tests."""

import sys
from unittest.mock import MagicMock

import pytest


class MockHTML2Text:
    """Mock html2text.HTML2Text class."""

    def __init__(self):
        self.ignore_links = False

    def handle(self, html: str) -> str:
        """Convert HTML to markdown (simple mock)."""
        # Simple conversion: strip HTML tags and preserve text content
        import re

        # Remove script and style elements
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)

        # Convert some common tags to markdown
        text = re.sub(r"<b>([^<]*)</b>", r"**\1**", text)
        text = re.sub(r"<i>([^<]*)</i>", r"*\1*", text)
        text = re.sub(r"<a[^>]*href=['\"]([^'\"]*)['\"][^>]*>([^<]*)</a>", r"[\2](\1)", text)

        # Remove remaining tags
        text = re.sub(r"<[^>]*>", "", text)

        # Clean up whitespace
        text = text.strip()

        return text


@pytest.fixture(scope="session", autouse=True)
def mock_html2text_module():
    """Mock html2text module to allow tests to run without the dependency."""
    if "html2text" not in sys.modules:
        mock_module = MagicMock()
        mock_module.HTML2Text = MockHTML2Text
        sys.modules["html2text"] = mock_module
