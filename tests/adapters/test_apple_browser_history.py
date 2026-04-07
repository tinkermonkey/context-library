"""Tests for the AppleBrowserHistoryAdapter."""

import pytest

from context_library.adapters.apple_browser_history import AppleBrowserHistoryAdapter
from context_library.adapters.base import EndpointFetchError
from context_library.storage.models import Domain, PollStrategy, NormalizedContent


class TestAppleBrowserHistoryAdapterInitialization:
    """Tests for AppleBrowserHistoryAdapter initialization."""

    def test_init_default_parameters(self):
        """__init__ uses default parameters when not provided."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"
        assert adapter._api_key == "test-token"
        assert adapter._account_id == "default"

    def test_init_custom_parameters(self):
        """__init__ accepts and stores custom parameters."""
        adapter = AppleBrowserHistoryAdapter(
            api_url="http://localhost:8000",
            api_key="test_key",
            account_id="work",
        )
        assert adapter._api_url == "http://localhost:8000"
        assert adapter._api_key == "test_key"
        assert adapter._account_id == "work"

    def test_init_strips_trailing_slash_from_url(self):
        """__init__ strips trailing slash from api_url."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123/", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"

    def test_init_no_trailing_slash(self):
        """__init__ leaves api_url unchanged if no trailing slash."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"

    def test_init_requires_api_key(self):
        """__init__ raises ValueError when api_key is empty."""
        with pytest.raises(ValueError, match="api_key is required"):
            AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="")


class TestAppleBrowserHistoryAdapterProperties:
    """Tests for AppleBrowserHistoryAdapter properties."""

    def test_adapter_id_format_default(self):
        """adapter_id has correct format: apple_browser_history:{account_id}."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.adapter_id == "apple_browser_history:default"

    def test_adapter_id_format_custom_account(self):
        """adapter_id uses custom account_id."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token", account_id="work")
        assert adapter.adapter_id == "apple_browser_history:work"

    def test_domain_property(self):
        """domain property returns Domain.EVENTS."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.domain == Domain.EVENTS

    def test_poll_strategy_property(self):
        """poll_strategy property returns PollStrategy.PULL."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.poll_strategy == PollStrategy.PULL

    def test_normalizer_version_property(self):
        """normalizer_version property returns '1.0.0'."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.normalizer_version == "1.0.0"


class TestAppleBrowserHistoryAdapterFetch:
    """Tests for AppleBrowserHistoryAdapter.fetch() method."""

    def test_fetch_single_visit(self, mock_httpx_client_browser_history):
        """fetch() yields NormalizedContent for a single browser visit."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        # Mock visits response
        visits_url = "http://127.0.0.1:7123/browser/history"
        mock_httpx_client_browser_history.set_response(visits_url, [
            {
                "id": "visit-1",
                "url": "https://example.com/page1",
                "title": "Example Page",
                "visitedAt": "2026-03-10T10:00:00Z",
                "browser": "safari",
                "visitCount": 5,
            }
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 1
        assert isinstance(results[0], NormalizedContent)
        assert results[0].source_id == "browser_history/visit-1"
        # Markdown is minimal
        assert results[0].markdown == "Visited: https://example.com/page1"
        # Metadata and extra fields in extra_metadata
        assert results[0].structural_hints.extra_metadata["event_id"] == "visit-1"
        assert results[0].structural_hints.extra_metadata["title"] == "Example Page"
        assert results[0].structural_hints.extra_metadata["start_date"] == "2026-03-10T10:00:00Z"
        assert results[0].structural_hints.extra_metadata["date_first_observed"] == "2026-03-10T10:00:00Z"
        assert results[0].structural_hints.extra_metadata["source_type"] == "browser_history"
        assert results[0].structural_hints.extra_metadata["url"] == "https://example.com/page1"
        assert results[0].structural_hints.extra_metadata["browser"] == "safari"
        assert results[0].structural_hints.extra_metadata["visitCount"] == 5

    def test_fetch_visit_with_empty_title_uses_url_fallback(self, mock_httpx_client_browser_history):
        """fetch() uses URL as title when title is empty."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        visits_url = "http://127.0.0.1:7123/browser/history"
        mock_httpx_client_browser_history.set_response(visits_url, [
            {
                "id": "visit-2",
                "url": "https://example.com/page2",
                "title": "",
                "visitedAt": "2026-03-10T11:00:00Z",
                "browser": "firefox",
                "visitCount": 1,
            }
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 1
        # Title should be URL (fallback)
        assert results[0].structural_hints.extra_metadata["title"] == "https://example.com/page2"
        # Event ID should be the visit id
        assert results[0].structural_hints.extra_metadata["event_id"] == "visit-2"

    def test_fetch_visit_with_null_title_uses_url_fallback(self, mock_httpx_client_browser_history):
        """fetch() uses URL as title when title is null."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        visits_url = "http://127.0.0.1:7123/browser/history"
        mock_httpx_client_browser_history.set_response(visits_url, [
            {
                "id": "visit-3",
                "url": "https://example.com/page3",
                "title": None,
                "visitedAt": "2026-03-10T12:00:00Z",
                "browser": "chrome",
                "visitCount": 3,
            }
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 1
        # Title should be URL (fallback)
        assert results[0].structural_hints.extra_metadata["title"] == "https://example.com/page3"
        # Event ID should be the visit id
        assert results[0].structural_hints.extra_metadata["event_id"] == "visit-3"

    def test_fetch_multiple_visits(self, mock_httpx_client_browser_history):
        """fetch() yields multiple visits."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        visits_url = "http://127.0.0.1:7123/browser/history"
        mock_httpx_client_browser_history.set_response(visits_url, [
            {
                "id": "visit-1",
                "url": "https://example.com/page1",
                "title": "Page 1",
                "visitedAt": "2026-03-10T10:00:00Z",
                "browser": "safari",
                "visitCount": 2,
            },
            {
                "id": "visit-2",
                "url": "https://example.com/page2",
                "title": "Page 2",
                "visitedAt": "2026-03-10T11:00:00Z",
                "browser": "firefox",
                "visitCount": 1,
            },
            {
                "id": "visit-3",
                "url": "https://example.com/page3",
                "title": "Page 3",
                "visitedAt": "2026-03-10T12:00:00Z",
                "browser": "chrome",
                "visitCount": 3,
            },
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 3

    def test_fetch_incremental_with_since(self, mock_httpx_client_browser_history):
        """fetch() passes 'since' query parameter for incremental fetch."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        visits_url = "http://127.0.0.1:7123/browser/history"
        mock_httpx_client_browser_history.set_response(visits_url, [])

        list(adapter.fetch("2026-03-06T10:00:00Z"))

        # Verify the since parameter was sent
        assert len(mock_httpx_client_browser_history.requests) == 1
        request = mock_httpx_client_browser_history.requests[0]
        assert request["params"]["since"] == "2026-03-06T10:00:00Z"

    def test_fetch_without_since_parameter(self, mock_httpx_client_browser_history):
        """fetch() does not send 'since' parameter when source_ref is empty."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        visits_url = "http://127.0.0.1:7123/browser/history"
        mock_httpx_client_browser_history.set_response(visits_url, [])

        list(adapter.fetch(""))

        # Verify no since parameter was sent
        assert len(mock_httpx_client_browser_history.requests) == 1
        request = mock_httpx_client_browser_history.requests[0]
        assert "since" not in request["params"] or request["params"] == {}

    def test_fetch_sends_authorization_header(self, mock_httpx_client_browser_history):
        """fetch() sends Authorization header with Bearer token."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="secret-token-123")

        visits_url = "http://127.0.0.1:7123/browser/history"
        mock_httpx_client_browser_history.set_response(visits_url, [])

        list(adapter.fetch(""))

        # Verify the Authorization header was sent
        assert len(mock_httpx_client_browser_history.requests) == 1
        request = mock_httpx_client_browser_history.requests[0]
        assert request["headers"]["Authorization"] == "Bearer secret-token-123"

    def test_fetch_happy_path_event_metadata(self, mock_httpx_client_browser_history):
        """Happy path test: correct EventMetadata with title, start_date, and extra_metadata."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        visits_url = "http://127.0.0.1:7123/browser/history"
        mock_httpx_client_browser_history.set_response(visits_url, [
            {
                "id": "visit-1",
                "url": "https://example.com/article",
                "title": "My Article",
                "visitedAt": "2026-03-10T10:30:00Z",
                "browser": "safari",
                "visitCount": 7,
            }
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 1
        result = results[0]

        # Check EventMetadata fields
        metadata = result.structural_hints.extra_metadata
        assert metadata["event_id"] == "visit-1"
        assert metadata["title"] == "My Article"
        assert metadata["start_date"] == "2026-03-10T10:30:00Z"
        assert metadata["date_first_observed"] == "2026-03-10T10:30:00Z"
        assert metadata["source_type"] == "browser_history"

        # Check extra_metadata fields
        assert metadata["url"] == "https://example.com/article"
        assert metadata["browser"] == "safari"
        assert metadata["visitCount"] == 7

        # Check markdown
        assert result.markdown == "Visited: https://example.com/article"

    def test_fetch_all_browser_types(self, mock_httpx_client_browser_history):
        """fetch() handles all three browser types: safari, firefox, chrome."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        visits_url = "http://127.0.0.1:7123/browser/history"
        mock_httpx_client_browser_history.set_response(visits_url, [
            {
                "id": "visit-safari",
                "url": "https://example.com/safari",
                "title": "Safari Page",
                "visitedAt": "2026-03-10T10:00:00Z",
                "browser": "safari",
                "visitCount": 1,
            },
            {
                "id": "visit-firefox",
                "url": "https://example.com/firefox",
                "title": "Firefox Page",
                "visitedAt": "2026-03-10T11:00:00Z",
                "browser": "firefox",
                "visitCount": 2,
            },
            {
                "id": "visit-chrome",
                "url": "https://example.com/chrome",
                "title": "Chrome Page",
                "visitedAt": "2026-03-10T12:00:00Z",
                "browser": "chrome",
                "visitCount": 3,
            },
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 3

        browsers = [r.structural_hints.extra_metadata["browser"] for r in results]
        assert "safari" in browsers
        assert "firefox" in browsers
        assert "chrome" in browsers

    def test_fetch_error_response_not_list(self, mock_httpx_client_browser_history):
        """fetch() raises ValueError if API returns non-list response."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        visits_url = "http://127.0.0.1:7123/browser/history"
        mock_httpx_client_browser_history.set_response(visits_url, {"error": "bad response"})

        with pytest.raises(ValueError, match="must be a list"):
            list(adapter.fetch(""))

    def test_fetch_missing_required_field_id(self, mock_httpx_client_browser_history):
        """fetch() raises EndpointFetchError if all visits are missing 'id' field."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        visits_url = "http://127.0.0.1:7123/browser/history"
        mock_httpx_client_browser_history.set_response(visits_url, [
            {
                # Missing 'id'
                "url": "https://example.com",
                "title": "Test",
                "visitedAt": "2026-03-10T10:00:00Z",
                "browser": "safari",
                "visitCount": 1,
            }
        ])

        with pytest.raises(EndpointFetchError, match="malformed"):
            list(adapter.fetch(""))

    def test_fetch_missing_required_field_visitedAt(self, mock_httpx_client_browser_history):
        """fetch() raises EndpointFetchError if all visits are missing 'visitedAt' field."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        visits_url = "http://127.0.0.1:7123/browser/history"
        mock_httpx_client_browser_history.set_response(visits_url, [
            {
                "id": "visit-1",
                "url": "https://example.com",
                "title": "Test",
                # Missing 'visitedAt'
                "browser": "safari",
                "visitCount": 1,
            }
        ])

        with pytest.raises(EndpointFetchError, match="malformed"):
            list(adapter.fetch(""))

    def test_fetch_missing_required_field_url(self, mock_httpx_client_browser_history):
        """fetch() raises EndpointFetchError if all visits are missing 'url' field."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        visits_url = "http://127.0.0.1:7123/browser/history"
        mock_httpx_client_browser_history.set_response(visits_url, [
            {
                "id": "visit-1",
                # Missing 'url'
                "title": "Test",
                "visitedAt": "2026-03-10T10:00:00Z",
                "browser": "safari",
                "visitCount": 1,
            }
        ])

        with pytest.raises(EndpointFetchError, match="malformed"):
            list(adapter.fetch(""))

    def test_fetch_empty_url_string_raises_error(self, mock_httpx_client_browser_history):
        """fetch() raises EndpointFetchError if all visits have empty 'url' strings."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        visits_url = "http://127.0.0.1:7123/browser/history"
        mock_httpx_client_browser_history.set_response(visits_url, [
            {
                "id": "visit-1",
                "url": "",  # Empty string
                "title": "Test",
                "visitedAt": "2026-03-10T10:00:00Z",
                "browser": "safari",
                "visitCount": 1,
            }
        ])

        with pytest.raises(EndpointFetchError, match="malformed"):
            list(adapter.fetch(""))

    def test_fetch_missing_required_field_browser(self, mock_httpx_client_browser_history):
        """fetch() raises EndpointFetchError if all visits are missing 'browser' field."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        visits_url = "http://127.0.0.1:7123/browser/history"
        mock_httpx_client_browser_history.set_response(visits_url, [
            {
                "id": "visit-1",
                "url": "https://example.com",
                "title": "Test",
                "visitedAt": "2026-03-10T10:00:00Z",
                # Missing 'browser'
                "visitCount": 1,
            }
        ])

        with pytest.raises(EndpointFetchError, match="malformed"):
            list(adapter.fetch(""))

    def test_fetch_missing_required_field_visitCount(self, mock_httpx_client_browser_history):
        """fetch() raises EndpointFetchError if all visits are missing 'visitCount' field."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        visits_url = "http://127.0.0.1:7123/browser/history"
        mock_httpx_client_browser_history.set_response(visits_url, [
            {
                "id": "visit-1",
                "url": "https://example.com",
                "title": "Test",
                "visitedAt": "2026-03-10T10:00:00Z",
                "browser": "safari",
                # Missing 'visitCount'
            }
        ])

        with pytest.raises(EndpointFetchError, match="malformed"):
            list(adapter.fetch(""))

    def test_fetch_http_error_response(self, mock_httpx_client_browser_history):
        """fetch() raises httpx.HTTPStatusError when API returns error status."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        visits_url = "http://127.0.0.1:7123/browser/history"
        mock_httpx_client_browser_history.set_response(visits_url, {"error": "Internal Server Error"}, status_code=500)

        with pytest.raises(Exception):  # httpx.HTTPStatusError
            list(adapter.fetch(""))

    def test_fetch_empty_response_yields_nothing(self, mock_httpx_client_browser_history):
        """fetch() yields nothing when API returns empty list."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        visits_url = "http://127.0.0.1:7123/browser/history"
        mock_httpx_client_browser_history.set_response(visits_url, [])

        results = list(adapter.fetch(""))
        assert len(results) == 0

    def test_fetch_partial_failure_valid_and_malformed_mix(self, mock_httpx_client_browser_history, caplog):
        """fetch() yields valid visits and skips malformed ones (does not raise)."""
        adapter = AppleBrowserHistoryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        visits_url = "http://127.0.0.1:7123/browser/history"
        mock_httpx_client_browser_history.set_response(visits_url, [
            {
                "id": "visit-1",
                "url": "https://example.com/page1",
                "title": "Good Page 1",
                "visitedAt": "2026-03-10T10:00:00Z",
                "browser": "safari",
                "visitCount": 5,
            },
            {
                "id": "visit-2",
                # Missing required 'url' field — malformed
                "title": "Bad Page",
                "visitedAt": "2026-03-10T11:00:00Z",
                "browser": "firefox",
                "visitCount": 1,
            },
            {
                "id": "visit-3",
                "url": "https://example.com/page3",
                "title": "Good Page 3",
                "visitedAt": "2026-03-10T12:00:00Z",
                "browser": "chrome",
                "visitCount": 3,
            },
        ])

        results = list(adapter.fetch(""))
        # Should yield only the 2 valid visits, skipping the malformed one
        assert len(results) == 2
        assert results[0].source_id == "browser_history/visit-1"
        assert results[1].source_id == "browser_history/visit-3"
        # Verify that error was logged for malformed visit
        assert any("Skipping malformed visit" in record.message for record in caplog.records)
