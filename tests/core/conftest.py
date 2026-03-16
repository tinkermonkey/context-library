"""Shared fixtures for core tests."""

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


class MockHTTPXGet:
    """Mock httpx.get that tracks requests and returns configured responses."""
    def __init__(self):
        self.requests = []
        self.responses = {}

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.requests.append({"url": url, "params": params, "headers": headers})
        if url not in self.responses:
            raise AssertionError(
                f"MockHTTPXGet: Unconfigured URL '{url}'\n"
                f"Configured URLs: {list(self.responses.keys())}"
            )
        return self.responses[url]

    def set_response(self, url, data, status_code=200):
        self.responses[url] = MockResponse(data, status_code, url=url)


@pytest.fixture
def mock_health_httpx_get(monkeypatch):
    """Fixture for mocking httpx.get() for Apple Health endpoints with request tracking."""
    mock_get = MockHTTPXGet()

    monkeypatch.setattr(
        "context_library.adapters.apple_health.httpx.get",
        mock_get
    )

    return mock_get


@pytest.fixture
def mock_oura_httpx_get(monkeypatch):
    """Fixture for mocking httpx.get() for Oura endpoints with request tracking."""
    mock_get = MockHTTPXGet()

    monkeypatch.setattr(
        "context_library.adapters.oura.httpx.get",
        mock_get
    )

    return mock_get


@pytest.fixture
def mock_all_health_endpoints_integration(mock_health_httpx_get):
    """Fixture that configures all Apple Health endpoints with empty responses for integration tests."""
    base_url = "http://127.0.0.1:7124"
    endpoints = ["/workouts", "/sleep", "/activity", "/hrv", "/spo2", "/mindfulness", "/heart_rate"]

    for endpoint in endpoints:
        mock_health_httpx_get.set_response(f"{base_url}{endpoint}", [])

    return mock_health_httpx_get


@pytest.fixture
def mock_all_oura_endpoints_integration(mock_oura_httpx_get):
    """Fixture that configures all Oura endpoints with empty responses for integration tests."""
    base_url = "http://localhost:8000"
    endpoints = ["/oura/sleep", "/oura/readiness", "/oura/activity", "/oura/workouts",
                 "/oura/spo2", "/oura/tags", "/oura/sessions", "/oura/heart_rate"]

    for endpoint in endpoints:
        mock_oura_httpx_get.set_response(f"{base_url}{endpoint}", [])

    return mock_oura_httpx_get
