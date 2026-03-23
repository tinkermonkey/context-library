"""Apple HealthKit adapter for a macOS-native helper process.

This adapter consumes a local HTTP REST API served by a macOS helper process that exposes
Apple HealthKit data via a local HTTP API.

Architecture
============

The adapter uses a layered architecture for security:

- **Helper process**: Runs on 127.0.0.1 only (localhost), exposing the Apple HealthKit API
  to local consumers only. This design is intentional: direct HealthKit access is
  restricted to the local machine.

- **Remote access**: To expose health data to remote clients, use serve_adapter() which
  wraps this adapter in an HTTP server. The serve_adapter can be configured to bind to
  0.0.0.0 or a specific network interface, providing the remote exposure layer while
  keeping the underlying helper process local and secure.

Expected local service API contract
===================================

The helper process exposes the following HTTP endpoints:

GET /health/workouts
  Query parameters:
    - since (optional): ISO 8601 timestamp; return only workouts starting after this time

  Response: JSON array of workout objects:
    [
      {
        "id": "<uuid>",
        "activityType": "<string>",           // e.g., "running", "cycling", "yoga"
        "startDate": "<ISO 8601>",
        "endDate": "<ISO 8601>",
        "durationSeconds": <int>,
        "totalEnergyBurned": <float | null>,  // kilocalories
        "totalDistance": <float | null>,      // meters
        "averageHeartRate": <float | null>,   // bpm
        "notes": "<string | null>"
      }
    ]

GET /health/activity
  Query parameters:
    - since (optional): ISO 8601 timestamp; return only days after this date

  Response: JSON array of daily activity summaries:
    [
      {
        "id": "<YYYY-MM-DD>",
        "date": "<YYYY-MM-DD>",
        "steps": <int | null>,
        "activeCalories": <float | null>,     // kcal
        "totalCalories": <float | null>,      // kcal (null for Apple Health)
        "exerciseMinutes": <int | null>,
        "standHours": <int | null>,
        "distanceMeters": <float | null>
      }
    ]

GET /health/sleep
  Query parameters:
    - since (optional): ISO 8601 timestamp; return only nights after this date

  Response: JSON array of daily sleep summaries:
    [
      {
        "id": "<YYYY-MM-DD>",
        "date": "<YYYY-MM-DD>",
        "totalSleepMinutes": <int>,
        "deepSleepMinutes": <int | null>,
        "remSleepMinutes": <int | null>,
        "lightSleepMinutes": <int | null>,
        "inBedMinutes": <int | null>
      }
    ]

GET /health/heart-rate
  Query parameters:
    - since (optional): ISO 8601 timestamp; return only samples after this date

  Response: JSON array of heart rate samples (grouped into hourly windows by adapter):
    [
      {
        "timestamp": "<ISO 8601>",
        "bpm": <float>,
        "source": "<string | null>"
      }
    ]

GET /health/spo2
  Query parameters:
    - since (optional): ISO 8601 timestamp; return only days after this date

  Response: JSON array of daily SpO2 summaries:
    [
      {
        "id": "<YYYY-MM-DD>",
        "date": "<YYYY-MM-DD>",
        "avgSpo2": <float>   // percentage (e.g. 97.2)
      }
    ]

GET /health/mindfulness
  Query parameters:
    - since (optional): ISO 8601 timestamp; return only sessions after this date

  Response: JSON array of mindfulness sessions:
    [
      {
        "id": "<string>",
        "startDate": "<ISO 8601>",
        "endDate": "<ISO 8601>",
        "durationSeconds": <int>,
        "sessionType": "<string>"
      }
    ]

Security Note: The helper process runs on 127.0.0.1 (localhost) only, ensuring HealthKit
data never leaves the local machine. A Bearer API token is REQUIRED for all requests to
authenticate the caller. For remote access, wrap this adapter with serve_adapter().

Example usage:
    adapter = AppleHealthAdapter(
        api_url="http://192.168.1.50:7124",
        api_key="your-api-token",
        device_id="macbook-pro-m1"
    )

    for normalized_content in adapter.fetch(""):  # Full fetch
        print(normalized_content.markdown)

    # Incremental fetch (only records starting after given timestamp)
    for normalized_content in adapter.fetch("2025-03-07T10:00:00+00:00"):
        print(normalized_content.markdown)
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Iterator

from context_library.adapters.base import (
    BaseAdapter,
    EndpointFetchError,
    AllEndpointsFailedError,
    PartialFetchError,
)
from context_library.storage.models import (
    Domain,
    HealthMetadata,
    NormalizedContent,
    PollStrategy,
    StructuralHints,
)

logger = logging.getLogger(__name__)

# Optional import guard
HAS_HTTPX = False
try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    pass


class AppleHealthAdapter(BaseAdapter):
    """Adapter for consuming Apple HealthKit data via local or remote HTTP REST API.

    Fetches all available health record types from a macOS helper process that reads
    Apple Health exports: workouts, daily activity, sleep analysis, heart rate series,
    SpO2 summaries, and mindfulness sessions.

    Each record is mapped to a vendor-neutral HealthMetadata type:
      - workout_session:      /health/workouts
      - activity_summary:    /health/activity
      - sleep_summary:       /health/sleep
      - heart_rate_series:   /health/heart-rate  (windowed hourly by this adapter)
      - spo2_summary:        /health/spo2
      - mindfulness_session: /health/mindfulness
    """

    @property
    def domain(self) -> Domain:
        return Domain.HEALTH

    @property
    def poll_strategy(self) -> PollStrategy:
        return PollStrategy.PULL

    @property
    def normalizer_version(self) -> str:
        return "3.0.0"

    def __init__(
        self,
        api_url: str,
        api_key: str,
        device_id: str = "default",
    ) -> None:
        """Initialize AppleHealthAdapter.

        Args:
            api_url: Base URL of the helper API (e.g., "http://192.168.1.50:7124")
            api_key: Required API key for Bearer token authentication
            device_id: Device identifier for adapter_id computation (default: "default")

        Raises:
            ImportError: If httpx is not installed
            ValueError: If api_key is empty
        """
        if not HAS_HTTPX:
            raise ImportError(
                "Apple Health adapter requires 'httpx' package. "
                "Install with: pip install context-library[apple-health]"
            )
        if not api_key:
            raise ValueError("api_key is required for AppleHealthAdapter")

        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._device_id = device_id

    @property
    def adapter_id(self) -> str:
        return f"apple_health:{self._device_id}"

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize all health data types from Apple Health export via helper API.

        Args:
            source_ref: ISO 8601 timestamp for incremental fetch, or empty string for full fetch

        Yields:
            NormalizedContent: Normalized health records with HealthMetadata in extra_metadata

        Raises:
            AllEndpointsFailedError: If all endpoints fail
            PartialFetchError: If some endpoints fail but others succeed
            httpx.HTTPStatusError: Auth errors (401/403) propagate immediately
        """
        since = source_ref if source_ref else None
        params = {"since": since} if since else {}
        headers = {"Authorization": f"Bearer {self._api_key}"}

        endpoints_config = [
            ("/health/workouts", self._process_workout, "workout"),
            ("/health/activity", self._process_activity, "activity record"),
            ("/health/sleep", self._process_sleep, "sleep record"),
            ("/health/spo2", self._process_spo2, "SpO2 record"),
            ("/health/mindfulness", self._process_mindfulness, "mindfulness session"),
        ]

        failed_endpoints = []

        for endpoint, handler, item_label in endpoints_config:
            try:
                yield from self._fetch_endpoint(endpoint, handler, item_label, params, headers)
            except httpx.HTTPStatusError:
                raise
            except EndpointFetchError:
                failed_endpoints.append(endpoint)

        # Heart rate requires hourly windowing — handled separately
        try:
            yield from self._fetch_heart_rate(since, headers)
        except httpx.HTTPStatusError:
            raise
        except EndpointFetchError:
            failed_endpoints.append("/health/heart-rate")

        total_endpoints = len(endpoints_config) + 1  # +1 for heart_rate
        if failed_endpoints:
            if len(failed_endpoints) == total_endpoints:
                raise AllEndpointsFailedError(
                    total_endpoints,
                    f"All {total_endpoints} Apple Health endpoints failed. "
                    "Check API connectivity, credentials, and service status.",
                )
            else:
                raise PartialFetchError(
                    failed_endpoints,
                    total_endpoints,
                    f"Partial fetch from Apple Health: {len(failed_endpoints)}/{total_endpoints} "
                    "endpoint(s) failed. Successful endpoints provided partial data.",
                )

    def _fetch_endpoint(
        self,
        endpoint: str,
        handler: Callable[[dict[str, Any]], Iterator[NormalizedContent]],
        item_label: str,
        params: dict[str, Any],
        headers: dict[str, str],
    ) -> Iterator[NormalizedContent]:
        """Fetch and process records from a single endpoint.

        Raises:
            httpx.HTTPStatusError: Auth errors (401/403) are immediately re-raised
            EndpointFetchError: If the endpoint fails for any other reason
        """
        try:
            response = httpx.get(
                f"{self._api_url}{endpoint}",
                params=params,
                headers=headers,
                timeout=120.0,
            )
            response.raise_for_status()

            records = response.json()
            if not isinstance(records, list):
                raise ValueError(f"Expected list from {endpoint}, got {type(records)}")

            for idx, record in enumerate(records):
                try:
                    yield from handler(record)
                except (ValueError, KeyError) as e:
                    record_id = record.get("id", f"<index {idx}>")
                    logger.error(f"Skipping malformed {item_label} (ID: {record_id}): {e}")
                    continue

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                logger.error(
                    f"Authentication error from Apple Health API {endpoint}: "
                    f"{e.response.status_code} {e.response.text}"
                )
                raise
            logger.error(f"HTTP error from Apple Health API {endpoint}: {e.response.status_code}")
            raise EndpointFetchError(f"HTTP {e.response.status_code} from {endpoint}")
        except httpx.RequestError as e:
            logger.error(f"Request error connecting to Apple Health API at {self._api_url}{endpoint}: {e}")
            raise EndpointFetchError(f"Network error at {endpoint}: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from {endpoint}: {e}")
            raise EndpointFetchError(f"JSON decode error at {endpoint}: {e}")
        except ValueError as e:
            logger.error(f"Invalid response schema from {endpoint}: {e}")
            raise EndpointFetchError(f"Invalid schema at {endpoint}: {e}")

    def _fetch_heart_rate(
        self,
        since: str | None,
        headers: dict[str, str],
    ) -> Iterator[NormalizedContent]:
        """Fetch heart rate samples and group into hourly windows.

        Raises:
            httpx.HTTPStatusError: Auth errors (401/403) are immediately re-raised
            EndpointFetchError: If the endpoint fails
        """
        params = {"since": since} if since else {}

        try:
            response = httpx.get(
                f"{self._api_url}/health/heart-rate",
                params=params,
                headers=headers,
                timeout=120.0,
            )
            response.raise_for_status()

            samples = response.json()
            if not isinstance(samples, list):
                raise ValueError(f"Expected list of heart rate samples, got {type(samples)}")

            # Group samples by date + hour
            windows: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
            for sample in samples:
                try:
                    timestamp = sample["timestamp"]
                    # Apple Health timestamps: "2026-01-15 09:30:00 -0500"
                    # fromisoformat requires no space before the timezone sign,
                    # so collapse "T09:30:00 -0500" → "T09:30:00-0500".
                    ts_iso = timestamp.replace(" ", "T", 1).replace(" -", "-").replace(" +", "+")
                    dt = datetime.fromisoformat(ts_iso)
                    date = dt.date().isoformat()
                    hour = dt.hour
                    windows[(date, hour)].append(sample)
                except (ValueError, KeyError) as e:
                    logger.error(f"Skipping malformed heart rate sample: {e}")
                    continue

            for (date, hour), window_samples in sorted(windows.items()):
                try:
                    yield from self._process_heart_rate_window(window_samples, date, hour)
                except (ValueError, KeyError) as e:
                    logger.error(f"Skipping malformed heart rate window ({date}T{hour:02d}): {e}")
                    continue

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                logger.error(
                    f"Authentication error from Apple Health API /health/heart-rate: "
                    f"{e.response.status_code} {e.response.text}"
                )
                raise
            logger.error(f"HTTP error from Apple Health API /health/heart-rate: {e.response.status_code}")
            raise EndpointFetchError(f"HTTP {e.response.status_code} from /health/heart-rate")
        except httpx.RequestError as e:
            logger.error(f"Request error connecting to Apple Health API /health/heart-rate: {e}")
            raise EndpointFetchError(f"Network error at /health/heart-rate: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from /health/heart-rate: {e}")
            raise EndpointFetchError(f"JSON decode error at /health/heart-rate: {e}")
        except ValueError as e:
            logger.error(f"Invalid heart rate response schema: {e}")
            raise EndpointFetchError(f"Invalid schema at /health/heart-rate: {e}")

    # ------------------------------------------------------------------
    # Record processors
    # ------------------------------------------------------------------

    def _process_workout(self, workout: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single workout record."""
        workout_id = workout["id"]
        if not workout_id:
            raise ValueError("Workout 'id' must not be empty")

        activity_type = workout["activityType"]
        if not activity_type:
            raise ValueError("Workout 'activityType' must not be empty")

        start_date = workout["startDate"]
        if not start_date:
            raise ValueError("Workout 'startDate' must not be empty")

        end_date = workout["endDate"]
        if not end_date:
            raise ValueError("Workout 'endDate' must not be empty")

        duration_seconds = workout["durationSeconds"]
        if not isinstance(duration_seconds, (int, float)):
            raise ValueError(f"Workout 'durationSeconds' must be numeric, got {type(duration_seconds)}")

        duration_minutes = int(duration_seconds // 60)
        now = datetime.now(timezone.utc).isoformat()
        date = start_date[:10]

        health_metadata_dict = {
            "record_id": workout_id,
            "health_type": "workout_session",
            "date": date,
            "source_type": "apple_health",
            "date_first_observed": now,
            "duration_minutes": duration_minutes,
            "calories_kcal": workout.get("totalEnergyBurned"),
            "distance_meters": workout.get("totalDistance"),
            "avg_heart_rate_bpm": workout.get("averageHeartRate"),
            "activity_type": activity_type,
        }

        try:
            HealthMetadata.model_validate(health_metadata_dict)
        except ValueError as e:
            logger.error(f"HealthMetadata validation failed for workout {workout_id}: {e}")
            raise

        source_id = f"apple_health/workout/{activity_type}/{workout_id}"
        markdown = self._build_workout_summary(workout, activity_type, duration_minutes)

        yield NormalizedContent(
            markdown=markdown,
            source_id=source_id,
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=True,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata=health_metadata_dict,
            ),
            normalizer_version=self.normalizer_version,
        )

    def _process_activity(self, record: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single daily activity summary record."""
        record_id = record["id"]
        if not record_id:
            raise ValueError("Activity record 'id' must not be empty")

        date = record["date"]
        if not date:
            raise ValueError("Activity record 'date' must not be empty")

        now = datetime.now(timezone.utc).isoformat()

        health_metadata_dict = {
            "record_id": record_id,
            "health_type": "activity_summary",
            "date": date,
            "source_type": "apple_health",
            "date_first_observed": now,
            "steps": record.get("steps"),
            "active_calories": record.get("activeCalories"),
            "total_calories": record.get("totalCalories"),
            "duration_minutes": record.get("exerciseMinutes"),
            "distance_meters": record.get("distanceMeters"),
        }

        try:
            HealthMetadata.model_validate(health_metadata_dict)
        except ValueError as e:
            logger.error(f"HealthMetadata validation failed for activity record {record_id}: {e}")
            raise

        source_id = f"apple_health/activity/{record_id}"
        markdown = self._build_activity_summary(record)

        yield NormalizedContent(
            markdown=markdown,
            source_id=source_id,
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=True,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata=health_metadata_dict,
            ),
            normalizer_version=self.normalizer_version,
        )

    def _process_sleep(self, record: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single daily sleep summary record."""
        record_id = record["id"]
        if not record_id:
            raise ValueError("Sleep record 'id' must not be empty")

        date = record["date"]
        if not date:
            raise ValueError("Sleep record 'date' must not be empty")

        total_sleep_minutes = record["totalSleepMinutes"]
        if not isinstance(total_sleep_minutes, (int, float)):
            raise ValueError(f"Sleep record 'totalSleepMinutes' must be numeric, got {type(total_sleep_minutes)}")

        now = datetime.now(timezone.utc).isoformat()

        health_metadata_dict = {
            "record_id": record_id,
            "health_type": "sleep_summary",
            "date": date,
            "source_type": "apple_health",
            "date_first_observed": now,
            "duration_minutes": int(total_sleep_minutes),
            "deep_sleep_minutes": record.get("deepSleepMinutes"),
            "rem_sleep_minutes": record.get("remSleepMinutes"),
            "light_sleep_minutes": record.get("lightSleepMinutes"),
        }

        try:
            HealthMetadata.model_validate(health_metadata_dict)
        except ValueError as e:
            logger.error(f"HealthMetadata validation failed for sleep record {record_id}: {e}")
            raise

        source_id = f"apple_health/sleep/{record_id}"
        markdown = self._build_sleep_summary(record, int(total_sleep_minutes))

        yield NormalizedContent(
            markdown=markdown,
            source_id=source_id,
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=True,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata=health_metadata_dict,
            ),
            normalizer_version=self.normalizer_version,
        )

    def _process_heart_rate_window(
        self,
        window: list[dict[str, Any]],
        window_date: str,
        window_hour: int,
    ) -> Iterator[NormalizedContent]:
        """Process an hourly window of heart rate samples."""
        if not window:
            raise ValueError("Heart rate window must not be empty")

        heart_rates = []
        for sample in window:
            bpm = sample["bpm"]
            if not isinstance(bpm, (int, float)):
                raise ValueError("Heart rate sample 'bpm' must be numeric")
            heart_rates.append(float(bpm))

        if not heart_rates:
            raise ValueError("No valid heart rates in window")

        avg_bpm = sum(heart_rates) / len(heart_rates)
        min_bpm = min(heart_rates)
        max_bpm = max(heart_rates)

        now = datetime.now(timezone.utc).isoformat()
        record_id = f"hr:apple_health:{self._device_id}:{window_date}T{window_hour:02d}"

        health_metadata_dict = {
            "record_id": record_id,
            "health_type": "heart_rate_series",
            "date": window_date,
            "source_type": "apple_health",
            "date_first_observed": now,
            "avg_bpm": avg_bpm,
            "min_bpm": min_bpm,
            "max_bpm": max_bpm,
            "sample_count": len(heart_rates),
            "hour": window_hour,
        }

        try:
            HealthMetadata.model_validate(health_metadata_dict)
        except ValueError as e:
            logger.error(f"HealthMetadata validation failed for heart rate window {record_id}: {e}")
            raise

        source_id = f"apple_health/heart_rate/{window_date}T{window_hour:02d}"
        markdown = self._build_heart_rate_summary(window, avg_bpm, min_bpm, max_bpm)

        yield NormalizedContent(
            markdown=markdown,
            source_id=source_id,
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=True,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata=health_metadata_dict,
            ),
            normalizer_version=self.normalizer_version,
        )

    def _process_spo2(self, record: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single daily SpO2 summary record."""
        record_id = record["id"]
        if not record_id:
            raise ValueError("SpO2 record 'id' must not be empty")

        date = record["date"]
        if not date:
            raise ValueError("SpO2 record 'date' must not be empty")

        avg_spo2 = record["avgSpo2"]
        if not isinstance(avg_spo2, (int, float)):
            raise ValueError(f"SpO2 record 'avgSpo2' must be numeric, got {type(avg_spo2)}")

        now = datetime.now(timezone.utc).isoformat()

        health_metadata_dict = {
            "record_id": record_id,
            "health_type": "spo2_summary",
            "date": date,
            "source_type": "apple_health",
            "date_first_observed": now,
            "avg_spo2": avg_spo2,
        }

        try:
            HealthMetadata.model_validate(health_metadata_dict)
        except ValueError as e:
            logger.error(f"HealthMetadata validation failed for SpO2 record {record_id}: {e}")
            raise

        source_id = f"apple_health/spo2/{record_id}"
        markdown = self._build_spo2_summary(record, avg_spo2)

        yield NormalizedContent(
            markdown=markdown,
            source_id=source_id,
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=True,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata=health_metadata_dict,
            ),
            normalizer_version=self.normalizer_version,
        )

    def _process_mindfulness(self, record: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single mindfulness session record."""
        record_id = record["id"]
        if not record_id:
            raise ValueError("Mindfulness record 'id' must not be empty")

        start_date = record["startDate"]
        if not start_date:
            raise ValueError("Mindfulness record 'startDate' must not be empty")

        end_date = record["endDate"]
        if not end_date:
            raise ValueError("Mindfulness record 'endDate' must not be empty")

        duration_seconds = record["durationSeconds"]
        if not isinstance(duration_seconds, (int, float)):
            raise ValueError(f"Mindfulness record 'durationSeconds' must be numeric, got {type(duration_seconds)}")

        duration_minutes = int(duration_seconds // 60)
        date = start_date[:10]
        session_type = record.get("sessionType", "mindful")
        now = datetime.now(timezone.utc).isoformat()

        health_metadata_dict = {
            "record_id": record_id,
            "health_type": "mindfulness_session",
            "date": date,
            "source_type": "apple_health",
            "date_first_observed": now,
            "duration_minutes": duration_minutes,
            "session_type": session_type,
        }

        try:
            HealthMetadata.model_validate(health_metadata_dict)
        except ValueError as e:
            logger.error(f"HealthMetadata validation failed for mindfulness record {record_id}: {e}")
            raise

        source_id = f"apple_health/mindfulness/{record_id}"
        markdown = self._build_mindfulness_summary(record, duration_minutes, session_type)

        yield NormalizedContent(
            markdown=markdown,
            source_id=source_id,
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=True,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata=health_metadata_dict,
            ),
            normalizer_version=self.normalizer_version,
        )

    # ------------------------------------------------------------------
    # Markdown summary builders
    # ------------------------------------------------------------------

    def _build_workout_summary(
        self, workout: dict[str, Any], activity_type: str, duration_minutes: int
    ) -> str:
        lines = [f"**{activity_type.title()}**"]

        total_energy_burned = workout.get("totalEnergyBurned")
        if total_energy_burned is not None:
            lines.append(f"- Calories: {total_energy_burned:.0f} kcal")

        total_distance = workout.get("totalDistance")
        if total_distance is not None:
            km = total_distance / 1000
            lines.append(f"- Distance: {km:.2f} km")

        average_heart_rate = workout.get("averageHeartRate")
        if average_heart_rate is not None:
            lines.append(f"- Avg heart rate: {average_heart_rate:.0f} bpm")

        lines.append(f"- Duration: {duration_minutes} minutes")

        notes = workout.get("notes")
        if notes:
            lines.append(f"\n{notes}")

        return "\n".join(lines)

    def _build_activity_summary(self, record: dict[str, Any]) -> str:
        date = record.get("date", "")
        lines = [f"**Activity — {date}**"]

        steps = record.get("steps")
        if steps is not None:
            lines.append(f"- Steps: {steps:,}")

        active_calories = record.get("activeCalories")
        if active_calories is not None:
            lines.append(f"- Active calories: {active_calories:.0f} kcal")

        exercise_minutes = record.get("exerciseMinutes")
        if exercise_minutes is not None:
            lines.append(f"- Exercise: {exercise_minutes} minutes")

        stand_hours = record.get("standHours")
        if stand_hours is not None:
            lines.append(f"- Stand hours: {stand_hours}")

        distance_meters = record.get("distanceMeters")
        if distance_meters is not None:
            km = distance_meters / 1000
            lines.append(f"- Distance: {km:.2f} km")

        return "\n".join(lines)

    def _build_sleep_summary(self, record: dict[str, Any], total_minutes: int) -> str:
        date = record.get("date", "")
        hours = total_minutes // 60
        mins = total_minutes % 60
        lines = [f"**Sleep — {date}**"]
        lines.append(f"- Total sleep: {hours}h {mins}m")

        deep = record.get("deepSleepMinutes")
        if deep is not None:
            lines.append(f"- Deep sleep: {deep} minutes")

        rem = record.get("remSleepMinutes")
        if rem is not None:
            lines.append(f"- REM sleep: {rem} minutes")

        light = record.get("lightSleepMinutes")
        if light is not None:
            lines.append(f"- Light sleep: {light} minutes")

        in_bed = record.get("inBedMinutes")
        if in_bed is not None:
            lines.append(f"- In bed: {in_bed} minutes")

        return "\n".join(lines)

    def _build_heart_rate_summary(
        self,
        window: list[dict[str, Any]],
        avg_bpm: float,
        min_bpm: float,
        max_bpm: float,
    ) -> str:
        lines = ["**Heart Rate**"]
        lines.append(f"- Avg: {avg_bpm:.0f} bpm")
        lines.append(f"- Min: {min_bpm:.0f} bpm")
        lines.append(f"- Max: {max_bpm:.0f} bpm")
        lines.append(f"- Samples: {len(window)}")
        return "\n".join(lines)

    def _build_spo2_summary(self, record: dict[str, Any], avg_spo2: float) -> str:
        date = record.get("date", "")
        lines = [f"**Blood Oxygen (SpO2) — {date}**"]
        lines.append(f"- Avg SpO2: {avg_spo2:.1f}%")
        return "\n".join(lines)

    def _build_mindfulness_summary(
        self, record: dict[str, Any], duration_minutes: int, session_type: str
    ) -> str:
        lines = [f"**{session_type.replace('_', ' ').title()} Session**"]
        lines.append(f"- Duration: {duration_minutes} minutes")
        return "\n".join(lines)
