"""Fixtures for domain tests."""

import pytest


# Import fixtures from adapters conftest to make them available in domain tests
# This allows domain integration tests to use adapter mocking fixtures
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


@pytest.fixture
def mock_apple_music_library_client(monkeypatch):
    """Fixture for mocking httpx.Client for Apple Music Library endpoints with request tracking.

    Provides a MockClient instance that can be configured with responses
    and tracks all requests made. Used for AppleMusicLibraryAdapter.
    """
    import httpx

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
