"""Apple HealthKit adapter for a macOS-native helper process.

This adapter consumes a local HTTP REST API served by a macOS helper process that exposes
Apple HealthKit data (workouts, activity summaries, mindfulness sessions) via a local HTTP API.

Expected local service API contract
===================================

The helper process exposes a single endpoint on 127.0.0.1 (localhost only):

GET /workouts
  Query parameters:
    - type (optional): Filter by activity type (e.g., "running", "cycling", "yoga", "mindfulness")
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

Security Note: The helper process MUST bind to 127.0.0.1 only and not expose the API
on network interfaces. Communication should occur only on the local machine.

Example usage:
    adapter = AppleHealthAdapter(
        api_url="http://127.0.0.1:7124",
        activity_type="running",
        device_id="macbook-pro-m1"
    )

    for normalized_content in adapter.fetch(""):  # Full fetch
        print(normalized_content.markdown)

    # Incremental fetch (only workouts starting after given timestamp)
    for normalized_content in adapter.fetch("2025-03-07T10:00:00+00:00"):
        print(normalized_content.markdown)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterator

from context_library.adapters.base import BaseAdapter
from context_library.storage.models import (
    Domain,
    EventMetadata,
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
    """Adapter for consuming Apple HealthKit data via local HTTP REST API.

    The adapter fetches health and fitness data (workouts, activities, mindfulness sessions)
    from a macOS helper process that wraps Apple HealthKit APIs.

    Each workout is mapped to an EventMetadata with:
    - title: Capitalized activity type (e.g., "Running", "Cycling")
    - start_date/end_date: ISO 8601 timestamps from workout data
    - duration_minutes: Computed from durationSeconds
    - host: None (no organizer for health events)
    - invitees: Empty tuple (no participants)
    - Additional health-specific fields in extra_metadata: calories_kcal, distance_meters, avg_heart_rate_bpm
    """

    @property
    def domain(self) -> Domain:
        """Return the domain this adapter handles."""
        return Domain.EVENTS

    @property
    def poll_strategy(self) -> PollStrategy:
        """Return the polling strategy for this adapter."""
        return PollStrategy.PULL

    @property
    def normalizer_version(self) -> str:
        """Return the normalizer version."""
        return "1.0.0"

    def __init__(
        self,
        api_url: str = "http://127.0.0.1:7124",
        api_key: str | None = None,
        activity_type: str | None = None,
        device_id: str = "default",
    ) -> None:
        """Initialize AppleHealthAdapter.

        Args:
            api_url: Base URL of the local helper API (default: http://127.0.0.1:7124)
            api_key: Optional API key for authentication (Bearer token)
            activity_type: Optional filter by activity type (e.g., "running", "cycling")
            device_id: Device identifier for adapter_id computation (default: "default")

        Raises:
            ImportError: If httpx is not installed
        """
        if not HAS_HTTPX:
            raise ImportError(
                "Apple Health adapter requires 'httpx' package. "
                "Install with: pip install context-library[apple-health]"
            )

        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._activity_type = activity_type
        self._device_id = device_id

    @property
    def adapter_id(self) -> str:
        """Return a deterministic, unique identifier for this adapter instance."""
        parts = [f"apple_health:{self._device_id}"]
        if self._activity_type:
            parts.append(f"type={self._activity_type}")
        return ":".join(parts) if len(parts) > 1 else parts[0]

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize health events from Apple HealthKit via local API.

        Args:
            source_ref: ISO 8601 timestamp for incremental fetch, or empty string for full fetch

        Yields:
            NormalizedContent: Normalized workout event with EventMetadata in extra_metadata

        Raises:
            httpx.RequestError: If HTTP request fails
            httpx.HTTPStatusError: If API returns an error status code
            ValueError: If API response is malformed or workout data is invalid
            KeyError: If a workout is missing required fields

        Note:
            Errors in workout processing are NOT caught — they propagate to the caller
            for visibility. This prevents silent skipping when the Apple Health API
            schema changes, ensuring format mismatches are surfaced immediately.
        """
        since = source_ref if source_ref else None

        # Build query parameters
        params = {}
        if self._activity_type:
            params["type"] = self._activity_type
        if since:
            params["since"] = since

        # Build request headers
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            # Fetch workouts from local API
            response = httpx.get(
                f"{self._api_url}/workouts",
                params=params,
                headers=headers,
                timeout=10.0,
            )
            response.raise_for_status()

            workouts = response.json()
            if not isinstance(workouts, list):
                raise ValueError(f"Expected list of workouts, got {type(workouts)}")

            # Process each workout
            for workout in workouts:
                yield from self._process_workout(workout)

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from Apple Health API: {e.response.status_code} {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error connecting to Apple Health API at {self._api_url}: {e}")
            raise

    def _process_workout(self, workout: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single workout and yield NormalizedContent.

        Args:
            workout: Workout dict from API response

        Yields:
            NormalizedContent: Normalized workout event

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

        # Get current timestamp
        now = datetime.now(timezone.utc).isoformat()

        # Create EventMetadata with health-specific extra fields
        event_metadata_dict = {
            "event_id": workout_id,
            "title": activity_type.title(),
            "start_date": start_date,
            "end_date": end_date,
            "duration_minutes": duration_minutes,
            "host": None,
            "invitees": [],
            "date_first_observed": now,
            "source_type": "apple_health",
            # Health-specific extras (do not overlap EventMetadata field names)
            "calories_kcal": total_energy_burned,
            "distance_meters": total_distance,
            "avg_heart_rate_bpm": average_heart_rate,
        }

        # Validate using EventMetadata model (with extra="ignore" it will accept extra fields)
        try:
            EventMetadata.model_validate(event_metadata_dict)
        except ValueError as e:
            logger.error(f"EventMetadata validation failed for workout {workout_id}: {e}")
            raise

        # Create source_id
        source_id = f"{activity_type}/{workout_id}"

        # Build markdown summary
        markdown = self._build_summary(workout, activity_type, duration_minutes)

        # Create structural hints with extra_metadata (preserve all fields including extras)
        # Use raw dict (not model_dump()) to preserve health-specific extra fields
        # that EventMetadata's extra="ignore" would discard
        structural_hints = StructuralHints(
            has_headings=True,
            has_lists=True,
            has_tables=False,
            natural_boundaries=(),
            extra_metadata=event_metadata_dict,
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

        Args:
            workout: Workout dict from API response
            activity_type: Activity type (e.g., "running", "cycling")
            duration_minutes: Duration in minutes

        Returns:
            Markdown string with activity summary
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
