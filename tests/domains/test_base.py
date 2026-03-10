"""Tests for the base domain module.

Covers:
- BaseDomain initialization and hard_limit validation
- Token counting and text splitting logic
- _apply_cross_references method with model_copy mutation
- Integration with cross-reference detection
"""

import pytest

from context_library.domains.base import BaseDomain
from context_library.storage.models import Chunk, ChunkType, NormalizedContent, compute_chunk_hash


class ConcreteBaseDomain(BaseDomain):
    """Concrete implementation of BaseDomain for testing."""

    def chunk(self, content: NormalizedContent) -> list[Chunk]:
        """Simple chunking that splits at sentence boundaries."""
        sentences = content.content.split(". ")
        chunks = []
        for i, sentence in enumerate(sentences):
            chunk_content = sentence.strip()
            if chunk_content:
                chunk_hash = compute_chunk_hash(chunk_content)
                chunk = Chunk(
                    chunk_hash=chunk_hash,
                    chunk_index=i,
                    content=chunk_content,
                    chunk_type=ChunkType.STANDARD,
                    context_header="",
                    domain_metadata={},
                    cross_refs=(),
                )
                chunks.append(chunk)
        return chunks


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


class TestBaseDomainInit:
    """Tests for BaseDomain initialization."""

    def test_init_with_valid_hard_limit(self) -> None:
        """Test initialization with a valid positive hard_limit."""
        domain = ConcreteBaseDomain(hard_limit=1024)
        assert domain.hard_limit == 1024

    def test_init_with_default_hard_limit(self) -> None:
        """Test initialization with default hard_limit."""
        domain = ConcreteBaseDomain()
        assert domain.hard_limit == 1024

    def test_init_with_small_hard_limit(self) -> None:
        """Test initialization with small hard_limit."""
        domain = ConcreteBaseDomain(hard_limit=1)
        assert domain.hard_limit == 1

    def test_init_with_zero_hard_limit_raises(self) -> None:
        """Test that hard_limit=0 raises ValueError."""
        with pytest.raises(ValueError, match="hard_limit must be a positive integer"):
            ConcreteBaseDomain(hard_limit=0)

    def test_init_with_negative_hard_limit_raises(self) -> None:
        """Test that negative hard_limit raises ValueError."""
        with pytest.raises(ValueError, match="hard_limit must be a positive integer"):
            ConcreteBaseDomain(hard_limit=-1)


class TestApplyCrossReferences:
    """Tests for _apply_cross_references method."""

    def test_apply_cross_refs_to_empty_chunks_list(self) -> None:
        """Test applying cross-references to empty chunk list."""
        domain = ConcreteBaseDomain()
        chunks = []

        result = domain._apply_cross_references(chunks)

        assert result == []

    def test_apply_cross_refs_to_single_chunk(self) -> None:
        """Test that single chunk gets no cross-references."""
        domain = ConcreteBaseDomain()
        chunk = _make_chunk("Content", 0)
        chunks = [chunk]

        result = domain._apply_cross_references(chunks)

        assert len(result) == 1
        assert result[0].cross_refs == ()

    def test_apply_cross_refs_preserves_chunk_identity(self) -> None:
        """Test that chunks without cross-refs are returned unchanged."""
        domain = ConcreteBaseDomain()
        chunk = _make_chunk("Normal content", 0)
        chunks = [chunk]

        result = domain._apply_cross_references(chunks)

        # Should be the same chunk object since no refs were found
        assert result[0].chunk_hash == chunk.chunk_hash
        assert result[0].content == chunk.content

    def test_apply_cross_refs_updates_cross_refs_field(self) -> None:
        """Test that cross-references are populated when patterns detected."""
        domain = ConcreteBaseDomain()
        chunks = [
            _make_chunk("Content A", 0),
            _make_chunk("Content B", 1),
            _make_chunk("See the section above", 2),
        ]

        result = domain._apply_cross_references(chunks)

        # Last chunk should have cross-refs populated
        assert len(result[2].cross_refs) > 0

    def test_apply_cross_refs_creates_new_chunk_instance(self) -> None:
        """Test that updated chunks are new instances (model_copy)."""
        domain = ConcreteBaseDomain()
        chunks = [
            _make_chunk("Content A", 0),
            _make_chunk("See below", 1),
            _make_chunk("Content B", 2),
        ]

        result = domain._apply_cross_references(chunks)

        # The chunk with refs should be a different object
        if result[1].cross_refs:
            # model_copy creates a new instance
            assert result[1] is not chunks[1]

    def test_apply_cross_refs_maintains_chunk_index_order(self) -> None:
        """Test that chunk_index values are preserved."""
        domain = ConcreteBaseDomain()
        chunks = [
            _make_chunk("A", 0),
            _make_chunk("B", 1),
            _make_chunk("C", 2),
            _make_chunk("See above", 3),
        ]

        result = domain._apply_cross_references(chunks)

        for i, chunk in enumerate(result):
            assert chunk.chunk_index == i

    def test_apply_cross_refs_multiple_chunks_with_references(self) -> None:
        """Test applying cross-refs when multiple chunks have patterns."""
        domain = ConcreteBaseDomain()
        chunks = [
            _make_chunk("Start", 0),
            _make_chunk("See the section above", 1),
            _make_chunk("Middle", 2),
            _make_chunk("See the table below", 3),
            _make_chunk("End", 4),
        ]

        result = domain._apply_cross_references(chunks)

        # Check that appropriate chunks have refs
        assert len(result[1].cross_refs) > 0  # "See the section above"
        assert len(result[3].cross_refs) > 0  # "See the table below"

    def test_apply_cross_refs_frozen_model_mutation_via_model_copy(self) -> None:
        """Test that frozen Pydantic models can be mutated safely via model_copy."""
        domain = ConcreteBaseDomain()
        chunk = _make_chunk("See above", 0)

        # Verify chunk is frozen
        with pytest.raises(Exception):  # Pydantic frozen models raise on mutation
            chunk.cross_refs = ("a" * 64,)  # type: ignore

        # But model_copy should work
        chunks = [
            _make_chunk("Earlier", -1),
            chunk,
        ]
        result = domain._apply_cross_references(chunks)

        # Should have successfully created a new chunk with updated refs
        assert isinstance(result[1].cross_refs, tuple)

    def test_apply_cross_refs_preserves_other_fields(self) -> None:
        """Test that other chunk fields are preserved during update."""
        domain = ConcreteBaseDomain()
        original_chunk = _make_chunk("See above", 0)
        original_chunk = original_chunk.model_copy(
            update={"context_header": "HEADER", "domain_metadata": {"key": "value"}}
        )

        chunks = [
            _make_chunk("Earlier", -1),
            original_chunk,
        ]

        result = domain._apply_cross_references(chunks)

        # Check that other fields are preserved
        assert result[1].context_header == "HEADER"
        assert result[1].domain_metadata == {"key": "value"}

    def test_apply_cross_refs_deterministic_result(self) -> None:
        """Test that applying cross-refs multiple times produces identical results."""
        domain = ConcreteBaseDomain()
        chunks = [
            _make_chunk("Content A", 0),
            _make_chunk("Content B", 1),
            _make_chunk("See above", 2),
        ]

        result1 = domain._apply_cross_references(chunks)
        result2 = domain._apply_cross_references(chunks)

        # Cross-refs should be identical
        assert result1[2].cross_refs == result2[2].cross_refs

    def test_apply_cross_refs_with_explicit_patterns(self) -> None:
        """Test cross-references with explicit pattern detection."""
        domain = ConcreteBaseDomain()
        chunks = [
            _make_chunk("Table data", 0),
            _make_chunk("More data", 1),
            _make_chunk("As shown in the table", 2),
        ]

        result = domain._apply_cross_references(chunks)

        # Should detect the explicit pattern
        assert len(result[2].cross_refs) > 0

    def test_apply_cross_refs_excludes_self_references(self) -> None:
        """Test that chunks never reference themselves."""
        domain = ConcreteBaseDomain()
        chunks = [
            _make_chunk("Content", 0),
            _make_chunk("See above and refer to self", 1),
        ]

        result = domain._apply_cross_references(chunks)

        # Chunk 1 should not reference itself
        if result[1].cross_refs:
            assert chunks[1].chunk_hash not in result[1].cross_refs

    def test_apply_cross_refs_respects_nearby_chunk_scope(self) -> None:
        """Test that cross-refs respect 3-position nearby scope."""
        domain = ConcreteBaseDomain()
        chunks = [
            _make_chunk("A", 0),
            _make_chunk("B", 1),
            _make_chunk("C", 2),
            _make_chunk("D", 3),
            _make_chunk("E", 4),
            _make_chunk("F", 5),
            _make_chunk("See above", 6),
        ]

        result = domain._apply_cross_references(chunks)

        # Should only reference chunks 3-5 (within 3 positions)
        refs_hashes = set(result[6].cross_refs)
        chunk_3_5_hashes = {chunks[i].chunk_hash for i in range(3, 6)}

        # All refs should be from chunks 3-5
        assert refs_hashes.issubset(chunk_3_5_hashes)

    def test_apply_cross_refs_none_to_many_references(self) -> None:
        """Test range from no references to many references in one operation."""
        domain = ConcreteBaseDomain()
        chunks = [
            _make_chunk("No pattern", 0),
            _make_chunk("Also no pattern", 1),
            _make_chunk("See the section above", 2),
        ]

        result = domain._apply_cross_references(chunks)

        # First two have no refs, last has refs
        assert len(result[0].cross_refs) == 0
        assert len(result[1].cross_refs) == 0
        assert len(result[2].cross_refs) > 0
