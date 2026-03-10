"""Tests for cross-reference detection module.

Covers:
- Pattern detection (positional, structural, explicit)
- Nearby chunk filtering (within 3 positions)
- Self-reference prevention
- Edge cases (empty content, single chunk, boundary conditions)
- Deterministic ordering of results
"""


from context_library.storage.cross_refs import detect_cross_references
from context_library.storage.models import Chunk, ChunkType, compute_chunk_hash


def _make_chunk(
    content: str,
    chunk_index: int,
    chunk_hash: str | None = None,
) -> Chunk:
    """Helper to create a test chunk.

    Args:
        content: Chunk content
        chunk_index: Position in sequence
        chunk_hash: Optional hash; computed from content if not provided

    Returns:
        A Chunk instance
    """
    if chunk_hash is None:
        chunk_hash = compute_chunk_hash(content)

    return Chunk(
        chunk_hash=chunk_hash,
        chunk_index=chunk_index,
        content=content,
        chunk_type=ChunkType.STANDARD,
        context_header="",
        domain_metadata={},
        cross_refs=(),
    )


class TestDetectCrossReferencesEmpty:
    """Tests for edge cases with empty or minimal content."""

    def test_empty_content_returns_no_refs(self) -> None:
        """Test that chunks with empty content produce no cross-references."""
        chunk = _make_chunk("", 0)
        all_chunks = [chunk]

        refs = detect_cross_references(chunk, all_chunks)

        assert refs == ()

    def test_whitespace_only_content_returns_no_refs(self) -> None:
        """Test that chunks with only whitespace produce no cross-references."""
        chunk = _make_chunk("   \n\n   ", 0)
        all_chunks = [chunk]

        refs = detect_cross_references(chunk, all_chunks)

        # Whitespace-only content is still truthy, but shouldn't match patterns
        assert refs == ()

    def test_single_chunk_no_self_reference(self) -> None:
        """Test that a single chunk does not reference itself."""
        chunk = _make_chunk("This chunk mentions above and below content.", 0)
        all_chunks = [chunk]

        refs = detect_cross_references(chunk, all_chunks)

        assert refs == ()


class TestPositionalPatterns:
    """Tests for positional pattern detection requiring specific phrases."""

    def test_positional_pattern_with_see_section_above(self) -> None:
        """Test 'see the section above' pattern triggers references."""
        chunks = [
            _make_chunk("Section Introduction", 0),
            _make_chunk("Section Details", 1),
            _make_chunk("More details", 2),
            _make_chunk("See the section above", 3),
        ]

        refs = detect_cross_references(chunks[3], chunks)

        # 'see the section above' matches positional pattern + has_above_ref
        expected_hashes = frozenset(
            chunks[i].chunk_hash for i in [0, 1, 2]
        )
        assert frozenset(refs) == expected_hashes

    def test_positional_pattern_with_table_below(self) -> None:
        """Test 'the table below' pattern triggers references."""
        chunks = [
            _make_chunk("See the table below", 0),
            _make_chunk("Table data 1", 1),
            _make_chunk("Table data 2", 2),
            _make_chunk("Table data 3", 3),
            _make_chunk("Final content", 4),
        ]

        refs = detect_cross_references(chunks[0], chunks)

        # 'the table below' matches positional pattern + has_below_ref
        expected_hashes = frozenset(
            chunks[i].chunk_hash for i in [1, 2, 3]
        )
        assert frozenset(refs) == expected_hashes

    def test_positional_pattern_respects_distance_limit(self) -> None:
        """Test that positional patterns only reference nearby chunks."""
        chunks = [
            _make_chunk("A", 0),
            _make_chunk("B", 1),
            _make_chunk("C", 2),
            _make_chunk("D", 3),
            _make_chunk("E", 4),
            _make_chunk("F", 5),
            _make_chunk("See the section above", 6),
        ]

        refs = detect_cross_references(chunks[6], chunks)

        # Should only reference chunks 3, 4, 5 (within 3 positions)
        expected_hashes = frozenset(
            chunks[i].chunk_hash for i in [3, 4, 5]
        )
        assert frozenset(refs) == expected_hashes

    def test_positional_pattern_as_shown_above(self) -> None:
        """Test 'as shown above' positional pattern."""
        chunks = [
            _make_chunk("Content 1", 0),
            _make_chunk("Content 2", 1),
            _make_chunk("As shown above", 2),
        ]

        refs = detect_cross_references(chunks[2], chunks)

        # 'as shown above' matches positional pattern
        expected_hashes = frozenset(
            chunks[i].chunk_hash for i in [0, 1]
        )
        assert frozenset(refs) == expected_hashes

    def test_multiple_directional_keywords(self) -> None:
        """Test that content with both 'above' and 'below' refs accumulates."""
        chunks = [
            _make_chunk("Earlier content", 0),
            _make_chunk("Content 1", 1),
            _make_chunk("Content 2", 2),
            _make_chunk("As shown above and explained below", 3),
            _make_chunk("Later content 1", 4),
            _make_chunk("Later content 2", 5),
        ]

        refs = detect_cross_references(chunks[3], chunks)

        # Should reference chunks 0, 1, 2 (above) and 4, 5 (below)
        expected_hashes = frozenset(
            chunks[i].chunk_hash for i in [0, 1, 2, 4, 5]
        )
        assert frozenset(refs) == expected_hashes


class TestStructuralPatterns:
    """Tests for structural reference patterns (Section, Table, Figure, etc.)."""

    def test_section_reference_with_above_keyword(self) -> None:
        """Test structural pattern with section reference."""
        chunks = [
            _make_chunk("Introduction content", 0),
            _make_chunk("Section content", 1),
            _make_chunk("Details content", 2),
            _make_chunk("See the section above for details", 3),
        ]

        refs = detect_cross_references(chunks[3], chunks)

        # 'see the section above' matches positional pattern
        expected_hashes = frozenset(
            chunks[i].chunk_hash for i in [0, 1, 2]
        )
        assert frozenset(refs) == expected_hashes

    def test_figure_reference_pattern(self) -> None:
        """Test 'the figure above' structural pattern."""
        chunks = [
            _make_chunk("Introduction", 0),
            _make_chunk("Figure data 1", 1),
            _make_chunk("Figure data 2", 2),
            _make_chunk("See the figure above", 3),
        ]

        refs = detect_cross_references(chunks[3], chunks)

        # 'see the figure above' matches positional pattern with above keyword
        expected_hashes = frozenset(
            chunks[i].chunk_hash for i in [0, 1, 2]
        )
        assert frozenset(refs) == expected_hashes

    def test_chapter_code_patterns(self) -> None:
        """Test pattern detection for Chapter and Code structures."""
        chunks = [
            _make_chunk("Chapter intro", 0),
            _make_chunk("Code snippet", 1),
            _make_chunk("More code", 2),
            _make_chunk("See the code above", 3),
        ]

        refs = detect_cross_references(chunks[3], chunks)

        # 'see the code above' matches positional pattern
        assert len(refs) > 0


class TestExplicitPatterns:
    """Tests for explicit reference patterns (see, refer to, as shown in, etc.)."""

    def test_as_shown_in_pattern(self) -> None:
        """Test 'as shown in the table/figure' explicit pattern."""
        chunks = [
            _make_chunk("Table data 1", 0),
            _make_chunk("Table data 2", 1),
            _make_chunk("Analysis", 2),
            _make_chunk("As shown in the table", 3),
        ]

        refs = detect_cross_references(chunks[3], chunks)

        # Should reference nearby chunks (both directions since no directional keyword)
        expected_hashes = frozenset(
            chunks[i].chunk_hash for i in [0, 1, 2]
        )
        assert frozenset(refs) == expected_hashes

    def test_see_pattern(self) -> None:
        """Test 'see the section/table' explicit pattern."""
        chunks = [
            _make_chunk("Content A", 0),
            _make_chunk("Content B", 1),
            _make_chunk("Content C", 2),
            _make_chunk("For more details, see the section", 3),
        ]

        refs = detect_cross_references(chunks[3], chunks)

        # Should reference nearby chunks (both directions)
        assert len(refs) > 0

    def test_refer_to_pattern(self) -> None:
        """Test 'refer to' explicit pattern."""
        chunks = [
            _make_chunk("Reference material", 0),
            _make_chunk("More reference", 1),
            _make_chunk("Details", 2),
            _make_chunk("Refer to the example in the section", 3),
        ]

        refs = detect_cross_references(chunks[3], chunks)

        assert len(refs) > 0

    def test_explicit_pattern_with_above_keyword(self) -> None:
        """Test explicit pattern with directional keyword (above)."""
        chunks = [
            _make_chunk("Earlier section", 0),
            _make_chunk("Content 1", 1),
            _make_chunk("Content 2", 2),
            _make_chunk("Content 3", 3),
            _make_chunk("As defined in the section above", 4),
        ]

        refs = detect_cross_references(chunks[4], chunks)

        # Should reference chunks within 3 positions above
        expected_hashes = frozenset(
            chunks[i].chunk_hash for i in [1, 2, 3]
        )
        assert frozenset(refs) == expected_hashes

    def test_explicit_pattern_with_below_keyword(self) -> None:
        """Test explicit pattern with directional keyword (below)."""
        chunks = [
            _make_chunk("See the figure below", 0),
            _make_chunk("Figure 1", 1),
            _make_chunk("Figure 2", 2),
            _make_chunk("Figure 3", 3),
        ]

        refs = detect_cross_references(chunks[0], chunks)

        # Should reference chunks within 3 positions below
        expected_hashes = frozenset(
            chunks[i].chunk_hash for i in [1, 2, 3]
        )
        assert frozenset(refs) == expected_hashes

    def test_explicit_pattern_without_directional_keyword(self) -> None:
        """Test explicit pattern linking in both directions when no direction specified."""
        chunks = [
            _make_chunk("Previous content", 0),
            _make_chunk("Content 1", 1),
            _make_chunk("Content 2", 2),
            _make_chunk("See the following table", 3),
            _make_chunk("Next content 1", 4),
            _make_chunk("Next content 2", 5),
        ]

        refs = detect_cross_references(chunks[3], chunks)

        # 'see the following table' matches explicit pattern with 'following' keyword
        # Since it has 'following' (a below keyword), only references below
        expected_hashes = frozenset(
            chunks[i].chunk_hash for i in [4, 5]
        )
        assert frozenset(refs) == expected_hashes


class TestNoPatternMatch:
    """Tests for content that doesn't match any cross-reference patterns."""

    def test_no_pattern_match_returns_empty(self) -> None:
        """Test that content without patterns produces no references."""
        chunks = [
            _make_chunk("Normal content without any keywords", 0),
            _make_chunk("More normal content", 1),
            _make_chunk("Just regular text here", 2),
        ]

        refs = detect_cross_references(chunks[1], chunks)

        assert refs == ()

    def test_isolated_keywords_without_phrase_pattern(self) -> None:
        """Test that isolated keywords without matching phrase patterns don't trigger refs."""
        chunks = [
            _make_chunk("Content A", 0),
            _make_chunk("Content B", 1),
            _make_chunk("The word above appears in this sentence", 2),
        ]

        refs = detect_cross_references(chunks[2], chunks)

        # Just having "above" without a phrase pattern doesn't trigger references
        # Pattern requires phrases like "see above" or "as shown above"
        assert refs == ()


class TestSelfReferenceExclusion:
    """Tests that chunks do not reference themselves."""

    def test_chunk_does_not_self_reference(self) -> None:
        """Test that a chunk never appears in its own cross_refs."""
        chunks = [
            _make_chunk("See above", 0),
            _make_chunk("Content", 1),
            _make_chunk("See below", 2),
        ]

        for chunk in chunks:
            refs = detect_cross_references(chunk, chunks)
            assert chunk.chunk_hash not in refs

    def test_self_reference_excluded_even_when_pattern_matches(self) -> None:
        """Test that self-references are excluded even with matching patterns."""
        chunks = [
            _make_chunk("Content with reference above and table", 0),
            _make_chunk("Data", 1),
        ]

        refs = detect_cross_references(chunks[0], chunks)

        # Should only reference chunk 1, not itself
        assert chunks[0].chunk_hash not in refs


class TestDeterministicOrdering:
    """Tests that cross-reference detection returns results in deterministic order."""

    def test_results_are_sorted(self) -> None:
        """Test that returned hashes are in sorted order."""
        chunks = [
            _make_chunk("Content 1", 0),
            _make_chunk("Content 2", 1),
            _make_chunk("Content 3", 2),
            _make_chunk("See above", 3),
        ]

        refs = detect_cross_references(chunks[3], chunks)

        # Should be sorted
        assert refs == tuple(sorted(refs))

    def test_multiple_runs_produce_same_order(self) -> None:
        """Test that running detection multiple times produces identical results."""
        chunks = [
            _make_chunk("Content A", 0),
            _make_chunk("Content B", 1),
            _make_chunk("Content C", 2),
            _make_chunk("As shown in the table above", 3),
        ]

        refs1 = detect_cross_references(chunks[3], chunks)
        refs2 = detect_cross_references(chunks[3], chunks)
        refs3 = detect_cross_references(chunks[3], chunks)

        assert refs1 == refs2 == refs3


class TestCaseInsensitivity:
    """Tests that pattern detection is case-insensitive."""

    def test_uppercase_explicit_pattern_detected(self) -> None:
        """Test that uppercase patterns are detected."""
        chunks = [
            _make_chunk("Content", 0),
            _make_chunk("Data", 1),
            _make_chunk("SEE THE TABLE", 2),
        ]

        refs = detect_cross_references(chunks[2], chunks)

        assert len(refs) > 0

    def test_mixed_case_pattern_detected(self) -> None:
        """Test that mixed-case patterns are detected."""
        chunks = [
            _make_chunk("Content", 0),
            _make_chunk("Data", 1),
            _make_chunk("See The Section Above", 2),
        ]

        refs = detect_cross_references(chunks[2], chunks)

        assert len(refs) > 0


class TestBoundaryConditions:
    """Tests for boundary cases and edge conditions."""

    def test_all_nearby_chunks_referenced_with_pattern(self) -> None:
        """Test referencing nearby chunks with explicit pattern."""
        chunks = [
            _make_chunk("A", 0),
            _make_chunk("B", 1),
            _make_chunk("C", 2),
            _make_chunk("See the section above", 3),
        ]

        refs = detect_cross_references(chunks[3], chunks)

        # Should reference chunks 0, 1, 2 (within 3 positions)
        expected_hashes = frozenset(
            chunks[i].chunk_hash for i in [0, 1, 2]
        )
        assert frozenset(refs) == expected_hashes

    def test_first_chunk_can_reference_below_with_pattern(self) -> None:
        """Test that first chunk (index 0) can reference below with proper pattern."""
        chunks = [
            _make_chunk("See the table below", 0),
            _make_chunk("Content", 1),
            _make_chunk("Content", 2),
        ]

        refs = detect_cross_references(chunks[0], chunks)

        # Should reference chunks 1 and 2 (within 3 positions)
        expected_hashes = frozenset(
            chunks[i].chunk_hash for i in [1, 2]
        )
        assert frozenset(refs) == expected_hashes

    def test_last_chunk_can_reference_above_with_pattern(self) -> None:
        """Test that last chunk can reference above with proper pattern."""
        chunks = [
            _make_chunk("Content", 0),
            _make_chunk("Content", 1),
            _make_chunk("See the section above", 2),
        ]

        refs = detect_cross_references(chunks[2], chunks)

        # Should reference chunks 0 and 1 (within 3 positions)
        expected_hashes = frozenset(
            chunks[i].chunk_hash for i in [0, 1]
        )
        assert frozenset(refs) == expected_hashes

    def test_chunk_exactly_3_positions_away_included(self) -> None:
        """Test that chunks exactly 3 positions away are included."""
        chunks = [
            _make_chunk("Content A", 0),
            _make_chunk("Content B", 1),
            _make_chunk("Content C", 2),
            _make_chunk("Reference chunk", 3),
            _make_chunk("Space", 4),
            _make_chunk("Space", 5),
            _make_chunk("See the section above", 6),  # Exactly 3 positions from index 3
        ]

        refs = detect_cross_references(chunks[6], chunks)

        # Chunk at index 3 should be included (distance = 3)
        assert chunks[3].chunk_hash in refs

    def test_chunks_4_positions_away_excluded(self) -> None:
        """Test that chunks 4 positions away are excluded."""
        chunks = [
            _make_chunk("Far content", 0),
            _make_chunk("Content", 1),
            _make_chunk("Content", 2),
            _make_chunk("Content", 3),
            _make_chunk("Reference chunk", 4),
            _make_chunk("Space", 5),
            _make_chunk("Space", 6),
            _make_chunk("Space", 7),
            _make_chunk("See the section above", 8),  # 4 positions away from index 4
        ]

        refs = detect_cross_references(chunks[8], chunks)

        # Chunk at index 4 should NOT be included (distance = 4)
        assert chunks[4].chunk_hash not in refs
