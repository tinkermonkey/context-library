"""Cross-reference detection for chunks.

Implements heuristic detection of cross-references between chunks to enable automatic
linking of related content. Currently supports intra-source linking using positional
patterns ("above", "below", etc.) and structural references ("Section", "Table", etc.).

Uses pattern matching to identify references like "above", "below", "see Section X",
"as defined in", "the following table", etc. Detection is best-effort with tolerance
for false positives (extra context is harmless) and false negatives (acceptable).
Detection is scoped to nearby chunks (within 3 positions) to minimize noise.

Roadmap: Cross-source linking via semantic similarity analysis is planned to support
"Automatic identification and linking of related content across multiple domains and sources."
"""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from context_library.storage.models import Chunk, Sha256Hash


def detect_cross_references(chunk: "Chunk", all_chunks: list["Chunk"]) -> tuple["Sha256Hash", ...]:
    """Detect cross-references from a chunk to other chunks within the same source.

    Identifies heuristic patterns that indicate references to other chunks
    and returns the hashes of referenced chunks. Detection is scoped to nearby chunks
    (within 3 positions) to minimize noise from broad references.

    Pattern detection looks for:
    - Positional keywords (triggering directional logic): "above", "below", "earlier", "previous",
      "preceding", "following", "next", "later" (with word boundaries to prevent false positives)
    - Structural references: "Section", "Chapter", "Figure", "Table", "Code", "Example", "Block"
    - Explicit patterns: "as shown in", "as defined in", "as described in", "as explained in",
      "see", "refer to"
    - Combined patterns: "the table below", "the code above", "the figure following", "the section
      previously mentioned", etc. (where "previously" may appear in compound patterns)

    Args:
        chunk: The chunk to analyze for cross-references
        all_chunks: All chunks in the same source (provides context for reference resolution)

    Returns:
        Tuple of chunk hashes (as SHA-256 hex strings) that are referenced by this chunk
    """
    if not chunk.content:
        return ()

    referenced_hashes: set["Sha256Hash"] = set()
    content_lower = chunk.content.lower()

    # Detect references to relative positions ("above", "below", etc.)
    # When detected, link to nearby chunks (within 3 positions) rather than all preceding/following chunks
    # to avoid excessive noise from broad positional references
    # NOTE: Word boundaries (\b) alone are insufficient to prevent false positives from bare keywords
    # like "earlier" in "earlier this year". False positive prevention relies on the two-gate logic:
    # a keyword must match BOTH (1) the bare keyword pattern AND (2) a compound phrase pattern
    # (positional or explicit) to create cross-references. Bare keywords without phrase patterns
    # do not generate refs. See test_isolated_keywords_without_phrase_pattern for verification.
    has_above_ref = bool(re.search(r"\b(?:above|earlier|previous|preceding)\b", content_lower))
    has_below_ref = bool(re.search(r"\b(?:below|following|next|later)\b", content_lower))

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

    # NOTE: The 3rd and 4th alternations of has_explicit_pattern contain directional keywords
    # (following, next, above, previous, below). When these alternations match, has_above_ref or
    # has_below_ref will also be True. The set-based referenced_hashes deduplicates any chunks added
    # through both has_positional_pattern and the directional branches of has_explicit_pattern,
    # so no duplicate refs are created. Non-directional patterns (1st and 2nd alternations)
    # fall through to the bidirectional fallback (if not has_above_ref and not has_below_ref)
    # when neither directional flag is set.

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
    # also use nearby chunk scope. If direction is specified (above/below), use that.
    # If no direction is specified, link to nearby chunks in both directions.
    if has_explicit_pattern:
        if has_above_ref:
            nearby_earlier = [
                c for c in all_chunks
                if c.chunk_index < chunk.chunk_index
                and chunk.chunk_index - c.chunk_index <= 3
            ]
            for earlier_chunk in nearby_earlier:
                referenced_hashes.add(earlier_chunk.chunk_hash)

        if has_below_ref:
            nearby_later = [
                c for c in all_chunks
                if c.chunk_index > chunk.chunk_index
                and c.chunk_index - chunk.chunk_index <= 3
            ]
            for later_chunk in nearby_later:
                referenced_hashes.add(later_chunk.chunk_hash)

        # If explicit pattern found but no directional keyword, link to nearby chunks
        # in both directions to capture references like "see Section X", "as shown in the table"
        if not has_above_ref and not has_below_ref:
            # Link to up to 3 chunks before and after
            nearby_all = [
                c for c in all_chunks
                if abs(c.chunk_index - chunk.chunk_index) <= 3
                and c.chunk_index != chunk.chunk_index
            ]
            for nearby_chunk in nearby_all:
                referenced_hashes.add(nearby_chunk.chunk_hash)

    # Remove self-references (chunk should not reference itself)
    referenced_hashes.discard(chunk.chunk_hash)

    # Return as sorted tuple for deterministic ordering
    return tuple(sorted(referenced_hashes))
