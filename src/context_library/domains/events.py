"""EventsDomain: time-windowed summaries for structured event records."""

from pydantic import ValidationError

from context_library.domains.base import BaseDomain
from context_library.storage.cross_refs import detect_cross_references
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
        super().__init__(hard_limit)

    def chunk(self, content: NormalizedContent) -> list[Chunk]:
        """Split event content into semantically coherent chunks.

        Algorithm:
        1. Extract EventMetadata from content.structural_hints.extra_metadata
        2. Build context_header as "{title} — {start_date}" with fallback to title only
        3. Split oversized event descriptions at sentence boundaries if exceeding hard_limit
        4. Compute chunk_hash from content only (excluding context_header)
        5. Assign sequential chunk_index values
        6. Set chunk_type to ChunkType.STANDARD
        7. Store domain_metadata preserving both validated fields and extra fields

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

        # Get the markdown text as the body
        text = content.markdown.strip()

        # Per spec: return empty list if no description content
        # (title is available in context_header, not needed in content)
        if not text:
            return []

        # Split if over hard_limit
        segments = self._split_if_needed(text)

        # Build Chunk objects with sequential indices
        chunks = []
        for idx, segment in enumerate(segments):
            chunk_hash = compute_chunk_hash(segment)
            # EventMetadata has extra="ignore" which strips unknown fields during validation.
            # However, extra fields (health metrics like calories_kcal) must be preserved in domain_metadata.
            # Merge validated model fields with original dict to preserve all metadata.
            domain_metadata = {**meta.model_dump(), **meta_dict}
            chunk = Chunk(
                chunk_hash=chunk_hash,
                content=segment,
                context_header=context_header,
                chunk_index=idx,
                chunk_type=ChunkType.STANDARD,
                domain_metadata=domain_metadata,
            )
            chunks.append(chunk)

        # Detect cross-references between chunks
        final_chunks = []
        for chunk in chunks:
            cross_refs = detect_cross_references(chunk, chunks)
            if cross_refs:
                # Reconstruct chunk with cross_refs
                chunk_with_refs = Chunk(
                    chunk_hash=chunk.chunk_hash,
                    content=chunk.content,
                    context_header=chunk.context_header,
                    chunk_index=chunk.chunk_index,
                    chunk_type=chunk.chunk_type,
                    domain_metadata=chunk.domain_metadata,
                    cross_refs=cross_refs,
                )
                final_chunks.append(chunk_with_refs)
            else:
                final_chunks.append(chunk)

        return final_chunks

