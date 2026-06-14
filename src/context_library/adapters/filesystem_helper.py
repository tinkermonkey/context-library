"""FilesystemHelperAdapter — ingests files from a context-helpers service.

Calls POST /filesystem/fetch on the context-helpers bridge and streams each document
as an NDJSON line, mapping results to NormalizedContent for the Documents domain.

The helper now indexes the watched tree in a local SQLite index and serves changes
keyed by an opaque change-sequence cursor. The wire shape is largely unchanged, but
the semantics differ in two important ways:

  * ``source_ref`` / ``next_cursor`` are now OPAQUE tokens (an integer-as-string
    change sequence on the helper side). This adapter never parses, compares, or
    interprets them — it simply echoes back the last ``next_cursor`` it received.
    An empty string means "from the beginning".
  * The stream may contain TOMBSTONE lines (``{"op": "delete", ...}``) signalling
    that a previously-served file was deleted and must be retired.

Expected endpoint contract:
  POST /filesystem/fetch[?ack=true]
    Authorization: Bearer <api_key>
    Content-Type: application/json

    Request body:
    {
      "source_ref": "<opaque cursor | empty string>",
      "page_size": <int | null>,
      "extensions": ["<ext>", ...] | null,
      "max_size_mb": <float | null>,
      "stream": true
    }

    Response (NDJSON, Content-Type: application/x-ndjson):
      One JSON object per line.
      Content lines:   NormalizedContent-shaped objects
      Tombstone lines: {"op": "delete", "source_id": "<str>", "modified_at": "<iso8601|null>"}
      Final line:      {"has_more": <bool>, "next_cursor": "<opaque str>"}

Commit-ack:
  When the helper serves a page under ``?ack=true`` it stages — but does not commit —
  the cursor advance. The library must call POST /collectors/filesystem/ack after the
  pipeline has durably committed the page, otherwise an uncommitted page is re-served
  on the next pull rather than lost. See ``ack()``.
"""

import json as _json
import logging
import mimetypes
from pathlib import PurePosixPath
from typing import Iterator

from pydantic import ValidationError

from context_library.adapters.remote import RemoteAdapter
from context_library.storage.models import (
    Domain,
    NormalizedContent,
    PollStrategy,
    StructuralHints,
)

logger = logging.getLogger(__name__)

#: Default safety cap on the number of pages drained within a single fetch() call.
#: Backfilling a large tree must not block the caller forever, so the drain stops
#: after this many pages even if the helper still reports has_more=True. The next
#: fetch() resumes from the persisted cursor, so no data is lost — it is merely
#: spread across multiple fetch() calls.
DEFAULT_MAX_PAGES = 200


class FilesystemHelperAdapter(RemoteAdapter):
    """Adapter that ingests files served by a context-helpers bridge service.

    Uses NDJSON streaming so peak memory on both sides is bounded to one file
    at a time rather than a full page. A single ``fetch()`` call drains successive
    pages until the helper reports ``has_more=False`` or a safety budget is hit,
    so a large backfill completes in one poll cycle rather than one page per cycle.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        directory_id: str = "default",
        extensions: list[str] | None = None,
        max_size_mb: float | None = None,
        page_size: int = 50,
        timeout: float = 300.0,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required for FilesystemHelperAdapter")
        if max_pages < 1:
            raise ValueError("max_pages must be >= 1")

        # Pass service_url with /filesystem suffix so RemoteAdapter posts to /filesystem/fetch
        # Use a long timeout (default 300s) because the bridge may scan a large directory
        # before streaming the first NDJSON line.
        super().__init__(
            service_url=f"{api_url.rstrip('/')}/filesystem",
            domain=Domain.DOCUMENTS,
            adapter_id=f"filesystem_helper:{directory_id}",
            api_key=api_key,
            timeout=timeout,
        )
        # Base URL without the /filesystem suffix — used to build the ack endpoint
        # (POST {base}/collectors/filesystem/ack) the same way reset is built.
        self._base_url = api_url.rstrip("/")
        self._directory_id = directory_id
        self._max_pages = max_pages
        # Opaque cursor persisted across fetch() calls. Advances as pages are drained
        # so a crash mid-drain resumes from the last fully-streamed page.
        self._cursor: str = ""
        # Cursor served (and staged on the helper) by the most recent fetch(), pending
        # commit-ack. ack() commits it on the helper after the pipeline commits.
        self._pending_ack_cursor: str | None = None
        self._fetch_params: dict = {"stream": True}
        if extensions is not None:
            self._fetch_params["extensions"] = extensions
        if max_size_mb is not None:
            self._fetch_params["max_size_mb"] = max_size_mb
        if page_size != 50:
            self._fetch_params["page_size"] = page_size

    #: FilesystemHelperAdapter requires proactive background polling.
    #: The bridge only pushes filesystem changes on file events; the library
    #: must also pull on a schedule to catch up after restarts or quiet periods.
    background_poll: bool = True

    @property
    def _collector_name(self) -> str:
        """Return the collector name for the filesystem helper service."""
        return "filesystem"

    @property
    def poll_strategy(self) -> PollStrategy:
        return PollStrategy.PULL

    @staticmethod
    def _synthesize_extra_metadata(
        source_id: str,
        modified_at: str | None = None,
        file_size_bytes: int | None = None,
    ) -> dict:
        """Build minimal DocumentMetadata when the bridge doesn't provide extra_metadata.

        Uses source_id as the file path to extract title and infer document_type.
        """
        path = PurePosixPath(source_id)
        stem = path.stem
        suffix = path.suffix.lower()
        mime, _ = mimetypes.guess_type(f"file{suffix}")
        return {
            "document_id": source_id,
            "title": stem.replace("-", " ").replace("_", " "),
            "document_type": mime or "text/markdown",
            "source_type": "filesystem",
            "modified_at": modified_at,
            "file_size_bytes": file_size_bytes,
        }

    def _make_tombstone(self, source_id: str, modified_at: str | None) -> NormalizedContent:
        """Build a deletion sentinel for a removed file.

        We retire a deleted source by yielding a NormalizedContent with empty
        markdown. The DocumentsDomain chunker returns zero chunks for empty
        markdown, so the differ sees an all-removed diff and the pipeline retires
        every chunk + vector for that source via its existing Case-2 removal path.

        extra_metadata is synthesized so the chunker's metadata guard is satisfied
        (it raises if extra_metadata is missing, even for empty content).
        """
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=(),
            modified_at=modified_at,
            file_size_bytes=None,
            extra_metadata=self._synthesize_extra_metadata(source_id, modified_at),
        )
        return NormalizedContent(
            markdown="",
            source_id=source_id,
            structural_hints=hints,
            normalizer_version=self.normalizer_version,
        )

    def fetch(self, source_ref: str, extra_body: dict | None = None) -> Iterator[NormalizedContent]:
        """Fetch and normalize content via NDJSON streaming, draining all pages.

        Streams the response line-by-line so neither side buffers a full page, then
        — if the meta line reports ``has_more`` — immediately requests the next page
        using ``next_cursor`` and continues. The drain stops when ``has_more`` is
        False or after ``max_pages`` pages (logged so a capped run is never silent).

        The internal cursor is advanced to each page's ``next_cursor`` as soon as
        that page's meta line is seen, so a crash mid-drain resumes correctly.

        The opaque cursor is authoritative: the per-source ``source_ref`` passed by
        the poller (a file path, not a cursor) is ignored in favour of the persisted
        cursor unless an explicit, non-empty cursor override is supplied.

        Args:
            source_ref: Opaque cursor string (empty = start from the persisted cursor)
            extra_body: Optional additional fields merged into the JSON request body.
                Pass ``{"ack": True}`` shape is NOT used here; ack is a query param
                controlled by the caller via the pipeline/poller (see ack()).

        Yields:
            NormalizedContent for each file in every drained page. Deleted files are
            yielded as empty-markdown tombstones that the pipeline retires.

        Raises:
            httpx.HTTPStatusError: on non-2xx responses
            ValueError: if a line cannot be parsed as JSON
            pydantic.ValidationError: if a content line fails NormalizedContent validation
        """
        headers: dict = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        # An explicit, non-empty source_ref overrides the persisted cursor (e.g. a
        # forced replay). Otherwise the persisted cursor is authoritative — the
        # poller passes per-file origin_refs as source_ref, which are NOT cursors.
        cursor = source_ref if source_ref else self._cursor

        # Commit-ack is the default for this poller-driven adapter: the helper stages
        # the cursor advance, and the caller commits it via ack() after the pipeline
        # commits. A caller may disable it explicitly with extra_body={"ack": False}.
        ack = True
        if extra_body is not None and "ack" in extra_body:
            ack = bool(extra_body["ack"])
        # Reset any stale pending-ack from a prior run before draining a fresh one.
        self._pending_ack_cursor = None

        pages_drained = 0
        while True:
            body = {"source_ref": cursor, **self._fetch_params}
            if extra_body:
                # Don't leak the local "ack" control flag into the JSON body; it is a
                # query param. Other extra_body fields pass through unchanged.
                body.update({k: v for k, v in extra_body.items() if k != "ack"})

            url = f"{self._service_url}/fetch"
            params = {"ack": "true"} if ack else None

            saw_meta = False
            with self._client.stream(
                "POST",
                url,
                params=params,
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
                        logger.error(
                            "FilesystemHelperAdapter: failed to parse NDJSON line: %s", e
                        )
                        raise

                    # Meta line — always last. Advance cursor, decide on continuation.
                    if "has_more" in obj:
                        saw_meta = True
                        next_cursor = obj.get("next_cursor")
                        # Echo the opaque token back verbatim on the next request.
                        if next_cursor is not None:
                            cursor = next_cursor
                            self._cursor = next_cursor
                        has_more = bool(obj.get("has_more"))
                        pages_drained += 1
                        # Stage the cursor served by this run for commit-ack.
                        if ack:
                            self._pending_ack_cursor = self._cursor
                        break

                    # Tombstone line — retire the deleted source.
                    if obj.get("op") == "delete":
                        source_id = obj.get("source_id")
                        if not source_id:
                            logger.warning(
                                "FilesystemHelperAdapter: delete line missing source_id: %r",
                                obj,
                            )
                            continue
                        yield self._make_tombstone(source_id, obj.get("modified_at"))
                        continue

                    # Content line — validate and yield.
                    try:
                        nc = NormalizedContent.model_validate(obj)
                    except ValidationError as e:
                        logger.error(
                            "FilesystemHelperAdapter: failed to validate NormalizedContent: %s",
                            e,
                        )
                        raise
                    # Bridge does not populate extra_metadata; synthesize it so
                    # DocumentsDomain has the required DocumentMetadata fields.
                    if nc.structural_hints.extra_metadata is None:
                        patched_hints = nc.structural_hints.model_copy(
                            update={
                                "extra_metadata": self._synthesize_extra_metadata(
                                    nc.source_id,
                                    nc.structural_hints.modified_at,
                                    nc.structural_hints.file_size_bytes,
                                )
                            }
                        )
                        nc = nc.model_copy(update={"structural_hints": patched_hints})
                    yield nc

            if not saw_meta:
                # Stream ended without a meta line — treat as the end of the drain
                # to avoid an infinite loop, but surface it: the helper violated the
                # contract (META line is always last).
                logger.warning(
                    "FilesystemHelperAdapter: stream ended without a meta line; "
                    "stopping drain (cursor=%s)",
                    cursor,
                )
                return

            if not has_more:
                return

            if pages_drained >= self._max_pages:
                logger.warning(
                    "FilesystemHelperAdapter: drain budget reached (%d pages); "
                    "more changes remain and will be fetched on the next poll "
                    "(cursor=%s)",
                    self._max_pages,
                    cursor,
                )
                return

    def ack(self) -> None:
        """Commit the most recently served page on the helper (commit-ack).

        Filesystem is a background_poll (poller-driven) adapter. When fetch() runs
        under ack mode, the helper stages the cursor advance but does not commit it;
        this method POSTs to the helper's ack endpoint to commit it *after* the
        pipeline has durably committed the page. If the process crashes between
        fetch() and ack(), the helper re-serves the page rather than losing it.

        No-op if there is no pending cursor to acknowledge (e.g. ack mode was off,
        or fetch() yielded no page).

        Raises:
            httpx.HTTPStatusError: If the ack request fails with 4xx/5xx status.
            httpx.RequestError: If the request fails (connection, timeout, etc.).
        """
        if self._pending_ack_cursor is None:
            return

        headers: dict = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        cursor = self._pending_ack_cursor
        response = self._client.post(
            f"{self._base_url}/collectors/{self._collector_name}/ack",
            json={"cursor": cursor},
            headers=headers,
            timeout=10.0,
        )
        response.raise_for_status()
        logger.debug("FilesystemHelperAdapter: committed cursor=%s via ack", cursor)
        self._pending_ack_cursor = None
