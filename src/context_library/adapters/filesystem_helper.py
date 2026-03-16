"""FilesystemHelperAdapter — ingests markdown files from a context-helpers service.

Calls POST /filesystem/fetch on the context-helpers bridge and streams each document
as an NDJSON line, mapping results to NormalizedContent for the Documents domain.

Expected endpoint contract:
  POST /filesystem/fetch
    Authorization: Bearer <api_key>
    Content-Type: application/json

    Request body:
    {
      "source_ref": "<ISO 8601 cursor | empty string>",
      "page_size": <int | null>,
      "extensions": ["<ext>", ...] | null,
      "max_size_mb": <float | null>,
      "stream": true
    }

    Response (NDJSON, Content-Type: application/x-ndjson):
      One JSON object per line.
      Content lines: NormalizedContent-shaped objects
      Final line:    {"has_more": <bool>, "next_cursor": "<ISO 8601 | null>"}
"""

import json as _json
import logging
from typing import Iterator

from pydantic import ValidationError

from context_library.adapters.remote import RemoteAdapter
from context_library.storage.models import Domain, NormalizedContent, PollStrategy

logger = logging.getLogger(__name__)


class FilesystemHelperAdapter(RemoteAdapter):
    """Adapter that ingests markdown files served by a context-helpers bridge service.

    Uses NDJSON streaming so peak memory on both sides is bounded to one file
    at a time rather than a full page.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        directory_id: str = "default",
        extensions: list[str] | None = None,
        max_size_mb: float | None = None,
        page_size: int = 50,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required for FilesystemHelperAdapter")

        # Pass service_url with /filesystem suffix so RemoteAdapter posts to /filesystem/fetch
        super().__init__(
            service_url=f"{api_url.rstrip('/')}/filesystem",
            domain=Domain.DOCUMENTS,
            adapter_id=f"filesystem_helper:{directory_id}",
            api_key=api_key,
        )
        self._directory_id = directory_id
        self._fetch_params: dict = {"stream": True}
        if extensions is not None:
            self._fetch_params["extensions"] = extensions
        if max_size_mb is not None:
            self._fetch_params["max_size_mb"] = max_size_mb
        if page_size != 50:
            self._fetch_params["page_size"] = page_size

    @property
    def poll_strategy(self) -> PollStrategy:
        return PollStrategy.PULL

    def fetch(self, source_ref: str, extra_body: dict | None = None) -> Iterator[NormalizedContent]:
        """Fetch and normalize content via NDJSON streaming.

        Streams the response line-by-line so neither side needs to buffer
        the full page. The server emits one NormalizedContent JSON object per
        line, then a closing ``{"has_more": ..., "next_cursor": ...}`` line.

        Args:
            source_ref: ISO 8601 cursor string (empty = start from beginning)
            extra_body: Optional additional fields merged into the JSON request body

        Yields:
            NormalizedContent for each file in the page

        Raises:
            httpx.HTTPStatusError: on non-2xx responses
            ValueError: if a line cannot be parsed as JSON
            pydantic.ValidationError: if a content line fails NormalizedContent validation

        Note on retry:
            Unlike RemoteAdapter.fetch(), this method does not retry on transient
            errors (502/503/504, connection failures).  Retry is handled at a higher
            level by the push-trigger or pipeline caller.  Adding per-call retry
            inside a streaming context is complex and unnecessary given the outer
            retry envelope.
        """
        headers: dict = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        body = {"source_ref": source_ref, **self._fetch_params}
        if extra_body:
            body.update(extra_body)

        with self._client.stream(
            "POST",
            f"{self._service_url}/fetch",
            json=body,
            headers=headers,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.strip():
                    continue
                try:
                    obj = _json.loads(line)
                except ValueError as e:
                    logger.error("FilesystemHelperAdapter: failed to parse NDJSON line: %s", e)
                    raise
                if "has_more" in obj:
                    # Meta line — log pagination state and stop
                    if obj.get("has_more"):
                        logger.debug(
                            "FilesystemHelperAdapter: has_more=True, next_cursor=%s",
                            obj.get("next_cursor"),
                        )
                    return
                try:
                    yield NormalizedContent.model_validate(obj)
                except ValidationError as e:
                    logger.error(
                        "FilesystemHelperAdapter: failed to validate NormalizedContent: %s", e
                    )
                    raise
