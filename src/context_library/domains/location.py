"""LocationDomain: geospatial chunking for place visits and current location snapshots."""

from pydantic import ValidationError

from context_library.domains.base import BaseDomain
from context_library.storage.models import (
    Chunk,
    ChunkType,
    LocationMetadata,
    NormalizedContent,
    compute_chunk_hash,
)

# Source type identifier for current location snapshots (from AppleLocationAdapter)
CURRENT_LOCATION_SOURCE_TYPE = "apple_location_current"


class LocationDomain(BaseDomain):
    """Domain-specific chunker for location content.

    Splits location content into semantically coherent chunks with location-specific
    handling: geospatial context headers, location metadata, and token-based
    splitting for long location descriptions.
    """

    def __init__(self, hard_limit: int = 1024) -> None:
        """Initialize the LocationDomain chunker.

        Args:
            hard_limit: Maximum token limit before forced splitting (default 1024)

        Raises:
            ValueError: If hard_limit is not a positive integer
        """
        super().__init__(hard_limit)

    def chunk(self, content: NormalizedContent) -> list[Chunk]:
        """Split location content into semantically coherent chunks.

        Algorithm:
        1. Extract LocationMetadata from content.structural_hints.extra_metadata
        2. Build context_header with place_name and arrival_date if available,
           otherwise fall back to "{latitude}, {longitude}"
        3. Split oversized descriptions at sentence boundaries if exceeding hard_limit
        4. Compute chunk_hash from content only (excluding context_header)
        5. Assign sequential chunk_index values
        6. Set chunk_type to ChunkType.STANDARD
        7. Store domain_metadata preserving both validated fields and extra fields

        Args:
            content: The normalized location content to chunk

        Returns:
            A list of Chunk instances with sequential chunk_index values
        """
        # Extract LocationMetadata from extra_metadata
        if not content.structural_hints.extra_metadata:
            raise ValueError(
                f"LocationDomain requires extra_metadata in structural_hints "
                f"for source {content.source_id}"
            )

        meta_dict = content.structural_hints.extra_metadata
        try:
            # Type contract: extra_metadata must be deserializable to LocationMetadata.
            # This is enforced at validation time rather than in the type system
            # because StructuralHints.extra_metadata is domain-agnostic (dict[str, object]).
            # See StructuralHints docstring for design rationale.
            meta = LocationMetadata(**meta_dict)  # type: ignore[arg-type]
        except ValidationError as e:
            raise ValueError(
                f"Invalid LocationMetadata for source {content.source_id}: "
                f"{e.error_count()} validation error(s) — {[err['msg'] for err in e.errors()]}"
            ) from e

        # Build context_header
        # For current location snapshots, use "Current location — {timestamp}" format
        if meta.source_type == CURRENT_LOCATION_SOURCE_TYPE:
            context_header = f"Current location — {meta.date_first_observed}"
        elif meta.place_name and meta.arrival_date:
            context_header = f"{meta.place_name} — {meta.arrival_date}"
        elif meta.place_name:
            context_header = meta.place_name
        else:
            # Fall back to coordinates
            context_header = f"{meta.latitude}, {meta.longitude}"

        # Get the markdown text as the body
        text = content.markdown.strip()

        # Per spec: return empty list if no description content
        # (location is available in context_header, not needed in content)
        if not text:
            return []

        # Split if over hard_limit
        segments = self._split_if_needed(text)

        # Build Chunk objects with sequential indices
        chunks = []
        for idx, segment in enumerate(segments):
            chunk_hash = compute_chunk_hash(segment)
            # LocationMetadata validates all fields during initialization.
            # Merge with validated model values taking precedence over raw unvalidated values.
            domain_metadata = {**meta_dict, **meta.model_dump()}
            chunk = Chunk(
                chunk_hash=chunk_hash,
                content=segment,
                context_header=context_header,
                chunk_index=idx,
                chunk_type=ChunkType.STANDARD,
                domain_metadata=domain_metadata,
            )
            chunks.append(chunk)

        # Apply cross-reference detection to all chunks
        return self._apply_cross_references(chunks)
