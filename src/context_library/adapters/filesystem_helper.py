"""FilesystemHelperAdapter — ingests markdown files from a context-helpers service.

Calls GET /documents on the context-helpers bridge and maps each document to
NormalizedContent for the Notes domain.

Expected endpoint contract:
  GET /documents
    Query params:
      - since (optional): ISO 8601 timestamp; return only files modified after this time
      - extensions (optional): comma-separated extensions to include, e.g. ".md,.txt"

    Response: JSON array of document objects:
    [
      {
        "source_id": "relative/path/to/file.md",
        "markdown": "<file content>",
        "modified_at": "<ISO 8601>",
        "file_path": "<absolute path>",
        "file_size_bytes": <int>,
        "has_headings": <bool>,
        "has_lists": <bool>,
        "has_tables": <bool>
      }
    ]
"""

import logging
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


class FilesystemHelperAdapter(BaseAdapter):
    """Adapter that ingests markdown files served by a context-helpers bridge service."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        directory_id: str = "default",
        extensions: list[str] | None = None,
    ) -> None:
        if not HAS_HTTPX:
            raise ImportError(
                "httpx is required for FilesystemHelperAdapter. "
                "Install with: pip install context-library[filesystem-helper]"
            )
        if not api_key:
            raise ValueError("api_key is required for FilesystemHelperAdapter")

        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._directory_id = directory_id
        self._extensions = extensions
        self._client = httpx.Client(timeout=60.0)

    @property
    def adapter_id(self) -> str:
        return f"filesystem_helper:{self._directory_id}"

    @property
    def domain(self) -> Domain:
        return Domain.NOTES

    @property
    def poll_strategy(self) -> PollStrategy:
        return PollStrategy.PULL

    @property
    def normalizer_version(self) -> str:
        return "1.0.0"

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        since = source_ref if source_ref else None
        headers = {"Authorization": f"Bearer {self._api_key}"}
        params: dict = {}
        if since:
            params["since"] = since
        if self._extensions:
            params["extensions"] = ",".join(self._extensions)

        response = self._client.get(
            f"{self._api_url}/documents",
            headers=headers,
            params=params,
        )
        response.raise_for_status()
        documents = response.json()

        for doc in documents:
            try:
                source_id = doc["source_id"]
                markdown = doc["markdown"]
                modified_at = doc.get("modified_at")

                structural_hints = StructuralHints(
                    has_headings=doc.get("has_headings", False),
                    has_lists=doc.get("has_lists", False),
                    has_tables=doc.get("has_tables", False),
                    natural_boundaries=(),
                    file_path=doc.get("file_path"),
                    modified_at=modified_at,
                    file_size_bytes=doc.get("file_size_bytes"),
                )

                yield NormalizedContent(
                    markdown=markdown,
                    source_id=source_id,
                    structural_hints=structural_hints,
                    normalizer_version=self.normalizer_version,
                )
            except (KeyError, ValueError) as e:
                logger.warning("Skipping malformed document from helper: %s", e)
                continue
