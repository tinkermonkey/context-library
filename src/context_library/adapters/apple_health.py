"""Apple HealthKit adapter for a macOS-native helper process.

This adapter consumes a local HTTP REST API served by a macOS helper process that exposes
Apple HealthKit workout data via a local HTTP API.

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

The helper process exposes the following HTTP endpoint:

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

from context_library.adapters.base import BaseAdapter, EndpointFetchError, AllEndpointsFailedError
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
    """Adapter for consuming Apple HealthKit workout data via local or remote HTTP REST API.

    Fetches workout data from a macOS helper process that wraps Apple HealthKit APIs.
    The helper service exposes GET /workouts and can run on the local machine or be
    accessible from a remote machine via serve_adapter for cross-machine deployments.

    Each workout is mapped to a HealthMetadata with:
    - record_id: Unique identifier for the workout
    - health_type: "workout_session"
    - date: ISO 8601 date (YYYY-MM-DD) for the workout
    - source_type: "apple_health"
    - date_first_observed: ISO 8601 timestamp when record was processed
    - Additional fields: calories_kcal, distance_meters, avg_heart_rate_bpm, activity_type
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
        """Fetch and normalize workout data from Apple HealthKit via local API.

        Args:
            source_ref: ISO 8601 timestamp for incremental fetch, or empty string for full fetch

        Yields:
            NormalizedContent: Normalized workout records with HealthMetadata in extra_metadata

        Raises:
            AllEndpointsFailedError: If the /workouts endpoint fails
            httpx.HTTPStatusError: Auth errors (401/403) propagate immediately

        Note:
            Errors in individual record processing are caught and logged. Malformed records
            are skipped gracefully. Auth errors (401/403) are immediately re-raised.
        """
        since = source_ref if source_ref else None
        params = {"since": since} if since else {}
        headers = {"Authorization": f"Bearer {self._api_key}"}

        # Apple Health helper only exposes workouts. Sleep, activity, HRV, SpO2,
        # mindfulness, and heart rate are served by the Oura collector (oura.py adapter).
        try:
            yield from self._fetch_endpoint("/workouts", self._process_workout, "workout", params, headers)
        except httpx.HTTPStatusError:
            raise
        except EndpointFetchError:
            raise AllEndpointsFailedError(
                1,
                "Failed to fetch from /workouts. "
                "Check API connectivity, credentials, and service status.",
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
            endpoint: API endpoint path (e.g., "/workouts")
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
                timeout=120.0,
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

    def _process_workout(self, workout: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single workout and yield NormalizedContent.

        Args:
            workout: Workout dict from API response

        Yields:
            NormalizedContent: Normalized workout with HealthMetadata

        Raises:
            ValueError: If required field values are empty or invalid
            KeyError: If required fields are missing from the record
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

