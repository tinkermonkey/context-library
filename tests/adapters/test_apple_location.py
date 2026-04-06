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

    @patch("httpx.get")
    def test_visit_happy_path(self, mock_get):
        """Visits endpoint yields correct LocationMetadata and context header."""
        def side_effect(url, **kwargs):
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = Mock()

            if "/location/visits" in url:
                mock_response.json.return_value = [
                    {
                        "id": "visit-001",
                        "latitude": 37.7749,
                        "longitude": -122.4194,
                        "place_name": "San Francisco",
                        "locality": "San Francisco County",
                        "country": "United States",
                        "arrival_date": "2025-02-10T08:00:00Z",
                        "departure_date": "2025-02-10T18:00:00Z",
                        "duration_minutes": 600,
                    }
                ]
            else:  # /location/current
                mock_response.json.return_value = {}

            return mock_response

        mock_get.side_effect = side_effect

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

    @patch("httpx.get")
    def test_visit_no_place_name_fallback(self, mock_get):
        """Visit without place name falls back to coordinates in markdown."""
        def side_effect(url, **kwargs):
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = Mock()

            if "/location/visits" in url:
                mock_response.json.return_value = [
                    {
                        "id": "visit-002",
                        "latitude": 40.7128,
                        "longitude": -74.0060,
                        "arrival_date": "2025-02-10T09:00:00Z",
                        "departure_date": "2025-02-10T17:00:00Z",
                        "duration_minutes": 480,
                    }
                ]
            else:  # /location/current
                mock_response.json.return_value = {}

            return mock_response

        mock_get.side_effect = side_effect

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

    @patch("httpx.get")
    def test_current_happy_path(self, mock_get):
        """Current location endpoint yields correct fixed source_id and metadata."""
        def side_effect(url, **kwargs):
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = Mock()

            if "/location/current" in url:
                mock_response.json.return_value = {
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "place_name": "San Francisco",
                    "locality": "San Francisco County",
                    "country": "United States",
                }
            else:  # /location/visits
                mock_response.json.return_value = []

            return mock_response

        mock_get.side_effect = side_effect

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

    @patch("httpx.get")
    def test_empty_current_location_skipped(self, mock_get):
        """Empty current location response yields no content."""
        def side_effect(url, **kwargs):
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = Mock()

            if "/location/current" in url:
                mock_response.json.return_value = {}  # Empty response
            else:
                mock_response.json.return_value = []  # Empty visits

            return mock_response

        mock_get.side_effect = side_effect

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

    @patch("httpx.get")
    def test_partial_failure_visits_down(self, mock_get):
        """When visits endpoint fails, current endpoint still yields data."""
        def side_effect(url, **kwargs):
            if "/location/visits" in url:
                raise httpx.RequestError("Connection refused")

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = Mock()
            mock_response.json.return_value = {
                "latitude": 37.7749,
                "longitude": -122.4194,
                "place_name": "San Francisco",
            }
            return mock_response

        mock_get.side_effect = side_effect

        adapter = AppleLocationAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
        )

        with pytest.raises(PartialFetchError) as exc_info:
            list(adapter.fetch(source_ref=""))

        assert "/location/visits" in exc_info.value.failed_endpoints
        # Content should still be yielded before the error is raised

    @patch("httpx.get")
    def test_partial_failure_current_down(self, mock_get):
        """When current endpoint fails, visits endpoint still yields data."""
        def side_effect(url, **kwargs):
            if "/location/current" in url:
                raise httpx.RequestError("Connection refused")

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = Mock()
            mock_response.json.return_value = [
                {
                    "id": "visit-001",
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "place_name": "San Francisco",
                }
            ]
            return mock_response

        mock_get.side_effect = side_effect

        adapter = AppleLocationAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
        )

        with pytest.raises(PartialFetchError) as exc_info:
            list(adapter.fetch(source_ref=""))

        assert "/location/current" in exc_info.value.failed_endpoints

    @patch("httpx.get")
    def test_all_endpoints_failed(self, mock_get):
        """When all endpoints fail, AllEndpointsFailedError is raised."""
        mock_get.side_effect = httpx.RequestError("Connection refused")

        adapter = AppleLocationAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
        )

        with pytest.raises(AllEndpointsFailedError):
            list(adapter.fetch(source_ref=""))


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
