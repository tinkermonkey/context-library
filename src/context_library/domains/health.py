"""Health domain chunker for health-related content."""

from pydantic import ValidationError

from context_library.domains.base import BaseDomain
from context_library.storage.models import (
    Chunk,
    ChunkType,
    HealthMetadata,
    NormalizedContent,
    compute_chunk_hash,
)


class HealthDomain(BaseDomain):
    """Domain-specific chunker for health content.

    Extracts HealthMetadata from extra_metadata, builds date-stamped context
    headers, groups time-series records into windowed chunks, and delegates
    oversized content to _split_if_needed().
    """

    def __init__(self, hard_limit: int = 1024, hr_window_minutes: int = 60) -> None:
        """Initialize HealthDomain with token limit and heart-rate window.

        Args:
            hard_limit: Maximum tokens before forced splitting (default: 1024)
            hr_window_minutes: Window size for heart_rate_series grouping (default: 60)
        """
        super().__init__(hard_limit)
        self._hr_window_minutes = hr_window_minutes

    def chunk(self, content: NormalizedContent) -> list[Chunk]:
        """Chunk health content into semantically coherent pieces.

        Algorithm:
        1. Extract and validate HealthMetadata from extra_metadata
        2. Build context_header in "{health_type} — {date}" format
        3. Guard against empty markdown body
        4. Split content if needed using hard_limit
        5. Create chunks with sequential indices and domain metadata
        6. Apply cross-reference detection

        Args:
            content: Normalized health content with metadata

        Returns:
            List of chunks, or empty list if markdown body is empty

        Raises:
            ValueError: If extra_metadata is missing or validation fails
        """
        # 1. Guard: require extra_metadata
        if not content.structural_hints.extra_metadata:
            raise ValueError(
                f"HealthDomain requires extra_metadata in structural_hints "
                f"for source {content.source_id}"
            )

        meta_dict = content.structural_hints.extra_metadata

        # 2. Validate via HealthMetadata
        try:
            meta = HealthMetadata(**meta_dict)  # type: ignore[arg-type]
        except ValidationError as e:
            raise ValueError(
                f"Invalid HealthMetadata for source {content.source_id}: "
                f"{e.error_count()} validation error(s) — "
                f"{[err['msg'] for err in e.errors()]}"
            ) from e

        # 3. Build context_header in "{health_type} — {date}" format
        context_header = f"{meta.health_type} — {meta.date}"

        # 4. Get body and guard against empty markdown
        text = content.markdown.strip()
        if not text:
            return []

        # 5. Split if needed
        segments = self._split_if_needed(text)

        # 6. Build chunks with sequential indices
        chunks = []
        for idx, segment in enumerate(segments):
            chunk_hash = compute_chunk_hash(segment)
            # Merge model_dump with original dict to preserve any extra fields
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

        # 7. Apply cross-reference detection
        return self._apply_cross_references(chunks)
