"""AppleRemindersAdapter for ingesting reminders from a macOS helper service.

This adapter consumes an HTTP REST API served by a macOS helper process that reads
from Apple EventKit and exposes Reminders data. The helper process binds to 0.0.0.0
and requires a Bearer API token for authentication.

Expected Local Service API Contract:
====================================

The macOS helper service should expose the following HTTP endpoint:

  GET /reminders
    Query parameters:
      - list (optional): Filter by Reminders list name
      - since (optional): ISO 8601 timestamp; return only reminders modified after this time

    Response: JSON array of reminder objects
    Status: 200 OK
    Content-Type: application/json

    Example response body:
    [
      {
        "id": "<uuid>",
        "title": "<string>",
        "notes": "<string | null>",
        "list": "<string>",
        "completed": <bool>,
        "completionDate": "<ISO 8601 | null>",
        "dueDate": "<ISO 8601 | null>",
        "priority": <int 0-9>,
        "modifiedAt": "<ISO 8601>",
        "collaborators": ["<email>", ...]
      }
    ]

Priority Mapping (EventKit uses 0-9):
  - 0: none (maps to None)
  - 1-3: highest (maps to 1)
  - 4: high (maps to 2)
  - 5-7: medium (maps to 3)
  - 8-9: low (maps to 4)

Security:
  The helper binds to 0.0.0.0 for network access from remote servers.
  A Bearer API token is REQUIRED: Authorization: Bearer <api_key>

This adapter:
- Fetches reminders from the local macOS helper API
- Maps Reminder fields to TaskMetadata
- Yields NormalizedContent with TaskMetadata in extra_metadata
- Supports both initial ingestion and incremental updates via 'since' parameter
- Supports filtering by Reminders list via 'list' query parameter
"""

import logging
from typing import Iterator

from context_library.adapters.base import BaseAdapter
from context_library.storage.models import (
    Domain,
    PollStrategy,
    TaskMetadata,
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


class AppleRemindersAdapter(BaseAdapter):
    """Adapter that ingests reminders from a macOS Apple Reminders helper service.

    This adapter communicates with an HTTP service on the Mac that reads from
    Apple EventKit and exposes Reminders data via REST API. The helper binds to
    0.0.0.0 and requires a Bearer API token for authentication.

    Usage: Start the macOS helper service, then instantiate this adapter with
    the helper's base URL and API key. The adapter will fetch reminders and
    normalize them to TaskMetadata for indexing.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        list_name: str | None = None,
        account_id: str = "default",
    ) -> None:
        """Initialize AppleRemindersAdapter.

        Args:
            api_url: Base URL of the macOS helper API (e.g., "http://192.168.1.50:7123")
            api_key: Required bearer token for API authentication
            list_name: Optional filter to specific Reminders list name
            account_id: Account identifier for adapter_id generation (default: "default")

        Raises:
            ImportError: If httpx is not installed.
            ValueError: If api_key is empty.
        """
        if not HAS_HTTPX:
            raise ImportError(
                "httpx is required for AppleRemindersAdapter. "
                "Install with: pip install context-library[apple-reminders]"
            )
        if not api_key:
            raise ValueError("api_key is required for AppleRemindersAdapter")

        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._list_name = list_name
        self._account_id = account_id
        self._client = httpx.Client(timeout=30.0)

    @property
    def adapter_id(self) -> str:
        """Return a deterministic adapter ID based on account_id.

        Returns:
            f"apple_reminders:{account_id}"
        """
        return f"apple_reminders:{self._account_id}"

    @property
    def domain(self) -> Domain:
        """Return the domain this adapter serves."""
        return Domain.TASKS

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
        """Fetch and normalize reminders from the macOS helper API.

        The source_ref can optionally contain a last_fetched_at timestamp in ISO 8601
        format. If provided, only reminders modified after that timestamp are fetched.
        Errors in reminder processing (schema mismatches, missing fields) are NOT caught —
        they propagate to caller for visibility. This prevents silent skipping when
        the API format changes.

        Args:
            source_ref: ISO 8601 timestamp for incremental ingestion, or empty string for initial

        Yields:
            NormalizedContent for each reminder

        Raises:
            httpx.HTTPError: If the API request fails
            ValueError: If the helper API returns unexpected response schema or a reminder
                has missing/malformed fields
            KeyError: If a reminder is missing required fields
            TypeError: If a reminder field has unexpected type
        """
        # Determine incremental fetch by presence of timestamp
        since = source_ref if source_ref else None

        # Fetch reminders from the local API (errors propagate)
        reminders = self._fetch_reminders(since)

        # Convert each reminder to NormalizedContent
        # Process without catching errors to ensure visibility of API schema changes
        for reminder in reminders:
            # Extract reminder metadata - errors propagate
            metadata = self._extract_task_metadata(reminder)

            # Build structural hints with metadata
            hints = StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata=metadata.model_dump(),
            )

            # Build markdown representation of reminder
            markdown = self._build_reminder_markdown(reminder, metadata)

            # Yield normalized content
            yield NormalizedContent(
                markdown=markdown,
                source_id=f"{reminder['list']}/{reminder['id']}",
                structural_hints=hints,
                normalizer_version=self.normalizer_version,
            )

    def _fetch_reminders(self, since: str | None) -> list[dict]:
        """Fetch reminder list from the local macOS helper API.

        Args:
            since: Optional ISO 8601 timestamp to fetch only reminders modified after this time

        Returns:
            List of reminder dictionaries

        Raises:
            httpx.HTTPError: If the API request fails
            ValueError: If the API returns unexpected response schema
        """
        # Build query parameters
        params = {}
        if self._list_name:
            params["list"] = self._list_name
        if since:
            params["since"] = since

        # Build headers
        headers = {"Authorization": f"Bearer {self._api_key}"}

        # Make the API request
        response = self._client.get(
            f"{self._api_url}/reminders",
            params=params,
            headers=headers,
        )
        response.raise_for_status()

        # Parse response
        reminders = response.json()

        # Validate that response is a list
        if not isinstance(reminders, list):
            raise ValueError(
                f"macOS helper API 'reminders' response must be a list, got {type(reminders).__name__}"
            )

        return reminders

    def _map_priority(self, eventkit_priority: int) -> int | None:
        """Map EventKit priority (0-9) to internal priority (1-4).

        Args:
            eventkit_priority: EventKit priority value (0-9)
                - 0: none
                - 1-3: highest
                - 4: high
                - 5-7: medium
                - 8-9: low

        Returns:
            Internal priority (1-4) or None if eventkit_priority is 0

        Raises:
            ValueError: If eventkit_priority is outside the valid range 0-9
        """
        # Validate priority is in valid range
        if not (0 <= eventkit_priority <= 9):
            raise ValueError(
                f"EventKit priority must be in range 0-9, got {eventkit_priority}"
            )

        if eventkit_priority == 0:
            return None

        # EventKit: 1-3 = highest, 4 = high, 5-7 = medium, 8-9 = low
        # Internal: 1 = highest, 2 = high, 3 = medium, 4 = low
        mapping = {
            1: 1, 2: 1, 3: 1,
            4: 2, 5: 3, 6: 3, 7: 3,
            8: 4, 9: 4,
        }
        return mapping[eventkit_priority]

    def _extract_task_metadata(self, reminder: dict) -> TaskMetadata:
        """Extract TaskMetadata from reminder response.

        Args:
            reminder: Reminder dictionary from macOS helper API

        Returns:
            TaskMetadata object with extracted fields

        Raises:
            KeyError: If required fields are missing
            TypeError: If fields have unexpected types
            ValueError: If fields fail validation
        """
        # Extract required fields
        if "id" not in reminder:
            raise KeyError("Reminder missing required 'id' field")
        reminder_id = reminder["id"]

        if "title" not in reminder:
            raise KeyError("Reminder missing required 'title' field")
        title = reminder["title"]

        if "completed" not in reminder:
            raise KeyError("Reminder missing required 'completed' field")
        completed = reminder["completed"]

        if not isinstance(completed, bool):
            raise TypeError(f"'completed' field must be bool, got {type(completed).__name__}")

        if "modifiedAt" not in reminder:
            raise KeyError("Reminder missing required 'modifiedAt' field")
        modified_at = reminder["modifiedAt"]

        # Validate title is non-empty
        if not isinstance(title, str):
            raise TypeError(f"'title' field must be str, got {type(title).__name__}")
        if not title:
            raise ValueError("Reminder title must be non-empty")

        # Map completion status to status string
        status = "completed" if completed else "open"

        # Extract optional fields
        due_date = reminder.get("dueDate")
        if due_date is not None and not isinstance(due_date, str):
            raise TypeError(f"'dueDate' field must be str or null, got {type(due_date).__name__}")

        priority_raw = reminder.get("priority", 0)
        if not isinstance(priority_raw, int):
            raise TypeError(f"'priority' field must be int, got {type(priority_raw).__name__}")
        priority = self._map_priority(priority_raw)

        collaborators_raw = reminder.get("collaborators", [])
        if not isinstance(collaborators_raw, list):
            raise TypeError(f"'collaborators' field must be list, got {type(collaborators_raw).__name__}")
        collaborators = tuple(collaborators_raw)

        # Extract list name for source identification
        if "list" not in reminder:
            raise KeyError("Reminder missing required 'list' field")
        list_name = reminder["list"]
        if not isinstance(list_name, str):
            raise TypeError(f"'list' field must be str, got {type(list_name).__name__}")

        # Build TaskMetadata
        return TaskMetadata(
            task_id=reminder_id,
            status=status,
            title=title,
            due_date=due_date,
            priority=priority,
            collaborators=collaborators,
            date_first_observed=modified_at,
            source_type="apple_reminders",
        )

    def _build_reminder_markdown(self, reminder: dict, metadata: TaskMetadata) -> str:
        """Build markdown representation of a reminder.

        Args:
            reminder: Raw reminder dictionary from API
            metadata: Extracted TaskMetadata

        Returns:
            Markdown string representation
        """
        parts = [f"# {metadata.title}"]

        # Add status
        parts.append(f"\n**Status:** {metadata.status}")

        # Add priority if present
        if metadata.priority is not None:
            priority_names = {1: "Highest", 2: "High", 3: "Medium", 4: "Low"}
            priority_name = priority_names.get(metadata.priority, "Unknown")
            parts.append(f"**Priority:** {priority_name}")

        # Add due date if present
        if metadata.due_date:
            parts.append(f"**Due:** {metadata.due_date}")

        # Add list/source
        parts.append(f"**List:** {reminder['list']}")

        # Add notes if present
        notes = reminder.get("notes")
        if notes:
            parts.append(f"\n## Notes\n\n{notes}")

        # Add collaborators if present
        if metadata.collaborators:
            parts.append("\n## Collaborators\n\n" + "\n".join(f"- {c}" for c in metadata.collaborators))

        return "\n".join(parts)
