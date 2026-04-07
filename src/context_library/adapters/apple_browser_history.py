"""AppleBrowserHistoryAdapter for ingesting browser history from a macOS helper service.

This adapter consumes an HTTP REST API served by a macOS helper process that reads
from browser history (Safari, Firefox, Chrome) and exposes visits and open tabs data.
The helper process binds to 0.0.0.0 and requires a Bearer API token for authentication.

Expected Local Service API Contract:
====================================

The macOS helper service should expose the following HTTP endpoints:

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

  GET /browser/tabs
    Response: JSON array of open tab objects
    Status: 200 OK
    Content-Type: application/json

    Example response body:
    [
      {
        "url": "<string>",
        "title": "<string>",
        "browser": "<string>"  # "safari", "firefox", or "chrome"
      }
    ]

Security:
  The helper binds to 0.0.0.0 for network access from remote servers.
  A Bearer API token is REQUIRED: Authorization: Bearer <api_key>

This adapter:
- Fetches browser visits and open tabs from the local macOS helper API
- Maps browser data to DocumentMetadata (using Domain.DOCUMENTS)
- Yields NormalizedContent with DocumentMetadata in extra_metadata
- Supports both initial ingestion and incremental updates via 'since' parameter for history
- Yields all visits and currently open tabs
"""

import hashlib
import logging
from typing import Iterator

from context_library.adapters.base import BaseAdapter, EndpointFetchError
from context_library.storage.models import (
    Domain,
    PollStrategy,
    DocumentMetadata,
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
    """Adapter that ingests browser visits and open tabs from a macOS Apple helper service.

    This adapter communicates with an HTTP service on the Mac that reads from
    browser history (Safari, Firefox, Chrome) and exposes visits and open tabs data via REST API.
    The helper binds to 0.0.0.0 and requires a Bearer API token for authentication.

    Browser history uses Domain.DOCUMENTS, treating each page as a document identified by its URL.
    The URL serves as the primary document identifier, and visitedAt (for history) or current time (for tabs)
    is the observation timestamp.

    Usage: Start the macOS helper service, then instantiate this adapter with
    the helper's base URL and API key. The adapter will fetch browser visits and open tabs,
    normalizing them to DocumentMetadata for indexing.
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
        return Domain.DOCUMENTS

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
        """Fetch and normalize browser visits and open tabs from the macOS helper API.

        The source_ref can optionally contain a last_fetched_at timestamp in ISO 8601
        format. If provided, only visits after that timestamp are fetched from /browser/history.
        Errors in item processing (schema mismatches, missing fields) are caught
        and logged; the adapter continues processing remaining items. If all items
        are malformed, raises EndpointFetchError to signal complete failure.

        Args:
            source_ref: ISO 8601 timestamp for incremental ingestion, or empty string for initial

        Yields:
            NormalizedContent for each browser visit and open tab as a document with URL as document_id

        Raises:
            httpx.HTTPError: If the API request fails
            ValueError: If the helper API returns unexpected response schema
            EndpointFetchError: If all items are malformed and none can be processed
        """
        # Determine incremental fetch by presence of timestamp
        since = source_ref if source_ref else None

        # Fetch visits and tabs from the local API (errors propagate)
        visits = self._fetch_visits(since)
        tabs = self._fetch_tabs()

        # Combine all items (visits and tabs)
        all_items = []
        for visit in visits:
            all_items.append(("history", visit))
        for tab in tabs:
            all_items.append(("tab", tab))

        # Convert each item to NormalizedContent
        # Per-item errors are caught to allow processing remaining items
        successful_count = 0
        for idx, (item_type, item_data) in enumerate(all_items):
            try:
                # Extract metadata based on item type
                metadata = self._extract_document_metadata(item_data, item_type)

                # Build markdown representation
                markdown = self._build_document_markdown(item_data, item_type)

                # Build structural hints with metadata and extra fields
                extra_meta = self._get_extra_metadata(item_data, item_type)
                hints = StructuralHints(
                    has_headings=False,
                    has_lists=False,
                    has_tables=False,
                    natural_boundaries=(),
                    extra_metadata=metadata.model_dump() | extra_meta,
                )

                # Build source_id: use URL as primary identifier (for documents)
                url = item_data.get("url", "")
                if item_type == "history":
                    visit_id = item_data.get("id", "")
                    source_id = f"browser_history/{visit_id}"
                else:  # tab
                    # For tabs, use a hash of URL since tabs don't have stable IDs
                    url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
                    source_id = f"browser_tab/{url_hash}"

                # Yield normalized content
                yield NormalizedContent(
                    markdown=markdown,
                    source_id=source_id,
                    structural_hints=hints,
                    normalizer_version=self.normalizer_version,
                )
                successful_count += 1

            except (ValueError, KeyError) as e:
                if isinstance(item_data, dict):
                    item_id = item_data.get("id") or item_data.get("url", f"<index {idx}>")
                else:
                    item_id = f"<index {idx}>"
                logger.error(f"Skipping malformed {item_type} (ID: {item_id}): {e}")
                continue

        # If all items were malformed, signal complete failure
        if all_items and successful_count == 0:
            raise EndpointFetchError(
                f"All {len(all_items)} items from /browser/history and /browser/tabs were malformed and could not be processed. "
                "This may indicate a helper API schema change or malformed response."
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

    def _fetch_tabs(self) -> list[dict]:
        """Fetch open tabs list from the local macOS helper API.

        Returns:
            List of tab dictionaries

        Raises:
            httpx.HTTPError: If the API request fails
            ValueError: If the API returns unexpected response schema
        """
        # Build headers
        headers = {"Authorization": f"Bearer {self._api_key}"}

        # Make the API request
        response = self._client.get(
            f"{self._api_url}/browser/tabs",
            headers=headers,
        )
        response.raise_for_status()

        # Parse response
        tabs = response.json()

        # Validate that response is a list
        if not isinstance(tabs, list):
            raise ValueError(
                f"macOS helper API 'browser/tabs' response must be a list, got {type(tabs).__name__}"
            )

        return tabs

    def _extract_document_metadata(self, item: dict, item_type: str) -> DocumentMetadata:
        """Extract DocumentMetadata from item response.

        Args:
            item: Item dictionary from macOS helper API (visit or tab)
            item_type: Type of item ("history" or "tab")

        Returns:
            DocumentMetadata object with extracted fields

        Raises:
            KeyError: If required fields are missing
            ValueError: If fields fail validation (via Pydantic)
        """
        if "url" not in item:
            raise KeyError(f"{item_type} missing required 'url' field")
        url = item["url"]

        if not url:
            raise ValueError(f"{item_type} 'url' field must be a non-empty string")

        # Extract title with fallback to URL if empty or null
        title = item.get("title")
        if not title:
            title = url

        # Build DocumentMetadata (Pydantic validates field types)
        # document_id is the URL (primary identifier of the page/resource)
        # source_type is "browser_history" or "browser_tabs"
        source_type = "browser_history" if item_type == "history" else "browser_tabs"

        return DocumentMetadata(
            document_id=url,
            title=title,
            document_type="text/html",
            source_type=source_type,
        )

    def _get_extra_metadata(self, item: dict, item_type: str) -> dict:
        """Extract extra metadata fields to pass through to extra_metadata.

        Args:
            item: Item dictionary from macOS helper API (visit or tab)
            item_type: Type of item ("history" or "tab")

        Returns:
            Dictionary with extra metadata fields specific to item type

        Raises:
            KeyError: If required fields are missing.
        """
        # Extract browser field (required for both history and tabs)
        if "browser" not in item:
            raise KeyError(f"{item_type} missing required 'browser' field")

        extra = {
            "browser": item["browser"],
        }

        # Extract visit-specific fields for history items
        if item_type == "history":
            if "id" not in item:
                raise KeyError("history item missing required 'id' field")
            if "visitCount" not in item:
                raise KeyError("history item missing required 'visitCount' field")
            if "visitedAt" not in item:
                raise KeyError("history item missing required 'visitedAt' field")

            extra.update({
                "visit_id": item["id"],
                "visitCount": item["visitCount"],
                "visitedAt": item["visitedAt"],
            })

        return extra

    def _build_document_markdown(self, item: dict, item_type: str) -> str:
        """Build markdown representation of a document (visit or tab).

        The document metadata (title, date, browser, url) is available in the merged
        extra_metadata dict (combined from DocumentMetadata and _get_extra_metadata)
        and will be used by DocumentsDomain to build context headers. This method
        returns just the minimal body.

        Args:
            item: Raw item dictionary from API (visit or tab)
            item_type: Type of item ("history" or "tab")

        Returns:
            Markdown string representation
        """
        url = item.get("url", "")
        if item_type == "history":
            return f"Visited: {url}"
        else:  # tab
            return f"Currently open: {url}"
