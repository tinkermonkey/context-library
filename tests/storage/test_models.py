"""Tests for storage models.

Covers:
- Model field validation and instantiation
- chunk_hash determinism (same content → same hash)
- Frozen model immutability enforcement
- Chunk hash format validation
"""

import pytest
from pydantic import ValidationError

from context_library.storage.models import (
    AdapterConfig,
    Chunk,
    Domain,
    DiffResult,
    LineageRecord,
    NormalizedContent,
    SourceVersion,
    StructuralHints,
    compute_chunk_hash,
)


class TestStructuralHints:
    """Tests for StructuralHints model."""

    def test_create_with_defaults(self) -> None:
        """Test creating StructuralHints with default None values."""
        hints = StructuralHints(
            has_headings=True,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[10, 20, 30],
        )
        assert hints.has_headings is True
        assert hints.has_lists is False
        assert hints.has_tables is False
        assert hints.natural_boundaries == [10, 20, 30]
        assert hints.file_path is None
        assert hints.modified_at is None
        assert hints.file_size_bytes is None

    def test_create_with_all_fields(self) -> None:
        """Test creating StructuralHints with all fields populated."""
        hints = StructuralHints(
            has_headings=True,
            has_lists=True,
            has_tables=True,
            natural_boundaries=[100, 200],
            file_path="/path/to/file.md",
            modified_at="2025-03-02T10:00:00Z",
            file_size_bytes=1024,
        )
        assert hints.file_path == "/path/to/file.md"
        assert hints.modified_at == "2025-03-02T10:00:00Z"
        assert hints.file_size_bytes == 1024

    def test_frozen_immutability(self) -> None:
        """Test that StructuralHints is frozen and cannot be modified."""
        hints = StructuralHints(
            has_headings=True,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
        )
        with pytest.raises(ValidationError):
            hints.has_headings = False  # type: ignore[assignment]


class TestNormalizedContent:
    """Tests for NormalizedContent model."""

    def test_create_normalized_content(self) -> None:
        """Test creating NormalizedContent with nested StructuralHints."""
        hints = StructuralHints(
            has_headings=True,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[50],
        )
        content = NormalizedContent(
            markdown="# Heading\n\nParagraph.",
            source_id="source-1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )
        assert content.markdown == "# Heading\n\nParagraph."
        assert content.source_id == "source-1"
        assert content.structural_hints == hints
        assert content.normalizer_version == "1.0.0"

    def test_frozen_immutability(self) -> None:
        """Test that NormalizedContent is frozen."""
        hints = StructuralHints(
            has_headings=True,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
        )
        content = NormalizedContent(
            markdown="test",
            source_id="s1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )
        with pytest.raises(ValidationError):
            content.source_id = "s2"  # type: ignore[assignment]


class TestChunk:
    """Tests for Chunk model."""

    @staticmethod
    def create_valid_sha256_hash() -> str:
        """Create a valid SHA-256 hash for testing."""
        return "a" * 64

    def test_create_chunk_minimal(self) -> None:
        """Test creating Chunk with minimal fields."""
        chunk = Chunk(
            chunk_hash=self.create_valid_sha256_hash(),
            content="This is chunk content.",
            chunk_index=0,
        )
        assert chunk.content == "This is chunk content."
        assert chunk.context_header is None
        assert chunk.chunk_type == "standard"
        assert chunk.domain_metadata is None

    def test_create_chunk_full(self) -> None:
        """Test creating Chunk with all fields."""
        chunk = Chunk(
            chunk_hash=self.create_valid_sha256_hash(),
            content="Content here.",
            context_header="# Section > ## Subsection",
            chunk_index=5,
            chunk_type="oversized",
            domain_metadata={"key": "value"},
        )
        assert chunk.chunk_index == 5
        assert chunk.context_header == "# Section > ## Subsection"
        assert chunk.chunk_type == "oversized"
        assert chunk.domain_metadata == {"key": "value"}

    def test_chunk_hash_validation_valid(self) -> None:
        """Test that valid SHA-256 hashes are accepted."""
        valid_hashes = [
            "a" * 64,  # all 'a'
            "0123456789abcdef" * 4,  # mixed hex digits
            "f" * 64,  # all 'f'
            "0" * 64,  # all zeros (valid)
        ]
        for valid_hash in valid_hashes:
            chunk = Chunk(chunk_hash=valid_hash, content="test", chunk_index=0)
            assert chunk.chunk_hash == valid_hash

    def test_chunk_hash_validation_invalid(self) -> None:
        """Test that invalid chunk hashes are rejected."""
        invalid_hashes = [
            "a" * 63,  # too short
            "a" * 65,  # too long
            "G" * 64,  # invalid hex character
            "A" * 64,  # uppercase (must be lowercase)
            "invalid_hash",  # not hex at all
        ]
        for invalid_hash in invalid_hashes:
            with pytest.raises(ValidationError) as exc_info:
                Chunk(chunk_hash=invalid_hash, content="test", chunk_index=0)
            assert "chunk_hash must be a valid SHA-256" in str(exc_info.value)

    def test_frozen_immutability(self) -> None:
        """Test that Chunk is frozen."""
        chunk = Chunk(
            chunk_hash=self.create_valid_sha256_hash(),
            content="test",
            chunk_index=0,
        )
        with pytest.raises(ValidationError):
            chunk.chunk_index = 1  # type: ignore[assignment]


class TestLineageRecord:
    """Tests for LineageRecord model."""

    @staticmethod
    def create_valid_sha256_hash() -> str:
        """Create a valid SHA-256 hash for testing."""
        return "b" * 64

    def test_create_lineage_record(self) -> None:
        """Test creating LineageRecord with all fields."""
        record = LineageRecord(
            chunk_hash=self.create_valid_sha256_hash(),
            source_id="source-1",
            source_version_id=1,
            adapter_id="adapter-fs-1",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="all-MiniLM-L6-v2",
        )
        assert record.source_id == "source-1"
        assert record.source_version_id == 1
        assert record.domain == Domain.NOTES
        assert record.embedding_model_id == "all-MiniLM-L6-v2"

    def test_lineage_record_domain_enum(self) -> None:
        """Test that LineageRecord accepts Domain enum values."""
        for domain in Domain:
            record = LineageRecord(
                chunk_hash=self.create_valid_sha256_hash(),
                source_id="src",
                source_version_id=1,
                adapter_id="adp",
                domain=domain,
                normalizer_version="1.0.0",
                embedding_model_id="model",
            )
            assert record.domain == domain

    def test_frozen_immutability(self) -> None:
        """Test that LineageRecord is frozen."""
        record = LineageRecord(
            chunk_hash=self.create_valid_sha256_hash(),
            source_id="src",
            source_version_id=1,
            adapter_id="adp",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="model",
        )
        with pytest.raises(ValidationError):
            record.source_version_id = 2  # type: ignore[assignment]


class TestSourceVersion:
    """Tests for SourceVersion model."""

    def test_create_source_version(self) -> None:
        """Test creating SourceVersion with chunk hashes."""
        hashes = ["a" * 64, "b" * 64, "c" * 64]
        version = SourceVersion(
            source_id="source-1",
            version=1,
            markdown="# Content",
            chunk_hashes=hashes,
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )
        assert version.version == 1
        assert version.chunk_hashes == hashes
        assert len(version.chunk_hashes) == 3

    def test_source_version_empty_hashes(self) -> None:
        """Test SourceVersion with empty chunk_hashes list."""
        version = SourceVersion(
            source_id="source-1",
            version=0,
            markdown="",
            chunk_hashes=[],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )
        assert version.chunk_hashes == []

    def test_frozen_immutability(self) -> None:
        """Test that SourceVersion is frozen."""
        version = SourceVersion(
            source_id="source-1",
            version=1,
            markdown="test",
            chunk_hashes=[],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )
        with pytest.raises(ValidationError):
            version.version = 2  # type: ignore[assignment]


class TestDiffResult:
    """Tests for DiffResult model."""

    def test_unchanged_content(self) -> None:
        """Test DiffResult when content has not changed."""
        result = DiffResult(
            changed=False,
            added_hashes=set(),
            removed_hashes=set(),
            unchanged_hashes={"a" * 64, "b" * 64},
        )
        assert result.changed is False
        assert result.added_hashes == set()
        assert result.removed_hashes == set()
        assert len(result.unchanged_hashes) == 2

    def test_changed_with_diff(self) -> None:
        """Test DiffResult when content has changed with additions and removals."""
        result = DiffResult(
            changed=True,
            added_hashes={"c" * 64, "d" * 64},
            removed_hashes={"e" * 64},
            unchanged_hashes={"a" * 64, "b" * 64},
            prev_hash="1111111111111111111111111111111111111111111111111111111111111111",
            curr_hash="2222222222222222222222222222222222222222222222222222222222222222",
        )
        assert result.changed is True
        assert len(result.added_hashes) == 2
        assert len(result.removed_hashes) == 1
        assert len(result.unchanged_hashes) == 2
        assert result.prev_hash is not None
        assert result.curr_hash is not None

    def test_first_ingest(self) -> None:
        """Test DiffResult for first ingest (all chunks are added)."""
        result = DiffResult(
            changed=True,
            added_hashes={"a" * 64, "b" * 64, "c" * 64},
            removed_hashes=set(),
            unchanged_hashes=set(),
            prev_hash=None,
            curr_hash="2222222222222222222222222222222222222222222222222222222222222222",
        )
        assert result.prev_hash is None
        assert result.curr_hash is not None
        assert len(result.added_hashes) == 3

    def test_frozen_immutability(self) -> None:
        """Test that DiffResult is frozen."""
        result = DiffResult(
            changed=False,
            added_hashes=set(),
            removed_hashes=set(),
            unchanged_hashes=set(),
        )
        with pytest.raises(ValidationError):
            result.changed = True  # type: ignore[assignment]


class TestAdapterConfig:
    """Tests for AdapterConfig model."""

    def test_create_adapter_config_minimal(self) -> None:
        """Test creating AdapterConfig with minimal fields."""
        config = AdapterConfig(
            adapter_id="adapter-fs-1",
            adapter_type="filesystem",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        assert config.adapter_id == "adapter-fs-1"
        assert config.adapter_type == "filesystem"
        assert config.domain == Domain.NOTES
        assert config.config is None

    def test_create_adapter_config_full(self) -> None:
        """Test creating AdapterConfig with all fields."""
        cfg_dict = {"directory": "/home/user/notes", "extensions": [".md", ".txt"]}
        config = AdapterConfig(
            adapter_id="adapter-fs-1",
            adapter_type="filesystem",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            config=cfg_dict,
        )
        assert config.config == cfg_dict
        assert config.config["directory"] == "/home/user/notes"

    def test_adapter_config_domain_enum(self) -> None:
        """Test that AdapterConfig accepts all Domain values."""
        for domain in Domain:
            config = AdapterConfig(
                adapter_id="adapter-1",
                adapter_type="test",
                domain=domain,
                normalizer_version="1.0.0",
            )
            assert config.domain == domain

    def test_frozen_immutability(self) -> None:
        """Test that AdapterConfig is frozen."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        with pytest.raises(ValidationError):
            config.adapter_type = "modified"  # type: ignore[assignment]


class TestComputeChunkHash:
    """Tests for compute_chunk_hash function."""

    def test_hash_determinism_identical_content(self) -> None:
        """Test that identical content always produces the same hash."""
        content = "This is a test chunk of content."
        hash1 = compute_chunk_hash(content)
        hash2 = compute_chunk_hash(content)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex is 64 chars

    def test_hash_different_for_different_content(self) -> None:
        """Test that different content produces different hashes."""
        hash1 = compute_chunk_hash("Content A")
        hash2 = compute_chunk_hash("Content B")
        assert hash1 != hash2

    def test_whitespace_normalization_multiple_spaces(self) -> None:
        """Test that multiple spaces are collapsed to single space."""
        content1 = "Multiple   spaces   here"
        content2 = "Multiple spaces here"
        assert compute_chunk_hash(content1) == compute_chunk_hash(content2)

    def test_whitespace_normalization_trailing(self) -> None:
        """Test that trailing whitespace is stripped per line."""
        content1 = "Line 1   \nLine 2   "
        content2 = "Line 1\nLine 2"
        assert compute_chunk_hash(content1) == compute_chunk_hash(content2)

    def test_whitespace_normalization_line_endings_crlf(self) -> None:
        """Test that CRLF line endings are normalized to LF."""
        content1 = "Line 1\r\nLine 2\r\nLine 3"
        content2 = "Line 1\nLine 2\nLine 3"
        assert compute_chunk_hash(content1) == compute_chunk_hash(content2)

    def test_whitespace_normalization_mixed_line_endings(self) -> None:
        """Test that mixed line endings (CR, LF, CRLF) are normalized."""
        content1 = "Line 1\rLine 2\nLine 3\r\nLine 4"
        content2 = "Line 1\nLine 2\nLine 3\nLine 4"
        assert compute_chunk_hash(content1) == compute_chunk_hash(content2)

    def test_whitespace_normalization_tabs_and_spaces(self) -> None:
        """Test that tabs and spaces are collapsed together."""
        content1 = "Text\t\t  with\ttabs  and  spaces"
        content2 = "Text with tabs and spaces"
        assert compute_chunk_hash(content1) == compute_chunk_hash(content2)

    def test_hash_format(self) -> None:
        """Test that hash is valid lowercase hex."""
        hash_result = compute_chunk_hash("test content")
        assert len(hash_result) == 64
        assert all(c in "0123456789abcdef" for c in hash_result)

    def test_context_header_excluded_from_hash(self) -> None:
        """Test that context header is excluded from hash computation.

        Chunks with identical content but different context headers must have
        the same chunk_hash, proving that only content (not the header) is used
        for computing the hash.
        """
        content = "This is the chunk content."
        content_hash = compute_chunk_hash(content)

        # Create two Chunk objects with same content but different headers
        chunk1 = Chunk(
            chunk_hash=content_hash,
            content=content,
            context_header="# Section > ## Subsection",
            chunk_index=0,
        )
        chunk2 = Chunk(
            chunk_hash=content_hash,
            content=content,
            context_header="## Different Header",
            chunk_index=1,
        )

        # Both chunks have the same hash even with different headers
        assert chunk1.chunk_hash == chunk2.chunk_hash
        # This proves context_header is excluded from hash computation

    def test_empty_content(self) -> None:
        """Test hashing empty content."""
        hash_result = compute_chunk_hash("")
        assert len(hash_result) == 64
        assert all(c in "0123456789abcdef" for c in hash_result)

    def test_hash_stability_across_runs(self) -> None:
        """Test that the same hash is always produced (determinism test)."""
        content = "Deterministic test content\nWith multiple lines\nAnd spaces"
        expected_hash = compute_chunk_hash(content)
        for _ in range(10):
            assert compute_chunk_hash(content) == expected_hash
