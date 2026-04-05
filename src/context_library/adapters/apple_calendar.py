"""AppleCalendarAdapter for ingesting calendar events from a macOS helper service.

This adapter consumes an HTTP REST API served by a macOS helper process that reads
from Apple Calendar and exposes events data. The helper process binds to 0.0.0.0
and requires a Bearer API token for authentication.

Expected Local Service API Contract:
====================================

The macOS helper service should expose the following HTTP endpoint:

  GET /calendar/events
    Query parameters:
      - since (optional): ISO 8601 timestamp; return only events modified after this time

    Response: JSON array of event objects
    Status: 200 OK
    Content-Type: application/json

    Example response body:
    [
      {
        "id": "<string>",
        "title": "<string>",
        "notes": "<string | null>",
        "startDate": "<ISO 8601>",
        "endDate": "<ISO 8601>",
        "isAllDay": <bool>,
        "calendar": "<string>",
        "location": "<string | null>",
        "status": "<string>",  # "confirmed" or "cancelled"
        "lastModified": "<ISO 8601>",
        "attendees": [
          {
            "name": "<string>",
            "email": "<string>"
          }
        ],
        "recurrence": <dict | null>,  # recurrence rules
        "url": "<string | null>"
      }
    ]

Security:
  The helper binds to 0.0.0.0 for network access from remote servers.
  A Bearer API token is REQUIRED: Authorization: Bearer <api_key>

This adapter:
- Fetches calendar events from the local macOS helper API
- Maps Calendar event fields to EventMetadata
- Yields NormalizedContent with EventMetadata in extra_metadata
- Supports both initial ingestion and incremental updates via 'since' parameter
- Only yields events with notes (empty notes → no yield)
"""

import logging
from typing import Iterator

from context_library.adapters.base import BaseAdapter
from context_library.storage.models import (
    Domain,
    PollStrategy,
    EventMetadata,
    NormalizedContent,
    StructuralHints,
)

logger = logging.getLogger(__name__)

# Try to import optional dependencies
HAS_HTTPX = False

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    pass


class AppleCalendarAdapter(BaseAdapter):
    """Adapter that ingests calendar events from a macOS Apple Calendar helper service.

    This adapter communicates with an HTTP service on the Mac that reads from
    Apple Calendar and exposes events data via REST API. The helper binds to
    0.0.0.0 and requires a Bearer API token for authentication.

    Usage: Start the macOS helper service, then instantiate this adapter with
    the helper's base URL and API key. The adapter will fetch calendar events and
    normalize them to EventMetadata for indexing.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        account_id: str = "default",
    ) -> None:
        """Initialize AppleCalendarAdapter.

        Args:
            api_url: Base URL of the macOS helper API (e.g., "http://192.168.1.50:7123")
            api_key: Required bearer token for API authentication
            account_id: Account identifier for adapter_id generation (default: "default")

        Raises:
            ImportError: If httpx is not installed.
            ValueError: If api_key is empty.
        """
        if not HAS_HTTPX:
            raise ImportError(
                "httpx is required for AppleCalendarAdapter. "
                "Install with: pip install context-library[apple-calendar]"
            )
        if not api_key:
            raise ValueError("api_key is required for AppleCalendarAdapter")

        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._account_id = account_id
        self._client = httpx.Client(timeout=30.0)

    @property
    def adapter_id(self) -> str:
        """Return a deterministic adapter ID based on account_id.

        Returns:
            f"apple_calendar:{account_id}"
        """
        return f"apple_calendar:{self._account_id}"

    @property
    def domain(self) -> Domain:
        """Return the domain this adapter serves."""
        return Domain.EVENTS

    @property
    def poll_strategy(self) -> PollStrategy:
        """Return the polling strategy for this adapter."""
        return PollStrategy.PULL

    @property
    def normalizer_version(self) -> str:
        """Return the normalizer version."""
        return "1.0.0"

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

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize calendar events from the macOS helper API.

        The source_ref can optionally contain a last_fetched_at timestamp in ISO 8601
        format. If provided, only events modified after that timestamp are fetched.
        Errors in event processing (schema mismatches, missing fields) are NOT caught —
        they propagate to caller for visibility. This prevents silent skipping when
        the API format changes.

        Args:
            source_ref: ISO 8601 timestamp for incremental ingestion, or empty string for initial

        Yields:
            NormalizedContent for each event with notes

        Raises:
            httpx.HTTPError: If the API request fails
            ValueError: If the helper API returns unexpected response schema or an event
                has missing/malformed fields
            KeyError: If an event is missing required fields
            TypeError: If an event field has unexpected type
        """
        # Determine incremental fetch by presence of timestamp
        since = source_ref if source_ref else None

        # Fetch events from the local API (errors propagate)
        events = self._fetch_events(since)

        # Convert each event to NormalizedContent
        # Process without catching errors to ensure visibility of API schema changes
        for event in events:
            # Extract event metadata - errors propagate
            metadata = self._extract_event_metadata(event)

            # Get notes for the markdown body
            notes = event.get("notes")

            # Only yield events with notes (empty notes → no yield)
            if not notes:
                continue

            # Build structural hints with metadata
            hints = StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata=metadata.model_dump() | self._get_extra_metadata(event),
            )

            # Build markdown representation of event
            markdown = self._build_event_markdown(event, metadata, notes)

            # Yield normalized content
            yield NormalizedContent(
                markdown=markdown,
                source_id=f"apple_calendar/{event['id']}",
                structural_hints=hints,
                normalizer_version=self.normalizer_version,
            )

    def _fetch_events(self, since: str | None) -> list[dict]:
        """Fetch event list from the local macOS helper API.

        Args:
            since: Optional ISO 8601 timestamp to fetch only events modified after this time

        Returns:
            List of event dictionaries

        Raises:
            httpx.HTTPError: If the API request fails
            ValueError: If the API returns unexpected response schema
        """
        # Build query parameters
        params = {}
        if since:
            params["since"] = since

        # Build headers
        headers = {"Authorization": f"Bearer {self._api_key}"}

        # Make the API request
        response = self._client.get(
            f"{self._api_url}/calendar/events",
            params=params,
            headers=headers,
        )
        response.raise_for_status()

        # Parse response
        events = response.json()

        # Validate that response is a list
        if not isinstance(events, list):
            raise ValueError(
                f"macOS helper API 'calendar/events' response must be a list, got {type(events).__name__}"
            )

        return events

    def _extract_event_metadata(self, event: dict) -> EventMetadata:
        """Extract EventMetadata from event response.

        Args:
            event: Event dictionary from macOS helper API

        Returns:
            EventMetadata object with extracted fields

        Raises:
            KeyError: If required fields are missing
            TypeError: If fields have unexpected types
            ValueError: If fields fail validation
        """
        # Extract required fields
        if "id" not in event:
            raise KeyError("Event missing required 'id' field")
        event_id = event["id"]

        if "title" not in event:
            raise KeyError("Event missing required 'title' field")
        title = event["title"]

        if "lastModified" not in event:
            raise KeyError("Event missing required 'lastModified' field")
        last_modified = event["lastModified"]

        # Validate title is non-empty
        if not isinstance(title, str):
            raise TypeError(f"'title' field must be str, got {type(title).__name__}")
        if not title:
            raise ValueError("Event title must be non-empty")

        # Extract optional fields
        start_date = event.get("startDate")
        if start_date is not None and not isinstance(start_date, str):
            raise TypeError(f"'startDate' field must be str or null, got {type(start_date).__name__}")

        end_date = event.get("endDate")
        if end_date is not None and not isinstance(end_date, str):
            raise TypeError(f"'endDate' field must be str or null, got {type(end_date).__name__}")

        # Extract attendees and format as display strings (name + email)
        attendees_raw = event.get("attendees", [])
        if not isinstance(attendees_raw, list):
            raise TypeError(f"'attendees' field must be list, got {type(attendees_raw).__name__}")

        attendees = tuple(
            f"{a.get('name', '')} <{a.get('email', '')}>".strip() if a.get('email') else a.get('name', '')
            for a in attendees_raw
            if a.get('name') or a.get('email')
        )

        # Build EventMetadata
        return EventMetadata(
            event_id=event_id,
            title=title,
            start_date=start_date,
            end_date=end_date,
            invitees=attendees,
            date_first_observed=last_modified,
            source_type="apple_calendar",
        )

    def _get_extra_metadata(self, event: dict) -> dict:
        """Extract extra metadata fields to pass through to extra_metadata.

        Args:
            event: Event dictionary from macOS helper API

        Returns:
            Dictionary with extra metadata fields
        """
        extra = {}

        # Pass through location
        location = event.get("location")
        if location is not None:
            extra["location"] = location

        # Pass through calendar
        calendar = event.get("calendar")
        if calendar is not None:
            extra["calendar"] = calendar

        # Pass through status
        status = event.get("status")
        if status is not None:
            extra["status"] = status

        # Pass through isAllDay
        is_all_day = event.get("isAllDay")
        if is_all_day is not None:
            extra["isAllDay"] = is_all_day

        # Pass through recurrence
        recurrence = event.get("recurrence")
        if recurrence is not None:
            extra["recurrence"] = recurrence

        # Pass through url
        url = event.get("url")
        if url is not None:
            extra["url"] = url

        return extra

    def _build_event_markdown(self, event: dict, metadata: EventMetadata, notes: str) -> str:
        """Build markdown representation of an event.

        Args:
            event: Raw event dictionary from API
            metadata: Extracted EventMetadata
            notes: Event notes/description

        Returns:
            Markdown string representation
        """
        parts = [f"# {metadata.title}"]

        # Add calendar if present
        calendar = event.get("calendar")
        if calendar:
            parts.append(f"\n**Calendar:** {calendar}")

        # Add dates
        if metadata.start_date:
            parts.append(f"**Start:** {metadata.start_date}")
        if metadata.end_date:
            parts.append(f"**End:** {metadata.end_date}")

        # Add location if present
        location = event.get("location")
        if location:
            parts.append(f"**Location:** {location}")

        # Add all-day indicator if true
        is_all_day = event.get("isAllDay", False)
        if is_all_day:
            parts.append("**All Day:** Yes")

        # Add status if not confirmed
        status = event.get("status", "confirmed")
        if status != "confirmed":
            parts.append(f"**Status:** {status}")

        # Add attendees if present
        if metadata.invitees:
            parts.append("\n## Attendees\n\n" + "\n".join(f"- {inv}" for inv in metadata.invitees))

        # Add notes as description
        parts.append(f"\n## Description\n\n{notes}")

        return "\n".join(parts)
