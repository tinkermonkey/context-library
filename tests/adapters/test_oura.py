"""Tests for the OuraAdapter."""

import pytest

from context_library.adapters.oura import OuraAdapter
from context_library.adapters.base import PartialFetchError
from context_library.storage.models import Domain, PollStrategy, NormalizedContent, HealthMetadata


class TestOuraAdapterInitialization:
    """Tests for OuraAdapter initialization."""

    def test_init_default_parameters(self):
        """__init__ uses default parameters when not provided."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")
        assert adapter._api_url == "http://localhost:8000"
        assert adapter._api_key == "test-token"
        assert adapter._device_id == "default"

    def test_init_requires_api_key(self):
        """__init__ raises ValueError when api_key is empty."""
        with pytest.raises(ValueError, match="api_key is required"):
            OuraAdapter(api_url="http://localhost:8000", api_key="")

    def test_init_custom_parameters(self):
        """__init__ accepts and stores custom parameters."""
        adapter = OuraAdapter(
            api_url="http://localhost:8000",
            api_key="test_key",
            device_id="oura-ring-gen3",
        )
        assert adapter._api_url == "http://localhost:8000"
        assert adapter._api_key == "test_key"
        assert adapter._device_id == "oura-ring-gen3"

    def test_init_strips_trailing_slash_from_url(self):
        """__init__ strips trailing slash from api_url."""
        adapter = OuraAdapter(api_url="http://localhost:8000/", api_key="test-token")
        assert adapter._api_url == "http://localhost:8000"

    def test_init_no_trailing_slash(self):
        """__init__ leaves api_url unchanged if no trailing slash."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")
        assert adapter._api_url == "http://localhost:8000"


class TestOuraAdapterProperties:
    """Tests for OuraAdapter properties."""

    def test_adapter_id_format_default(self):
        """adapter_id has correct format: oura:{device_id}."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")
        assert adapter.adapter_id == "oura:default"

    def test_adapter_id_format_custom_device(self):
        """adapter_id uses custom device_id."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token", device_id="oura-ring-gen3")
        assert adapter.adapter_id == "oura:oura-ring-gen3"

    def test_adapter_id_deterministic(self):
        """adapter_id is deterministic for the same configuration."""
        adapter1 = OuraAdapter(api_url="http://localhost:8000", api_key="test-token", device_id="ring-1")
        adapter2 = OuraAdapter(api_url="http://localhost:8000", api_key="test-token", device_id="ring-1")
        assert adapter1.adapter_id == adapter2.adapter_id

    def test_different_devices_different_ids(self):
        """Different device IDs produce different adapter_ids."""
        adapter1 = OuraAdapter(api_url="http://localhost:8000", api_key="test-token", device_id="ring-1")
        adapter2 = OuraAdapter(api_url="http://localhost:8000", api_key="test-token", device_id="ring-2")
        assert adapter1.adapter_id != adapter2.adapter_id

    def test_domain_property(self):
        """domain property returns Domain.HEALTH."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")
        assert adapter.domain == Domain.HEALTH

    def test_poll_strategy_property(self):
        """poll_strategy property returns PollStrategy.PULL."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")
        assert adapter.poll_strategy == PollStrategy.PULL

    def test_normalizer_version_property(self):
        """normalizer_version property returns '1.0.0'."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")
        assert adapter.normalizer_version == "1.0.0"


class TestOuraAdapterFetch:
    """Tests for OuraAdapter.fetch() method."""

    def test_fetch_single_sleep_record(self, mock_all_oura_endpoints):
        """fetch() yields NormalizedContent for a single sleep record."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sleep", [
            {
                "id": "sleep-1",
                "date": "2026-03-07",
                "score": 85,
                "totalSleepMinutes": 480,
                "deepSleepMinutes": 120,
                "remSleepMinutes": 100,
                "lightSleepMinutes": 260,
                "efficiency": 0.92,
            }
        ])

        results = list(adapter.fetch(""))
        assert len(results) >= 1
        sleep_records = [r for r in results if "sleep" in r.source_id]
        assert len(sleep_records) == 1
        assert isinstance(sleep_records[0], NormalizedContent)
        assert sleep_records[0].source_id == "oura/sleep/sleep-1"
        assert "Sleep Summary" in sleep_records[0].markdown

    def test_fetch_single_readiness_record(self, mock_all_oura_endpoints):
        """fetch() yields NormalizedContent for a single readiness record."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/readiness", [
            {
                "id": "readiness-1",
                "date": "2026-03-07",
                "score": 75,
                "avgHrv": 45.5,
                "restingHeartRate": 58.0,
                "bodyTemperatureDeviation": 0.2,
            }
        ])

        results = list(adapter.fetch(""))
        readiness_records = [r for r in results if "readiness" in r.source_id]
        assert len(readiness_records) == 1
        assert readiness_records[0].source_id == "oura/readiness/readiness-1"
        assert "Readiness Summary" in readiness_records[0].markdown

    def test_fetch_single_activity_record(self, mock_all_oura_endpoints):
        """fetch() yields NormalizedContent for a single activity record."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/activity", [
            {
                "id": "activity-1",
                "date": "2026-03-07",
                "steps": 8500,
                "activeCalories": 450.0,
                "totalCalories": 2100.0,
                "activeMinutes": 60,
                "sedentaryMinutes": 400,
                "distanceMeters": 6000.0,
            }
        ])

        results = list(adapter.fetch(""))
        activity_records = [r for r in results if "activity" in r.source_id]
        assert len(activity_records) == 1
        assert activity_records[0].source_id == "oura/activity/activity-1"
        assert "Activity Summary" in activity_records[0].markdown

    def test_fetch_single_workout(self, mock_all_oura_endpoints):
        """fetch() yields NormalizedContent for a single workout."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/workouts", [
            {
                "id": "workout-1",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "activityType": "running",
                "calories": 250.0,
                "distanceMeters": 5000.0,
                "avgHeartRate": 145.0,
                "maxHeartRate": 165.0,
                "intensity": "high",
            }
        ])

        results = list(adapter.fetch(""))
        workout_records = [r for r in results if "workout" in r.source_id]
        assert len(workout_records) == 1
        assert workout_records[0].source_id == "oura/workout/workout-1"
        assert "Running" in workout_records[0].markdown

    def test_fetch_single_spo2_record(self, mock_all_oura_endpoints):
        """fetch() yields NormalizedContent for a single SpO2 record."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/spo2", [
            {
                "id": "spo2-1",
                "date": "2026-03-07",
                "avgSpo2": 96.5,
                "breathingDisturbanceIndex": 2.3,
            }
        ])

        results = list(adapter.fetch(""))
        spo2_records = [r for r in results if "spo2" in r.source_id]
        assert len(spo2_records) == 1
        assert spo2_records[0].source_id == "oura/spo2/spo2-1"
        assert "Blood Oxygen" in spo2_records[0].markdown

    def test_fetch_single_tag(self, mock_all_oura_endpoints):
        """fetch() yields NormalizedContent for a single user health tag."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/tags", [
            {
                "id": "tag-1",
                "date": "2026-03-07",
                "text": "Great sleep quality",
                "tags": ["sleep", "quality"],
            }
        ])

        results = list(adapter.fetch(""))
        tag_records = [r for r in results if "tag" in r.source_id]
        assert len(tag_records) == 1
        assert tag_records[0].source_id == "oura/tag/tag-1"
        assert "Health Tag" in tag_records[0].markdown

    def test_fetch_single_mindfulness_session(self, mock_all_oura_endpoints):
        """fetch() yields NormalizedContent for a single mindfulness session."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sessions", [
            {
                "id": "session-1",
                "startDate": "2026-03-07T08:00:00+00:00",
                "endDate": "2026-03-07T08:10:00+00:00",
                "durationSeconds": 600,
                "sessionType": "meditation",
                "mood": "calm",
                "tags": ["meditation", "morning"],
            }
        ])

        results = list(adapter.fetch(""))
        session_records = [r for r in results if "session" in r.source_id]
        assert len(session_records) == 1
        assert session_records[0].source_id == "oura/session/session-1"
        assert "Meditation Session" in session_records[0].markdown

    def test_fetch_incremental_with_since(self, mock_all_oura_endpoints):
        """fetch() passes 'since' query parameter for incremental fetch."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        list(adapter.fetch("2026-03-06T10:00:00Z"))

        # Verify the first request (sleep) was made with the 'since' parameter
        request = mock_all_oura_endpoints.requests[0]
        assert request["params"]["since"] == "2026-03-06T10:00:00Z"

    def test_fetch_with_api_key_auth(self, mock_all_oura_endpoints):
        """fetch() sends Authorization header when api_key is provided."""
        adapter = OuraAdapter(
            api_url="http://localhost:8000",
            api_key="test_token_123"
        )

        list(adapter.fetch(""))

        # Verify the first request (sleep) was made with Authorization header
        request = mock_all_oura_endpoints.requests[0]
        assert request["headers"]["Authorization"] == "Bearer test_token_123"

    def test_fetch_health_metadata_contains_required_fields(self, mock_all_oura_endpoints):
        """fetch() produces HealthMetadata that passes model_validate."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sleep", [
            {
                "id": "sleep-1",
                "date": "2026-03-07",
                "score": 85,
                "totalSleepMinutes": 480,
                "deepSleepMinutes": 120,
                "remSleepMinutes": 100,
                "lightSleepMinutes": 260,
                "efficiency": 0.92,
            }
        ])

        results = list(adapter.fetch(""))
        sleep_records = [r for r in results if "sleep" in r.source_id]
        metadata_dict = sleep_records[0].structural_hints.extra_metadata

        # This should not raise if HealthMetadata validation passes
        metadata = HealthMetadata.model_validate(metadata_dict)
        assert metadata.record_id == "sleep-1"
        assert metadata.health_type == "sleep_summary"
        assert metadata.date == "2026-03-07"
        assert metadata.duration_minutes == 480
        assert metadata.source_type == "oura"

    def test_fetch_health_type_per_endpoint(self, mock_all_oura_endpoints):
        """fetch() produces correct health_type for each endpoint."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        # Configure each endpoint with a sample record
        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sleep", [
            {"id": "sleep-1", "date": "2026-03-07", "totalSleepMinutes": 480}
        ])
        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/readiness", [
            {"id": "read-1", "date": "2026-03-07", "score": 75, "avgHrv": 45.5}
        ])
        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/activity", [
            {"id": "act-1", "date": "2026-03-07", "steps": 8500}
        ])
        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/workouts", [
            {"id": "wo-1", "startDate": "2026-03-07T10:00:00+00:00", "endDate": "2026-03-07T10:30:00+00:00",
             "durationSeconds": 1800, "activityType": "running"}
        ])
        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/spo2", [
            {"id": "spo2-1", "date": "2026-03-07", "avgSpo2": 96.5}
        ])
        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/tags", [
            {"id": "tag-1", "date": "2026-03-07", "text": "Good day"}
        ])
        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sessions", [
            {"id": "sess-1", "startDate": "2026-03-07T08:00:00+00:00", "endDate": "2026-03-07T08:10:00+00:00",
             "durationSeconds": 600, "sessionType": "meditation"}
        ])
        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/heart_rate", [])

        results = list(adapter.fetch(""))
        health_types = [r.structural_hints.extra_metadata["health_type"] for r in results]

        assert "sleep_summary" in health_types
        assert "readiness_summary" in health_types
        assert "activity_summary" in health_types
        assert "workout_session" in health_types
        assert "spo2_summary" in health_types
        assert "user_health_tag" in health_types
        assert "mindfulness_session" in health_types

    def test_fetch_source_type_is_oura(self, mock_all_oura_endpoints):
        """fetch() sets source_type='oura' for all records."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sleep", [
            {"id": "sleep-1", "date": "2026-03-07", "totalSleepMinutes": 480}
        ])

        results = list(adapter.fetch(""))
        sleep_records = [r for r in results if "sleep" in r.source_id]
        assert sleep_records[0].structural_hints.extra_metadata["source_type"] == "oura"

    def test_fetch_heart_rate_hourly_windowing(self, mock_all_oura_endpoints):
        """fetch() groups heart rate samples into hourly windows."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/heart_rate", [
            {"timestamp": "2026-03-07T10:00:00+00:00", "bpm": 65},
            {"timestamp": "2026-03-07T10:15:00+00:00", "bpm": 68},
            {"timestamp": "2026-03-07T10:30:00+00:00", "bpm": 70},
            {"timestamp": "2026-03-07T11:00:00+00:00", "bpm": 72},
            {"timestamp": "2026-03-07T11:15:00+00:00", "bpm": 75},
        ])

        results = list(adapter.fetch(""))
        heart_rate_records = [r for r in results if "heart_rate" in r.source_id]

        # Should have 2 hourly windows: one for hour 10, one for hour 11
        assert len(heart_rate_records) == 2
        assert heart_rate_records[0].source_id == "oura/heart_rate/2026-03-07T10"
        assert heart_rate_records[1].source_id == "oura/heart_rate/2026-03-07T11"

    def test_fetch_http_error_logged_continues(self, mock_all_oura_endpoints):
        """fetch() logs HTTP errors and surfaces partial failures via PartialFetchError."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        # Set sleep to error, but activity to succeed
        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sleep", {}, status_code=500)
        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/activity", [
            {
                "id": "activity-1",
                "date": "2026-03-07",
                "steps": 8500,
            }
        ])

        # Should yield activity data but raise PartialFetchError for the failed sleep endpoint
        with pytest.raises(PartialFetchError) as exc_info:
            list(adapter.fetch(""))

        # Verify the error indicates which endpoint failed
        assert "/oura/sleep" in exc_info.value.failed_endpoints
        assert len(exc_info.value.failed_endpoints) == 1

    def test_fetch_invalid_response_schema_logged_continues(self, mock_all_oura_endpoints):
        """fetch() logs invalid response schema and surfaces partial failure via PartialFetchError."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        # Set sleep endpoint to return dict instead of list (invalid schema)
        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sleep", {"sleep": []})
        # Set activity endpoint to return valid data
        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/activity", [
            {
                "id": "activity-1",
                "date": "2026-03-07",
                "steps": 8500,
            }
        ])

        # Should yield activity data but raise PartialFetchError for the invalid sleep endpoint
        with pytest.raises(PartialFetchError) as exc_info:
            list(adapter.fetch(""))

        # Verify the error indicates which endpoint failed
        assert "/oura/sleep" in exc_info.value.failed_endpoints
        assert len(exc_info.value.failed_endpoints) == 1

    def test_fetch_missing_required_field_skips_record(self, mock_all_oura_endpoints):
        """fetch() skips and logs records with missing required fields."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sleep", [
            {
                "id": "sleep-1",
                # Missing 'date'
                "totalSleepMinutes": 480,
            }
        ])

        # Should not raise, just skip the malformed record
        results = list(adapter.fetch(""))
        sleep_records = [r for r in results if "sleep" in r.source_id]
        assert len(sleep_records) == 0

    def test_fetch_missing_id_field_skips_record(self, mock_all_oura_endpoints):
        """fetch() skips and logs records with missing 'id' field."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sleep", [
            {
                # Missing 'id'
                "date": "2026-03-07",
                "totalSleepMinutes": 480,
            }
        ])

        # Should not raise, just skip the malformed record
        results = list(adapter.fetch(""))
        sleep_records = [r for r in results if "sleep" in r.source_id]
        assert len(sleep_records) == 0

    def test_fetch_empty_id_skips_record(self, mock_all_oura_endpoints):
        """fetch() skips and logs records with empty 'id'."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sleep", [
            {
                "id": "",  # Empty
                "date": "2026-03-07",
                "totalSleepMinutes": 480,
            }
        ])

        # Should not raise, just skip the malformed record
        results = list(adapter.fetch(""))
        sleep_records = [r for r in results if "sleep" in r.source_id]
        assert len(sleep_records) == 0

    def test_fetch_invalid_numeric_type_skips_record(self, mock_all_oura_endpoints):
        """fetch() skips records with invalid numeric field types."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sleep", [
            {
                "id": "sleep-1",
                "date": "2026-03-07",
                "totalSleepMinutes": "not a number",  # Should be numeric
            }
        ])

        # Should not raise, just skip the malformed record
        results = list(adapter.fetch(""))
        sleep_records = [r for r in results if "sleep" in r.source_id]
        assert len(sleep_records) == 0

    def test_fetch_malformed_record_skipped_continues(self, mock_all_oura_endpoints):
        """fetch() skips malformed records and continues to next."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sleep", [
            {
                "id": "sleep-1",
                "date": "2026-03-07",
                "totalSleepMinutes": 480,
            },
            {
                "id": "",  # Malformed
                "date": "2026-03-08",
                "totalSleepMinutes": 500,
            },
            {
                "id": "sleep-3",
                "date": "2026-03-09",
                "totalSleepMinutes": 450,
            },
        ])

        results = list(adapter.fetch(""))
        sleep_records = [r for r in results if "sleep" in r.source_id]
        # Should have 2 results, skipping the malformed one in the middle
        assert len(sleep_records) == 2
        assert sleep_records[0].source_id == "oura/sleep/sleep-1"
        assert sleep_records[1].source_id == "oura/sleep/sleep-3"


class TestOuraAdapterImportGuard:
    """Tests for import guard and error handling."""

    def test_import_error_without_httpx(self, monkeypatch):
        """OuraAdapter raises ImportError if httpx is not installed."""
        monkeypatch.setattr(
            "context_library.adapters.oura.HAS_HTTPX",
            False
        )

        with pytest.raises(ImportError, match="Oura adapter requires"):
            OuraAdapter(api_url="http://localhost:8000", api_key="test-token")


class TestOuraAdapterMarkdownGeneration:
    """Tests for markdown generation in fetch()."""

    def test_sleep_markdown_includes_total_sleep(self, mock_all_oura_endpoints):
        """Sleep markdown includes total sleep minutes."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sleep", [
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
        sleep_records = [r for r in results if "sleep" in r.source_id]
        assert "Total sleep: 480 minutes" in sleep_records[0].markdown

    def test_sleep_efficiency_decimal_range(self, mock_all_oura_endpoints):
        """Sleep markdown formats efficiency correctly when in 0.0–1.0 decimal range."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sleep", [
            {
                "id": "sleep-1",
                "date": "2026-03-07",
                "totalSleepMinutes": 480,
                "deepSleepMinutes": 120,
                "remSleepMinutes": 100,
                "lightSleepMinutes": 260,
                "efficiency": 0.95,  # Decimal range
                "score": 85,
            }
        ])

        results = list(adapter.fetch(""))
        sleep_records = [r for r in results if "sleep" in r.source_id]
        markdown = sleep_records[0].markdown

        # 0.95 should format as 95.0%
        assert "95.0%" in markdown

    def test_sleep_efficiency_percentage_range(self, mock_all_oura_endpoints):
        """Sleep markdown formats efficiency correctly when in 0–100 percentage range."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sleep", [
            {
                "id": "sleep-1",
                "date": "2026-03-07",
                "totalSleepMinutes": 480,
                "deepSleepMinutes": 120,
                "remSleepMinutes": 100,
                "lightSleepMinutes": 260,
                "efficiency": 92,  # Percentage range (0–100)
                "score": 85,
            }
        ])

        results = list(adapter.fetch(""))
        sleep_records = [r for r in results if "sleep" in r.source_id]
        markdown = sleep_records[0].markdown

        # 92 should format as 92.0%
        assert "92.0%" in markdown

    def test_sleep_efficiency_boundary_100_percent(self, mock_all_oura_endpoints):
        """Sleep markdown formats efficiency correctly at 100% boundary (1.0)."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sleep", [
            {
                "id": "sleep-1",
                "date": "2026-03-07",
                "totalSleepMinutes": 480,
                "deepSleepMinutes": 120,
                "remSleepMinutes": 100,
                "lightSleepMinutes": 260,
                "efficiency": 1.0,  # Boundary: 100%
                "score": 85,
            }
        ])

        results = list(adapter.fetch(""))
        sleep_records = [r for r in results if "sleep" in r.source_id]
        markdown = sleep_records[0].markdown

        # 1.0 should format as 100.0%
        assert "100.0%" in markdown

    def test_readiness_markdown_includes_score(self, mock_all_oura_endpoints):
        """Readiness markdown includes score."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/readiness", [
            {
                "id": "readiness-1",
                "date": "2026-03-07",
                "score": 75,
                "avgHrv": 45.5,
            }
        ])

        results = list(adapter.fetch(""))
        readiness_records = [r for r in results if "readiness" in r.source_id]
        assert "Score: 75" in readiness_records[0].markdown

    def test_activity_markdown_includes_steps(self, mock_all_oura_endpoints):
        """Activity markdown includes steps."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/activity", [
            {
                "id": "activity-1",
                "date": "2026-03-07",
                "steps": 8500,
                "activeCalories": 450.0,
            }
        ])

        results = list(adapter.fetch(""))
        activity_records = [r for r in results if "activity" in r.source_id]
        assert "Steps: 8,500" in activity_records[0].markdown

    def test_workout_markdown_includes_activity_type(self, mock_all_oura_endpoints):
        """Workout markdown includes activity type capitalized."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/workouts", [
            {
                "id": "workout-1",
                "startDate": "2026-03-07T10:00:00+00:00",
                "endDate": "2026-03-07T10:30:00+00:00",
                "durationSeconds": 1800,
                "activityType": "running",
                "calories": 250.0,
            }
        ])

        results = list(adapter.fetch(""))
        workout_records = [r for r in results if "workout" in r.source_id]
        assert "**Running**" in workout_records[0].markdown

    def test_heart_rate_markdown_includes_stats(self, mock_all_oura_endpoints):
        """Heart rate markdown includes avg, min, max BPM."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/heart_rate", [
            {"timestamp": "2026-03-07T10:00:00+00:00", "bpm": 65},
            {"timestamp": "2026-03-07T10:15:00+00:00", "bpm": 70},
            {"timestamp": "2026-03-07T10:30:00+00:00", "bpm": 75},
        ])

        results = list(adapter.fetch(""))
        heart_rate_records = [r for r in results if "heart_rate" in r.source_id]
        markdown = heart_rate_records[0].markdown
        assert "Average:" in markdown
        assert "Min:" in markdown
        assert "Max:" in markdown
        assert "Samples:" in markdown

    def test_spo2_markdown_includes_percentage(self, mock_all_oura_endpoints):
        """SpO2 markdown includes oxygen saturation percentage."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/spo2", [
            {
                "id": "spo2-1",
                "date": "2026-03-07",
                "avgSpo2": 96.5,
            }
        ])

        results = list(adapter.fetch(""))
        spo2_records = [r for r in results if "spo2" in r.source_id]
        assert "Average: 96.5%" in spo2_records[0].markdown

    def test_tag_markdown_includes_text(self, mock_all_oura_endpoints):
        """Tag markdown includes tag text."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/tags", [
            {
                "id": "tag-1",
                "date": "2026-03-07",
                "text": "Great sleep quality",
                "tags": ["sleep", "quality"],
            }
        ])

        results = list(adapter.fetch(""))
        tag_records = [r for r in results if "tag" in r.source_id]
        assert "Great sleep quality" in tag_records[0].markdown

    def test_session_markdown_includes_type_and_duration(self, mock_all_oura_endpoints):
        """Session markdown includes session type and duration."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sessions", [
            {
                "id": "session-1",
                "startDate": "2026-03-07T08:00:00+00:00",
                "endDate": "2026-03-07T08:10:00+00:00",
                "durationSeconds": 600,
                "sessionType": "meditation",
                "mood": "calm",
            }
        ])

        results = list(adapter.fetch(""))
        session_records = [r for r in results if "session" in r.source_id]
        markdown = session_records[0].markdown
        assert "Meditation Session" in markdown
        assert "Duration: 10 minutes" in markdown

    def test_structural_hints_has_headings_false(self, mock_all_oura_endpoints):
        """StructuralHints.has_headings is False (no heading-level markers in markdown)."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sleep", [
            {
                "id": "sleep-1",
                "date": "2026-03-07",
                "totalSleepMinutes": 480,
            }
        ])

        results = list(adapter.fetch(""))
        sleep_records = [r for r in results if "sleep" in r.source_id]
        content = sleep_records[0]

        # Verify has_headings is False because markdown uses **bold** not # headings
        assert content.structural_hints.has_headings is False

        # Verify markdown doesn't contain heading-level markers
        assert not content.markdown.startswith("#"), "Markdown should not start with #"
        assert "\n#" not in content.markdown, "Markdown should not contain heading markers"

        # Verify markdown contains bold and lists (what actually exists)
        assert content.structural_hints.has_lists is True
        assert "**" in content.markdown, "Markdown should contain bold text"

    def test_structural_hints_extra_metadata_contains_health_fields(self, mock_all_oura_endpoints):
        """StructuralHints.extra_metadata preserves health-specific fields."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sleep", [
            {
                "id": "sleep-123",
                "date": "2026-03-07",
                "totalSleepMinutes": 480,
                "deepSleepMinutes": 120,
            }
        ])

        results = list(adapter.fetch(""))
        sleep_records = [r for r in results if "sleep" in r.source_id]
        content = sleep_records[0]

        # Verify extra_metadata contains all health-specific fields
        metadata = content.structural_hints.extra_metadata
        assert metadata["record_id"] == "sleep-123"
        assert metadata["health_type"] == "sleep_summary"
        assert metadata["date"] == "2026-03-07"
        assert metadata["duration_minutes"] == 480
        assert metadata["deep_sleep_minutes"] == 120


class TestOuraAdapterNetworkErrors:
    """Tests for OuraAdapter network error handling."""

    def test_fetch_network_error_request_error_resilience(self, mock_all_oura_endpoints):
        """fetch() handles RequestError (network errors) gracefully and continues."""
        import httpx

        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        # Mock the mock_get to raise for sleep but return data for activity
        original_call = mock_all_oura_endpoints.__call__

        def patched_call(url, params=None, headers=None, timeout=None):
            if "sleep" in url:
                raise httpx.RequestError("Connection refused")
            return original_call(url, params=params, headers=headers, timeout=timeout)

        mock_all_oura_endpoints.__call__ = patched_call

        # Setup a successful activity response
        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/activity", [
            {
                "id": "activity-1",
                "date": "2026-03-07",
                "score": 75,
                "activeCalories": 350,
                "totalCalories": 2500,
                "steps": 8000,
                "totalDistance": 5000,
            }
        ])

        # Should not raise; continues after sleep failure
        results = list(adapter.fetch(""))

        # Should have activity results despite sleep endpoint failing
        activity_results = [r for r in results if "activity" in r.source_id.lower()]
        assert len(activity_results) > 0

    def test_fetch_dns_resolution_error_all_endpoints_fail(self, monkeypatch):
        """fetch() raises RuntimeError when ALL endpoints fail with network errors."""
        import httpx

        adapter = OuraAdapter(api_url="http://invalid-oura-host.local", api_key="test-token")

        def mock_get_with_dns_error(*args, **kwargs):
            raise httpx.RequestError("Name resolution failed")

        # Use monkeypatch for consistent error handling
        monkeypatch.setattr(
            "context_library.adapters.oura.httpx.get",
            mock_get_with_dns_error
        )

        # Should raise AllEndpointsFailedError when all endpoints fail
        from context_library.adapters.base import AllEndpointsFailedError
        with pytest.raises(AllEndpointsFailedError, match="All.*endpoints failed"):
            list(adapter.fetch(""))


class TestOuraAdapterAuthErrors:
    """Tests for OuraAdapter 401/403 authentication error handling."""

    def test_fetch_401_unauthorized_re_raised_immediately(self, monkeypatch):
        """fetch() re-raises 401 Unauthorized without wrapping in EndpointFetchError."""
        import httpx

        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="invalid-token")

        def mock_get_401(*args, **kwargs):
            # Simulate 401 response
            response = httpx.Response(
                status_code=401,
                content=b"Unauthorized",
                request=httpx.Request("GET", args[0] if args else "http://test"),
            )
            raise httpx.HTTPStatusError("401 Client Error", request=response.request, response=response)

        monkeypatch.setattr(
            "context_library.adapters.oura.httpx.get",
            mock_get_401
        )

        # Should raise HTTPStatusError, not EndpointFetchError
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            list(adapter.fetch(""))

        assert exc_info.value.response.status_code == 401

    def test_fetch_403_forbidden_re_raised_immediately(self, monkeypatch):
        """fetch() re-raises 403 Forbidden without wrapping in EndpointFetchError."""
        import httpx

        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        def mock_get_403(*args, **kwargs):
            # Simulate 403 response
            response = httpx.Response(
                status_code=403,
                content=b"Forbidden",
                request=httpx.Request("GET", args[0] if args else "http://test"),
            )
            raise httpx.HTTPStatusError("403 Client Error", request=response.request, response=response)

        monkeypatch.setattr(
            "context_library.adapters.oura.httpx.get",
            mock_get_403
        )

        # Should raise HTTPStatusError, not EndpointFetchError
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            list(adapter.fetch(""))

        assert exc_info.value.response.status_code == 403

    def test_fetch_401_on_single_endpoint_stops_all_fetching(self, monkeypatch):
        """fetch() immediately stops when 401 occurs on any endpoint."""
        import httpx

        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="invalid-token")
        call_count = [0]

        def mock_get_401_sleep_only(url, **kwargs):
            call_count[0] += 1
            if "sleep" in url:
                request = httpx.Request("GET", url)
                response = httpx.Response(
                    status_code=401,
                    content=b"Unauthorized",
                    request=request,
                )
                raise httpx.HTTPStatusError("401 Client Error", request=request, response=response)
            # Other endpoints would succeed, but we shouldn't get there
            request = httpx.Request("GET", url)
            return httpx.Response(status_code=200, content=b"[]", request=request)

        monkeypatch.setattr(
            "context_library.adapters.oura.httpx.get",
            mock_get_401_sleep_only
        )

        # fetch() should raise immediately on 401
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            list(adapter.fetch(""))

        assert exc_info.value.response.status_code == 401
        # Should have called at least once (hit the failing /oura/sleep endpoint - first in order)
        # and fewer than all 7 endpoints + heart_rate (would be 8+ if it continued)
        assert 1 <= call_count[0] < 8, f"Expected 1-7 calls, got {call_count[0]}"

    def test_fetch_403_on_single_endpoint_stops_all_fetching(self, monkeypatch):
        """fetch() immediately stops when 403 occurs on any endpoint."""
        import httpx

        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")
        call_count = [0]

        def mock_get_403_activity_only(url, **kwargs):
            call_count[0] += 1
            if "activity" in url:
                request = httpx.Request("GET", url)
                response = httpx.Response(
                    status_code=403,
                    content=b"Forbidden",
                    request=request,
                )
                raise httpx.HTTPStatusError("403 Client Error", request=request, response=response)
            # Other endpoints would succeed, but we shouldn't get there
            request = httpx.Request("GET", url)
            return httpx.Response(status_code=200, content=b"[]", request=request)

        monkeypatch.setattr(
            "context_library.adapters.oura.httpx.get",
            mock_get_403_activity_only
        )

        # fetch() should raise immediately on 403
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            list(adapter.fetch(""))

        assert exc_info.value.response.status_code == 403
        # Should have called at least once (hit the failing /oura/activity endpoint)
        # and fewer than all 7 endpoints + heart_rate (would be 8+ if it continued)
        assert 1 <= call_count[0] < 8, f"Expected 1-7 calls, got {call_count[0]}"

    def test_fetch_other_http_errors_wrapped_in_endpoint_fetch_error(self, monkeypatch):
        """fetch() wraps non-auth HTTP errors (4xx/5xx) in EndpointFetchError."""
        import httpx
        from context_library.adapters.base import EndpointFetchError

        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        def mock_get_500(*args, **kwargs):
            response = httpx.Response(
                status_code=500,
                content=b"Internal Server Error",
                request=httpx.Request("GET", args[0] if args else "http://test"),
            )
            raise httpx.HTTPStatusError("500 Server Error", request=response.request, response=response)

        monkeypatch.setattr(
            "context_library.adapters.oura.httpx.get",
            mock_get_500
        )

        # Should raise AllEndpointsFailedError (which wraps EndpointFetchError)
        from context_library.adapters.base import AllEndpointsFailedError
        with pytest.raises(AllEndpointsFailedError):
            list(adapter.fetch(""))


class TestOuraAdapterWorkoutValidation:
    """Tests for Oura workout validation, including endDate."""

    def test_fetch_workout_missing_enddate_skips_record(self, mock_all_oura_endpoints):
        """fetch() skips workout records missing endDate field."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/workouts", [
            {
                "id": "workout-1",
                "activityType": "running",
                "startDate": "2026-03-07T08:00:00Z",
                # Missing 'endDate'
                "durationSeconds": 1800,
            }
        ])

        # Should not raise, just skip the malformed record
        results = list(adapter.fetch(""))
        workout_records = [r for r in results if "workout" in r.source_id.lower()]
        assert len(workout_records) == 0

    def test_fetch_workout_missing_required_fields_skips_record(self, mock_all_oura_endpoints):
        """fetch() skips workout records with missing required fields."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        # Test missing id
        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/workouts", [
            {
                # Missing 'id'
                "activityType": "running",
                "startDate": "2026-03-07T08:00:00Z",
                "endDate": "2026-03-07T08:30:00Z",
                "durationSeconds": 1800,
            }
        ])

        results = list(adapter.fetch(""))
        workout_records = [r for r in results if "workout" in r.source_id.lower()]
        assert len(workout_records) == 0

        # Test missing startDate
        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/workouts", [
            {
                "id": "workout-2",
                "activityType": "cycling",
                # Missing 'startDate'
                "endDate": "2026-03-07T09:00:00Z",
                "durationSeconds": 2400,
            }
        ])

        results = list(adapter.fetch(""))
        workout_records = [r for r in results if "workout" in r.source_id.lower()]
        assert len(workout_records) == 0


class TestOuraAdapterSessionValidation:
    """Tests for Oura session validation, including endDate."""

    def test_fetch_session_missing_enddate_skips_record(self, mock_all_oura_endpoints):
        """fetch() skips session records missing endDate field."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sessions", [
            {
                "id": "session-1",
                "startDate": "2026-03-07T10:00:00Z",
                # Missing 'endDate'
                "durationSeconds": 600,
                "sessionType": "meditation",
            }
        ])

        # Should not raise, just skip the malformed record
        results = list(adapter.fetch(""))
        session_records = [r for r in results if "session" in r.source_id.lower()]
        assert len(session_records) == 0

    def test_fetch_session_missing_required_fields_skips_record(self, mock_all_oura_endpoints):
        """fetch() skips session records with missing required fields."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        # Test missing id
        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sessions", [
            {
                # Missing 'id'
                "startDate": "2026-03-07T10:00:00Z",
                "endDate": "2026-03-07T10:10:00Z",
                "durationSeconds": 600,
                "sessionType": "meditation",
            }
        ])

        results = list(adapter.fetch(""))
        session_records = [r for r in results if "session" in r.source_id.lower()]
        assert len(session_records) == 0

        # Test missing sessionType
        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/sessions", [
            {
                "id": "session-2",
                "startDate": "2026-03-07T11:00:00Z",
                "endDate": "2026-03-07T11:10:00Z",
                "durationSeconds": 600,
                # Missing 'sessionType'
            }
        ])

        results = list(adapter.fetch(""))
        session_records = [r for r in results if "session" in r.source_id.lower()]
        assert len(session_records) == 0


class TestOuraAdapterHeartRateBpmValidation:
    """Tests for heart rate BPM type validation."""

    def test_fetch_heart_rate_invalid_bpm_string_skips_window(self, mock_all_oura_endpoints):
        """fetch() skips heart rate windows when bpm is a string instead of numeric."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/heart_rate", [
            {"timestamp": "2026-03-07T10:00:00+00:00", "bpm": "65"},  # Invalid: string
            {"timestamp": "2026-03-07T10:15:00+00:00", "bpm": 68},
            {"timestamp": "2026-03-07T10:30:00+00:00", "bpm": 70},
        ])

        # Should not raise, just skip the window with invalid bpm
        results = list(adapter.fetch(""))
        heart_rate_records = [r for r in results if "heart_rate" in r.source_id]
        assert len(heart_rate_records) == 0

    def test_fetch_heart_rate_invalid_bpm_null_skips_window(self, mock_all_oura_endpoints):
        """fetch() skips heart rate windows when bpm is null/None."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/heart_rate", [
            {"timestamp": "2026-03-07T10:00:00+00:00", "bpm": None},  # Invalid: null
            {"timestamp": "2026-03-07T10:15:00+00:00", "bpm": 68},
        ])

        # Should not raise, just skip the window with invalid bpm
        results = list(adapter.fetch(""))
        heart_rate_records = [r for r in results if "heart_rate" in r.source_id]
        assert len(heart_rate_records) == 0

    def test_fetch_heart_rate_valid_int_bpm_succeeds(self, mock_all_oura_endpoints):
        """fetch() successfully processes heart rate windows with integer bpm values."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/heart_rate", [
            {"timestamp": "2026-03-07T10:00:00+00:00", "bpm": 65},
            {"timestamp": "2026-03-07T10:15:00+00:00", "bpm": 68},
            {"timestamp": "2026-03-07T10:30:00+00:00", "bpm": 70},
        ])

        results = list(adapter.fetch(""))
        heart_rate_records = [r for r in results if "heart_rate" in r.source_id]
        assert len(heart_rate_records) == 1
        assert "Average:" in heart_rate_records[0].markdown

    def test_fetch_heart_rate_valid_float_bpm_succeeds(self, mock_all_oura_endpoints):
        """fetch() successfully processes heart rate windows with float bpm values."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/heart_rate", [
            {"timestamp": "2026-03-07T10:00:00+00:00", "bpm": 65.5},
            {"timestamp": "2026-03-07T10:15:00+00:00", "bpm": 68.2},
            {"timestamp": "2026-03-07T10:30:00+00:00", "bpm": 70.1},
        ])

        results = list(adapter.fetch(""))
        heart_rate_records = [r for r in results if "heart_rate" in r.source_id]
        assert len(heart_rate_records) == 1
        assert "Average:" in heart_rate_records[0].markdown

    def test_fetch_heart_rate_mixed_int_float_bpm_succeeds(self, mock_all_oura_endpoints):
        """fetch() successfully processes heart rate windows with mixed int/float bpm values."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/heart_rate", [
            {"timestamp": "2026-03-07T10:00:00+00:00", "bpm": 65},      # int
            {"timestamp": "2026-03-07T10:15:00+00:00", "bpm": 68.5},    # float
            {"timestamp": "2026-03-07T10:30:00+00:00", "bpm": 70},      # int
        ])

        results = list(adapter.fetch(""))
        heart_rate_records = [r for r in results if "heart_rate" in r.source_id]
        assert len(heart_rate_records) == 1
        metadata = heart_rate_records[0].structural_hints.extra_metadata
        assert "avg_bpm" in metadata
        assert "min_bpm" in metadata
        assert "max_bpm" in metadata

    def test_fetch_heart_rate_invalid_bpm_dict_skips_window(self, mock_all_oura_endpoints):
        """fetch() skips heart rate windows when bpm is a dict (object) instead of numeric."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/heart_rate", [
            {"timestamp": "2026-03-07T10:00:00+00:00", "bpm": {"value": 65}},  # Invalid: dict
        ])

        # Should not raise, just skip the window with invalid bpm
        results = list(adapter.fetch(""))
        heart_rate_records = [r for r in results if "heart_rate" in r.source_id]
        assert len(heart_rate_records) == 0

    def test_fetch_heart_rate_invalid_bpm_list_skips_window(self, mock_all_oura_endpoints):
        """fetch() skips heart rate windows when bpm is a list instead of numeric."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        mock_all_oura_endpoints.set_response("http://localhost:8000/oura/heart_rate", [
            {"timestamp": "2026-03-07T10:00:00+00:00", "bpm": [65]},  # Invalid: list
        ])

        # Should not raise, just skip the window with invalid bpm
        results = list(adapter.fetch(""))
        heart_rate_records = [r for r in results if "heart_rate" in r.source_id]
        assert len(heart_rate_records) == 0
