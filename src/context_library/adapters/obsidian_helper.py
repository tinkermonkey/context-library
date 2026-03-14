"""ObsidianHelperAdapter — ingests Obsidian vault notes from a context-helpers service.

Calls GET /vault-notes on the context-helpers bridge and maps each note to
NormalizedContent for the Notes domain with full Obsidian metadata.

Expected endpoint contract:
  GET /vault-notes
    Query params:
      - since (optional): ISO 8601 timestamp; return only notes modified after this time

    Response: JSON array of note objects:
    [
      {
        "source_id": "relative/path/to/note.md",
        "markdown": "<note content>",
        "modified_at": "<ISO 8601>",
        "created_at": "<ISO 8601>",
        "file_size_bytes": <int>,
        "has_headings": <bool>,
        "has_lists": <bool>,
        "has_tables": <bool>,
        "tags": ["tag1", "tag2"],
        "aliases": ["alias1"],
        "frontmatter": {"key": "value"},
        "dataview_fields": {"status": "done"},
        "wikilinks": ["Other Note"],
        "backlinks": ["Another Note"]
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


class ObsidianHelperAdapter(BaseAdapter):
    """Adapter that ingests an Obsidian vault served by a context-helpers bridge service."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        vault_id: str = "default",
    ) -> None:
        if not HAS_HTTPX:
            raise ImportError(
                "httpx is required for ObsidianHelperAdapter. "
                "Install with: pip install context-library[obsidian-helper]"
            )
        if not api_key:
            raise ValueError("api_key is required for ObsidianHelperAdapter")

        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._vault_id = vault_id
        self._client = httpx.Client(timeout=60.0)

    @property
    def adapter_id(self) -> str:
        return f"obsidian_helper:{self._vault_id}"

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

        response = self._client.get(
            f"{self._api_url}/vault-notes",
            headers=headers,
            params=params,
        )
        response.raise_for_status()
        notes = response.json()

        for note in notes:
            try:
                source_id = note["source_id"]
                markdown = note["markdown"]
                modified_at = note.get("modified_at")

                extra_metadata: dict = {
                    "tags": note.get("tags", []),
                    "aliases": note.get("aliases", []),
                    "frontmatter": note.get("frontmatter", {}),
                    "dataview_fields": note.get("dataview_fields", {}),
                    "wikilinks": note.get("wikilinks", []),
                    "backlinks": note.get("backlinks", []),
                    "created_at": note.get("created_at"),
                    "modified_at": modified_at,
                }

                structural_hints = StructuralHints(
                    has_headings=note.get("has_headings", False),
                    has_lists=note.get("has_lists", False),
                    has_tables=note.get("has_tables", False),
                    natural_boundaries=(),
                    modified_at=modified_at,
                    file_size_bytes=note.get("file_size_bytes"),
                    extra_metadata=extra_metadata,
                )

                yield NormalizedContent(
                    markdown=markdown,
                    source_id=source_id,
                    structural_hints=structural_hints,
                    normalizer_version=self.normalizer_version,
                )
            except (KeyError, ValueError) as e:
                logger.warning("Skipping malformed note from helper: %s", e)
                continue
