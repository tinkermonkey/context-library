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

    def test_fetch_http_error_logged_continues(self, mock_all_health_endpoints):
        """fetch() logs HTTP errors without raising, allowing other endpoints to proceed."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        # Set workouts to error, but sleep to succeed
        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", {}, status_code=500)
        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/sleep", [
            {
                "id": "sleep-1",
                "date": "2026-03-07",
                "totalSleepMinutes": 480,
                "deepSleepMinutes": 120,
                "remSleepMinutes": 100,
                "lightSleepMinutes": 260,
                "efficiency": 0.92,
                "score": 85,
            }
        ])

        # Should not raise, just log the error and continue to next endpoints
        results = list(adapter.fetch(""))
        sleep_records = [r for r in results if r.source_id.startswith("sleep/")]
        assert len(sleep_records) == 1  # Sleep endpoint succeeded despite workouts failing

    def test_fetch_invalid_response_schema_logged_continues(self, mock_all_health_endpoints):
        """fetch() logs invalid response schema and continues to next endpoint."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        # Set workouts endpoint to return dict instead of list (invalid schema)
        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/workouts", {"workouts": []})
        # Set sleep endpoint to return valid data
        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/sleep", [
            {
                "id": "sleep-1",
                "date": "2026-03-07",
                "totalSleepMinutes": 450,
            }
        ])

        # Should not raise, just skip the invalid endpoint and continue
        results = list(adapter.fetch(""))
        assert len(results) == 1  # Only sleep record succeeds
        assert results[0].structural_hints.extra_metadata["health_type"] == "sleep_summary"

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


class TestAppleHealthAdapterSleep:
    """Tests for sleep endpoint handler (_process_sleep)."""

    def test_fetch_single_sleep_record(self, mock_all_health_endpoints):
        """fetch() yields NormalizedContent for a single sleep record."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/sleep", [
            {
                "id": "sleep-1",
                "date": "2026-03-07",
                "totalSleepMinutes": 480,
                "deepSleepMinutes": 120,
                "remSleepMinutes": 100,
                "lightSleepMinutes": 260,
                "efficiency": 0.95,
                "score": 85,
            }
        ])

        results = list(adapter.fetch(""))
        sleep_records = [r for r in results if r.source_id.startswith("sleep/")]
        assert len(sleep_records) == 1
        assert sleep_records[0].source_id == "sleep/sleep-1"
        assert "Sleep Summary" in sleep_records[0].markdown
        assert "480" in sleep_records[0].markdown  # Total sleep


class TestAppleHealthAdapterActivity:
    """Tests for activity endpoint handler (_process_activity)."""

    def test_fetch_single_activity_record(self, mock_all_health_endpoints):
        """fetch() yields NormalizedContent for a single activity record."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/activity", [
            {
                "id": "activity-1",
                "date": "2026-03-07",
                "steps": 10000,
                "activeCalories": 500.0,
                "totalCalories": 2000.0,
                "activeMinutes": 60,
                "sedentaryMinutes": 540,
                "distanceMeters": 8000.0,
            }
        ])

        results = list(adapter.fetch(""))
        activity_records = [r for r in results if r.source_id.startswith("activity/")]
        assert len(activity_records) == 1
        assert activity_records[0].source_id == "activity/activity-1"
        assert "Activity Summary" in activity_records[0].markdown
        assert "10,000" in activity_records[0].markdown  # Steps (formatted with comma)


class TestAppleHealthAdapterHRV:
    """Tests for HRV endpoint handler (_process_hrv)."""

    def test_fetch_single_hrv_record(self, mock_all_health_endpoints):
        """fetch() yields NormalizedContent for a single HRV record."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/hrv", [
            {
                "id": "hrv-1",
                "date": "2026-03-07",
                "avgHrv": 50.5,
                "restingHeartRate": 55.0,
                "bodyTemperatureDeviation": 0.2,
            }
        ])

        results = list(adapter.fetch(""))
        hrv_records = [r for r in results if r.source_id.startswith("hrv/")]
        assert len(hrv_records) == 1
        assert hrv_records[0].source_id == "hrv/hrv-1"
        assert "HRV / Readiness" in hrv_records[0].markdown
        assert "50.5" in hrv_records[0].markdown  # Avg HRV


class TestAppleHealthAdapterHeartRate:
    """Tests for heart rate endpoint handler with hourly windowing."""

    def test_fetch_heart_rate_hourly_windowing(self, mock_all_health_endpoints):
        """fetch() groups heart rate samples into hourly windows."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token", device_id="device-1")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/heart_rate", [
            {
                "timestamp": "2026-03-07T10:15:00+00:00",
                "bpm": 70,
                "context": "resting",
            },
            {
                "timestamp": "2026-03-07T10:30:00+00:00",
                "bpm": 72,
                "context": "resting",
            },
            {
                "timestamp": "2026-03-07T10:45:00+00:00",
                "bpm": 75,
                "context": "active",
            },
            {
                "timestamp": "2026-03-07T11:15:00+00:00",
                "bpm": 80,
                "context": "active",
            },
        ])

        results = list(adapter.fetch(""))
        hr_records = [r for r in results if r.source_id.startswith("heart_rate/")]
        # Should have 2 hourly windows: 10:00 and 11:00
        assert len(hr_records) == 2
        assert hr_records[0].source_id == "heart_rate/2026-03-07T10"
        assert hr_records[1].source_id == "heart_rate/2026-03-07T11"


class TestAppleHealthAdapterSpO2:
    """Tests for SpO2 endpoint handler (_process_spo2)."""

    def test_fetch_single_spo2_record(self, mock_all_health_endpoints):
        """fetch() yields NormalizedContent for a single SpO2 record."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/spo2", [
            {
                "id": "spo2-1",
                "date": "2026-03-07",
                "avgSpo2": 97.5,
                "breathingDisturbanceIndex": 2.1,
            }
        ])

        results = list(adapter.fetch(""))
        spo2_records = [r for r in results if r.source_id.startswith("spo2/")]
        assert len(spo2_records) == 1
        assert spo2_records[0].source_id == "spo2/spo2-1"
        assert "Blood Oxygen" in spo2_records[0].markdown
        assert "97.5" in spo2_records[0].markdown  # Avg SpO2


class TestAppleHealthAdapterMindfulness:
    """Tests for mindfulness endpoint handler (_process_mindfulness)."""

    def test_fetch_single_mindfulness_record(self, mock_all_health_endpoints):
        """fetch() yields NormalizedContent for a single mindfulness record."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/mindfulness", [
            {
                "id": "mindfulness-1",
                "startDate": "2026-03-07T18:00:00+00:00",
                "endDate": "2026-03-07T18:10:00+00:00",
                "durationSeconds": 600,
                "sessionType": "meditation",
                "mood": "calm",
                "tags": ["evening", "relaxation"],
            }
        ])

        results = list(adapter.fetch(""))
        mindfulness_records = [r for r in results if r.source_id.startswith("mindfulness/")]
        assert len(mindfulness_records) == 1
        assert mindfulness_records[0].source_id == "mindfulness/mindfulness-1"
        assert "Meditation Session" in mindfulness_records[0].markdown
        assert "10" in mindfulness_records[0].markdown  # Duration in minutes


class TestAppleHealthAdapterSleepIncremental:
    """Tests for sleep endpoint incremental fetch."""

    def test_fetch_sleep_incremental_with_since(self, mock_all_health_endpoints):
        """fetch() passes 'since' parameter to sleep endpoint."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/sleep", [
            {
                "id": "sleep-1",
                "date": "2026-03-07",
                "totalSleepMinutes": 480,
                "deepSleepMinutes": 120,
                "remSleepMinutes": 100,
                "lightSleepMinutes": 260,
                "efficiency": 0.92,
                "score": 85,
            }
        ])

        list(adapter.fetch("2026-03-06T10:00:00Z"))

        # Find sleep request in mock requests
        sleep_request = None
        for req in mock_all_health_endpoints.requests:
            if "/sleep" in req["url"]:
                sleep_request = req
                break

        assert sleep_request is not None
        assert sleep_request["params"]["since"] == "2026-03-06T10:00:00Z"

    def test_fetch_sleep_missing_required_field_skips(self, mock_all_health_endpoints):
        """fetch() skips sleep records with missing required fields."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/sleep", [
            {
                # Missing 'id'
                "date": "2026-03-07",
                "totalSleepMinutes": 480,
                "deepSleepMinutes": 120,
                "remSleepMinutes": 100,
                "lightSleepMinutes": 260,
                "efficiency": 0.92,
                "score": 85,
            }
        ])

        results = list(adapter.fetch(""))
        sleep_records = [r for r in results if r.source_id.startswith("sleep/")]
        assert len(sleep_records) == 0

    def test_fetch_sleep_markdown_content(self, mock_all_health_endpoints):
        """fetch() generates markdown with sleep metrics."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/sleep", [
            {
                "id": "sleep-1",
                "date": "2026-03-07",
                "totalSleepMinutes": 480,
                "deepSleepMinutes": 120,
                "remSleepMinutes": 100,
                "lightSleepMinutes": 260,
                "efficiency": 0.92,
                "score": 85,
            }
        ])

        results = list(adapter.fetch(""))
        sleep_records = [r for r in results if r.source_id.startswith("sleep/")]
        markdown = sleep_records[0].markdown

        assert "Sleep Summary" in markdown
        assert "480" in markdown  # Total sleep
        assert "120" in markdown  # Deep sleep
        assert "100" in markdown  # REM sleep
        assert "260" in markdown  # Light sleep
        assert "92" in markdown or "92.0" in markdown  # Efficiency as percentage
        assert "85" in markdown  # Score


class TestAppleHealthAdapterActivityIncremental:
    """Tests for activity endpoint incremental fetch."""

    def test_fetch_activity_incremental_with_since(self, mock_all_health_endpoints):
        """fetch() passes 'since' parameter to activity endpoint."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/activity", [
            {
                "id": "activity-1",
                "date": "2026-03-07",
                "steps": 10000,
                "activeCalories": 500.0,
                "totalCalories": 2000.0,
                "activeMinutes": 60,
                "sedentaryMinutes": 480,
                "distanceMeters": 7500.0,
            }
        ])

        list(adapter.fetch("2026-03-06T10:00:00Z"))

        # Find activity request in mock requests
        activity_request = None
        for req in mock_all_health_endpoints.requests:
            if "/activity" in req["url"]:
                activity_request = req
                break

        assert activity_request is not None
        assert activity_request["params"]["since"] == "2026-03-06T10:00:00Z"

    def test_fetch_activity_missing_required_field_skips(self, mock_all_health_endpoints):
        """fetch() skips activity records with missing required fields."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/activity", [
            {
                "id": "activity-1",
                # Missing 'date'
                "steps": 10000,
                "activeCalories": 500.0,
                "totalCalories": 2000.0,
                "activeMinutes": 60,
                "sedentaryMinutes": 480,
                "distanceMeters": 7500.0,
            }
        ])

        results = list(adapter.fetch(""))
        activity_records = [r for r in results if r.source_id.startswith("activity/")]
        assert len(activity_records) == 0

    def test_fetch_activity_markdown_content(self, mock_all_health_endpoints):
        """fetch() generates markdown with activity metrics."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/activity", [
            {
                "id": "activity-1",
                "date": "2026-03-07",
                "steps": 10000,
                "activeCalories": 500.0,
                "totalCalories": 2000.0,
                "activeMinutes": 60,
                "sedentaryMinutes": 480,
                "distanceMeters": 7500.0,
            }
        ])

        results = list(adapter.fetch(""))
        activity_records = [r for r in results if r.source_id.startswith("activity/")]
        markdown = activity_records[0].markdown

        assert "Activity Summary" in markdown
        assert "10,000" in markdown  # Steps formatted with comma
        assert "500" in markdown  # Active calories
        assert "2000" in markdown  # Total calories
        assert "60" in markdown  # Active minutes
        assert "480" in markdown  # Sedentary minutes
        assert "7.50" in markdown or "7.5" in markdown  # Distance in km


class TestAppleHealthAdapterHRVIncremental:
    """Tests for HRV endpoint incremental fetch."""

    def test_fetch_hrv_incremental_with_since(self, mock_all_health_endpoints):
        """fetch() passes 'since' parameter to HRV endpoint."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/hrv", [
            {
                "id": "hrv-1",
                "date": "2026-03-07",
                "avgHrv": 45.5,
                "restingHeartRate": 58.0,
                "bodyTemperatureDeviation": 0.2,
            }
        ])

        list(adapter.fetch("2026-03-06T10:00:00Z"))

        # Find HRV request in mock requests
        hrv_request = None
        for req in mock_all_health_endpoints.requests:
            if "/hrv" in req["url"]:
                hrv_request = req
                break

        assert hrv_request is not None
        assert hrv_request["params"]["since"] == "2026-03-06T10:00:00Z"

    def test_fetch_hrv_missing_required_field_skips(self, mock_all_health_endpoints):
        """fetch() skips HRV records with missing required fields."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/hrv", [
            {
                "id": "hrv-1",
                # Missing 'avgHrv'
                "date": "2026-03-07",
                "restingHeartRate": 58.0,
                "bodyTemperatureDeviation": 0.2,
            }
        ])

        results = list(adapter.fetch(""))
        hrv_records = [r for r in results if r.source_id.startswith("hrv/")]
        assert len(hrv_records) == 0

    def test_fetch_hrv_markdown_content(self, mock_all_health_endpoints):
        """fetch() generates markdown with HRV metrics."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/hrv", [
            {
                "id": "hrv-1",
                "date": "2026-03-07",
                "avgHrv": 45.5,
                "restingHeartRate": 58.0,
                "bodyTemperatureDeviation": 0.2,
            }
        ])

        results = list(adapter.fetch(""))
        hrv_records = [r for r in results if r.source_id.startswith("hrv/")]
        markdown = hrv_records[0].markdown

        assert "HRV / Readiness" in markdown
        assert "45.5" in markdown  # Avg HRV
        assert "58" in markdown  # Resting heart rate
        assert "0.2" in markdown  # Temperature deviation


class TestAppleHealthAdapterHeartRateIncremental:
    """Tests for heart rate endpoint incremental fetch."""

    def test_fetch_heart_rate_incremental_with_since(self, mock_all_health_endpoints):
        """fetch() passes 'since' parameter to heart_rate endpoint."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/heart_rate", [
            {
                "timestamp": "2026-03-07T10:15:00+00:00",
                "bpm": 72,
                "context": "resting",
            }
        ])

        list(adapter.fetch("2026-03-06T10:00:00Z"))

        # Find heart_rate request in mock requests
        hr_request = None
        for req in mock_all_health_endpoints.requests:
            if "/heart_rate" in req["url"]:
                hr_request = req
                break

        assert hr_request is not None
        assert hr_request["params"]["since"] == "2026-03-06T10:00:00Z"

    def test_fetch_heart_rate_missing_required_field_skips(self, mock_all_health_endpoints):
        """fetch() skips malformed heart rate samples."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/heart_rate", [
            {
                # Missing 'timestamp'
                "bpm": 72,
                "context": "resting",
            }
        ])

        results = list(adapter.fetch(""))
        hr_records = [r for r in results if r.source_id.startswith("heart_rate/")]
        # Should have no records since the only sample was malformed
        assert len(hr_records) == 0

    def test_fetch_heart_rate_markdown_content(self, mock_all_health_endpoints):
        """fetch() generates markdown with heart rate metrics."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/heart_rate", [
            {
                "timestamp": "2026-03-07T10:15:00+00:00",
                "bpm": 72,
                "context": "resting",
            },
            {
                "timestamp": "2026-03-07T10:30:00+00:00",
                "bpm": 75,
                "context": "resting",
            },
            {
                "timestamp": "2026-03-07T10:45:00+00:00",
                "bpm": 68,
                "context": "resting",
            }
        ])

        results = list(adapter.fetch(""))
        hr_records = [r for r in results if r.source_id.startswith("heart_rate/")]
        markdown = hr_records[0].markdown

        assert "Heart Rate" in markdown
        assert "72" in markdown or "71" in markdown  # Average (72+75+68)/3 ≈ 71.67
        assert "68" in markdown  # Min
        assert "75" in markdown  # Max
        assert "3" in markdown  # Sample count


class TestAppleHealthAdapterSpO2Incremental:
    """Tests for SpO2 endpoint incremental fetch."""

    def test_fetch_spo2_incremental_with_since(self, mock_all_health_endpoints):
        """fetch() passes 'since' parameter to SpO2 endpoint."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/spo2", [
            {
                "id": "spo2-1",
                "date": "2026-03-07",
                "avgSpo2": 97.5,
                "breathingDisturbanceIndex": 2.1,
            }
        ])

        list(adapter.fetch("2026-03-06T10:00:00Z"))

        # Find SpO2 request in mock requests
        spo2_request = None
        for req in mock_all_health_endpoints.requests:
            if "/spo2" in req["url"]:
                spo2_request = req
                break

        assert spo2_request is not None
        assert spo2_request["params"]["since"] == "2026-03-06T10:00:00Z"

    def test_fetch_spo2_missing_required_field_skips(self, mock_all_health_endpoints):
        """fetch() skips SpO2 records with missing required fields."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/spo2", [
            {
                # Missing 'avgSpo2'
                "id": "spo2-1",
                "date": "2026-03-07",
                "breathingDisturbanceIndex": 2.1,
            }
        ])

        results = list(adapter.fetch(""))
        spo2_records = [r for r in results if r.source_id.startswith("spo2/")]
        assert len(spo2_records) == 0

    def test_fetch_spo2_markdown_content(self, mock_all_health_endpoints):
        """fetch() generates markdown with SpO2 metrics."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/spo2", [
            {
                "id": "spo2-1",
                "date": "2026-03-07",
                "avgSpo2": 97.5,
                "breathingDisturbanceIndex": 2.1,
            }
        ])

        results = list(adapter.fetch(""))
        spo2_records = [r for r in results if r.source_id.startswith("spo2/")]
        markdown = spo2_records[0].markdown

        assert "Blood Oxygen" in markdown
        assert "97.5" in markdown  # Avg SpO2
        assert "2.1" in markdown  # Breathing disturbance index


class TestAppleHealthAdapterMindfulnessIncremental:
    """Tests for mindfulness endpoint incremental fetch."""

    def test_fetch_mindfulness_incremental_with_since(self, mock_all_health_endpoints):
        """fetch() passes 'since' parameter to mindfulness endpoint."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/mindfulness", [
            {
                "id": "mindfulness-1",
                "startDate": "2026-03-07T18:00:00+00:00",
                "endDate": "2026-03-07T18:10:00+00:00",
                "durationSeconds": 600,
                "sessionType": "meditation",
                "mood": "calm",
                "tags": ["evening", "relaxation"],
            }
        ])

        list(adapter.fetch("2026-03-06T10:00:00Z"))

        # Find mindfulness request in mock requests
        mindfulness_request = None
        for req in mock_all_health_endpoints.requests:
            if "/mindfulness" in req["url"]:
                mindfulness_request = req
                break

        assert mindfulness_request is not None
        assert mindfulness_request["params"]["since"] == "2026-03-06T10:00:00Z"

    def test_fetch_mindfulness_missing_required_field_skips(self, mock_all_health_endpoints):
        """fetch() skips mindfulness records with missing required fields."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/mindfulness", [
            {
                # Missing 'sessionType'
                "id": "mindfulness-1",
                "startDate": "2026-03-07T18:00:00+00:00",
                "endDate": "2026-03-07T18:10:00+00:00",
                "durationSeconds": 600,
                "mood": "calm",
                "tags": ["evening", "relaxation"],
            }
        ])

        results = list(adapter.fetch(""))
        mindfulness_records = [r for r in results if r.source_id.startswith("mindfulness/")]
        assert len(mindfulness_records) == 0

    def test_fetch_mindfulness_markdown_content(self, mock_all_health_endpoints):
        """fetch() generates markdown with mindfulness metrics."""
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/mindfulness", [
            {
                "id": "mindfulness-1",
                "startDate": "2026-03-07T18:00:00+00:00",
                "endDate": "2026-03-07T18:10:00+00:00",
                "durationSeconds": 600,
                "sessionType": "meditation",
                "mood": "calm",
                "tags": ["evening", "relaxation"],
            }
        ])

        results = list(adapter.fetch(""))
        mindfulness_records = [r for r in results if r.source_id.startswith("mindfulness/")]
        markdown = mindfulness_records[0].markdown

        assert "Meditation Session" in markdown
        assert "10" in markdown  # Duration in minutes
        assert "calm" in markdown  # Mood
        assert "evening" in markdown  # Tags
        assert "relaxation" in markdown  # Tags


class TestAppleHealthAdapterNetworkErrors:
    """Tests for AppleHealthAdapter network error handling."""

    def test_fetch_network_error_request_error_resilience(self, mock_all_health_endpoints):
        """fetch() handles RequestError (network errors) gracefully and continues."""
        import httpx

        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        # Configure workouts endpoint to raise RequestError (network failure)
        def raise_request_error(*args, **kwargs):
            raise httpx.RequestError("Connection refused")

        # Mock the mock_get to raise for workouts but return data for sleep
        original_call = mock_all_health_endpoints.__call__

        def patched_call(url, params=None, headers=None, timeout=None):
            if "workouts" in url:
                raise httpx.RequestError("Connection refused")
            return original_call(url, params=params, headers=headers, timeout=timeout)

        # Set up proper responses for other endpoints
        mock_all_health_endpoints.__call__ = patched_call

        # Setup a successful sleep response
        mock_all_health_endpoints.set_response("http://127.0.0.1:7124/sleep", [
            {
                "id": "sleep-1",
                "date": "2026-03-07",
                "totalSleepMinutes": 480,
                "deepSleepMinutes": 120,
                "remSleepMinutes": 100,
                "lightSleepMinutes": 260,
                "efficiency": 0.92,
                "score": 90,
            }
        ])

        # Should not raise; continues after workouts failure
        results = list(adapter.fetch(""))

        # Should have sleep results despite workouts endpoint failing
        sleep_results = [r for r in results if "sleep" in r.source_id.lower()]
        assert len(sleep_results) > 0

    def test_fetch_dns_resolution_error_all_endpoints_fail(self):
        """fetch() raises RuntimeError when ALL endpoints fail with network errors."""
        import httpx

        adapter = AppleHealthAdapter(api_url="http://invalid-host-xyz.local", api_key="test-token")

        # Create a mock that always raises RequestError
        from unittest.mock import MagicMock

        def mock_get_with_dns_error(*args, **kwargs):
            raise httpx.RequestError("Name resolution failed")

        # Patch httpx.get at module level
        import context_library.adapters.apple_health
        original_get = context_library.adapters.apple_health.httpx.get
        context_library.adapters.apple_health.httpx.get = mock_get_with_dns_error

        try:
            # Should raise RuntimeError when all endpoints fail
            with pytest.raises(RuntimeError, match="All.*endpoints failed"):
                list(adapter.fetch(""))
        finally:
            # Restore original
            context_library.adapters.apple_health.httpx.get = original_get
