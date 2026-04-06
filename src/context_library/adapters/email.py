"""EmailAdapter for ingesting email from EmailEngine's REST API."""

import logging
from datetime import datetime
from typing import Iterator, Literal

from context_library.adapters.base import BaseAdapter
from context_library.storage.models import (
    Domain,
    MessageMetadata,
    NormalizedContent,
    StructuralHints,
)

logger = logging.getLogger(__name__)

# Try to import optional dependencies
HAS_HTTPX = False
HAS_HTML2TEXT = False

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    pass

try:
    import html2text

    HAS_HTML2TEXT = True
except ImportError:
    pass


class EmailAdapter(BaseAdapter):
    """Adapter that ingests email from EmailEngine's REST API.

    EmailEngine is a self-hosted headless email client that provides a unified REST API
    abstracting provider-specific protocols and authentication. It supports:
    - IMAP (RFC 3501) for direct IMAP/SMTP servers
    - Gmail API (via OAuth 2.0)
    - Microsoft Graph API (Outlook, Exchange, etc. via OAuth 2.0)
    - And other SMTP/IMAP-compatible providers

    This adapter:
    - Fetches messages from EmailEngine's unified REST API
    - Converts HTML bodies to markdown
    - Extracts email headers and thread context
    - Yields NormalizedContent with MessageMetadata
    - Supports both initial ingestion and incremental updates

    Usage: Configure EmailEngine to connect to your desired email provider, then
    point this adapter to the EmailEngine API URL. See https://github.com/postalsys/emailengine.
    """

    def __init__(
        self,
        emailengine_url: str,  # e.g., "http://localhost:3000"
        account_id: str,       # EmailEngine account identifier
        max_initial_messages: int = 100,  # per-fetch limit for initial full ingestion
        max_incremental_messages: int = 50,  # per-fetch limit for incremental updates
    ) -> None:
        """Initialize EmailAdapter.

        Args:
            emailengine_url: Base URL of the EmailEngine API (will strip trailing slash)
            account_id: EmailEngine account identifier
            max_initial_messages: Maximum messages to fetch on initial full ingest (default: 100).
                Used when source_ref is empty string (initial ingestion).
            max_incremental_messages: Maximum messages to fetch on incremental updates (default: 50).
                Used when source_ref has a timestamp (subsequent fetches).

        Raises:
            ImportError: If httpx or html2text are not installed.
            ValueError: If message limits are not positive integers.
        """
        if not HAS_HTTPX:
            raise ImportError(
                "httpx is required for EmailAdapter. "
                "Install with: pip install context-library[email]"
            )
        if not HAS_HTML2TEXT:
            raise ImportError(
                "html2text is required for EmailAdapter. "
                "Install with: pip install context-library[email]"
            )

        if max_initial_messages <= 0:
            raise ValueError(
                f"max_initial_messages must be a positive integer, got {max_initial_messages}"
            )
        if max_incremental_messages <= 0:
            raise ValueError(
                f"max_incremental_messages must be a positive integer, got {max_incremental_messages}"
            )

        self._emailengine_url = emailengine_url.rstrip("/")
        self._account_id = account_id
        self._max_initial_messages = max_initial_messages
        self._max_incremental_messages = max_incremental_messages
        self._client = httpx.Client(timeout=30.0)

    @property
    def adapter_id(self) -> str:
        """Return a deterministic adapter ID based on account_id.

        Returns:
            f"email:{account_id}"
        """
        return f"email:{self._account_id}"

    @property
    def domain(self) -> Domain:
        """Return the domain this adapter serves."""
        return Domain.MESSAGES

    @property
    def normalizer_version(self) -> str:
        """Return the normalizer version."""
        return "1.0.0"

    def __enter__(self):
        """Context manager entry: return self for use in with statement."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> Literal[False]:
        """Context manager exit: clean up httpx.Client session."""
        self._client.close()
        return False

    def __del__(self) -> None:
        """Clean up httpx.Client session when adapter is destroyed (safety net)."""
        if hasattr(self, "_client"):
            self._client.close()

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize email messages from EmailEngine.

        The source_ref can optionally contain a last_fetched_at timestamp in ISO 8601
        format. If provided, only messages newer than that timestamp are fetched.
        Errors in message processing (schema mismatches, missing fields) are NOT caught —
        they propagate to caller for visibility. This prevents silent skipping when
        EmailEngine API format changes.

        Args:
            source_ref: ISO 8601 timestamp for incremental ingestion, or empty string for initial

        Yields:
            NormalizedContent for each message

        Raises:
            httpx.HTTPError: If the API request fails
            ValueError: If EmailEngine returns unexpected response schema, or if a message
                has missing/malformed fields (including missing 'text' field)
            KeyError: If a message is missing required identity/header fields
            TypeError: If a message field has unexpected type
        """
        # Determine whether this is initial or incremental ingestion
        since = source_ref if source_ref else None
        is_initial = not since
        limit = self._max_initial_messages if is_initial else self._max_incremental_messages

        # Fetch messages from EmailEngine (errors propagate)
        messages = self._fetch_messages(since, limit)

        # Convert each message to NormalizedContent
        # Process without catching errors to ensure visibility of API schema changes
        for msg in messages:
            # Fetch the full message body (HTML) - errors propagate
            message_body = self._fetch_message_body(msg["id"])

            # Convert HTML to markdown - should not raise
            markdown_body = self._html_to_markdown(message_body)

            # Extract message metadata - errors propagate
            metadata = self._extract_message_metadata(msg)

            # Build structural hints with metadata
            hints = StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata=metadata.model_dump(),
            )

            # Yield normalized content
            yield NormalizedContent(
                markdown=markdown_body,
                source_id=f"email:{self._account_id}:{msg['id']}",
                structural_hints=hints,
                normalizer_version=self.normalizer_version,
            )

    def _fetch_messages(self, since: str | None, limit: int) -> list[dict]:
        """Fetch message list from EmailEngine API.

        Args:
            since: Optional ISO 8601 timestamp to fetch only newer messages
            limit: Page size limit for this fetch (required)

        Returns:
            List of message metadata dictionaries

        Raises:
            httpx.HTTPError: If the API request fails
            ValueError: If EmailEngine returns unexpected response schema
        """
        params: dict[str, int | str] = {"pageSize": limit}
        if since:
            params["search[since]"] = since

        response = self._client.get(
            f"{self._emailengine_url}/v1/account/{self._account_id}/messages",
            params=params,
        )
        response.raise_for_status()

        data = response.json()

        # EmailEngine API should return {"messages": [...]} as top-level structure
        if "messages" not in data:
            raise ValueError(
                f"EmailEngine API response missing 'messages' key. Got keys: {list(data.keys())}"
            )

        messages = data["messages"]

        # Validate that messages is a list
        if not isinstance(messages, list):
            raise ValueError(
                f"EmailEngine API 'messages' field must be a list, got {type(messages).__name__}"
            )

        return messages

    def _fetch_message_body(self, message_id: str) -> str:
        """Fetch the full message body (HTML) from EmailEngine API.

        Args:
            message_id: The message ID to fetch

        Returns:
            The HTML body content

        Raises:
            httpx.HTTPError: If the API request fails
            ValueError: If the response is missing the 'text' field or has unexpected schema
        """
        response = self._client.get(
            f"{self._emailengine_url}/v1/account/{self._account_id}/message/{message_id}",
            params={"textType": "html"},
        )
        response.raise_for_status()

        data = response.json()

        # EmailEngine must return 'text' field with HTML body
        if "text" not in data:
            raise ValueError(
                f"EmailEngine API response for message {message_id} missing 'text' field. "
                f"Got keys: {list(data.keys())}"
            )

        body = data["text"]

        # Validate that text is a string
        if not isinstance(body, str):
            raise ValueError(
                f"EmailEngine API 'text' field must be a string, got {type(body).__name__}"
            )

        return body

    def _html_to_markdown(self, html: str) -> str:
        """Convert HTML to markdown.

        Args:
            html: HTML content to convert

        Returns:
            Markdown representation of the HTML
        """
        h = html2text.HTML2Text()
        h.ignore_links = False
        return h.handle(html)

    def _extract_message_metadata(self, msg: dict) -> MessageMetadata:
        """Extract MessageMetadata from EmailEngine message response.

        Args:
            msg: Message dictionary from EmailEngine API

        Returns:
            MessageMetadata object with extracted fields

        Raises:
            KeyError: If required fields are missing
            TypeError: If fields have unexpected types
            ValueError: If identity fields cannot be populated
        """
        # Extract sender address (required field)
        if "from" not in msg:
            raise KeyError("Message missing required 'from' field")

        from_header = msg["from"]
        if isinstance(from_header, dict):
            if "address" not in from_header:
                raise KeyError("'from' field missing required 'address' subfield")
            sender = from_header["address"]
        elif isinstance(from_header, str):
            sender = from_header
        else:
            raise TypeError(f"'from' field must be dict or str, got {type(from_header).__name__}")

        # Extract recipient addresses (required field)
        if "to" not in msg:
            raise KeyError("Message missing required 'to' field")

        to_header = msg["to"]
        if not isinstance(to_header, list):
            raise TypeError(f"'to' field must be a list, got {type(to_header).__name__}")

        recipients = []
        for i, recipient in enumerate(to_header):
            if isinstance(recipient, dict):
                if "address" not in recipient:
                    raise KeyError(f"'to[{i}]' missing required 'address' subfield")
                recipients.append(recipient["address"])
            elif isinstance(recipient, str):
                recipients.append(recipient)
            else:
                raise TypeError(f"'to[{i}]' must be dict or str, got {type(recipient).__name__}")

        # Extract thread context (identity fields)
        # Use threadId/messageId from EmailEngine, fallback to message 'id' if empty
        thread_id = msg.get("threadId") or ""
        message_id = msg.get("messageId") or ""

        if "id" not in msg:
            raise KeyError("Message missing required 'id' field for fallback identity")

        # If threadId or messageId are empty, use the message id as fallback
        if not thread_id:
            thread_id = msg["id"]
        if not message_id:
            message_id = msg["id"]

        # Extract optional fields
        in_reply_to = msg.get("inReplyTo")
        subject = msg.get("subject")

        # Timestamp should be ISO 8601 format from EmailEngine
        timestamp = msg.get("date", "")

        # Validate timestamp is present and attempt normalization if needed
        if not timestamp:
            raise ValueError("Message missing 'date' field")

        # If timestamp ends with 'Z', it's already in ISO 8601 UTC format
        if timestamp.endswith("Z"):
            # Python's fromisoformat doesn't handle 'Z', convert to '+00:00'
            normalized_timestamp = timestamp[:-1] + "+00:00"
        elif "T" in timestamp:
            # Already ISO 8601 format
            normalized_timestamp = timestamp
        else:
            # Non-ISO 8601 format, attempt to parse and reformat
            try:
                parsed = datetime.fromisoformat(timestamp)
                normalized_timestamp = parsed.isoformat()
            except ValueError as e:
                raise ValueError(f"Unable to parse timestamp '{timestamp}': {e}")

        # Determine if this is a thread root (no in_reply_to)
        is_thread_root = in_reply_to is None

        return MessageMetadata(
            thread_id=thread_id,
            message_id=message_id,
            sender=sender,
            recipients=tuple(recipients),
            timestamp=normalized_timestamp,
            in_reply_to=in_reply_to,
            subject=subject,
            is_thread_root=is_thread_root,
            is_from_me=False,
        )
