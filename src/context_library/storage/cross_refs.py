"""Cross-reference detection for chunks.

Implements heuristic detection of cross-references between chunks to enable
automatic linking and retrieval of related content across multiple domains.

Uses pattern matching to identify references like "above", "below", "see Section X",
"as defined in", "the following table", etc. Detection is best-effort with tolerance
for false positives (extra context is harmless) and false negatives (acceptable).
"""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from context_library.storage.models import Chunk


def detect_cross_references(chunk: "Chunk", all_chunks: list["Chunk"]) -> tuple[str, ...]:
    """Detect cross-references from a chunk to other chunks.

    Identifies heuristic patterns that indicate references to other chunks
    and returns the hashes of referenced chunks.

    Pattern detection looks for:
    - "above", "below", "previously", "following"
    - "Section X", "Chapter X", "Figure X", "Table X"
    - "as shown in", "as defined in", "see X"
    - "the table below", "the code above", etc.

    When positional references are detected, links to nearby chunks (within 3 positions).
    This limits noise from over-broad references.

    Args:
        chunk: The chunk to analyze for cross-references
        all_chunks: All chunks in the source (for context about what exists)

    Returns:
        Tuple of chunk hashes that are referenced by this chunk
    """
    if not chunk.content:
        return ()

    referenced_hashes = set()
    content_lower = chunk.content.lower()

    # Detect references to relative positions ("above", "below", etc.)
    # When detected, link to nearby chunks (within 3 positions) rather than all preceding/following chunks
    # to avoid excessive noise from broad positional references
    has_above_ref = bool(re.search(r"(?:above|earlier|previous|preceding)", content_lower))
    has_below_ref = bool(re.search(r"(?:below|following|next|later)", content_lower))

    has_positional_pattern = bool(
        re.search(
            r"(?:as\s+)?(?:shown|defined|described)\s+(?:in\s+)?(?:the\s+)?(?:above|previous|preceding|below|following|next|later)|"
            r"(?:in\s+)?(?:the\s+)?(?:table|figure|code|section|chapter)\s+(?:above|below|earlier|later|previously|following|next|previous)|"
            r"(?:see\s+)?(?:the\s+)?(?:table|figure|section|chapter)\s+(?:above|below)|"
            r"(?:as\s+shown|as\s+defined)\s+(?:above|below)",
            content_lower,
        )
    )

    has_explicit_pattern = bool(
        re.search(
            r"as\s+(?:shown|defined|explained|described)\s+in\s+(?:the\s+)?(?:table|figure|section|chapter|code|example)|"
            r"(?:see|refer\s+to)\s+(?:the\s+)?(?:table|figure|section|chapter|code|example)|"
            r"(?:the\s+)?(?:following|next|above|previous)\s+(?:table|figure|section|chapter|code|block|example)|"
            r"(?:in\s+)?(?:the\s+)?(?:table|figure|section|chapter)\s+(?:below|above)",
            content_lower,
        )
    )

    # For positional patterns, link only to nearby chunks to avoid noise
    if has_positional_pattern:
        if has_above_ref:
            # Link to up to 3 chunks immediately before
            nearby_earlier = [
                c for c in all_chunks
                if c.chunk_index < chunk.chunk_index
                and chunk.chunk_index - c.chunk_index <= 3
            ]
            for earlier_chunk in nearby_earlier:
                referenced_hashes.add(earlier_chunk.chunk_hash)

        if has_below_ref:
            # Link to up to 3 chunks immediately after
            nearby_later = [
                c for c in all_chunks
                if c.chunk_index > chunk.chunk_index
                and c.chunk_index - chunk.chunk_index <= 3
            ]
            for later_chunk in nearby_later:
                referenced_hashes.add(later_chunk.chunk_hash)

    # For explicit patterns (e.g., "see Section X", "as defined in the table"),
    # also use nearby chunk scope
    if has_explicit_pattern:
        if has_below_ref:
            nearby_later = [
                c for c in all_chunks
                if c.chunk_index > chunk.chunk_index
                and c.chunk_index - chunk.chunk_index <= 3
            ]
            for later_chunk in nearby_later:
                referenced_hashes.add(later_chunk.chunk_hash)

        if has_above_ref:
            nearby_earlier = [
                c for c in all_chunks
                if c.chunk_index < chunk.chunk_index
                and chunk.chunk_index - c.chunk_index <= 3
            ]
            for earlier_chunk in nearby_earlier:
                referenced_hashes.add(earlier_chunk.chunk_hash)

    # Remove self-references (chunk should not reference itself)
    referenced_hashes.discard(chunk.chunk_hash)

    # Return as sorted tuple for deterministic ordering
    return tuple(sorted(referenced_hashes))
