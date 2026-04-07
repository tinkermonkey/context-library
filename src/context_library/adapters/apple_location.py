"""Apple Location adapter for place visits and current location snapshots.

This adapter ingests both place visits and current location from an Apple Location
helper service, both yielding to the Location domain:

- **Visits**: Historical place visit records with arrival/departure times
  Source ID: `apple_location/visit/{id}` (stable for hash dedup)

- **Current**: Current location snapshot
  Source ID: `apple-location-current` (fixed, overwritten each fetch)

Both endpoints are fetched independently; one endpoint failure yields a
PartialFetchError while both endpoints failing yields AllEndpointsFailedError.

Expected Local Service API Contract
====================================

GET /location/visits?since=
  Query parameters:
    - since (optional): ISO 8601 timestamp; return visits strictly after this date.
      Omit to use the configured lookback window.

  Response: JSON array of visit items
    [
      {
        "id": "<unique-identifier>",
        "latitude": <float>,
        "longitude": <float>,
        "placeName": "<optional place name>",
        "locality": "<optional city>",
        "country": "<optional country>",
        "arrivalDate": "<ISO 8601 timestamp>",
        "departureDate": "<ISO 8601 timestamp>",
        "durationMinutes": <int>
      }
    ]

GET /location/current
  Response: JSON object with current location or empty object
    {
      "latitude": <float>,
      "longitude": <float>,
      "placeName": "<optional place name>",
      "locality": "<optional city>",
      "country": "<optional country>",
      "accuracy": <float>,
      "updatedAt": "<ISO 8601 timestamp>"
    }
    or {} if no current location available

Security:
  A Bearer API token is REQUIRED: Authorization: Bearer <api_key>
"""

from __future__ import annotations

import json
import logging
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
    LocationMetadata,
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


class AppleLocationAdapter(BaseAdapter):
    """Adapter for consuming Apple Location data via local or remote HTTP REST API.

    Fetches both place visits and current location from a macOS helper process that reads
    Location data. Both types of records are yielded as location domain content.

    Each endpoint is fetched independently, allowing partial data retrieval when
    one endpoint fails.
    """

    @property
    def domain(self) -> Domain:
        return Domain.LOCATION

    @property
    def poll_strategy(self) -> PollStrategy:
        return PollStrategy.PULL

    @property
    def normalizer_version(self) -> str:
        return "1.0.0"

    def __init__(
        self,
        api_url: str,
        api_key: str,
        device_id: str = "default",
    ) -> None:
        """Initialize AppleLocationAdapter.

        Args:
            api_url: Base URL of the helper API (e.g., "http://192.168.1.50:7123")
            api_key: Required API key for Bearer token authentication
            device_id: Device identifier for adapter_id computation (default: "default")

        Raises:
            ImportError: If httpx is not installed
            ValueError: If api_key is empty
        """
        if not HAS_HTTPX:
            raise ImportError(
                "Apple Location adapter requires 'httpx' package. "
                "Install with: pip install context-library[apple-location]"
            )
        if not api_key:
            raise ValueError("api_key is required for AppleLocationAdapter")

        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._device_id = device_id
        self._client = httpx.Client(timeout=30.0)

    def __enter__(self):
        """Context manager entry: return self for use in with statement."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: clean up httpx.Client session."""
        self._client.close()
        return False

    def __del__(self) -> None:
        """Clean up httpx.Client session when adapter is destroyed (safety net)."""
        if hasattr(self, "_client"):
            self._client.close()

    @property
    def adapter_id(self) -> str:
        return f"apple_location:{self._device_id}"

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize both place visits and current location from Apple Location.

        Args:
            source_ref: ISO 8601 timestamp for incremental fetch, or empty string for full fetch

        Yields:
            NormalizedContent: Normalized Location records

        Raises:
            AllEndpointsFailedError: If all endpoints fail
            PartialFetchError: If some endpoints fail but others succeed
            httpx.HTTPStatusError: Auth errors (401/403) propagate immediately
        """
        since = source_ref if source_ref else None
        params = {"since": since} if since else {}
        headers = {"Authorization": f"Bearer {self._api_key}"}

        failed_endpoints = []
        total_endpoints = 2

        # Fetch place visits
        try:
            yield from self._fetch_visits(params, headers)
        except httpx.HTTPStatusError:
            raise
        except EndpointFetchError:
            failed_endpoints.append("/location/visits")

        # Fetch current location
        try:
            yield from self._fetch_current(headers)
        except httpx.HTTPStatusError:
            raise
        except EndpointFetchError:
            failed_endpoints.append("/location/current")

        # Raise appropriate error based on failure count
        if failed_endpoints:
            if len(failed_endpoints) == total_endpoints:
                raise AllEndpointsFailedError(
                    total_endpoints,
                    f"All {total_endpoints} Apple Location endpoints failed. "
                    "Check API connectivity, credentials, and service status.",
                )
            else:
                raise PartialFetchError(
                    failed_endpoints,
                    total_endpoints,
                    f"Partial fetch from Apple Location: {len(failed_endpoints)}/{total_endpoints} "
                    "endpoint(s) failed. Successful endpoints provided partial data.",
                )

    def _fetch_visits(
        self,
        params: dict[str, Any],
        headers: dict[str, str],
    ) -> Iterator[NormalizedContent]:
        """Fetch and process place visits from /location/visits endpoint.

        Raises:
            httpx.HTTPStatusError: Auth errors (401/403) are immediately re-raised
            EndpointFetchError: If the endpoint fails for any other reason
        """
        try:
            response = self._client.get(
                f"{self._api_url}/location/visits",
                params=params,
                headers=headers,
            )
            response.raise_for_status()

            items = response.json()
            if not isinstance(items, list):
                raise ValueError(f"Expected list from /location/visits, got {type(items)}")

            item_count = len(items)
            yielded_count = 0
            error_count = 0

            for idx, item in enumerate(items):
                try:
                    for normalized_content in self._process_visit_item(item):
                        yielded_count += 1
                        yield normalized_content
                except (ValueError, KeyError) as e:
                    error_count += 1
                    item_id = item.get("id", f"<index {idx}>") if isinstance(item, dict) else f"<index {idx}>"
                    logger.error(f"Skipping malformed visit item ({item_id}): {e}")
                    continue

            # Only raise error if all items were malformed (raised exceptions)
            if item_count > 0 and error_count == item_count:
                logger.error(f"All {item_count} items from /location/visits failed validation; 100% malformed")
                raise EndpointFetchError(f"100% item skip rate from /location/visits: all {item_count} items malformed")

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                logger.error(
                    f"Authentication error from Apple Location API /location/visits: "
                    f"{e.response.status_code} {e.response.text}"
                )
                raise
            logger.error(f"HTTP error from Apple Location API /location/visits: {e.response.status_code}")
            raise EndpointFetchError(f"HTTP {e.response.status_code} from /location/visits")
        except httpx.RequestError as e:
            logger.error(
                f"Request error connecting to Apple Location API at {self._api_url}/location/visits: {e}"
            )
            raise EndpointFetchError(f"Network error at /location/visits: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from /location/visits: {e}")
            raise EndpointFetchError(f"JSON decode error at /location/visits: {e}")
        except ValueError as e:
            logger.error(f"Invalid response schema from /location/visits: {e}")
            raise EndpointFetchError(f"Invalid schema at /location/visits: {e}")

    def _fetch_current(
        self,
        headers: dict[str, str],
    ) -> Iterator[NormalizedContent]:
        """Fetch and process current location from /location/current endpoint.

        Raises:
            httpx.HTTPStatusError: Auth errors (401/403) are immediately re-raised
            EndpointFetchError: If the endpoint fails for any other reason
        """
        try:
            response = self._client.get(
                f"{self._api_url}/location/current",
                headers=headers,
            )
            response.raise_for_status()

            item = response.json()
            if not isinstance(item, dict):
                raise ValueError(f"Expected dict from /location/current, got {type(item)}")

            # Gracefully skip empty response
            if not item:
                return

            yield from self._process_current_item(item)

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                logger.error(
                    f"Authentication error from Apple Location API /location/current: "
                    f"{e.response.status_code} {e.response.text}"
                )
                raise
            logger.error(f"HTTP error from Apple Location API /location/current: {e.response.status_code}")
            raise EndpointFetchError(f"HTTP {e.response.status_code} from /location/current")
        except httpx.RequestError as e:
            logger.error(
                f"Request error connecting to Apple Location API at {self._api_url}/location/current: {e}"
            )
            raise EndpointFetchError(f"Network error at /location/current: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from /location/current: {e}")
            raise EndpointFetchError(f"JSON decode error at /location/current: {e}")
        except ValueError as e:
            logger.error(f"Invalid response schema from /location/current: {e}")
            raise EndpointFetchError(f"Invalid schema at /location/current: {e}")

    def _process_visit_item(self, item: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single place visit item and yield NormalizedContent.

        Args:
            item: Visit item from the API

        Raises:
            KeyError: If required fields are missing
            ValueError: If fields fail validation
        """
        location_id = item.get("id", "")
        if not location_id:
            raise ValueError("Visit item 'id' must not be empty")

        latitude = item.get("latitude")
        if latitude is None:
            raise ValueError("Visit item 'latitude' is required")

        longitude = item.get("longitude")
        if longitude is None:
            raise ValueError("Visit item 'longitude' is required")

        arrival_date = item.get("arrivalDate")
        departure_date = item.get("departureDate")
        duration_minutes = item.get("durationMinutes")
        place_name = item.get("placeName")
        locality = item.get("locality")
        country = item.get("country")

        # Build location metadata
        now = datetime.now(timezone.utc).isoformat()
        location_metadata: dict[str, Any] = {
            "location_id": f"apple_location/visit/{location_id}",
            "latitude": latitude,
            "longitude": longitude,
            "source_type": "apple_location_visit",
            "date_first_observed": now,
            "place_name": place_name,
            "locality": locality,
            "country": country,
            "arrival_date": arrival_date,
            "departure_date": departure_date,
            "duration_minutes": duration_minutes,
        }

        try:
            LocationMetadata.model_validate(location_metadata)
        except ValueError as e:
            logger.error(f"LocationMetadata validation failed for visit {location_id}: {e}")
            raise

        # Build markdown representation
        location_lines = []
        if place_name:
            location_lines.append(f"**{place_name}**")
        else:
            location_lines.append(f"**{latitude}, {longitude}**")

        if arrival_date and departure_date:
            location_lines.append(f"- Visit: {arrival_date} to {departure_date}")
        elif arrival_date:
            location_lines.append(f"- Arrival: {arrival_date}")

        if duration_minutes:
            location_lines.append(f"- Duration: {duration_minutes} minutes")

        if locality or country:
            location_parts = []
            if locality:
                location_parts.append(locality)
            if country:
                location_parts.append(country)
            location_lines.append(f"- Location: {', '.join(location_parts)}")

        yield NormalizedContent(
            markdown="\n".join(location_lines),
            source_id=f"apple_location/visit/{location_id}",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=True,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata={
                    **location_metadata,
                    "id": location_id,
                },
            ),
            normalizer_version=self.normalizer_version,
            domain=Domain.LOCATION,
        )

    def _process_current_item(self, item: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process current location item and yield NormalizedContent.

        Args:
            item: Current location item from the API

        Raises:
            KeyError: If required fields are missing
            ValueError: If fields fail validation
        """
        latitude = item.get("latitude")
        if latitude is None:
            raise ValueError("Current location 'latitude' is required")

        longitude = item.get("longitude")
        if longitude is None:
            raise ValueError("Current location 'longitude' is required")

        place_name = item.get("placeName")
        locality = item.get("locality")
        country = item.get("country")

        # Use updatedAt timestamp from API if available, otherwise use current time
        timestamp = item.get("updatedAt")
        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()

        # Build location metadata
        location_metadata: dict[str, Any] = {
            "location_id": "apple-location-current",
            "latitude": latitude,
            "longitude": longitude,
            "source_type": "apple_location_current",
            "date_first_observed": timestamp,
            "place_name": place_name,
            "locality": locality,
            "country": country,
            "arrival_date": None,
            "departure_date": None,
            "duration_minutes": None,
        }

        try:
            LocationMetadata.model_validate(location_metadata)
        except ValueError as e:
            logger.error(f"LocationMetadata validation failed for current location: {e}")
            raise

        # Build markdown representation
        location_lines = []
        if place_name:
            location_lines.append(f"**Current: {place_name}**")
        else:
            location_lines.append(f"**Current location: {latitude}, {longitude}**")

        if locality or country:
            location_parts = []
            if locality:
                location_parts.append(locality)
            if country:
                location_parts.append(country)
            location_lines.append(f"- Location: {', '.join(location_parts)}")

        location_lines.append(f"- Coordinates: {latitude}, {longitude}")
        location_lines.append(f"- Timestamp: {timestamp}")

        yield NormalizedContent(
            markdown="\n".join(location_lines),
            source_id="apple-location-current",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=True,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata=location_metadata,
            ),
            normalizer_version=self.normalizer_version,
            domain=Domain.LOCATION,
        )
