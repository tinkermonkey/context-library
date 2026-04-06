"""AppleBrowserHistoryAdapter for ingesting browser history from a macOS helper service.

This adapter consumes an HTTP REST API served by a macOS helper process that reads
from browser history (Safari, Firefox, Chrome) and exposes visits data. The helper
process binds to 0.0.0.0 and requires a Bearer API token for authentication.

Expected Local Service API Contract:
====================================

The macOS helper service should expose the following HTTP endpoint:

  GET /browser/history
    Query parameters:
      - since (optional): ISO 8601 timestamp; return only visits after this time

    Response: JSON array of visit objects
    Status: 200 OK
    Content-Type: application/json

    Example response body:
    [
      {
        "id": "<string>",
        "url": "<string>",
        "title": "<string | null>",
        "visitedAt": "<ISO 8601>",
        "browser": "<string>",  # "safari", "firefox", or "chrome"
        "visitCount": <int>
      }
    ]

Security:
  The helper binds to 0.0.0.0 for network access from remote servers.
  A Bearer API token is REQUIRED: Authorization: Bearer <api_key>

This adapter:
- Fetches browser visits from the local macOS helper API
- Maps browser visit fields to EventMetadata (using Domain.EVENTS)
- Yields NormalizedContent with EventMetadata in extra_metadata
- Supports both initial ingestion and incremental updates via 'since' parameter
- Yields all visits (unlike calendar which filters on notes)
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


class AppleBrowserHistoryAdapter(BaseAdapter):
    """Adapter that ingests browser visit events from a macOS Apple helper service.

    This adapter communicates with an HTTP service on the Mac that reads from
    browser history (Safari, Firefox, Chrome) and exposes visits data via REST API.
    The helper binds to 0.0.0.0 and requires a Bearer API token for authentication.

    Browser history uses Domain.EVENTS, treating each visit as a timestamped event.
    The visit id serves as the primary event identifier, and visitedAt is the event timestamp.

    Usage: Start the macOS helper service, then instantiate this adapter with
    the helper's base URL and API key. The adapter will fetch browser visits and
    normalize them to EventMetadata for indexing.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        account_id: str = "default",
    ) -> None:
        """Initialize AppleBrowserHistoryAdapter.

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
                "httpx is required for AppleBrowserHistoryAdapter. "
                "Install with: pip install context-library[apple-browser-history]"
            )
        if not api_key:
            raise ValueError("api_key is required for AppleBrowserHistoryAdapter")

        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._account_id = account_id
        self._client = httpx.Client(timeout=30.0)

    @property
    def adapter_id(self) -> str:
        """Return a deterministic adapter ID based on account_id.

        Returns:
            f"apple_browser_history:{account_id}"
        """
        return f"apple_browser_history:{self._account_id}"

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
        """Fetch and normalize browser visits from the macOS helper API.

        The source_ref can optionally contain a last_fetched_at timestamp in ISO 8601
        format. If provided, only visits after that timestamp are fetched.
        Errors in visit processing (schema mismatches, missing fields) are NOT caught —
        they propagate to caller for visibility. This prevents silent skipping when
        the API format changes.

        Args:
            source_ref: ISO 8601 timestamp for incremental ingestion, or empty string for initial

        Yields:
            NormalizedContent for each browser visit as an event with visit id as event_id

        Raises:
            httpx.HTTPError: If the API request fails
            ValueError: If the helper API returns unexpected response schema or a visit
                has missing/malformed fields
            KeyError: If a visit is missing required fields
            TypeError: If a visit field has unexpected type
        """
        # Determine incremental fetch by presence of timestamp
        since = source_ref if source_ref else None

        # Fetch visits from the local API (errors propagate)
        visits = self._fetch_visits(since)

        # Convert each visit to NormalizedContent
        # Process without catching errors to ensure visibility of API schema changes
        for visit in visits:
            # Extract visit metadata - errors propagate
            metadata = self._extract_visit_metadata(visit)

            # Build markdown representation of visit
            markdown = self._build_visit_markdown(visit)

            # Build structural hints with metadata and extra fields
            hints = StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata=metadata.model_dump() | self._get_extra_metadata(visit),
            )

            # Yield normalized content
            yield NormalizedContent(
                markdown=markdown,
                source_id=f"browser_history/{visit['id']}",
                structural_hints=hints,
                normalizer_version=self.normalizer_version,
            )

    def _fetch_visits(self, since: str | None) -> list[dict]:
        """Fetch visit list from the local macOS helper API.

        Args:
            since: Optional ISO 8601 timestamp to fetch only visits after this time

        Returns:
            List of visit dictionaries

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
            f"{self._api_url}/browser/history",
            params=params,
            headers=headers,
        )
        response.raise_for_status()

        # Parse response
        visits = response.json()

        # Validate that response is a list
        if not isinstance(visits, list):
            raise ValueError(
                f"macOS helper API 'browser/history' response must be a list, got {type(visits).__name__}"
            )

        return visits

    def _extract_visit_metadata(self, visit: dict) -> EventMetadata:
        """Extract EventMetadata from visit response.

        Args:
            visit: Visit dictionary from macOS helper API

        Returns:
            EventMetadata object with extracted fields

        Raises:
            KeyError: If required fields are missing
            ValueError: If fields fail validation (via Pydantic)
        """
        if "id" not in visit:
            raise KeyError("Visit missing required 'id' field")
        event_id = visit["id"]

        if "url" not in visit:
            raise KeyError("Visit missing required 'url' field")
        url = visit["url"]

        if not url:
            raise ValueError("Visit 'url' field must be a non-empty string")

        if "visitedAt" not in visit:
            raise KeyError("Visit missing required 'visitedAt' field")
        visited_at = visit["visitedAt"]

        # Extract title with fallback to URL if empty or null
        title = visit.get("title")
        if not title:
            title = url

        # Build EventMetadata (Pydantic validates field types)
        # event_id is the visit's id field
        # start_date is the visit timestamp (single moment in time)
        # date_first_observed is also the visit timestamp
        return EventMetadata(
            event_id=event_id,
            title=title,
            start_date=visited_at,
            date_first_observed=visited_at,
            source_type="browser_history",
        )

    def _get_extra_metadata(self, visit: dict) -> dict:
        """Extract extra metadata fields to pass through to extra_metadata.

        Args:
            visit: Visit dictionary from macOS helper API

        Returns:
            Dictionary with extra metadata fields (visit_api_id, browser, visitCount)

        Raises:
            KeyError: If required fields (id, browser, visitCount) are missing.
        """
        # Validate required fields for extra_metadata
        if "id" not in visit:
            raise KeyError("Visit missing required 'id' field")
        if "browser" not in visit:
            raise KeyError("Visit missing required 'browser' field")
        if "visitCount" not in visit:
            raise KeyError("Visit missing required 'visitCount' field")

        # Extract fields (visit['id'] is kept as visit_api_id for reference)
        return {
            "visit_api_id": visit["id"],
            "browser": visit["browser"],
            "visitCount": visit["visitCount"],
        }

    def _build_visit_markdown(self, visit: dict) -> str:
        """Build markdown representation of a visit.

        The visit metadata (title, date, browser, url) is available in extra_metadata
        and will be used by EventsDomain to build context headers. This method
        returns just the minimal body.

        Args:
            visit: Raw visit dictionary from API

        Returns:
            Markdown string representation
        """
        url = visit.get("url", "")
        return f"Visited: {url}"
