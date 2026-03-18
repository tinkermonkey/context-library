"""AppleNotesAdapter for ingesting Apple Notes from a macOS helper service.

This adapter consumes an HTTP REST API served by a macOS helper process that reads
from the Apple Notes SQLite database and exposes note data.

Expected Local Service API Contract:
====================================

The macOS helper service should expose the following HTTP endpoint:

  GET /notes/notes
    Query parameters:
      - since (optional): ISO 8601 timestamp; return only notes modified after this time

    Response: JSON array of note objects
    Status: 200 OK
    Content-Type: application/json

    Example response body:
    [
      {
        "id": "<string>",
        "title": "<string>",
        "body_markdown": "<string>",
        "folder": "<string | null>",
        "created_at": "<ISO 8601>",
        "modified_at": "<ISO 8601>"
      }
    ]

Security:
  The helper binds to 0.0.0.0 for network access from remote servers.
  A Bearer API token is REQUIRED: Authorization: Bearer <api_key>

This adapter:
- Fetches notes from the local macOS helper API
- Yields NormalizedContent with note metadata in extra_metadata
- Supports incremental updates via 'since' parameter
"""

import logging
from datetime import datetime
from typing import Iterator

from context_library.adapters.base import BaseAdapter
from context_library.storage.models import (
    Domain,
    NormalizedContent,
    PollStrategy,
    StructuralHints,
)

logger = logging.getLogger(__name__)

HAS_HTTPX = False
try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    pass


class AppleNotesAdapter(BaseAdapter):
    """Adapter that ingests Apple Notes from a macOS helper service.

    Communicates with an HTTP service on the Mac that reads from
    NoteStore.sqlite and exposes notes via REST API.
    Requires Full Disk Access for the helper process.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        folder_filter: str | None = None,
        account_id: str = "default",
    ) -> None:
        """Initialize AppleNotesAdapter.

        Args:
            api_url: Base URL of the macOS helper API (e.g., "http://192.168.1.50:7123")
            api_key: Required bearer token for API authentication
            folder_filter: Optional filter to a specific folder name
            account_id: Account identifier for adapter_id generation (default: "default")

        Raises:
            ImportError: If httpx is not installed.
            ValueError: If api_key is empty.
        """
        if not HAS_HTTPX:
            raise ImportError(
                "httpx is required for AppleNotesAdapter. "
                "Install with: pip install context-library[apple-notes]"
            )
        if not api_key:
            raise ValueError("api_key is required for AppleNotesAdapter")

        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._folder_filter = folder_filter
        self._account_id = account_id
        self._client = httpx.Client(timeout=30.0)

    @property
    def adapter_id(self) -> str:
        return f"apple_notes:{self._account_id}"

    @property
    def domain(self) -> Domain:
        return Domain.NOTES

    @property
    def poll_strategy(self) -> PollStrategy:
        return PollStrategy.PULL

    @property
    def normalizer_version(self) -> str:
        return "1.0.0"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._client.close()
        return False

    def __del__(self) -> None:
        if hasattr(self, "_client"):
            self._client.close()

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize Apple Notes from the macOS helper API.

        Args:
            source_ref: ISO 8601 timestamp for incremental ingestion, or empty string for initial

        Yields:
            NormalizedContent for each note

        Raises:
            httpx.HTTPError: If the API request fails
            ValueError: If the helper API returns unexpected response schema
            KeyError: If a note is missing required fields
        """
        since = source_ref if source_ref else None
        notes = self._fetch_notes(since)

        for note in notes:
            self._validate_note(note)

            # Ensure modified_at has timezone info — macOS timestamps are local time
            # with no offset; treat as UTC if no timezone is present.
            modified_at = note["modified_at"]
            if modified_at:
                try:
                    dt = datetime.fromisoformat(modified_at)
                    if dt.tzinfo is None:
                        modified_at = modified_at + "+00:00"
                except ValueError:
                    pass  # leave as-is if parsing fails

            hints = StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=(),
                modified_at=modified_at,
                extra_metadata={
                    "note_id": note["id"],
                    "title": note["title"],
                    "folder": note.get("folder"),
                    "created_at": note["created_at"],
                    "modified_at": modified_at,
                    "source_type": "apple_notes",
                },
            )

            folder = note.get("folder") or "Notes"
            yield NormalizedContent(
                markdown=note["body_markdown"],
                source_id=f"{folder}/{note['id']}",
                structural_hints=hints,
                normalizer_version=self.normalizer_version,
            )

    def _fetch_notes(self, since: str | None) -> list[dict]:
        params = {}
        if since:
            params["since"] = since
        if self._folder_filter:
            params["folder"] = self._folder_filter

        headers = {"Authorization": f"Bearer {self._api_key}"}

        response = self._client.get(
            f"{self._api_url}/notes/notes",
            params=params,
            headers=headers,
        )
        response.raise_for_status()

        notes = response.json()
        if not isinstance(notes, list):
            raise ValueError(
                f"macOS helper API 'notes' response must be a list, got {type(notes).__name__}"
            )

        return notes

    def _validate_note(self, note: dict) -> None:
        """Validate required note fields.

        Raises:
            KeyError: If required fields are missing
            ValueError: If fields fail validation
        """
        for field in ("id", "title", "body_markdown", "created_at", "modified_at"):
            if field not in note:
                raise KeyError(f"Note missing required '{field}' field")

        if not isinstance(note["title"], str):
            raise ValueError(f"Note 'title' must be a string, got {type(note['title']).__name__}")
        if not note["title"]:
            raise ValueError("Note 'title' must be non-empty")
