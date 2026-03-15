"""Apple HealthKit adapter for a macOS-native helper process.

This adapter consumes a local HTTP REST API served by a macOS helper process that exposes
Apple HealthKit data (workouts, activity summaries, sleep, heart rate, SpO2, mindfulness,
HRV/readiness) via a local HTTP API.

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

GET /workouts
  Query parameters:
    - since (optional): ISO 8601 timestamp; return only workouts starting after this time

  Response: JSON array of workout objects with the following schema:
    [
      {
        "id": "<uuid>",
        "activityType": "<string>",           // e.g., "running", "cycling", "yoga"
        "startDate": "<ISO 8601>",            // e.g., "2025-03-07T10:00:00+00:00"
        "endDate": "<ISO 8601>",              // e.g., "2025-03-07T10:30:00+00:00"
        "durationSeconds": <int>,             // seconds
        "totalEnergyBurned": <float | null>,  // kilocalories
        "totalDistance": <float | null>,      // meters
        "averageHeartRate": <float | null>,   // beats per minute (bpm)
        "notes": "<string | null>"            // optional notes
      }
    ]

GET /sleep
  Query parameters:
    - since (optional): ISO 8601 timestamp; return only sleep records starting after this time

  Response: JSON array of sleep records
    [
      {
        "id": "<uuid>",
        "date": "<YYYY-MM-DD>",
        "totalSleepMinutes": <int>,
        "deepSleepMinutes": <int>,
        "remSleepMinutes": <int>,
        "lightSleepMinutes": <int>,
        "efficiency": <float>,
        "score": <int | null>
      }
    ]

GET /activity
  Query parameters:
    - since (optional): ISO 8601 timestamp; return only activity records starting after this time

  Response: JSON array of activity records
    [
      {
        "id": "<uuid>",
        "date": "<YYYY-MM-DD>",
        "steps": <int>,
        "activeCalories": <float>,
        "totalCalories": <float>,
        "activeMinutes": <int>,
        "sedentaryMinutes": <int>,
        "distanceMeters": <float>
      }
    ]

GET /hrv
  Query parameters:
    - since (optional): ISO 8601 timestamp; return only records starting after this time

  Response: JSON array of HRV records (heart rate variability / readiness)
    [
      {
        "id": "<uuid>",
        "date": "<YYYY-MM-DD>",
        "avgHrv": <float>,
        "restingHeartRate": <float | null>,
        "bodyTemperatureDeviation": <float | null>
      }
    ]

GET /heart_rate
  Query parameters:
    - since (optional): ISO 8601 timestamp; return only samples starting after this time

  Response: JSON array of individual heart rate samples (grouped by hour in adapter)
    [
      {
        "timestamp": "<ISO 8601>",
        "bpm": <int>,
        "context": "<string | null>"        // e.g., "resting", "active"
      }
    ]

GET /spo2
  Query parameters:
    - since (optional): ISO 8601 timestamp; return only records starting after this time

  Response: JSON array of SpO2 records
    [
      {
        "id": "<uuid>",
        "date": "<YYYY-MM-DD>",
        "avgSpo2": <float>,
        "breathingDisturbanceIndex": <float | null>
      }
    ]

GET /mindfulness
  Query parameters:
    - since (optional): ISO 8601 timestamp; return only sessions starting after this time

  Response: JSON array of mindfulness session records
    [
      {
        "id": "<uuid>",
        "startDate": "<ISO 8601>",
        "endDate": "<ISO 8601>",
        "durationSeconds": <int>,
        "sessionType": "<string>",          // e.g., "meditation", "breathing"
        "mood": "<string | null>",
        "tags": [<string>, ...]
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

Example usage (remote via serve_adapter):
    adapter = AppleHealthAdapter(
        api_url="http://127.0.0.1:7124",
        api_key="your-api-token",
        device_id="macbook-pro"
    )
    serve_adapter(adapter, host="0.0.0.0", port=8000)
    # Now remote clients can access via http://<mac-ip>:8000/fetch
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Iterator

from context_library.adapters.base import BaseAdapter
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


class EndpointFetchError(Exception):
    """Raised when an endpoint fails to fetch (non-auth error)."""

    pass


class AppleHealthAdapter(BaseAdapter):
    """Adapter for consuming Apple HealthKit data via local or remote HTTP REST API.

    The adapter fetches health and fitness data (workouts, sleep, activity summaries,
    heart rate series, SpO2, mindfulness sessions, and HRV/readiness) from a macOS helper
    process that wraps Apple HealthKit APIs. The helper service can run on the local machine
    (127.0.0.1:7124) or be accessible from a remote machine via serve_adapter for
    cross-machine deployments.

    Each health record is mapped to a HealthMetadata with:
    - record_id: Unique identifier for the record
    - health_type: One of the eight vendor-neutral types (workout_session, sleep_summary, etc.)
    - date: ISO 8601 date (YYYY-MM-DD) for the record
    - source_type: "apple_health"
    - date_first_observed: ISO 8601 timestamp when record was processed
    - Additional health-specific fields in extra_metadata: calories_kcal, distance_meters, etc.
    """

    @property
    def domain(self) -> Domain:
        """Return the domain this adapter handles."""
        return Domain.HEALTH

    @property
    def poll_strategy(self) -> PollStrategy:
        """Return the polling strategy for this adapter."""
        return PollStrategy.PULL

    @property
    def normalizer_version(self) -> str:
        """Return the normalizer version."""
        return "2.0.0"

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
        """Return a deterministic, unique identifier for this adapter instance."""
        return f"apple_health:{self._device_id}"

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize all health data types from Apple HealthKit via local API.

        Fetches data from all seven endpoints (workouts, sleep, activity, HRV, heart rate, SpO2, mindfulness)
        and yields normalized content for each record or windowed group.

        Args:
            source_ref: ISO 8601 timestamp for incremental fetch, or empty string for full fetch

        Yields:
            NormalizedContent: Normalized health records with HealthMetadata in extra_metadata

        Raises:
            RuntimeError: If ALL endpoints fail (indicates service/credential issue)
            httpx.HTTPStatusError: Auth errors (401/403) propagate immediately

        Note:
            Errors in individual record processing are caught and logged. Malformed records
            are skipped gracefully, allowing the adapter to continue processing subsequent
            records. Auth errors (401/403) are immediately re-raised to signal credential issues.
            If all endpoints fail, raises an aggregate RuntimeError after attempting all endpoints.
        """
        since = source_ref if source_ref else None
        params = {"since": since} if since else {}
        headers = {"Authorization": f"Bearer {self._api_key}"}

        # Fetch from all endpoints in order (six via generic handler, one via specialized heart_rate handler)
        endpoints_config = [
            ("/workouts", self._process_workout, "workout"),
            ("/sleep", self._process_sleep, "sleep record"),
            ("/activity", self._process_activity, "activity record"),
            ("/hrv", self._process_hrv, "HRV record"),
            ("/spo2", self._process_spo2, "SpO2 record"),
            ("/mindfulness", self._process_mindfulness, "mindfulness record"),
        ]
        failed_endpoints = []

        for endpoint, handler, item_label in endpoints_config:
            try:
                yield from self._fetch_endpoint(endpoint, handler, item_label, params, headers)
            except httpx.HTTPStatusError:
                # Auth errors already logged and re-raised by _fetch_endpoint
                raise
            except EndpointFetchError:
                failed_endpoints.append(endpoint)

        # Fetch heart rate separately (requires windowing by hour)
        try:
            yield from self._fetch_heart_rate(since, headers)
        except httpx.HTTPStatusError:
            # Auth errors already logged and re-raised by _fetch_heart_rate
            raise
        except EndpointFetchError:
            failed_endpoints.append("/heart_rate")

        # Raise aggregate error if all endpoints failed
        total_endpoints = len(endpoints_config) + 1  # +1 for heart_rate
        if len(failed_endpoints) == total_endpoints:
            raise RuntimeError(
                f"All {total_endpoints} endpoints failed to fetch from Apple Health API. "
                "Check API connectivity, credentials, and service status."
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

        Args:
            endpoint: API endpoint path (e.g., "/sleep", "/activity")
            handler: Handler method to process each record
            item_label: Label for logging (e.g., "sleep record")
            params: Query parameters (including "since" if incremental)
            headers: HTTP headers (including Authorization)

        Yields:
            NormalizedContent: Processed records from the endpoint

        Raises:
            httpx.HTTPStatusError: Auth errors (401/403) are immediately re-raised
            EndpointFetchError: If endpoint fails (non-auth errors)

        Note:
            Logs and skips individual malformed records without raising.
            Logs and raises EndpointFetchError for endpoint-level failures (HTTP, request, invalid response schema).
            Auth errors (401/403) are immediately re-raised to signal credential issues.
        """
        try:
            response = httpx.get(
                f"{self._api_url}{endpoint}",
                params=params,
                headers=headers,
                timeout=10.0,
            )
            response.raise_for_status()

            records = response.json()
            if not isinstance(records, list):
                raise ValueError(f"Expected list of records from {endpoint}, got {type(records)}")

            # Process each record
            for idx, record in enumerate(records):
                try:
                    yield from handler(record)
                except (ValueError, KeyError) as e:
                    record_id = record.get("id", f"<index {idx}>")
                    logger.error(f"Skipping malformed {item_label} (ID: {record_id}): {e}")
                    continue

        except httpx.HTTPStatusError as e:
            # Re-raise auth errors immediately
            if e.response.status_code in (401, 403):
                logger.error(
                    f"Authentication error from Apple Health API {endpoint}: "
                    f"{e.response.status_code} {e.response.text}"
                )
                raise
            logger.error(f"HTTP error from Apple Health API {endpoint}: {e.response.status_code} {e.response.text}")
            raise EndpointFetchError(f"HTTP {e.response.status_code} from {endpoint}")
        except httpx.RequestError as e:
            logger.error(f"Request error connecting to Apple Health API at {self._api_url}{endpoint}: {e}")
            raise EndpointFetchError(f"Network error at {endpoint}: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from {endpoint} (possible proxy/HTML response): {e}")
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

        Args:
            since: Optional ISO 8601 timestamp for incremental fetch
            headers: HTTP headers (including Authorization)

        Yields:
            NormalizedContent: One NormalizedContent per hourly window

        Raises:
            httpx.HTTPStatusError: Auth errors (401/403) are immediately re-raised
            EndpointFetchError: If endpoint fails (non-auth errors)

        Note:
            Groups samples by date + hour. Each hourly window becomes one NormalizedContent.
            Logs and skips individual malformed samples without raising.
            Logs and raises EndpointFetchError for endpoint-level failures.
            Auth errors (401/403) are immediately re-raised to signal credential issues.
        """
        params = {"since": since} if since else {}

        try:
            response = httpx.get(
                f"{self._api_url}/heart_rate",
                params=params,
                headers=headers,
                timeout=10.0,
            )
            response.raise_for_status()

            samples = response.json()
            if not isinstance(samples, list):
                raise ValueError(f"Expected list of heart rate samples, got {type(samples)}")

            # Group samples by date + hour
            windows: dict[tuple[str, int], list[dict[str, Any]]] = {}
            for sample in samples:
                try:
                    timestamp = sample["timestamp"]
                    # Parse ISO 8601 to extract date and hour
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    date = dt.date().isoformat()  # YYYY-MM-DD
                    hour = dt.hour
                    key = (date, hour)

                    if key not in windows:
                        windows[key] = []
                    windows[key].append(sample)
                except (ValueError, KeyError) as e:
                    logger.error(f"Skipping malformed heart rate sample: {e}")
                    continue

            # Process each hourly window
            for (date, hour), window_samples in sorted(windows.items()):
                try:
                    yield from self._process_heart_rate(window_samples, date, hour)
                except (ValueError, KeyError) as e:
                    logger.error(f"Skipping malformed heart rate window ({date}T{hour:02d}): {e}")
                    continue

        except httpx.HTTPStatusError as e:
            # Re-raise auth errors immediately
            if e.response.status_code in (401, 403):
                logger.error(
                    f"Authentication error from Apple Health API /heart_rate: "
                    f"{e.response.status_code} {e.response.text}"
                )
                raise
            logger.error(f"HTTP error from Apple Health API /heart_rate: {e.response.status_code} {e.response.text}")
            raise EndpointFetchError(f"HTTP {e.response.status_code} from /heart_rate")
        except httpx.RequestError as e:
            logger.error(f"Request error connecting to Apple Health API at {self._api_url}/heart_rate: {e}")
            raise EndpointFetchError(f"Network error at /heart_rate: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from /heart_rate (possible proxy/HTML response): {e}")
            raise EndpointFetchError(f"JSON decode error at /heart_rate: {e}")
        except ValueError as e:
            logger.error(f"Invalid heart rate response schema: {e}")
            raise EndpointFetchError(f"Invalid schema at /heart_rate: {e}")

    def _process_workout(self, workout: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single workout and yield NormalizedContent.

        Args:
            workout: Workout dict from API response

        Yields:
            NormalizedContent: Normalized workout with HealthMetadata

        Raises:
            ValueError: If required fields are missing or invalid
            KeyError: If required fields are missing
        """
        # Extract required fields
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

        # Extract optional fields
        total_energy_burned = workout.get("totalEnergyBurned")
        total_distance = workout.get("totalDistance")
        average_heart_rate = workout.get("averageHeartRate")

        # Compute duration in minutes
        duration_minutes = int(duration_seconds // 60)

        # Get current timestamp and extract date from start_date
        now = datetime.now(timezone.utc).isoformat()
        date = start_date[:10]  # Extract YYYY-MM-DD

        # Create HealthMetadata with health-specific extra fields
        health_metadata_dict = {
            "record_id": workout_id,
            "health_type": "workout_session",
            "date": date,
            "source_type": "apple_health",
            "date_first_observed": now,
            "duration_minutes": duration_minutes,
            "calories_kcal": total_energy_burned,
            "distance_meters": total_distance,
            "avg_heart_rate_bpm": average_heart_rate,
            "activity_type": activity_type,
        }

        # Validate using HealthMetadata model (validates required fields only)
        try:
            HealthMetadata.model_validate(health_metadata_dict)
        except ValueError as e:
            logger.error(f"HealthMetadata validation failed for workout {workout_id}: {e}")
            raise

        # Create source_id
        source_id = f"{activity_type}/{workout_id}"

        # Build markdown summary
        markdown = self._build_summary(workout, activity_type, duration_minutes)

        # Create structural hints with extra_metadata to preserve all fields
        structural_hints = StructuralHints(
            has_headings=False,
            has_lists=True,
            has_tables=False,
            natural_boundaries=(),
            extra_metadata=health_metadata_dict,
        )

        # Create NormalizedContent
        normalized_content = NormalizedContent(
            markdown=markdown,
            source_id=source_id,
            structural_hints=structural_hints,
            normalizer_version=self.normalizer_version,
        )

        yield normalized_content

    def _process_sleep(self, record: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single sleep record and yield NormalizedContent.

        Args:
            record: Sleep record dict from API response

        Yields:
            NormalizedContent: Normalized sleep summary

        Raises:
            ValueError: If required fields are missing or invalid
            KeyError: If required fields are missing
        """
        # Extract required fields
        record_id = record["id"]
        if not record_id:
            raise ValueError("Sleep record 'id' must not be empty")

        date = record["date"]
        if not date:
            raise ValueError("Sleep record 'date' must not be empty")

        total_sleep_minutes = record["totalSleepMinutes"]
        if not isinstance(total_sleep_minutes, (int, float)):
            raise ValueError("Sleep record 'totalSleepMinutes' must be numeric")

        # Extract optional fields
        deep_sleep_minutes = record.get("deepSleepMinutes")
        rem_sleep_minutes = record.get("remSleepMinutes")
        light_sleep_minutes = record.get("lightSleepMinutes")
        efficiency = record.get("efficiency")
        score = record.get("score")

        now = datetime.now(timezone.utc).isoformat()

        # Create HealthMetadata
        health_metadata_dict = {
            "record_id": record_id,
            "health_type": "sleep_summary",
            "date": date,
            "source_type": "apple_health",
            "date_first_observed": now,
            "duration_minutes": total_sleep_minutes,
            "score": score,
            "deep_sleep_minutes": deep_sleep_minutes,
            "rem_sleep_minutes": rem_sleep_minutes,
            "light_sleep_minutes": light_sleep_minutes,
            "efficiency": efficiency,
        }

        try:
            HealthMetadata.model_validate(health_metadata_dict)
        except ValueError as e:
            logger.error(f"HealthMetadata validation failed for sleep record {record_id}: {e}")
            raise

        source_id = f"sleep/{record_id}"
        markdown = self._build_sleep_summary(record, int(total_sleep_minutes))

        structural_hints = StructuralHints(
            has_headings=False,
            has_lists=True,
            has_tables=False,
            natural_boundaries=(),
            extra_metadata=health_metadata_dict,
        )

        normalized_content = NormalizedContent(
            markdown=markdown,
            source_id=source_id,
            structural_hints=structural_hints,
            normalizer_version=self.normalizer_version,
        )

        yield normalized_content

    def _process_activity(self, record: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single activity summary record and yield NormalizedContent.

        Args:
            record: Activity record dict from API response

        Yields:
            NormalizedContent: Normalized activity summary

        Raises:
            ValueError: If required fields are missing or invalid
            KeyError: If required fields are missing
        """
        # Extract required fields
        record_id = record["id"]
        if not record_id:
            raise ValueError("Activity record 'id' must not be empty")

        date = record["date"]
        if not date:
            raise ValueError("Activity record 'date' must not be empty")

        steps = record["steps"]
        if not isinstance(steps, (int, float)):
            raise ValueError("Activity record 'steps' must be numeric")

        # Extract optional fields
        active_calories = record.get("activeCalories")
        total_calories = record.get("totalCalories")
        active_minutes = record.get("activeMinutes")
        sedentary_minutes = record.get("sedentaryMinutes")
        distance_meters = record.get("distanceMeters")

        now = datetime.now(timezone.utc).isoformat()

        # Create HealthMetadata
        health_metadata_dict = {
            "record_id": record_id,
            "health_type": "activity_summary",
            "date": date,
            "source_type": "apple_health",
            "date_first_observed": now,
            "duration_minutes": active_minutes,
            "steps": steps,
            "active_calories": active_calories,
            "total_calories": total_calories,
            "sedentary_minutes": sedentary_minutes,
            "distance_meters": distance_meters,
        }

        try:
            HealthMetadata.model_validate(health_metadata_dict)
        except ValueError as e:
            logger.error(f"HealthMetadata validation failed for activity record {record_id}: {e}")
            raise

        source_id = f"activity/{record_id}"
        markdown = self._build_activity_summary(record, int(steps))

        structural_hints = StructuralHints(
            has_headings=False,
            has_lists=True,
            has_tables=False,
            natural_boundaries=(),
            extra_metadata=health_metadata_dict,
        )

        normalized_content = NormalizedContent(
            markdown=markdown,
            source_id=source_id,
            structural_hints=structural_hints,
            normalizer_version=self.normalizer_version,
        )

        yield normalized_content

    def _process_hrv(self, record: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single HRV (heart rate variability / readiness) record and yield NormalizedContent.

        Args:
            record: HRV record dict from API response

        Yields:
            NormalizedContent: Normalized readiness summary

        Raises:
            ValueError: If required fields are missing or invalid
            KeyError: If required fields are missing
        """
        # Extract required fields
        record_id = record["id"]
        if not record_id:
            raise ValueError("HRV record 'id' must not be empty")

        date = record["date"]
        if not date:
            raise ValueError("HRV record 'date' must not be empty")

        avg_hrv = record["avgHrv"]
        if not isinstance(avg_hrv, (int, float)):
            raise ValueError("HRV record 'avgHrv' must be numeric")

        # Extract optional fields
        resting_heart_rate = record.get("restingHeartRate")
        body_temperature_deviation = record.get("bodyTemperatureDeviation")

        now = datetime.now(timezone.utc).isoformat()

        # Create HealthMetadata
        health_metadata_dict = {
            "record_id": record_id,
            "health_type": "readiness_summary",
            "date": date,
            "source_type": "apple_health",
            "date_first_observed": now,
            "avg_hrv": avg_hrv,
            "resting_heart_rate": resting_heart_rate,
            "body_temperature_deviation": body_temperature_deviation,
        }

        try:
            HealthMetadata.model_validate(health_metadata_dict)
        except ValueError as e:
            logger.error(f"HealthMetadata validation failed for HRV record {record_id}: {e}")
            raise

        source_id = f"hrv/{record_id}"
        markdown = self._build_hrv_summary(record, avg_hrv)

        structural_hints = StructuralHints(
            has_headings=False,
            has_lists=True,
            has_tables=False,
            natural_boundaries=(),
            extra_metadata=health_metadata_dict,
        )

        normalized_content = NormalizedContent(
            markdown=markdown,
            source_id=source_id,
            structural_hints=structural_hints,
            normalizer_version=self.normalizer_version,
        )

        yield normalized_content

    def _process_heart_rate(
        self,
        window: list[dict[str, Any]],
        window_date: str,
        window_hour: int,
    ) -> Iterator[NormalizedContent]:
        """Process an hourly window of heart rate samples and yield NormalizedContent.

        Args:
            window: List of heart rate sample dicts for the hour
            window_date: Date in YYYY-MM-DD format
            window_hour: Hour (0-23)

        Yields:
            NormalizedContent: Normalized heart rate series for the hour

        Raises:
            ValueError: If required fields are missing or invalid
            KeyError: If required fields are missing
        """
        if not window:
            raise ValueError("Heart rate window must not be empty")

        # Extract heart rates and validate
        heart_rates = []
        for sample in window:
            bpm = sample["bpm"]
            if not isinstance(bpm, (int, float)):
                raise ValueError("Heart rate sample 'bpm' must be numeric")
            heart_rates.append(bpm)

        if not heart_rates:
            raise ValueError("No valid heart rates in window")

        # Compute statistics
        avg_bpm = sum(heart_rates) / len(heart_rates)
        min_bpm = min(heart_rates)
        max_bpm = max(heart_rates)

        now = datetime.now(timezone.utc).isoformat()
        record_id = f"hr:{self._device_id}:{window_date}T{window_hour:02d}"

        # Create HealthMetadata
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

        source_id = f"heart_rate/{window_date}T{window_hour:02d}"
        markdown = self._build_heart_rate_summary(window, avg_bpm, min_bpm, max_bpm)

        structural_hints = StructuralHints(
            has_headings=False,
            has_lists=True,
            has_tables=False,
            natural_boundaries=(),
            extra_metadata=health_metadata_dict,
        )

        normalized_content = NormalizedContent(
            markdown=markdown,
            source_id=source_id,
            structural_hints=structural_hints,
            normalizer_version=self.normalizer_version,
        )

        yield normalized_content

    def _process_spo2(self, record: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single SpO2 (blood oxygen) record and yield NormalizedContent.

        Args:
            record: SpO2 record dict from API response

        Yields:
            NormalizedContent: Normalized SpO2 summary

        Raises:
            ValueError: If required fields are missing or invalid
            KeyError: If required fields are missing
        """
        # Extract required fields
        record_id = record["id"]
        if not record_id:
            raise ValueError("SpO2 record 'id' must not be empty")

        date = record["date"]
        if not date:
            raise ValueError("SpO2 record 'date' must not be empty")

        avg_spo2 = record["avgSpo2"]
        if not isinstance(avg_spo2, (int, float)):
            raise ValueError("SpO2 record 'avgSpo2' must be numeric")

        # Extract optional fields
        breathing_disturbance_index = record.get("breathingDisturbanceIndex")

        now = datetime.now(timezone.utc).isoformat()

        # Create HealthMetadata
        health_metadata_dict = {
            "record_id": record_id,
            "health_type": "spo2_summary",
            "date": date,
            "source_type": "apple_health",
            "date_first_observed": now,
            "avg_spo2": avg_spo2,
            "breathing_disturbance_index": breathing_disturbance_index,
        }

        try:
            HealthMetadata.model_validate(health_metadata_dict)
        except ValueError as e:
            logger.error(f"HealthMetadata validation failed for SpO2 record {record_id}: {e}")
            raise

        source_id = f"spo2/{record_id}"
        markdown = self._build_spo2_summary(record, avg_spo2)

        structural_hints = StructuralHints(
            has_headings=False,
            has_lists=True,
            has_tables=False,
            natural_boundaries=(),
            extra_metadata=health_metadata_dict,
        )

        normalized_content = NormalizedContent(
            markdown=markdown,
            source_id=source_id,
            structural_hints=structural_hints,
            normalizer_version=self.normalizer_version,
        )

        yield normalized_content

    def _process_mindfulness(self, record: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single mindfulness session record and yield NormalizedContent.

        Args:
            record: Mindfulness record dict from API response

        Yields:
            NormalizedContent: Normalized mindfulness session

        Raises:
            ValueError: If required fields are missing or invalid
            KeyError: If required fields are missing
        """
        # Extract required fields
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
            raise ValueError("Mindfulness record 'durationSeconds' must be numeric")

        session_type = record["sessionType"]
        if not session_type:
            raise ValueError("Mindfulness record 'sessionType' must not be empty")

        # Extract optional fields
        mood = record.get("mood")
        tags = record.get("tags", [])

        # Compute duration in minutes
        duration_minutes = int(duration_seconds // 60)

        now = datetime.now(timezone.utc).isoformat()
        date = start_date[:10]  # Extract YYYY-MM-DD

        # Create HealthMetadata
        health_metadata_dict = {
            "record_id": record_id,
            "health_type": "mindfulness_session",
            "date": date,
            "source_type": "apple_health",
            "date_first_observed": now,
            "duration_minutes": duration_minutes,
            "session_type": session_type,
            "mood": mood,
            "tags": tags,
        }

        try:
            HealthMetadata.model_validate(health_metadata_dict)
        except ValueError as e:
            logger.error(f"HealthMetadata validation failed for mindfulness record {record_id}: {e}")
            raise

        source_id = f"mindfulness/{record_id}"
        markdown = self._build_mindfulness_summary(record, session_type, duration_minutes)

        structural_hints = StructuralHints(
            has_headings=False,
            has_lists=True,
            has_tables=False,
            natural_boundaries=(),
            extra_metadata=health_metadata_dict,
        )

        normalized_content = NormalizedContent(
            markdown=markdown,
            source_id=source_id,
            structural_hints=structural_hints,
            normalizer_version=self.normalizer_version,
        )

        yield normalized_content

    def _build_summary(self, workout: dict[str, Any], activity_type: str, duration_minutes: int) -> str:
        """Build a human-readable markdown summary of a workout.

        Generates markdown with bold title and bulleted metrics (no heading-level markers).

        Args:
            workout: Workout dict from API response
            activity_type: Activity type (e.g., "running", "cycling")
            duration_minutes: Duration in minutes

        Returns:
            Markdown string with bold title and bulleted activity summary
        """
        lines = [f"**{activity_type.title()}**"]

        # Add key metrics
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

        # Add duration
        lines.append(f"- Duration: {duration_minutes} minutes")

        # Add notes if present
        notes = workout.get("notes")
        if notes:
            lines.append(f"\n{notes}")

        return "\n".join(lines)

    def _build_sleep_summary(self, record: dict[str, Any], total_sleep_minutes: int) -> str:
        """Build markdown summary of a sleep record.

        Args:
            record: Sleep record dict from API response
            total_sleep_minutes: Total sleep duration in minutes

        Returns:
            Markdown string with sleep metrics
        """
        lines = ["**Sleep Summary**"]

        lines.append(f"- Total sleep: {total_sleep_minutes} minutes")

        deep_sleep = record.get("deepSleepMinutes")
        if deep_sleep is not None:
            lines.append(f"- Deep sleep: {deep_sleep} minutes")

        rem_sleep = record.get("remSleepMinutes")
        if rem_sleep is not None:
            lines.append(f"- REM sleep: {rem_sleep} minutes")

        light_sleep = record.get("lightSleepMinutes")
        if light_sleep is not None:
            lines.append(f"- Light sleep: {light_sleep} minutes")

        efficiency = record.get("efficiency")
        if efficiency is not None:
            lines.append(f"- Efficiency: {efficiency:.1%}")

        score = record.get("score")
        if score is not None:
            lines.append(f"- Score: {score}")

        return "\n".join(lines)

    def _build_activity_summary(self, record: dict[str, Any], steps: int) -> str:
        """Build markdown summary of an activity record.

        Args:
            record: Activity record dict from API response
            steps: Step count

        Returns:
            Markdown string with activity metrics
        """
        lines = ["**Activity Summary**"]

        lines.append(f"- Steps: {steps:,}")

        active_calories = record.get("activeCalories")
        if active_calories is not None:
            lines.append(f"- Active calories: {active_calories:.0f} kcal")

        total_calories = record.get("totalCalories")
        if total_calories is not None:
            lines.append(f"- Total calories: {total_calories:.0f} kcal")

        active_minutes = record.get("activeMinutes")
        if active_minutes is not None:
            lines.append(f"- Active minutes: {active_minutes} min")

        sedentary_minutes = record.get("sedentaryMinutes")
        if sedentary_minutes is not None:
            lines.append(f"- Sedentary minutes: {sedentary_minutes} min")

        distance_meters = record.get("distanceMeters")
        if distance_meters is not None:
            km = distance_meters / 1000
            lines.append(f"- Distance: {km:.2f} km")

        return "\n".join(lines)

    def _build_hrv_summary(self, record: dict[str, Any], avg_hrv: float) -> str:
        """Build markdown summary of an HRV record.

        Args:
            record: HRV record dict from API response
            avg_hrv: Average heart rate variability

        Returns:
            Markdown string with HRV metrics
        """
        lines = ["**HRV / Readiness**"]

        lines.append(f"- Avg HRV: {avg_hrv:.1f} ms")

        resting_hr = record.get("restingHeartRate")
        if resting_hr is not None:
            lines.append(f"- Resting heart rate: {resting_hr:.0f} bpm")

        temp_dev = record.get("bodyTemperatureDeviation")
        if temp_dev is not None:
            lines.append(f"- Temperature deviation: {temp_dev:.2f}°C")

        return "\n".join(lines)

    def _build_heart_rate_summary(
        self,
        window: list[dict[str, Any]],
        avg_bpm: float,
        min_bpm: float,
        max_bpm: float,
    ) -> str:
        """Build markdown summary of an hourly heart rate window.

        Args:
            window: List of heart rate samples
            avg_bpm: Average BPM in window
            min_bpm: Minimum BPM in window
            max_bpm: Maximum BPM in window

        Returns:
            Markdown string with heart rate metrics
        """
        lines = ["**Heart Rate**"]

        lines.append(f"- Average: {avg_bpm:.0f} bpm")
        lines.append(f"- Min: {min_bpm:.0f} bpm")
        lines.append(f"- Max: {max_bpm:.0f} bpm")
        lines.append(f"- Samples: {len(window)}")

        return "\n".join(lines)

    def _build_spo2_summary(self, record: dict[str, Any], avg_spo2: float) -> str:
        """Build markdown summary of a SpO2 record.

        Args:
            record: SpO2 record dict from API response
            avg_spo2: Average blood oxygen saturation percentage

        Returns:
            Markdown string with SpO2 metrics
        """
        lines = ["**Blood Oxygen (SpO2)**"]

        lines.append(f"- Average: {avg_spo2:.1f}%")

        bdi = record.get("breathingDisturbanceIndex")
        if bdi is not None:
            lines.append(f"- Breathing disturbance index: {bdi:.1f}")

        return "\n".join(lines)

    def _build_mindfulness_summary(
        self,
        record: dict[str, Any],
        session_type: str,
        duration_minutes: int,
    ) -> str:
        """Build markdown summary of a mindfulness session.

        Args:
            record: Mindfulness record dict from API response
            session_type: Type of mindfulness session
            duration_minutes: Duration in minutes

        Returns:
            Markdown string with mindfulness metrics
        """
        lines = [f"**{session_type.title()} Session**"]

        lines.append(f"- Duration: {duration_minutes} minutes")

        mood = record.get("mood")
        if mood:
            lines.append(f"- Mood: {mood}")

        tags = record.get("tags", [])
        if tags:
            lines.append(f"- Tags: {', '.join(tags)}")

        return "\n".join(lines)
