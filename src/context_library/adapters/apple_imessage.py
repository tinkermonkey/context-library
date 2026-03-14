"""AppleiMessageAdapter for ingesting iMessages from a macOS helper service.

This adapter consumes an HTTP REST API served by a macOS helper process that reads
from the iMessage SQLite database and exposes message data.

Expected Local Service API Contract:
====================================

The macOS helper service should expose the following HTTP endpoint:

  GET /messages
    Query parameters:
      - since (optional): ISO 8601 timestamp; return only messages after this time

    Response: JSON array of message objects
    Status: 200 OK
    Content-Type: application/json

    Example response body:
    [
      {
        "id": "<string>",
        "text": "<string>",
        "sender": "<string>",
        "recipients": ["<string>", ...],
        "timestamp": "<ISO 8601>",
        "thread_id": "<string>",
        "is_from_me": <bool>
      }
    ]

Security:
  The helper binds to 0.0.0.0 for network access from remote servers.
  A Bearer API token is REQUIRED: Authorization: Bearer <api_key>

This adapter:
- Fetches messages from the local macOS helper API
- Maps message fields to MessageMetadata
- Yields NormalizedContent with MessageMetadata in extra_metadata
- Supports incremental updates via 'since' parameter
"""

import logging
from typing import Iterator

from context_library.adapters.base import BaseAdapter
from context_library.storage.models import (
    Domain,
    MessageMetadata,
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


class AppleiMessageAdapter(BaseAdapter):
    """Adapter that ingests iMessages from a macOS helper service.

    Communicates with an HTTP service on the Mac that reads from
    ~/Library/Messages/chat.db and exposes messages via REST API.
    Requires Full Disk Access for the helper process.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        account_id: str = "default",
    ) -> None:
        """Initialize AppleiMessageAdapter.

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
                "httpx is required for AppleiMessageAdapter. "
                "Install with: pip install context-library[apple-imessage]"
            )
        if not api_key:
            raise ValueError("api_key is required for AppleiMessageAdapter")

        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._account_id = account_id
        self._client = httpx.Client(timeout=30.0)

    @property
    def adapter_id(self) -> str:
        return f"apple_imessage:{self._account_id}"

    @property
    def domain(self) -> Domain:
        return Domain.MESSAGES

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
        """Fetch and normalize iMessages from the macOS helper API.

        Args:
            source_ref: ISO 8601 timestamp for incremental ingestion, or empty string for initial

        Yields:
            NormalizedContent for each message

        Raises:
            httpx.HTTPError: If the API request fails
            ValueError: If the helper API returns unexpected response schema
            KeyError: If a message is missing required fields
        """
        since = source_ref if source_ref else None
        messages = self._fetch_messages(since)

        for message in messages:
            metadata = self._extract_message_metadata(message)

            hints = StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata=metadata.model_dump(),
            )

            markdown = self._build_message_markdown(message, metadata)

            yield NormalizedContent(
                markdown=markdown,
                source_id=f"{message['thread_id']}/{message['id']}",
                structural_hints=hints,
                normalizer_version=self.normalizer_version,
            )

    def _fetch_messages(self, since: str | None) -> list[dict]:
        params = {}
        if since:
            params["since"] = since

        headers = {"Authorization": f"Bearer {self._api_key}"}

        response = self._client.get(
            f"{self._api_url}/messages",
            params=params,
            headers=headers,
        )
        response.raise_for_status()

        messages = response.json()
        if not isinstance(messages, list):
            raise ValueError(
                f"macOS helper API 'messages' response must be a list, got {type(messages).__name__}"
            )

        return messages

    def _extract_message_metadata(self, message: dict) -> MessageMetadata:
        """Extract MessageMetadata from a message response dict.

        Raises:
            KeyError: If required fields are missing
            TypeError: If fields have unexpected types
            ValueError: If fields fail validation
        """
        for field in ("id", "text", "sender", "timestamp", "thread_id"):
            if field not in message:
                raise KeyError(f"Message missing required '{field}' field")

        message_id = str(message["id"])
        sender = message["sender"]
        timestamp = message["timestamp"]
        thread_id = str(message["thread_id"])

        if not isinstance(sender, str) or not sender:
            raise ValueError("Message 'sender' must be a non-empty string")

        recipients_raw = message.get("recipients", [])
        if not isinstance(recipients_raw, list):
            raise TypeError(f"'recipients' must be a list, got {type(recipients_raw).__name__}")
        recipients = tuple(str(r) for r in recipients_raw)

        return MessageMetadata(
            thread_id=thread_id,
            message_id=message_id,
            sender=sender,
            recipients=recipients,
            timestamp=timestamp,
            in_reply_to=None,
            subject=None,
            # The iMessage API does not expose reply-chain information, so we cannot
            # reliably determine thread roots at the adapter layer. Setting False here
            # is safe: MessageMetadata requires is_thread_root and in_reply_to to be
            # mutually exclusive, and both False/None satisfies that invariant.
            is_thread_root=False,
        )

    def _build_message_markdown(self, message: dict, metadata: MessageMetadata) -> str:
        """Build markdown representation of a message."""
        is_from_me = message.get("is_from_me", False)
        direction = "Me" if is_from_me else metadata.sender

        parts = [f"**{direction}** ({metadata.timestamp})"]

        text = message.get("text", "")
        if text:
            parts.append(f"\n{text}")

        if metadata.recipients:
            parts.append(f"\n**To:** {', '.join(metadata.recipients)}")

        return "\n".join(parts)
