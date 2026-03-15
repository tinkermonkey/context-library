"""Health domain chunker for health-related content."""

import logging
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
    headers, and delegates oversized content to _split_if_needed().

    Note: Time-series windowing is performed by adapters (e.g., hourly heart rate
    grouping in AppleHealthAdapter._fetch_heart_rate) before normalization, not
    by this chunker.
    """

    def __init__(self, hard_limit: int = 1024) -> None:
        """Initialize the HealthDomain chunker.

        Args:
            hard_limit: Maximum token limit before forced splitting (default 1024)

        Raises:
            ValueError: If hard_limit is not a positive integer
        """
        super().__init__(hard_limit)

    def chunk(self, content: NormalizedContent) -> list[Chunk]:
        """Chunk health content into semantically coherent pieces.

        Algorithm:
        1. Extract and validate HealthMetadata from extra_metadata
        2. Build context_header in "{health_type} — {date}" format using the single date
           from metadata. (Note: Date-range windowing occurs at the adapter level.
           For example, AppleHealthAdapter._fetch_heart_rate groups individual samples
           into hourly windows, with each window becoming a separate NormalizedContent.
           This chunker sees the already-windowed markdown body and extracts its single
           date from metadata.)
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


logger = logging.getLogger(__name__)


def format_sleep_efficiency(efficiency: float | int | None) -> str:
    """Format sleep efficiency value for markdown output.

    Args:
        efficiency: Sleep efficiency as either 0.0–1.0 (decimal) or 0–100 (percentage).

    Returns:
        Formatted efficiency string with % suffix, e.g. "92.0%"

    Note:
        The API contract ambiguity is handled defensively:
        - If efficiency <= 1.0, assumes 0.0–1.0 range and formats as percentage (0.92 → 92.0%)
        - If efficiency > 1.0, assumes 0–100 range and formats as-is with % suffix (92 → 92.0%)
        - Values between 1.0 and ~10 are ambiguous (could indicate bad data) and log a warning.

    Examples:
        format_sleep_efficiency(0.92) → "92.0%"
        format_sleep_efficiency(92) → "92.0%"
        format_sleep_efficiency(1.0) → "100.0%"
    """
    if efficiency is None:
        return ""

    efficiency_float = float(efficiency)

    # Ambiguous boundary: warn if value is between 1 and 10 (likely bad data)
    if 1.0 < efficiency_float < 10:
        logger.warning(
            f"Suspicious sleep efficiency value {efficiency_float}: "
            "between 1.0 and 10 (could indicate data format error). "
            "Treating as 0–100 range."
        )

    # API contract: efficiency is 0.0–1.0. If value > 1, treat as percentage (0–100).
    if efficiency_float > 1.0:
        return f"{efficiency_float:.1f}%"
    else:
        return f"{efficiency_float:.1%}"
