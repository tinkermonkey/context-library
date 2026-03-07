"""Fixtures and configuration for adapter tests."""

import sys
from unittest.mock import MagicMock

import httpx
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


class MockResponse:
    """Mock httpx.Response for testing."""

    def __init__(self, json_data, status_code=200, url="", text=""):
        self._json_data = json_data
        self.status_code = status_code
        self.url = url
        self.text = text if text else str(json_data)

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=None,
                response=self,
            )


@pytest.fixture
def mock_httpx_client(monkeypatch):
    """Fixture for mocking httpx.Client with request tracking.

    Provides a MockClient instance that can be configured with responses
    and tracks all requests made.
    """

    class MockClient:
        """Mock httpx.Client that tracks requests and returns configured responses."""
        def __init__(self, *args, **kwargs):
            self.requests = []
            self.responses = {}
            self.timeout = kwargs.get("timeout")

        def get(self, url, params=None, headers=None, timeout=None):
            self.requests.append({"url": url, "params": params, "headers": headers})
            (url, tuple(sorted(params.items())) if params else ())
            return self.responses.get(url, MockResponse({}, url=url))

        def set_response(self, url, data, status_code=200):
            self.responses[url] = MockResponse(data, status_code, url=url)

        def close(self):
            """No-op for mock client."""
            pass

    mock_client = MockClient()

    monkeypatch.setattr(
        "context_library.adapters.apple_reminders.httpx.Client",
        lambda *args, **kwargs: mock_client
    )

    return mock_client


@pytest.fixture
def mock_httpx_get(monkeypatch):
    """Fixture for mocking httpx.get() function with request tracking.

    Provides a MockHTTPXGet instance that can be configured with responses
    and tracks all requests made. Used for adapters that call httpx.get()
    directly instead of using httpx.Client().
    """

    class MockHTTPXGet:
        """Mock httpx.get that tracks requests and returns configured responses."""
        def __init__(self):
            self.requests = []
            self.responses = {}

        def __call__(self, url, params=None, headers=None, timeout=None):
            self.requests.append({"url": url, "params": params, "headers": headers})
            return self.responses.get(url, MockResponse({}, url=url))

        def set_response(self, url, data, status_code=200):
            self.responses[url] = MockResponse(data, status_code, url=url)

    mock_get = MockHTTPXGet()

    monkeypatch.setattr(
        "context_library.adapters.apple_health.httpx.get",
        mock_get
    )

    return mock_get
