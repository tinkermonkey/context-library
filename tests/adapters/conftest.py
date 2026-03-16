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
        """Mock httpx.Client that tracks requests and returns configured responses.

        Raises AssertionError if attempting to access a URL that hasn't been
        configured with set_response(), to catch tests that hit the wrong endpoint.
        """
        def __init__(self, *args, **kwargs):
            self.requests = []
            self.responses = {}
            self.timeout = kwargs.get("timeout")

        def get(self, url, params=None, headers=None, timeout=None):
            self.requests.append({"method": "GET", "url": url, "params": params, "headers": headers})
            if url not in self.responses:
                raise AssertionError(
                    f"MockClient.get() called with unconfigured URL: {url}. "
                    f"Configured URLs: {list(self.responses.keys())}. "
                    f"Did you call set_response() for this URL?"
                )
            return self.responses[url]

        def post(self, url, json=None, headers=None, timeout=None):
            self.requests.append({"method": "POST", "url": url, "json": json, "headers": headers})
            if url not in self.responses:
                raise AssertionError(
                    f"MockClient.post() called with unconfigured URL: {url}. "
                    f"Configured URLs: {list(self.responses.keys())}. "
                    f"Did you call set_response() for this URL?"
                )
            return self.responses[url]

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
    monkeypatch.setattr(
        "context_library.adapters.remote.httpx.Client",
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
            if url not in self.responses:
                configured_urls = list(self.responses.keys())
                raise AssertionError(
                    f"MockHTTPXGet: Unconfigured URL '{url}'\n"
                    f"Configured URLs: {configured_urls}\n"
                    f"Call set_response('{url}', data) to configure this URL."
                )
            return self.responses[url]

        def set_response(self, url, data, status_code=200):
            self.responses[url] = MockResponse(data, status_code, url=url)

    mock_get = MockHTTPXGet()

    monkeypatch.setattr(
        "context_library.adapters.apple_health.httpx.get",
        mock_get
    )

    return mock_get


@pytest.fixture
def mock_all_health_endpoints(mock_httpx_get):
    """Fixture that configures all Apple Health endpoints with empty responses.

    Convenience fixture for tests that want to mock all health endpoints
    and only override the ones they care about.
    """
    base_url = "http://127.0.0.1:7124"
    endpoints = ["/workouts", "/sleep", "/activity", "/hrv", "/spo2", "/mindfulness", "/heart_rate"]

    for endpoint in endpoints:
        mock_httpx_get.set_response(f"{base_url}{endpoint}", [])

    return mock_httpx_get


@pytest.fixture
def mock_caldav_client():
    """Mock CalDAV client and related objects.

    Provides a tuple of (mock_client, mock_calendar) for testing CalDAV adapters.
    """
    # Create mock calendar
    mock_calendar = MagicMock()
    mock_calendar.name = "Default"

    # Create mock principal
    mock_principal = MagicMock()
    mock_principal.calendars.return_value = [mock_calendar]

    # Create mock client
    mock_client = MagicMock()
    mock_client.principal.return_value = mock_principal

    return mock_client, mock_calendar


@pytest.fixture
def mock_oura_httpx_get(monkeypatch):
    """Fixture for mocking httpx.get() function for Oura endpoints with request tracking.

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
            if url not in self.responses:
                configured_urls = list(self.responses.keys())
                raise AssertionError(
                    f"MockHTTPXGet: Unconfigured URL '{url}'\n"
                    f"Configured URLs: {configured_urls}\n"
                    f"Call set_response('{url}', data) to configure this URL."
                )
            return self.responses[url]

        def set_response(self, url, data, status_code=200):
            self.responses[url] = MockResponse(data, status_code, url=url)

    mock_get = MockHTTPXGet()

    monkeypatch.setattr(
        "context_library.adapters.oura.httpx.get",
        mock_get
    )

    return mock_get


@pytest.fixture
def mock_all_oura_endpoints(mock_oura_httpx_get):
    """Fixture that configures all Oura endpoints with empty responses.

    Convenience fixture for tests that want to mock all Oura endpoints
    and only override the ones they care about.
    """
    base_url = "http://localhost:8000"
    endpoints = ["/oura/sleep", "/oura/readiness", "/oura/activity", "/oura/workouts",
                 "/oura/spo2", "/oura/tags", "/oura/sessions", "/oura/heart_rate"]

    for endpoint in endpoints:
        mock_oura_httpx_get.set_response(f"{base_url}{endpoint}", [])

    return mock_oura_httpx_get


@pytest.fixture
def mock_apple_music_library_client(monkeypatch):
    """Fixture for mocking httpx.Client for Apple Music Library endpoints with request tracking.

    Provides a MockClient instance that can be configured with responses
    and tracks all requests made. Used for AppleMusicLibraryAdapter.
    """

    class MockClient:
        """Mock httpx.Client that tracks requests and returns configured responses."""
        def __init__(self, *args, **kwargs):
            self.requests = []
            self.responses = {}
            self.timeout = kwargs.get("timeout")

        def get(self, url, params=None, headers=None, timeout=None):
            self.requests.append({"method": "GET", "url": url, "params": params, "headers": headers})
            if url not in self.responses:
                raise AssertionError(
                    f"MockClient.get() called with unconfigured URL: {url}. "
                    f"Configured URLs: {list(self.responses.keys())}. "
                    f"Did you call set_response() for this URL?"
                )
            return self.responses[url]

        def set_response(self, url, data, status_code=200):
            self.responses[url] = MockResponse(data, status_code, url=url)

        def close(self):
            """No-op for mock client."""
            pass

    mock_client = MockClient()

    monkeypatch.setattr(
        "context_library.adapters.apple_music_library.httpx.Client",
        lambda *args, **kwargs: mock_client
    )

    return mock_client


@pytest.fixture
def mock_apple_music_library_endpoints(mock_apple_music_library_client):
    """Fixture that configures Apple Music Library endpoint with empty response.

    Convenience fixture for tests that want to mock the Apple Music Library endpoint
    and only override the ones they care about.
    """
    base_url = "http://127.0.0.1:7123"
    endpoints = ["/tracks"]

    for endpoint in endpoints:
        mock_apple_music_library_client.set_response(f"{base_url}{endpoint}", [])

    return mock_apple_music_library_client
