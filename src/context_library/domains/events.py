"""EventsDomain: time-windowed summaries for structured event records."""

import re

from pydantic import ValidationError

from context_library.domains.base import BaseDomain
from context_library.storage.models import (
    Chunk,
    ChunkType,
    EventMetadata,
    NormalizedContent,
    compute_chunk_hash,
)


class EventsDomain(BaseDomain):
    """Domain-specific chunker for event content.

    Splits event content into semantically coherent chunks with event-specific
    handling: time-aware context headers, temporal metadata, and token-based
    splitting for long event descriptions.
    """

    def __init__(self, hard_limit: int = 1024) -> None:
        """Initialize the EventsDomain chunker.

        Args:
            hard_limit: Maximum token limit before forced splitting (default 1024)

        Raises:
            ValueError: If hard_limit is not a positive integer
        """
        if hard_limit <= 0:
            raise ValueError(
                f"hard_limit must be a positive integer, got {hard_limit}"
            )
        self.hard_limit = hard_limit

    def chunk(self, content: NormalizedContent) -> list[Chunk]:
        """Split event content into semantically coherent chunks.

        Algorithm:
        1. Extract EventMetadata from content.structural_hints.extra_metadata
        2. Build context_header as "{title} — {start_date}" with fallback to title only
        3. Split oversized event descriptions at sentence boundaries if exceeding hard_limit
        4. Compute chunk_hash from content only (excluding context_header)
        5. Assign sequential chunk_index values
        6. Set chunk_type to ChunkType.STANDARD
        7. Store domain_metadata from EventMetadata.model_dump()

        Args:
            content: The normalized event content to chunk

        Returns:
            A list of Chunk instances with sequential chunk_index values
        """
        # Extract EventMetadata from extra_metadata
        if not content.structural_hints.extra_metadata:
            raise ValueError(
                f"EventsDomain requires extra_metadata in structural_hints "
                f"for source {content.source_id}"
            )

        meta_dict = content.structural_hints.extra_metadata
        try:
            # Type contract: extra_metadata must be deserializable to EventMetadata.
            # This is enforced at validation time rather than in the type system
            # because StructuralHints.extra_metadata is domain-agnostic (dict[str, object]).
            # See StructuralHints docstring for design rationale.
            meta = EventMetadata(**meta_dict)  # type: ignore[arg-type]
        except ValidationError as e:
            raise ValueError(
                f"Invalid EventMetadata for source {content.source_id}: "
                f"{e.error_count()} validation error(s) — {[err['msg'] for err in e.errors()]}"
            ) from e

        # Build context_header
        if meta.start_date:
            context_header = f"{meta.title} — {meta.start_date}"
        else:
            context_header = meta.title

        # Get the markdown text
        text = content.markdown

        # Guard against empty content
        if not text.strip():
            return []

        # Split if over hard_limit
        segments = self._split_if_needed(text)

        # Build Chunk objects with sequential indices
        chunks = []
        for idx, segment in enumerate(segments):
            chunk_hash = compute_chunk_hash(segment)
            chunk = Chunk(
                chunk_hash=chunk_hash,
                content=segment,
                context_header=context_header,
                chunk_index=idx,
                chunk_type=ChunkType.STANDARD,
                domain_metadata=meta.model_dump(),
            )
            chunks.append(chunk)

        return chunks

