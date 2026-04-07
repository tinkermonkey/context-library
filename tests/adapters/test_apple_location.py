"""Tests for AppleLocationAdapter."""

import pytest
from unittest.mock import Mock, patch

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

from context_library.adapters.apple_location import AppleLocationAdapter
from context_library.adapters.base import (
    PartialFetchError,
    AllEndpointsFailedError,
)
from context_library.storage.models import Domain


@pytest.mark.skipif(not HAS_HTTPX, reason="httpx not installed")
class TestAppleLocationAdapterInit:
    """Test AppleLocationAdapter initialization."""

    def test_init_valid_credentials(self):
        """Adapter initializes with valid credentials."""
        adapter = AppleLocationAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
            device_id="test-device",
        )
        assert adapter.adapter_id == "apple_location:test-device"
        assert adapter.domain == Domain.LOCATION
        assert adapter.poll_strategy.name == "PULL"

    def test_init_requires_api_key(self):
        """Adapter raises ValueError if api_key is empty."""
        with pytest.raises(ValueError, match="api_key is required"):
            AppleLocationAdapter(
                api_url="http://localhost:7123",
                api_key="",
            )

    def test_init_default_device_id(self):
        """Adapter uses 'default' device_id if not provided."""
        adapter = AppleLocationAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
        )
        assert adapter.adapter_id == "apple_location:default"

    def test_normalizer_version(self):
        """Adapter has a normalizer version."""
        adapter = AppleLocationAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
        )
        assert adapter.normalizer_version == "1.0.0"


@pytest.mark.skipif(not HAS_HTTPX, reason="httpx not installed")
class TestAppleLocationAdapterVisits:
    """Test location visits endpoint handling."""

    @patch("context_library.adapters.apple_location.httpx.Client")
    def test_visit_happy_path(self, mock_client_class):
        """Visits endpoint yields correct LocationMetadata and context header."""
        # Create a mock client instance
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        def get_side_effect(url, **kwargs):
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = Mock()

            if "/location/visits" in url:
                mock_response.json.return_value = [
                    {
                        "id": "visit-001",
                        "latitude": 37.7749,
                        "longitude": -122.4194,
                        "placeName": "San Francisco",
                        "locality": "San Francisco County",
                        "country": "United States",
                        "arrivalDate": "2025-02-10T08:00:00Z",
                        "departureDate": "2025-02-10T18:00:00Z",
                        "durationMinutes": 600,
                    }
                ]
            else:  # /location/current
                mock_response.json.return_value = {}

            return mock_response

        mock_client.get.side_effect = get_side_effect
        mock_client.close = Mock()

        adapter = AppleLocationAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
        )

        contents = list(adapter.fetch(source_ref=""))
        assert len(contents) == 1

        content = contents[0]
        assert content.source_id == "apple_location/visit/visit-001"
        assert "San Francisco" in content.markdown
        assert "Visit: 2025-02-10T08:00:00Z to 2025-02-10T18:00:00Z" in content.markdown
        assert "Duration: 600 minutes" in content.markdown

        # Check metadata
        metadata = content.structural_hints.extra_metadata
        assert metadata["source_type"] == "apple_location_visit"
        assert metadata["place_name"] == "San Francisco"
        assert metadata["latitude"] == 37.7749
        assert metadata["longitude"] == -122.4194

    def test_visit_no_place_name_fallback(self, mock_httpx_client_location):
        """Visit without place name falls back to coordinates in markdown."""
        mock_httpx_client_location.set_response(
            "http://localhost:7123/location/visits",
            [
                {
                    "id": "visit-002",
                    "latitude": 40.7128,
                    "longitude": -74.0060,
                    "arrivalDate": "2025-02-10T09:00:00Z",
                    "departureDate": "2025-02-10T17:00:00Z",
                    "durationMinutes": 480,
                }
            ]
        )
        mock_httpx_client_location.set_response(
            "http://localhost:7123/location/current",
            {}
        )

        adapter = AppleLocationAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
        )

        contents = list(adapter.fetch(source_ref=""))
        assert len(contents) == 1

        content = contents[0]
        # Without place_name, markdown should show coordinates
        assert "**40.7128, -74.006**" in content.markdown


@pytest.mark.skipif(not HAS_HTTPX, reason="httpx not installed")
class TestAppleLocationAdapterCurrent:
    """Test current location endpoint handling."""

    def test_current_happy_path(self, mock_httpx_client_location):
        """Current location endpoint yields correct fixed source_id and metadata."""
        mock_httpx_client_location.set_response(
            "http://localhost:7123/location/current",
            {
                "latitude": 37.7749,
                "longitude": -122.4194,
                "placeName": "San Francisco",
                "locality": "San Francisco County",
                "country": "United States",
            }
        )
        mock_httpx_client_location.set_response(
            "http://localhost:7123/location/visits",
            []
        )

        adapter = AppleLocationAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
        )

        contents = list(adapter.fetch(source_ref=""))

        # Find current location content (should be one of the contents)
        current_contents = [c for c in contents if c.source_id == "apple-location-current"]
        assert len(current_contents) == 1

        content = current_contents[0]
        assert content.source_id == "apple-location-current"
        assert "Current:" in content.markdown
        assert "San Francisco" in content.markdown

        # Check metadata
        metadata = content.structural_hints.extra_metadata
        assert metadata["source_type"] == "apple_location_current"
        assert metadata["location_id"] == "apple-location-current"
        assert metadata["arrival_date"] is None
        assert metadata["departure_date"] is None
        assert metadata["duration_minutes"] is None

    def test_empty_current_location_skipped(self, mock_httpx_client_location):
        """Empty current location response yields no content."""
        mock_httpx_client_location.set_response(
            "http://localhost:7123/location/current",
            {}  # Empty response
        )
        mock_httpx_client_location.set_response(
            "http://localhost:7123/location/visits",
            []  # Empty visits
        )

        adapter = AppleLocationAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
        )

        contents = list(adapter.fetch(source_ref=""))
        # Only empty lists from both endpoints
        assert len(contents) == 0


@pytest.mark.skipif(not HAS_HTTPX, reason="httpx not installed")
class TestAppleLocationAdapterPartialFailure:
    """Test partial failure behavior."""

    def test_partial_failure_visits_down(self, mock_httpx_client_location):
        """When visits endpoint fails, current endpoint still yields data."""
        # Configure /location/visits to raise an error
        def raise_error(*args, **kwargs):
            raise httpx.RequestError("Connection refused")

        # We need to set up custom behavior for visits - let's use the mock client's capability
        # Store the old get method to replace it
        original_get = mock_httpx_client_location.get

        def custom_get(url, **kwargs):
            if "/location/visits" in url:
                raise httpx.RequestError("Connection refused")
            return original_get(url, **kwargs)

        mock_httpx_client_location.get = custom_get
        mock_httpx_client_location.set_response(
            "http://localhost:7123/location/current",
            {
                "latitude": 37.7749,
                "longitude": -122.4194,
                "placeName": "San Francisco",
            }
        )

        adapter = AppleLocationAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
        )

        with pytest.raises(PartialFetchError) as exc_info:
            list(adapter.fetch(source_ref=""))

        assert "/location/visits" in exc_info.value.failed_endpoints
        # Content should still be yielded before the error is raised

    def test_partial_failure_current_down(self, mock_httpx_client_location):
        """When current endpoint fails, visits endpoint still yields data."""
        # Configure /location/current to raise an error
        original_get = mock_httpx_client_location.get

        def custom_get(url, **kwargs):
            if "/location/current" in url:
                raise httpx.RequestError("Connection refused")
            return original_get(url, **kwargs)

        mock_httpx_client_location.get = custom_get
        mock_httpx_client_location.set_response(
            "http://localhost:7123/location/visits",
            [
                {
                    "id": "visit-001",
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "placeName": "San Francisco",
                }
            ]
        )

        adapter = AppleLocationAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
        )

        with pytest.raises(PartialFetchError) as exc_info:
            list(adapter.fetch(source_ref=""))

        assert "/location/current" in exc_info.value.failed_endpoints

    def test_all_endpoints_failed(self, mock_httpx_client_location):
        """When all endpoints fail, AllEndpointsFailedError is raised."""
        # Configure both endpoints to raise an error
        def raise_error(*args, **kwargs):
            raise httpx.RequestError("Connection refused")

        mock_httpx_client_location.get = raise_error

        adapter = AppleLocationAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
        )

        with pytest.raises(AllEndpointsFailedError):
            list(adapter.fetch(source_ref=""))


@pytest.mark.skipif(not HAS_HTTPX, reason="httpx not installed")
class TestAppleLocationAdapterSilentSkipDetection:
    """Test that 100% item skip rate is detected and raises an error."""

    def test_all_visits_malformed_raises_error(self, mock_httpx_client_location):
        """When all visits items are malformed, the visits endpoint is marked as failed."""
        # Configure mocked endpoints
        mock_httpx_client_location.set_response(
            "http://localhost:7123/location/visits",
            [
                {"id": "visit-001"},  # Missing latitude/longitude
                {"id": "visit-002"},  # Missing latitude/longitude
            ]
        )
        mock_httpx_client_location.set_response(
            "http://localhost:7123/location/current",
            {}
        )

        adapter = AppleLocationAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
        )

        from context_library.adapters.base import PartialFetchError
        # When visits has 100% skip rate and current returns empty, visits fails but current succeeds
        # This results in PartialFetchError for one failed endpoint
        with pytest.raises(PartialFetchError) as exc_info:
            list(adapter.fetch(source_ref=""))

        # Verify that /location/visits is in the failed endpoints
        assert "/location/visits" in exc_info.value.failed_endpoints


@pytest.mark.skipif(not HAS_HTTPX, reason="httpx not installed")
class TestAppleLocationAdapterAuthErrors:
    """Test 401/403 authentication error propagation."""

    def test_401_auth_error_propagates_visits(self, mock_httpx_client_location):
        """401 auth error from /location/visits is propagated immediately."""
        # Configure /location/visits to return 401
        mock_httpx_client_location.set_status(
            "http://localhost:7123/location/visits",
            status_code=401
        )
        # Configure /location/current to succeed
        mock_httpx_client_location.set_response(
            "http://localhost:7123/location/current",
            {}
        )

        adapter = AppleLocationAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
        )

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            list(adapter.fetch(source_ref=""))

        assert exc_info.value.response.status_code == 401

    def test_403_auth_error_propagates_current(self, mock_httpx_client_location):
        """403 auth error from /location/current is propagated immediately."""
        # Configure /location/visits to succeed
        mock_httpx_client_location.set_response(
            "http://localhost:7123/location/visits",
            []
        )
        # Configure /location/current to return 403
        mock_httpx_client_location.set_status(
            "http://localhost:7123/location/current",
            status_code=403
        )

        adapter = AppleLocationAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
        )

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            list(adapter.fetch(source_ref=""))

        assert exc_info.value.response.status_code == 403


@pytest.mark.skipif(not HAS_HTTPX, reason="httpx not installed")
class TestAppleLocationAdapterImportability:
    """Test adapter is properly importable."""

    def test_importable_from_context_library_adapters(self):
        """AppleLocationAdapter is importable from context_library.adapters."""
        from context_library.adapters import AppleLocationAdapter as ImportedAdapter
        assert ImportedAdapter is AppleLocationAdapter

    def test_adapter_in_registry(self):
        """AppleLocationAdapter is accessible when httpx is installed."""
        # If we got here, httpx is installed, so the adapter should be importable
        from context_library.adapters import AppleLocationAdapter as ImportedAdapter
        assert ImportedAdapter == AppleLocationAdapter
