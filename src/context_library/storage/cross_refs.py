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

    # Pattern 1: References to relative positions ("above", "below", etc.)
    # Only match if they seem to be genuinely referential
    position_patterns = [
        r"(?:as\s+)?(?:shown|defined|described)\s+(?:in\s+)?(?:the\s+)?(?:above|previous|preceding)",
        r"(?:in\s+)?(?:the\s+)?(?:table|figure|code|section|chapter)\s+(?:above|below|earlier|later|previously|following|next|previous)",
        r"(?:see\s+)?(?:the\s+)?(?:table|figure|section|chapter)\s+(?:above|below)",
        r"(?:as\s+shown|as\s+defined)\s+(?:above|below)",
    ]

    for pattern in position_patterns:
        if re.search(pattern, content_lower):
            # Find chunks that appear before this one (for "above"/"earlier" patterns)
            if re.search(r"(?:above|earlier|previous|preceding)", content_lower):
                earlier_chunks = [c for c in all_chunks if c.chunk_index < chunk.chunk_index]
                for earlier_chunk in earlier_chunks:
                    referenced_hashes.add(earlier_chunk.chunk_hash)

            # Find chunks that appear after this one (for "below"/"following" patterns)
            if re.search(r"(?:below|following|next|later)", content_lower):
                later_chunks = [c for c in all_chunks if c.chunk_index > chunk.chunk_index]
                for later_chunk in later_chunks:
                    referenced_hashes.add(later_chunk.chunk_hash)

    # Pattern 2: Explicit cross-reference patterns
    # Look for references that use specific terminology
    cross_ref_patterns = [
        r"as\s+(?:shown|defined|explained|described)\s+in\s+(?:the\s+)?(?:table|figure|section|chapter|code|example)",
        r"(?:see|refer\s+to)\s+(?:the\s+)?(?:table|figure|section|chapter|code|example)",
        r"(?:the\s+)?(?:following|next|above|previous)\s+(?:table|figure|section|chapter|code|block|example)",
        r"(?:in\s+)?(?:the\s+)?(?:table|figure|section|chapter)\s+(?:below|above|above)",
    ]

    for pattern in cross_ref_patterns:
        if re.search(pattern, content_lower):
            # For "the following X" and "the X above" patterns, link to nearby chunks
            # that might be referenced
            if re.search(r"(?:following|next|below)", content_lower):
                later_chunks = [c for c in all_chunks if c.chunk_index > chunk.chunk_index]
                for later_chunk in later_chunks:
                    referenced_hashes.add(later_chunk.chunk_hash)

            if re.search(r"(?:above|previous|preceding|earlier)", content_lower):
                earlier_chunks = [c for c in all_chunks if c.chunk_index < chunk.chunk_index]
                for earlier_chunk in earlier_chunks:
                    referenced_hashes.add(earlier_chunk.chunk_hash)

    # Remove self-references (chunk should not reference itself)
    referenced_hashes.discard(chunk.chunk_hash)

    # Return as sorted tuple for deterministic ordering
    return tuple(sorted(referenced_hashes))
