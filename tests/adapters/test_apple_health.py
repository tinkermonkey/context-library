"""Tests for the AppleHealthAdapter."""

import pytest


from context_library.adapters.apple_health import AppleHealthAdapter
from context_library.storage.models import Domain, PollStrategy, NormalizedContent, HealthMetadata


class TestAppleHealthAdapterInitialization:
    """Tests for AppleHealthAdapter initialization."""

    def test_init_default_parameters(self):
        """__init__ uses default parameters when not provided."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7124"
        assert adapter._api_key == "test-token"
        assert adapter._device_id == "default"

    def test_init_requires_api_key(self):
        """__init__ raises ValueError when api_key is empty."""
        with pytest.raises(ValueError, match="api_key is required"):
            AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="")

    def test_init_custom_parameters(self):
        """__init__ accepts and stores custom parameters."""
        adapter = AppleHealthAdapter(
            api_url="http://localhost:8000",
            api_key="test_key",
            device_id="macbook-pro-m1",
        )
        assert adapter._api_url == "http://localhost:8000"
        assert adapter._api_key == "test_key"
        assert adapter._device_id == "macbook-pro-m1"

    def test_init_strips_trailing_slash_from_url(self):
        """__init__ strips trailing slash from api_url."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124/", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7124"

    def test_init_no_trailing_slash(self):
        """__init__ leaves api_url unchanged if no trailing slash."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7124"


class TestAppleHealthAdapterProperties:
    """Tests for AppleHealthAdapter properties."""

    def test_adapter_id_format_default(self):
        """adapter_id has correct format: apple_health:{device_id}."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")
        assert adapter.adapter_id == "apple_health:default"

    def test_adapter_id_format_custom_device(self):
        """adapter_id uses custom device_id."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token", device_id="macbook-pro-m1")
        assert adapter.adapter_id == "apple_health:macbook-pro-m1"

    def test_adapter_id_deterministic(self):
        """adapter_id is deterministic for the same configuration."""
        adapter1 = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token", device_id="watch-s7")
        adapter2 = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token", device_id="watch-s7")
        assert adapter1.adapter_id == adapter2.adapter_id

    def test_different_devices_different_ids(self):
        """Different device IDs produce different adapter_ids."""
        adapter1 = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token", device_id="watch-s7")
        adapter2 = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token", device_id="iphone-15")
        assert adapter1.adapter_id != adapter2.adapter_id

    def test_domain_property(self):
        """domain property returns Domain.HEALTH."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")
        assert adapter.domain == Domain.HEALTH

    def test_poll_strategy_property(self):
        """poll_strategy property returns PollStrategy.PULL."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")
        assert adapter.poll_strategy == PollStrategy.PULL

    def test_normalizer_version_property(self):
        """normalizer_version property returns '2.0.0'."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")
        assert adapter.normalizer_version == "2.0.0"


class TestAppleHealthAdapterFetch:
    """Tests for AppleHealthAdapter.fetch() method."""

    def test_fetch_single_workout(self, mock_all_health_endpoints):
        """fetch() yields NormalizedContent for a single workout."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-1",
                "activityType": "running",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "totalEnergyBurned": 250.5,
                "totalDistance": 5000.0,
                "averageHeartRate": 145.0,
                "notes": "Morning run",
            }
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 1
        assert isinstance(results[0], NormalizedContent)
        assert results[0].source_id == "running/workout-1"
        assert "Running" in results[0].markdown
        assert "250" in results[0].markdown  # Calories

    def test_fetch_multiple_workouts(self, mock_all_health_endpoints):
        """fetch() yields NormalizedContent for multiple workouts."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-1",
                "activityType": "running",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "totalEnergyBurned": 250.5,
                "totalDistance": 5000.0,
                "averageHeartRate": 145.0,
                "notes": None,
            },
            {
                "id": "workout-2",
                "activityType": "cycling",
                "startDate": "2026-03-06T14:00:00+00:00",
                "endDate": "2026-03-06T15:00:00+00:00",
                "durationSeconds": 3600,
                "totalEnergyBurned": 400.0,
                "totalDistance": 15000.0,
                "averageHeartRate": 130.0,
                "notes": None,
            },
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 2
        assert results[0].source_id == "running/workout-1"
        assert results[1].source_id == "cycling/workout-2"

    def test_fetch_incremental_with_since(self, mock_all_health_endpoints):
        """fetch() passes 'since' query parameter for incremental fetch."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        list(adapter.fetch("2026-03-06T10:00:00Z"))

        # Verify the first request (workouts) was made with the 'since' parameter
        request = mock_all_health_endpoints.requests[0]
        assert request["params"]["since"] == "2026-03-06T10:00:00Z"


    def test_fetch_with_api_key_auth(self, mock_all_health_endpoints):
        """fetch() sends Authorization header when api_key is provided."""
        adapter = AppleHealthAdapter(
            api_url="http://127.0.0.1:7124",
            api_key="test_token_123"
        )

        list(adapter.fetch(""))

        # Verify the first request (workouts) was made with Authorization header
        request = mock_all_health_endpoints.requests[0]
        assert request["headers"]["Authorization"] == "Bearer test_token_123"

    def test_fetch_health_metadata_contains_required_fields(self, mock_all_health_endpoints):
        """fetch() produces HealthMetadata that passes model_validate."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-1",
                "activityType": "running",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "totalEnergyBurned": 250.5,
                "totalDistance": 5000.0,
                "averageHeartRate": 145.0,
                "notes": "Morning run",
            }
        ])

        results = list(adapter.fetch(""))
        metadata_dict = results[0].structural_hints.extra_metadata

        # This should not raise if HealthMetadata validation passes
        metadata = HealthMetadata.model_validate(metadata_dict)
        assert metadata.record_id == "workout-1"
        assert metadata.health_type == "workout_session"
        assert metadata.date == "2026-03-07"
        assert metadata.duration_minutes == 30
        assert metadata.source_type == "apple_health"

    def test_fetch_extra_metadata_contains_health_fields(self, mock_all_health_endpoints):
        """fetch() includes health-specific fields in extra_metadata."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-1",
                "activityType": "running",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "totalEnergyBurned": 250.5,
                "totalDistance": 5000.0,
                "averageHeartRate": 145.0,
                "notes": None,
            }
        ])

        results = list(adapter.fetch(""))
        metadata_dict = results[0].structural_hints.extra_metadata

        # Check that health-specific fields are present
        assert metadata_dict["calories_kcal"] == 250.5
        assert metadata_dict["distance_meters"] == 5000.0
        assert metadata_dict["avg_heart_rate_bpm"] == 145.0

    def test_fetch_optional_fields_can_be_null(self, mock_all_health_endpoints):
        """fetch() handles null values for optional health fields."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-1",
                "activityType": "mindfulness",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:10:00+00:00",
                "durationSeconds": 600,
                "totalEnergyBurned": None,
                "totalDistance": None,
                "averageHeartRate": None,
                "notes": None,
            }
        ])

        results = list(adapter.fetch(""))
        metadata_dict = results[0].structural_hints.extra_metadata

        # Should validate even with None values
        metadata = HealthMetadata.model_validate(metadata_dict)
        assert metadata.record_id == "workout-1"
        assert metadata_dict["calories_kcal"] is None
        assert metadata_dict["distance_meters"] is None
        assert metadata_dict["avg_heart_rate_bpm"] is None

    def test_fetch_http_error_raises_all_endpoints_failed(self, mock_all_health_endpoints):
        """fetch() raises AllEndpointsFailedError when /workouts returns HTTP error."""
        from context_library.adapters.base import AllEndpointsFailedError
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", {}, status_code=500)

        with pytest.raises(AllEndpointsFailedError):
            list(adapter.fetch(""))

    def test_fetch_invalid_response_schema_raises_all_endpoints_failed(self, mock_all_health_endpoints):
        """fetch() raises AllEndpointsFailedError when /workouts returns invalid schema."""
        from context_library.adapters.base import AllEndpointsFailedError
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        # Return dict instead of list (invalid schema)
        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", {"workouts": []})

        with pytest.raises(AllEndpointsFailedError):
            list(adapter.fetch(""))

    def test_fetch_missing_required_field_skips_workout(self, mock_all_health_endpoints):
        """fetch() skips and logs workouts with missing required fields."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-1",
                # Missing 'activityType'
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "totalEnergyBurned": 250.5,
                "totalDistance": 5000.0,
                "averageHeartRate": 145.0,
                "notes": None,
            }
        ])

        # Should not raise, just skip the malformed workout
        results = list(adapter.fetch(""))
        assert len(results) == 0

    def test_fetch_missing_id_field_skips_workout(self, mock_all_health_endpoints):
        """fetch() skips and logs workouts with missing 'id' field."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                # Missing 'id'
                "activityType": "running",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "totalEnergyBurned": 250.5,
                "totalDistance": 5000.0,
                "averageHeartRate": 145.0,
                "notes": None,
            }
        ])

        # Should not raise, just skip the malformed workout
        results = list(adapter.fetch(""))
        assert len(results) == 0

    def test_fetch_invalid_duration_type_skips_workout(self, mock_all_health_endpoints):
        """fetch() skips and logs workouts with invalid durationSeconds type."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-1",
                "activityType": "running",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": "not a number",  # Should be numeric
                "totalEnergyBurned": 250.5,
                "totalDistance": 5000.0,
                "averageHeartRate": 145.0,
                "notes": None,
            }
        ])

        # Should not raise, just skip the malformed workout
        results = list(adapter.fetch(""))
        assert len(results) == 0

    def test_fetch_empty_id_skips_workout(self, mock_all_health_endpoints):
        """fetch() skips and logs workouts with empty 'id'."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "",  # Empty
                "activityType": "running",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "totalEnergyBurned": 250.5,
                "totalDistance": 5000.0,
                "averageHeartRate": 145.0,
                "notes": None,
            }
        ])

        # Should not raise, just skip the malformed workout
        results = list(adapter.fetch(""))
        assert len(results) == 0

    def test_fetch_empty_activity_type_skips_workout(self, mock_all_health_endpoints):
        """fetch() skips and logs workouts with empty activityType."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-1",
                "activityType": "",  # Empty
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "totalEnergyBurned": 250.5,
                "totalDistance": 5000.0,
                "averageHeartRate": 145.0,
                "notes": None,
            }
        ])

        # Should not raise, just skip the malformed workout
        results = list(adapter.fetch(""))
        assert len(results) == 0

    def test_fetch_malformed_workout_skipped_continues(self, mock_all_health_endpoints):
        """fetch() skips malformed workouts and continues to next."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-1",
                "activityType": "running",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "totalEnergyBurned": 250.5,
                "totalDistance": 5000.0,
                "averageHeartRate": 145.0,
                "notes": None,
            },
            {
                "id": "",  # Malformed
                "activityType": "cycling",
                "startDate": "2026-03-06T14:00:00+00:00",
                "endDate": "2026-03-06T15:00:00+00:00",
                "durationSeconds": 3600,
                "totalEnergyBurned": 400.0,
                "totalDistance": 15000.0,
                "averageHeartRate": 130.0,
                "notes": None,
            },
            {
                "id": "workout-3",
                "activityType": "yoga",
                "startDate": "2026-03-05T08:00:00+00:00",
                "endDate": "2026-03-05T09:00:00+00:00",
                "durationSeconds": 3600,
                "totalEnergyBurned": 100.0,
                "totalDistance": None,
                "averageHeartRate": 80.0,
                "notes": None,
            },
        ])

        results = list(adapter.fetch(""))
        # Should have 2 results, skipping the malformed one in the middle
        assert len(results) == 2
        assert results[0].source_id == "running/workout-1"
        assert results[1].source_id == "yoga/workout-3"


class TestAppleHealthAdapterImportGuard:
    """Tests for import guard and error handling."""

    def test_import_error_without_httpx(self, monkeypatch):
        """AppleHealthAdapter raises ImportError if httpx is not installed."""
        monkeypatch.setattr(
            "context_library.adapters.apple_health.HAS_HTTPX",
            False
        )

        with pytest.raises(ImportError, match="Apple Health adapter requires"):
            AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")


class TestAppleHealthAdapterMarkdownGeneration:
    """Tests for markdown generation in fetch()."""

    def test_markdown_includes_activity_type(self, mock_all_health_endpoints):
        """Generated markdown includes activity type capitalized."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-1",
                "activityType": "running",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "totalEnergyBurned": 250.5,
                "totalDistance": 5000.0,
                "averageHeartRate": 145.0,
                "notes": None,
            }
        ])

        results = list(adapter.fetch(""))
        assert "**Running**" in results[0].markdown

    def test_markdown_includes_calories_when_present(self, mock_all_health_endpoints):
        """Generated markdown includes calories when available."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-1",
                "activityType": "running",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "totalEnergyBurned": 250.5,
                "totalDistance": 5000.0,
                "averageHeartRate": 145.0,
                "notes": None,
            }
        ])

        results = list(adapter.fetch(""))
        assert "Calories: 250 kcal" in results[0].markdown or "Calories: 250.5" in results[0].markdown

    def test_markdown_excludes_calories_when_null(self, mock_all_health_endpoints):
        """Generated markdown excludes calories when null."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-1",
                "activityType": "mindfulness",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:10:00+00:00",
                "durationSeconds": 600,
                "totalEnergyBurned": None,
                "totalDistance": None,
                "averageHeartRate": None,
                "notes": None,
            }
        ])

        results = list(adapter.fetch(""))
        assert "Calories" not in results[0].markdown

    def test_markdown_includes_distance_when_present(self, mock_all_health_endpoints):
        """Generated markdown includes distance in kilometers."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-1",
                "activityType": "running",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "totalEnergyBurned": 250.5,
                "totalDistance": 5000.0,
                "averageHeartRate": 145.0,
                "notes": None,
            }
        ])

        results = list(adapter.fetch(""))
        assert "Distance: 5.00 km" in results[0].markdown

    def test_markdown_includes_heart_rate_when_present(self, mock_all_health_endpoints):
        """Generated markdown includes average heart rate."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-1",
                "activityType": "running",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "totalEnergyBurned": 250.5,
                "totalDistance": 5000.0,
                "averageHeartRate": 145.0,
                "notes": None,
            }
        ])

        results = list(adapter.fetch(""))
        assert "Avg heart rate: 145 bpm" in results[0].markdown

    def test_markdown_includes_duration(self, mock_all_health_endpoints):
        """Generated markdown includes duration in minutes."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-1",
                "activityType": "running",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "totalEnergyBurned": 250.5,
                "totalDistance": 5000.0,
                "averageHeartRate": 145.0,
                "notes": None,
            }
        ])

        results = list(adapter.fetch(""))
        assert "Duration: 30 minutes" in results[0].markdown

    def test_markdown_includes_notes_when_present(self, mock_all_health_endpoints):
        """Generated markdown includes notes when present."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-1",
                "activityType": "running",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "totalEnergyBurned": 250.5,
                "totalDistance": 5000.0,
                "averageHeartRate": 145.0,
                "notes": "Great morning run!",
            }
        ])

        results = list(adapter.fetch(""))
        assert "Great morning run!" in results[0].markdown

    def test_markdown_excludes_notes_when_null(self, mock_all_health_endpoints):
        """Generated markdown excludes notes when null."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-1",
                "activityType": "running",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "totalEnergyBurned": 250.5,
                "totalDistance": 5000.0,
                "averageHeartRate": 145.0,
                "notes": None,
            }
        ])

        results = list(adapter.fetch(""))
        markdown = results[0].markdown
        # Should only have the summary lines, no extra blank note lines
        assert markdown.count("\n") == 4  # Title + 4 metric lines

    def test_structural_hints_has_headings_false(self, mock_all_health_endpoints):
        """StructuralHints.has_headings is False (no heading-level markers in markdown)."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-1",
                "activityType": "running",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "totalEnergyBurned": 250.5,
                "totalDistance": 5000.0,
                "averageHeartRate": 145.0,
                "notes": None,
            }
        ])

        results = list(adapter.fetch(""))
        content = results[0]

        # Verify has_headings is False because markdown uses **bold** not # headings
        assert content.structural_hints.has_headings is False, \
            "has_headings should be False since markdown uses **bold** not heading markers"

        # Verify markdown doesn't contain heading-level markers
        assert not content.markdown.startswith("#"), "Markdown should not start with #"
        assert "\n#" not in content.markdown, "Markdown should not contain heading markers"

        # Verify markdown contains bold and lists (what actually exists)
        assert content.structural_hints.has_lists is True
        assert "**" in content.markdown, "Markdown should contain bold text"

    def test_structural_hints_extra_metadata_contains_health_fields(self, mock_all_health_endpoints):
        """StructuralHints.extra_metadata preserves health-specific fields."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-123",
                "activityType": "running",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "totalEnergyBurned": 250.5,
                "totalDistance": 5000.0,
                "averageHeartRate": 145.0,
                "notes": None,
            }
        ])

        results = list(adapter.fetch(""))
        content = results[0]

        # Verify extra_metadata contains all health-specific fields
        assert content.structural_hints.extra_metadata is not None
        extra = content.structural_hints.extra_metadata

        assert "calories_kcal" in extra, "Health metric calories_kcal missing from extra_metadata"
        assert extra["calories_kcal"] == 250.5

        assert "distance_meters" in extra, "Health metric distance_meters missing from extra_metadata"
        assert extra["distance_meters"] == 5000.0

        assert "avg_heart_rate_bpm" in extra, "Health metric avg_heart_rate_bpm missing from extra_metadata"
        assert extra["avg_heart_rate_bpm"] == 145.0

        # Verify standard HealthMetadata fields are present
        assert extra["record_id"] == "workout-123"
        assert extra["health_type"] == "workout_session"
        assert extra["source_type"] == "apple_health"



class TestAppleHealthAdapterNetworkErrors:
    """Tests for AppleHealthAdapter network error handling."""

    def test_fetch_network_error_raises_all_endpoints_failed(self, monkeypatch):
        """fetch() raises AllEndpointsFailedError when /workouts fails with a network error."""
        import httpx
        from context_library.adapters.base import AllEndpointsFailedError

        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        def mock_get_with_error(*args, **kwargs):
            raise httpx.RequestError("Connection refused")

        monkeypatch.setattr(
            "context_library.adapters.apple_health.httpx.get",
            mock_get_with_error
        )

        with pytest.raises(AllEndpointsFailedError):
            list(adapter.fetch(""))

    def test_fetch_dns_resolution_error_all_endpoints_fail(self, monkeypatch):
        """fetch() raises RuntimeError when ALL endpoints fail with network errors."""
        import httpx

        adapter = AppleHealthAdapter(api_url="http://invalid-host-xyz.local", api_key="test-token")

        def mock_get_with_dns_error(*args, **kwargs):
            raise httpx.RequestError("Name resolution failed")

        # Use monkeypatch for consistent error handling
        monkeypatch.setattr(
            "context_library.adapters.apple_health.httpx.get",
            mock_get_with_dns_error
        )

        # Should raise AllEndpointsFailedError when all endpoints fail
        from context_library.adapters.base import AllEndpointsFailedError
        with pytest.raises(AllEndpointsFailedError):
            list(adapter.fetch(""))


class TestAppleHealthAdapterAuthErrors:
    """Tests for AppleHealthAdapter 401/403 authentication error handling."""

    def test_fetch_401_unauthorized_re_raised_immediately(self, monkeypatch):
        """fetch() re-raises 401 Unauthorized without wrapping in EndpointFetchError."""
        import httpx

        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="invalid-token")

        def mock_get_401(*args, **kwargs):
            # Simulate 401 response
            response = httpx.Response(
                status_code=401,
                content=b"Unauthorized",
                request=httpx.Request("GET", args[0] if args else "http://test"),
            )
            raise httpx.HTTPStatusError("401 Client Error", request=response.request, response=response)

        monkeypatch.setattr(
            "context_library.adapters.apple_health.httpx.get",
            mock_get_401
        )

        # Should raise HTTPStatusError, not EndpointFetchError
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            list(adapter.fetch(""))

        assert exc_info.value.response.status_code == 401

    def test_fetch_403_forbidden_re_raised_immediately(self, monkeypatch):
        """fetch() re-raises 403 Forbidden without wrapping in EndpointFetchError."""
        import httpx

        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        def mock_get_403(*args, **kwargs):
            # Simulate 403 response
            response = httpx.Response(
                status_code=403,
                content=b"Forbidden",
                request=httpx.Request("GET", args[0] if args else "http://test"),
            )
            raise httpx.HTTPStatusError("403 Client Error", request=response.request, response=response)

        monkeypatch.setattr(
            "context_library.adapters.apple_health.httpx.get",
            mock_get_403
        )

        # Should raise HTTPStatusError, not EndpointFetchError
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            list(adapter.fetch(""))

        assert exc_info.value.response.status_code == 403

    def test_fetch_403_on_workouts_stops_immediately(self, monkeypatch):
        """fetch() immediately stops when 403 occurs on /workouts."""
        import httpx

        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")
        call_count = [0]

        def mock_get_403(url, **kwargs):
            call_count[0] += 1
            request = httpx.Request("GET", url)
            response = httpx.Response(
                status_code=403,
                content=b"Forbidden",
                request=request,
            )
            raise httpx.HTTPStatusError("403 Client Error", request=request, response=response)

        monkeypatch.setattr(
            "context_library.adapters.apple_health.httpx.get",
            mock_get_403
        )

        # fetch() should raise immediately on 403
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            list(adapter.fetch(""))

        assert exc_info.value.response.status_code == 403
        assert call_count[0] == 1  # Only /workouts is called

    def test_fetch_other_http_errors_wrapped_in_endpoint_fetch_error(self, monkeypatch):
        """fetch() wraps non-auth HTTP errors (4xx/5xx) in EndpointFetchError."""
        import httpx

        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        def mock_get_500(*args, **kwargs):
            response = httpx.Response(
                status_code=500,
                content=b"Internal Server Error",
                request=httpx.Request("GET", args[0] if args else "http://test"),
            )
            raise httpx.HTTPStatusError("500 Server Error", request=response.request, response=response)

        monkeypatch.setattr(
            "context_library.adapters.apple_health.httpx.get",
            mock_get_500
        )

        # Should raise AllEndpointsFailedError (which wraps EndpointFetchError)
        from context_library.adapters.base import AllEndpointsFailedError
        with pytest.raises(AllEndpointsFailedError):
            list(adapter.fetch(""))
