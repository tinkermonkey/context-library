"""Apple ScreenTime adapter for app usage and device focus events.

This adapter ingests both app usage and focus events from an Apple ScreenTime
helper service, both yielding to the Events domain:

- **App Usage**: Per-app screen time aggregated by day
  Source ID: `screentime/app-usage/{bundleId}/{date}` (stable for hash dedup)

- **Focus Events**: Device lock/unlock events
  Source ID: `screentime/focus/{timestamp}`

Both endpoints are fetched independently; one endpoint failure yields a
PartialFetchError while both endpoints failing yields AllEndpointsFailedError.

Expected Local Service API Contract
====================================

GET /screentime/app-usage?since=
  Query parameters:
    - since (optional): ISO 8601 timestamp; return records for days strictly
      after this date. Omit to use the configured lookback window.

  Response: JSON array of app usage items
    [
      {
        "date": "<YYYY-MM-DD>",
        "bundleId": "<bundle-id>",
        "appName": "<derived app name>",
        "durationSeconds": <int>
      }
    ]

GET /screentime/focus?since=
  Query parameters:
    - since (optional): ISO 8601 timestamp; return lock/unlock events after this

  Response: JSON array of focus events
    [
      {
        "timestamp": "<ISO 8601>",
        "eventType": "<lock|unlock>"
      }
    ]

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


class AppleScreenTimeAdapter(BaseAdapter):
    """Adapter for consuming Apple ScreenTime data via local or remote HTTP REST API.

    Fetches both app usage and focus events from a macOS helper process that reads
    ScreenTime data. Both types of records are yielded as events.

    Each endpoint is fetched independently, allowing partial data retrieval when
    one endpoint fails.
    """

    @property
    def domain(self) -> Domain:
        return Domain.EVENTS

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
        """Initialize AppleScreenTimeAdapter.

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
                "Apple ScreenTime adapter requires 'httpx' package. "
                "Install with: pip install context-library[apple-screentime]"
            )
        if not api_key:
            raise ValueError("api_key is required for AppleScreenTimeAdapter")

        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._device_id = device_id

    @property
    def adapter_id(self) -> str:
        return f"apple_screentime:{self._device_id}"

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize both app usage and focus events from Apple ScreenTime.

        Args:
            source_ref: ISO 8601 timestamp for incremental fetch, or empty string for full fetch

        Yields:
            NormalizedContent: Normalized ScreenTime events

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

        # Fetch app usage
        try:
            yield from self._fetch_app_usage(params, headers)
        except httpx.HTTPStatusError:
            raise
        except EndpointFetchError:
            failed_endpoints.append("/screentime/app-usage")

        # Fetch focus events
        try:
            yield from self._fetch_focus_events(params, headers)
        except httpx.HTTPStatusError:
            raise
        except EndpointFetchError:
            failed_endpoints.append("/screentime/focus")

        # Raise appropriate error based on failure count
        if failed_endpoints:
            if len(failed_endpoints) == total_endpoints:
                raise AllEndpointsFailedError(
                    total_endpoints,
                    f"All {total_endpoints} Apple ScreenTime endpoints failed. "
                    "Check API connectivity, credentials, and service status.",
                )
            else:
                raise PartialFetchError(
                    failed_endpoints,
                    total_endpoints,
                    f"Partial fetch from Apple ScreenTime: {len(failed_endpoints)}/{total_endpoints} "
                    "endpoint(s) failed. Successful endpoints provided partial data.",
                )

    def _fetch_app_usage(
        self,
        params: dict[str, Any],
        headers: dict[str, str],
    ) -> Iterator[NormalizedContent]:
        """Fetch and process app usage from /screentime/app-usage endpoint.

        Raises:
            httpx.HTTPStatusError: Auth errors (401/403) are immediately re-raised
            EndpointFetchError: If the endpoint fails for any other reason
        """
        try:
            response = httpx.get(
                f"{self._api_url}/screentime/app-usage",
                params=params,
                headers=headers,
                timeout=120.0,
            )
            response.raise_for_status()

            items = response.json()
            if not isinstance(items, list):
                raise ValueError(f"Expected list from /screentime/app-usage, got {type(items)}")

            for idx, item in enumerate(items):
                try:
                    yield from self._process_app_usage_item(item)
                except (ValueError, KeyError) as e:
                    item_id = item.get("bundleId", f"<index {idx}>") if isinstance(item, dict) else f"<index {idx}>"
                    logger.error(f"Skipping malformed app usage item ({item_id}): {e}")
                    continue

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                logger.error(
                    f"Authentication error from Apple ScreenTime API /screentime/app-usage: "
                    f"{e.response.status_code} {e.response.text}"
                )
                raise
            logger.error(f"HTTP error from Apple ScreenTime API /screentime/app-usage: {e.response.status_code}")
            raise EndpointFetchError(f"HTTP {e.response.status_code} from /screentime/app-usage")
        except httpx.RequestError as e:
            logger.error(
                f"Request error connecting to Apple ScreenTime API at {self._api_url}/screentime/app-usage: {e}"
            )
            raise EndpointFetchError(f"Network error at /screentime/app-usage: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from /screentime/app-usage: {e}")
            raise EndpointFetchError(f"JSON decode error at /screentime/app-usage: {e}")
        except ValueError as e:
            logger.error(f"Invalid response schema from /screentime/app-usage: {e}")
            raise EndpointFetchError(f"Invalid schema at /screentime/app-usage: {e}")

    def _fetch_focus_events(
        self,
        params: dict[str, Any],
        headers: dict[str, str],
    ) -> Iterator[NormalizedContent]:
        """Fetch and process focus events from /screentime/focus endpoint.

        Raises:
            httpx.HTTPStatusError: Auth errors (401/403) are immediately re-raised
            EndpointFetchError: If the endpoint fails for any other reason
        """
        try:
            response = httpx.get(
                f"{self._api_url}/screentime/focus",
                params=params,
                headers=headers,
                timeout=120.0,
            )
            response.raise_for_status()

            items = response.json()
            if not isinstance(items, list):
                raise ValueError(f"Expected list from /screentime/focus, got {type(items)}")

            for idx, item in enumerate(items):
                try:
                    yield from self._process_focus_event(item)
                except (ValueError, KeyError) as e:
                    item_id = item.get("timestamp", f"<index {idx}>") if isinstance(item, dict) else f"<index {idx}>"
                    logger.error(f"Skipping malformed focus event ({item_id}): {e}")
                    continue

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                logger.error(
                    f"Authentication error from Apple ScreenTime API /screentime/focus: "
                    f"{e.response.status_code} {e.response.text}"
                )
                raise
            logger.error(f"HTTP error from Apple ScreenTime API /screentime/focus: {e.response.status_code}")
            raise EndpointFetchError(f"HTTP {e.response.status_code} from /screentime/focus")
        except httpx.RequestError as e:
            logger.error(
                f"Request error connecting to Apple ScreenTime API at {self._api_url}/screentime/focus: {e}"
            )
            raise EndpointFetchError(f"Network error at /screentime/focus: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from /screentime/focus: {e}")
            raise EndpointFetchError(f"JSON decode error at /screentime/focus: {e}")
        except ValueError as e:
            logger.error(f"Invalid response schema from /screentime/focus: {e}")
            raise EndpointFetchError(f"Invalid schema at /screentime/focus: {e}")

    def _process_app_usage_item(self, item: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single app usage item and yield NormalizedContent.

        Args:
            item: App usage item from the API

        Raises:
            KeyError: If required fields are missing
            ValueError: If fields fail validation
        """
        date = item["date"]
        if not date:
            raise ValueError("App usage item 'date' must not be empty")

        bundle_id = item.get("bundleId", "")
        if not bundle_id:
            raise ValueError("App usage item 'bundleId' must not be empty")

        app_name = item.get("appName", bundle_id)
        duration_seconds = item.get("durationSeconds", 0)

        # Compute duration in minutes
        duration_minutes = int(duration_seconds // 60) if duration_seconds else 0

        # Format title as "{appName} — {duration_minutes} min"
        title = f"{app_name} — {duration_minutes} min"

        # Convert date to ISO 8601 timestamp (midnight UTC)
        start_date_iso = f"{date}T00:00:00Z"

        # Build event metadata
        now = datetime.now(timezone.utc).isoformat()
        event_metadata: dict[str, Any] = {
            "event_id": f"screentime/app-usage/{bundle_id}/{date}",
            "title": title,
            "start_date": start_date_iso,
            "end_date": None,
            "duration_minutes": duration_minutes,
            "host": None,
            "invitees": [],
            "date_first_observed": now,
            "source_type": "screentime_app_usage",
        }

        try:
            EventMetadata.model_validate(event_metadata)
        except ValueError as e:
            logger.error(f"EventMetadata validation failed for app usage {bundle_id}/{date}: {e}")
            raise

        # Build markdown representation
        event_lines = [
            f"**{app_name}** screen time on {date}",
            f"- Duration: {duration_minutes} minutes ({duration_seconds} seconds)",
        ]

        yield NormalizedContent(
            markdown="\n".join(event_lines),
            source_id=f"screentime/app-usage/{bundle_id}/{date}",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=True,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata={
                    **event_metadata,
                    "bundleId": bundle_id,
                    "durationSeconds": duration_seconds,
                },
            ),
            normalizer_version=self.normalizer_version,
            domain=Domain.EVENTS,
        )

    def _process_focus_event(self, item: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single focus event and yield NormalizedContent.

        Args:
            item: Focus event item from the API

        Raises:
            KeyError: If required fields are missing
            ValueError: If fields fail validation
        """
        timestamp = item["timestamp"]
        if not timestamp:
            raise ValueError("Focus event 'timestamp' must not be empty")

        event_type = item.get("eventType", "")
        if event_type not in ("lock", "unlock"):
            raise ValueError(f"Focus event 'eventType' must be 'lock' or 'unlock', got '{event_type}'")

        # Format title based on event type
        title = "Device lock" if event_type == "lock" else "Device unlock"

        # Build event metadata
        now = datetime.now(timezone.utc).isoformat()
        event_metadata: dict[str, Any] = {
            "event_id": f"screentime/focus/{timestamp}",
            "title": title,
            "start_date": timestamp,
            "end_date": None,
            "duration_minutes": None,
            "host": None,
            "invitees": [],
            "date_first_observed": now,
            "source_type": "screentime_focus",
        }

        try:
            EventMetadata.model_validate(event_metadata)
        except ValueError as e:
            logger.error(f"EventMetadata validation failed for focus event {timestamp}: {e}")
            raise

        # Build markdown representation
        event_lines = [
            f"**{title}** at {timestamp}",
        ]

        yield NormalizedContent(
            markdown="\n".join(event_lines),
            source_id=f"screentime/focus/{timestamp}",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata={
                    **event_metadata,
                    "eventType": event_type,
                },
            ),
            normalizer_version=self.normalizer_version,
            domain=Domain.EVENTS,
        )
