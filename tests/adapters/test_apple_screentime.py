"""Tests for the AppleScreenTimeAdapter."""

import pytest

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

from context_library.adapters.apple_screentime import AppleScreenTimeAdapter
from context_library.adapters.base import AllEndpointsFailedError, PartialFetchError
from context_library.storage.models import Domain, PollStrategy, NormalizedContent


class TestAppleScreenTimeAdapterInitialization:
    """Tests for AppleScreenTimeAdapter initialization."""

    def test_init_default_parameters(self):
        """__init__ uses default parameters when not provided."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"
        assert adapter._api_key == "test-token"
        assert adapter._device_id == "default"

    def test_init_requires_api_key(self):
        """__init__ raises ValueError when api_key is empty."""
        with pytest.raises(ValueError, match="api_key is required"):
            AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="")

    def test_init_custom_parameters(self):
        """__init__ accepts and stores custom parameters."""
        adapter = AppleScreenTimeAdapter(
            api_url="http://localhost:8000",
            api_key="test_key",
            device_id="macbook-pro-m1",
        )
        assert adapter._api_url == "http://localhost:8000"
        assert adapter._api_key == "test_key"
        assert adapter._device_id == "macbook-pro-m1"

    def test_init_strips_trailing_slash_from_url(self):
        """__init__ strips trailing slash from api_url."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123/", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"

    def test_init_no_trailing_slash(self):
        """__init__ leaves api_url unchanged if no trailing slash."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"


class TestAppleScreenTimeAdapterProperties:
    """Tests for AppleScreenTimeAdapter properties."""

    def test_adapter_id_format_default(self):
        """adapter_id has correct format: apple_screentime:{device_id}."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.adapter_id == "apple_screentime:default"

    def test_adapter_id_format_custom_device(self):
        """adapter_id uses custom device_id."""
        adapter = AppleScreenTimeAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test-token",
            device_id="macbook-pro-m1"
        )
        assert adapter.adapter_id == "apple_screentime:macbook-pro-m1"

    def test_adapter_id_deterministic(self):
        """adapter_id is deterministic for the same configuration."""
        adapter1 = AppleScreenTimeAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test-token",
            device_id="device-1"
        )
        adapter2 = AppleScreenTimeAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test-token",
            device_id="device-1"
        )
        assert adapter1.adapter_id == adapter2.adapter_id

    def test_domain_property(self):
        """domain property returns Domain.EVENTS."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.domain == Domain.EVENTS

    def test_poll_strategy_property(self):
        """poll_strategy property returns PollStrategy.PULL."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.poll_strategy == PollStrategy.PULL

    def test_normalizer_version_property(self):
        """normalizer_version property returns '1.0.0'."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.normalizer_version == "1.0.0"


class TestAppleScreenTimeAdapterFetchAppUsage:
    """Tests for AppleScreenTimeAdapter.fetch() with app usage."""

    def test_fetch_app_usage_single_item(self, mock_all_screentime_endpoints):
        """fetch() yields NormalizedContent for a single app usage item."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/app-usage", [
            {
                "date": "2026-03-20",
                "bundleId": "com.apple.Safari",
                "appName": "Safari",
                "durationSeconds": 3600,
            }
        ])

        results = list(adapter.fetch(""))
        assert len(results) >= 1
        # Find the app usage item
        app_usage_items = [r for r in results if "app-usage" in r.source_id]
        assert len(app_usage_items) == 1
        item = app_usage_items[0]
        assert isinstance(item, NormalizedContent)
        assert item.domain == Domain.EVENTS
        assert "Safari" in item.markdown
        assert "60 min" in item.markdown

    def test_fetch_app_usage_multiple_items(self, mock_all_screentime_endpoints):
        """fetch() yields NormalizedContent for multiple app usage items."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/app-usage", [
            {
                "date": "2026-03-20",
                "bundleId": "com.apple.Safari",
                "appName": "Safari",
                "durationSeconds": 3600,
            },
            {
                "date": "2026-03-20",
                "bundleId": "com.slack.Slack",
                "appName": "Slack",
                "durationSeconds": 5400,
            },
        ])

        results = list(adapter.fetch(""))
        app_usage_items = [r for r in results if "app-usage" in r.source_id]
        assert len(app_usage_items) == 2
        assert app_usage_items[0].source_id == "screentime/app-usage/com.apple.Safari/2026-03-20"
        assert app_usage_items[1].source_id == "screentime/app-usage/com.slack.Slack/2026-03-20"

    def test_fetch_app_usage_title_format(self, mock_all_screentime_endpoints):
        """fetch() formats app usage title as '{appName} — {duration_minutes} min'."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/app-usage", [
            {
                "date": "2026-03-20",
                "bundleId": "com.apple.Safari",
                "appName": "Safari",
                "durationSeconds": 3600,
            }
        ])

        results = list(adapter.fetch(""))
        app_usage_items = [r for r in results if "app-usage" in r.source_id]
        assert len(app_usage_items) == 1
        # The title should be formatted as "{appName} — {duration_minutes} min" in the metadata
        metadata_dict = app_usage_items[0].structural_hints.extra_metadata
        assert metadata_dict["title"] == "Safari — 60 min"

    def test_fetch_app_usage_source_id_stable(self, mock_all_screentime_endpoints):
        """fetch() produces stable source_id: screentime/app-usage/{bundleId}/{date}."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/app-usage", [
            {
                "date": "2026-03-20",
                "bundleId": "com.apple.Safari",
                "appName": "Safari",
                "durationSeconds": 3600,
            }
        ])

        results = list(adapter.fetch(""))
        app_usage_items = [r for r in results if "app-usage" in r.source_id]
        assert len(app_usage_items) == 1
        # Source ID should be deterministic: bundleId + date
        assert app_usage_items[0].source_id == "screentime/app-usage/com.apple.Safari/2026-03-20"

    def test_fetch_app_usage_source_type(self, mock_all_screentime_endpoints):
        """fetch() sets source_type to 'screentime_app_usage' in event metadata."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/app-usage", [
            {
                "date": "2026-03-20",
                "bundleId": "com.apple.Safari",
                "appName": "Safari",
                "durationSeconds": 3600,
            }
        ])

        results = list(adapter.fetch(""))
        app_usage_items = [r for r in results if "app-usage" in r.source_id]
        assert len(app_usage_items) == 1
        metadata_dict = app_usage_items[0].structural_hints.extra_metadata
        assert metadata_dict["source_type"] == "screentime_app_usage"

    def test_fetch_app_usage_extra_metadata(self, mock_all_screentime_endpoints):
        """fetch() includes bundleId and durationSeconds in extra_metadata."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/app-usage", [
            {
                "date": "2026-03-20",
                "bundleId": "com.apple.Safari",
                "appName": "Safari",
                "durationSeconds": 3600,
            }
        ])

        results = list(adapter.fetch(""))
        app_usage_items = [r for r in results if "app-usage" in r.source_id]
        assert len(app_usage_items) == 1
        metadata_dict = app_usage_items[0].structural_hints.extra_metadata
        assert metadata_dict["bundleId"] == "com.apple.Safari"
        assert metadata_dict["durationSeconds"] == 3600

    def test_fetch_app_usage_with_since_parameter(self, mock_all_screentime_endpoints):
        """fetch() passes 'since' query parameter for incremental fetch."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/app-usage", [])

        list(adapter.fetch("2026-03-06T10:00:00Z"))

        # Check app usage request
        request = None
        for r in mock_all_screentime_endpoints.requests:
            if "/screentime/app-usage" in r["url"]:
                request = r
                break

        assert request is not None
        assert request["params"] == {"since": "2026-03-06T10:00:00Z"}

    def test_fetch_app_usage_zero_duration(self, mock_all_screentime_endpoints):
        """fetch() handles zero duration correctly."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/app-usage", [
            {
                "date": "2026-03-20",
                "bundleId": "com.apple.Safari",
                "appName": "Safari",
                "durationSeconds": 0,
            }
        ])

        results = list(adapter.fetch(""))
        app_usage_items = [r for r in results if "app-usage" in r.source_id]
        assert len(app_usage_items) == 1
        metadata_dict = app_usage_items[0].structural_hints.extra_metadata
        assert metadata_dict["title"] == "Safari — 0 min"


class TestAppleScreenTimeAdapterFetchFocusEvents:
    """Tests for AppleScreenTimeAdapter.fetch() with focus events."""

    def test_fetch_focus_events_lock(self, mock_all_screentime_endpoints):
        """fetch() yields 'Device lock' for lock event type."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/focus", [
            {
                "timestamp": "2026-03-20T10:00:00+00:00",
                "eventType": "lock",
            }
        ])

        results = list(adapter.fetch(""))
        focus_items = [r for r in results if "focus" in r.source_id]
        assert len(focus_items) == 1
        item = focus_items[0]
        assert isinstance(item, NormalizedContent)
        assert item.domain == Domain.EVENTS
        assert "Device lock" in item.markdown

    def test_fetch_focus_events_unlock(self, mock_all_screentime_endpoints):
        """fetch() yields 'Device unlock' for unlock event type."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/focus", [
            {
                "timestamp": "2026-03-20T10:05:00+00:00",
                "eventType": "unlock",
            }
        ])

        results = list(adapter.fetch(""))
        focus_items = [r for r in results if "focus" in r.source_id]
        assert len(focus_items) == 1
        item = focus_items[0]
        assert "Device unlock" in item.markdown

    def test_fetch_focus_events_multiple_items(self, mock_all_screentime_endpoints):
        """fetch() yields NormalizedContent for multiple focus events."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/focus", [
            {
                "timestamp": "2026-03-20T10:00:00+00:00",
                "eventType": "lock",
            },
            {
                "timestamp": "2026-03-20T10:05:00+00:00",
                "eventType": "unlock",
            },
            {
                "timestamp": "2026-03-20T12:00:00+00:00",
                "eventType": "lock",
            },
        ])

        results = list(adapter.fetch(""))
        focus_items = [r for r in results if "focus" in r.source_id]
        assert len(focus_items) == 3

    def test_fetch_focus_events_source_id_uses_timestamp(self, mock_all_screentime_endpoints):
        """fetch() produces source_id: screentime/focus/{timestamp}."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/focus", [
            {
                "timestamp": "2026-03-20T10:00:00+00:00",
                "eventType": "lock",
            }
        ])

        results = list(adapter.fetch(""))
        focus_items = [r for r in results if "focus" in r.source_id]
        assert len(focus_items) == 1
        assert focus_items[0].source_id == "screentime/focus/2026-03-20T10:00:00+00:00"

    def test_fetch_focus_events_source_type(self, mock_all_screentime_endpoints):
        """fetch() sets source_type to 'screentime_focus' in event metadata."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/focus", [
            {
                "timestamp": "2026-03-20T10:00:00+00:00",
                "eventType": "lock",
            }
        ])

        results = list(adapter.fetch(""))
        focus_items = [r for r in results if "focus" in r.source_id]
        assert len(focus_items) == 1
        metadata_dict = focus_items[0].structural_hints.extra_metadata
        assert metadata_dict["source_type"] == "screentime_focus"

    def test_fetch_focus_events_extra_metadata(self, mock_all_screentime_endpoints):
        """fetch() includes eventType in extra_metadata."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/focus", [
            {
                "timestamp": "2026-03-20T10:00:00+00:00",
                "eventType": "lock",
            }
        ])

        results = list(adapter.fetch(""))
        focus_items = [r for r in results if "focus" in r.source_id]
        assert len(focus_items) == 1
        metadata_dict = focus_items[0].structural_hints.extra_metadata
        assert metadata_dict["eventType"] == "lock"

    def test_fetch_focus_events_with_since_parameter(self, mock_all_screentime_endpoints):
        """fetch() passes 'since' query parameter for incremental fetch."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/focus", [])

        list(adapter.fetch("2026-03-06T10:00:00Z"))

        # Check focus request
        request = None
        for r in mock_all_screentime_endpoints.requests:
            if "/screentime/focus" in r["url"]:
                request = r
                break

        assert request is not None
        assert request["params"] == {"since": "2026-03-06T10:00:00Z"}

    def test_fetch_focus_events_invalid_event_type(self, mock_all_screentime_endpoints):
        """fetch() skips focus events with invalid eventType (not 'lock' or 'unlock')."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/focus", [
            {
                "timestamp": "2026-03-20T10:00:00+00:00",
                "eventType": "invalid",
            },
            {
                "timestamp": "2026-03-20T10:05:00+00:00",
                "eventType": "lock",
            },
            {
                "timestamp": "2026-03-20T10:10:00+00:00",
                "eventType": "bad_value",
            },
        ])

        results = list(adapter.fetch(""))
        focus_items = [r for r in results if "focus" in r.source_id]

        # Only the valid 'lock' event should be yielded
        assert len(focus_items) == 1
        assert focus_items[0].source_id == "screentime/focus/2026-03-20T10:05:00+00:00"
        assert "Device lock" in focus_items[0].markdown


class TestAppleScreenTimeAdapterPartialFailure:
    """Tests for AppleScreenTimeAdapter partial failure handling."""

    def test_partial_failure_app_usage_endpoint_down(self, mock_all_screentime_endpoints):
        """fetch() raises PartialFetchError when app-usage endpoint fails but focus succeeds."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        # App usage endpoint fails
        mock_all_screentime_endpoints.set_response(
            "http://127.0.0.1:7123/screentime/app-usage",
            {"error": "internal server error"},
            status_code=500
        )

        # Focus endpoint succeeds
        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/focus", [
            {
                "timestamp": "2026-03-20T10:00:00+00:00",
                "eventType": "lock",
            }
        ])

        with pytest.raises(PartialFetchError) as exc_info:
            list(adapter.fetch(""))

        error = exc_info.value
        assert "/screentime/app-usage" in error.failed_endpoints
        assert error.total_endpoints == 2
        assert len(error.failed_endpoints) == 1

    def test_partial_failure_focus_endpoint_down(self, mock_all_screentime_endpoints):
        """fetch() raises PartialFetchError when focus endpoint fails but app-usage succeeds."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        # App usage endpoint succeeds
        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/app-usage", [
            {
                "date": "2026-03-20",
                "bundleId": "com.apple.Safari",
                "appName": "Safari",
                "durationSeconds": 3600,
            }
        ])

        # Focus endpoint fails
        mock_all_screentime_endpoints.set_response(
            "http://127.0.0.1:7123/screentime/focus",
            {"error": "internal server error"},
            status_code=500
        )

        with pytest.raises(PartialFetchError) as exc_info:
            list(adapter.fetch(""))

        error = exc_info.value
        assert "/screentime/focus" in error.failed_endpoints
        assert error.total_endpoints == 2
        assert len(error.failed_endpoints) == 1

    def test_all_endpoints_failed(self, mock_all_screentime_endpoints):
        """fetch() raises AllEndpointsFailedError when all endpoints fail."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        # Both endpoints fail
        mock_all_screentime_endpoints.set_response(
            "http://127.0.0.1:7123/screentime/app-usage",
            {"error": "internal server error"},
            status_code=500
        )
        mock_all_screentime_endpoints.set_response(
            "http://127.0.0.1:7123/screentime/focus",
            {"error": "internal server error"},
            status_code=500
        )

        with pytest.raises(AllEndpointsFailedError) as exc_info:
            list(adapter.fetch(""))

        error = exc_info.value
        assert error.total_endpoints == 2


class TestAppleScreenTimeAdapterIdempotency:
    """Tests for AppleScreenTimeAdapter idempotency."""

    def test_idempotency_app_usage_same_source_id(self, mock_all_screentime_endpoints):
        """fetch() produces the same source_id for the same app-usage record (hash dedup)."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/app-usage", [
            {
                "date": "2026-03-20",
                "bundleId": "com.apple.Safari",
                "appName": "Safari",
                "durationSeconds": 3600,
            }
        ])

        results1 = list(adapter.fetch(""))
        app_usage_items1 = [r for r in results1 if "app-usage" in r.source_id]
        source_id1 = app_usage_items1[0].source_id

        # Fetch again with same data
        results2 = list(adapter.fetch(""))
        app_usage_items2 = [r for r in results2 if "app-usage" in r.source_id]
        source_id2 = app_usage_items2[0].source_id

        # source_id should be the same for idempotent ingestion (hash dedup)
        assert source_id1 == source_id2
        assert source_id1 == "screentime/app-usage/com.apple.Safari/2026-03-20"

    def test_idempotency_different_apps_different_source_ids(self, mock_all_screentime_endpoints):
        """fetch() produces different source_ids for different apps."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/app-usage", [
            {
                "date": "2026-03-20",
                "bundleId": "com.apple.Safari",
                "appName": "Safari",
                "durationSeconds": 3600,
            },
            {
                "date": "2026-03-20",
                "bundleId": "com.slack.Slack",
                "appName": "Slack",
                "durationSeconds": 5400,
            },
        ])

        results = list(adapter.fetch(""))
        app_usage_items = [r for r in results if "app-usage" in r.source_id]

        # Different apps should have different source_ids
        assert app_usage_items[0].source_id != app_usage_items[1].source_id

    def test_idempotency_same_app_different_dates_different_source_ids(self, mock_all_screentime_endpoints):
        """fetch() produces different source_ids for same app on different dates."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_screentime_endpoints.set_response("http://127.0.0.1:7123/screentime/app-usage", [
            {
                "date": "2026-03-20",
                "bundleId": "com.apple.Safari",
                "appName": "Safari",
                "durationSeconds": 3600,
            },
            {
                "date": "2026-03-21",
                "bundleId": "com.apple.Safari",
                "appName": "Safari",
                "durationSeconds": 4800,
            },
        ])

        results = list(adapter.fetch(""))
        app_usage_items = [r for r in results if "app-usage" in r.source_id]

        # Same app on different dates should have different source_ids
        assert app_usage_items[0].source_id != app_usage_items[1].source_id
        assert "2026-03-20" in app_usage_items[0].source_id
        assert "2026-03-21" in app_usage_items[1].source_id


class TestAppleScreenTimeAdapterAuthErrors:
    """Tests for 401/403 authentication error propagation."""

    def test_fetch_401_auth_error_app_usage(self, mock_httpx_client_screentime):
        """fetch() propagates 401 auth error from app-usage endpoint immediately."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        # App usage returns 401
        mock_httpx_client_screentime.set_response("http://127.0.0.1:7123/screentime/app-usage", None, status_code=401)

        # Focus events would succeed (but won't be reached if auth error is propagated)
        mock_httpx_client_screentime.set_response("http://127.0.0.1:7123/screentime/focus", [])

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            list(adapter.fetch(""))

        assert exc_info.value.response.status_code == 401

    def test_fetch_403_auth_error_focus(self, mock_httpx_client_screentime):
        """fetch() propagates 403 auth error from focus endpoint immediately."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        # App usage succeeds
        mock_httpx_client_screentime.set_response("http://127.0.0.1:7123/screentime/app-usage", [])

        # Focus events return 403
        mock_httpx_client_screentime.set_response("http://127.0.0.1:7123/screentime/focus", None, status_code=403)

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            list(adapter.fetch(""))

        assert exc_info.value.response.status_code == 403


class TestAppleScreenTimeAdapterSilentSkipDetection:
    """Test that 100% item skip rate is detected and raises an error."""

    def test_fetch_all_app_usage_items_malformed_raises_error(self, mock_httpx_client_screentime):
        """fetch() raises PartialFetchError when all app usage items are malformed (100% skip rate)."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        # All items missing required bundleId
        mock_httpx_client_screentime.set_response("http://127.0.0.1:7123/screentime/app-usage", [
            {
                "date": "2026-03-20",
                # Missing bundleId
                "appName": "Safari",
                "durationSeconds": 3600,
            },
            {
                "date": "2026-03-20",
                # Missing bundleId
                "appName": "Slack",
                "durationSeconds": 5400,
            },
        ])
        mock_httpx_client_screentime.set_response("http://127.0.0.1:7123/screentime/focus", [])

        # When app-usage has 100% skip rate, it raises EndpointFetchError internally,
        # which is caught by fetch() and converted to PartialFetchError (since focus succeeds)
        with pytest.raises(PartialFetchError) as exc_info:
            list(adapter.fetch(""))

        assert "/screentime/app-usage" in exc_info.value.failed_endpoints

    def test_fetch_all_focus_events_malformed_raises_error(self, mock_httpx_client_screentime):
        """fetch() raises PartialFetchError when all focus events are malformed (100% skip rate)."""
        adapter = AppleScreenTimeAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_httpx_client_screentime.set_response("http://127.0.0.1:7123/screentime/app-usage", [])

        # All focus events with invalid eventType
        mock_httpx_client_screentime.set_response("http://127.0.0.1:7123/screentime/focus", [
            {
                "timestamp": "2026-03-20T10:00:00+00:00",
                "eventType": "invalid",  # Must be 'lock' or 'unlock'
            },
            {
                "timestamp": "2026-03-20T10:05:00+00:00",
                "eventType": "bad_value",  # Must be 'lock' or 'unlock'
            },
        ])

        # When focus has 100% skip rate, it raises EndpointFetchError internally,
        # which is caught by fetch() and converted to PartialFetchError (since app-usage succeeds)
        with pytest.raises(PartialFetchError) as exc_info:
            list(adapter.fetch(""))

        assert "/screentime/focus" in exc_info.value.failed_endpoints
