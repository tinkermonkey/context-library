"""EmailAdapter for ingesting email from EmailEngine's REST API."""

import html2text
import httpx
import logging
from datetime import datetime
from typing import Iterator

from context_library.adapters.base import BaseAdapter
from context_library.storage.models import (
    Domain,
    MessageMetadata,
    NormalizedContent,
    StructuralHints,
)

logger = logging.getLogger(__name__)


class EmailAdapter(BaseAdapter):
    """Adapter that ingests email from EmailEngine's REST API.

    EmailEngine is a self-hosted headless email client that provides a REST API
    for accessing email. This adapter:
    - Fetches messages from EmailEngine API
    - Converts HTML bodies to markdown
    - Extracts email headers and thread context
    - Yields NormalizedContent with MessageMetadata
    """

    def __init__(
        self,
        emailengine_url: str,  # e.g., "http://localhost:3000"
        account_id: str,       # EmailEngine account identifier
        max_messages: int = 100,  # per-fetch limit for initial ingestion
    ) -> None:
        """Initialize EmailAdapter.

        Args:
            emailengine_url: Base URL of the EmailEngine API (will strip trailing slash)
            account_id: EmailEngine account identifier
            max_messages: Maximum number of messages to fetch per request (default: 100)
        """
        self._emailengine_url = emailengine_url.rstrip("/")
        self._account_id = account_id
        self._max_messages = max_messages

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

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize email messages from EmailEngine.

        The source_ref can optionally contain a last_fetched_at timestamp in ISO 8601
        format. If provided, only messages newer than that timestamp are fetched.

        Args:
            source_ref: Optional ISO 8601 timestamp for incremental ingestion

        Yields:
            NormalizedContent for each message

        Raises:
            httpx.HTTPError: If the API request fails
        """
        # Extract last_fetched_at from source_ref if provided
        since = source_ref if source_ref else None

        # Fetch messages from EmailEngine
        messages = self._fetch_messages(since)

        # Convert each message to NormalizedContent
        for msg in messages:
            try:
                # Fetch the full message body (HTML)
                message_body = self._fetch_message_body(msg["id"])

                # Convert HTML to markdown
                markdown_body = self._html_to_markdown(message_body)

                # Extract message metadata
                metadata = self._extract_message_metadata(msg)

                # Build structural hints with metadata
                hints = StructuralHints(
                    has_headings=False,
                    has_lists=False,
                    has_tables=False,
                    natural_boundaries=[],
                    extra_metadata=metadata.model_dump(),
                )

                # Yield normalized content
                yield NormalizedContent(
                    markdown=markdown_body,
                    source_id=f"email:{self._account_id}:{msg['id']}",
                    structural_hints=hints,
                    normalizer_version=self.normalizer_version,
                )

            except Exception as e:
                logger.warning(f"Failed to process message {msg.get('id')}: {e}")
                continue

    def _fetch_messages(self, since: str | None) -> list[dict]:
        """Fetch message list from EmailEngine API.

        Args:
            since: Optional ISO 8601 timestamp to fetch only newer messages

        Returns:
            List of message metadata dictionaries

        Raises:
            httpx.HTTPError: If the API request fails
        """
        params = {"pageSize": self._max_messages}
        if since:
            params["search[since]"] = since

        response = httpx.get(
            f"{self._emailengine_url}/v1/account/{self._account_id}/messages",
            params=params,
            timeout=30.0
        )
        response.raise_for_status()

        # EmailEngine returns messages in nested structure: {"messages": {"messages": [...]}}
        data = response.json()
        return data.get("messages", {}).get("messages", [])

    def _fetch_message_body(self, message_id: str) -> str:
        """Fetch the full message body (HTML) from EmailEngine API.

        Args:
            message_id: The message ID to fetch

        Returns:
            The HTML body content

        Raises:
            httpx.HTTPError: If the API request fails
        """
        response = httpx.get(
            f"{self._emailengine_url}/v1/account/{self._account_id}/message/{message_id}",
            params={"textType": "html"},
            timeout=30.0
        )
        response.raise_for_status()

        data = response.json()
        # EmailEngine returns text content under 'text' key
        return data.get("text", "") or ""

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
        """
        # Extract sender address
        from_header = msg.get("from", {})
        sender = from_header.get("address", "") if isinstance(from_header, dict) else str(from_header)

        # Extract recipient addresses
        to_header = msg.get("to", [])
        if isinstance(to_header, list):
            recipients = [r.get("address", "") if isinstance(r, dict) else str(r) for r in to_header]
        else:
            recipients = []

        # Extract thread context
        thread_id = msg.get("threadId", "")
        message_id = msg.get("messageId", "")
        in_reply_to = msg.get("inReplyTo")
        subject = msg.get("subject")

        # Timestamp should be ISO 8601 format from EmailEngine
        timestamp = msg.get("date", "")
        if timestamp and not timestamp.endswith("Z") and "T" not in timestamp:
            # If timestamp is not ISO 8601, attempt to parse and reformat
            try:
                parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                timestamp = parsed.isoformat()
            except (ValueError, AttributeError):
                # If parsing fails, use as-is and let validation handle it
                pass

        # Determine if this is a thread root (no in_reply_to)
        is_thread_root = in_reply_to is None

        return MessageMetadata(
            thread_id=thread_id,
            message_id=message_id,
            sender=sender,
            recipients=recipients,
            timestamp=timestamp,
            in_reply_to=in_reply_to,
            subject=subject,
            is_thread_root=is_thread_root,
        )
