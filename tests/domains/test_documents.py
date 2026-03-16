"""Tests for the documents domain."""

import pytest

from context_library.domains.documents import DocumentsDomain
from context_library.domains.registry import Domain, get_domain_chunker
from context_library.storage.models import (
    Chunk,
    ChunkType,
    DocumentMetadata,
    NormalizedContent,
    StructuralHints,
    compute_chunk_hash,
)


@pytest.fixture
def documents_domain():
    """Create a DocumentsDomain instance with default limits."""
    return DocumentsDomain(hard_limit=1024)


@pytest.fixture
def sample_document_metadata():
    """Create sample DocumentMetadata for testing."""
    return DocumentMetadata(
        document_id="doc-001",
        title="Technical Architecture Guide",
        document_type="text/markdown",
        source_type="filesystem",
        date_first_observed="2026-03-07T08:00:00Z",
    )


@pytest.fixture
def base_structural_hints():
    """Create base structural hints for testing."""
    return StructuralHints(
        has_headings=False,
        has_lists=False,
        has_tables=False,
        natural_boundaries=[],
    )


class TestDocumentsDomainRegistry:
    """Tests for DocumentsDomain domain registry integration."""

    def test_domain_chunker_registry_returns_documents_domain(self):
        """get_domain_chunker(Domain.DOCUMENTS) returns a DocumentsDomain instance."""
        domain = get_domain_chunker(Domain.DOCUMENTS)

        assert isinstance(domain, DocumentsDomain)
        assert domain.hard_limit == 1024


class TestDocumentsDomainBasics:
    """Basic tests for DocumentsDomain initialization and properties."""

    def test_initialization_with_defaults(self):
        """DocumentsDomain initializes with default hard_limit."""
        domain = DocumentsDomain()

        assert domain.hard_limit == 1024

    def test_initialization_with_custom_hard_limit(self):
        """DocumentsDomain initializes with custom hard_limit."""
        domain = DocumentsDomain(hard_limit=512)

        assert domain.hard_limit == 512

    def test_initialization_rejects_zero_hard_limit(self):
        """DocumentsDomain rejects hard_limit=0."""
        with pytest.raises(ValueError, match="hard_limit must be a positive integer"):
            DocumentsDomain(hard_limit=0)

    def test_initialization_rejects_negative_hard_limit(self):
        """DocumentsDomain rejects negative hard_limit."""
        with pytest.raises(ValueError, match="hard_limit must be a positive integer"):
            DocumentsDomain(hard_limit=-1)

    def test_chunk_returns_list_of_chunks(
        self, documents_domain, sample_document_metadata, base_structural_hints
    ):
        """chunk() returns a list of Chunk instances."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_document_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="This is a sample document with important information.",
            source_id="doc_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        result = documents_domain.chunk(content)

        assert isinstance(result, list)
        assert all(isinstance(chunk, Chunk) for chunk in result)
        assert len(result) >= 1

    def test_chunk_raises_without_extra_metadata(
        self, documents_domain, base_structural_hints
    ):
        """chunk() raises ValueError if extra_metadata is missing."""
        content = NormalizedContent(
            markdown="Document data",
            source_id="doc_1",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        with pytest.raises(ValueError, match="extra_metadata"):
            documents_domain.chunk(content)


class TestSingleDocumentChunk:
    """Tests for chunking single documents."""

    def test_single_document_creates_one_chunk(
        self, documents_domain, sample_document_metadata
    ):
        """A single document creates exactly one chunk."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_document_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="This is the document content.",
            source_id="doc_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = documents_domain.chunk(content)

        assert len(chunks) == 1
        assert chunks[0].content == "This is the document content."
        assert chunks[0].chunk_index == 0

    def test_document_with_empty_markdown_returns_empty_list(
        self, documents_domain, sample_document_metadata
    ):
        """A document with empty markdown returns an empty list."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_document_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="",
            source_id="doc_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = documents_domain.chunk(content)

        assert len(chunks) == 0

    def test_document_with_whitespace_only_returns_empty_list(
        self, documents_domain, sample_document_metadata
    ):
        """A document with whitespace-only markdown returns an empty list."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_document_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="   \n\t\n   ",
            source_id="doc_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = documents_domain.chunk(content)

        assert len(chunks) == 0

    def test_chunk_has_correct_context_header_format(
        self, documents_domain, sample_document_metadata
    ):
        """chunk() sets context_header to '{title} — {document_type}' format."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_document_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Document content.",
            source_id="doc_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = documents_domain.chunk(content)

        assert chunks[0].context_header == "Technical Architecture Guide — text/markdown"

    def test_chunk_has_domain_metadata(
        self, documents_domain, sample_document_metadata
    ):
        """chunk() populates domain_metadata with all DocumentMetadata fields."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_document_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Document content.",
            source_id="doc_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = documents_domain.chunk(content)

        assert chunks[0].domain_metadata is not None
        assert chunks[0].domain_metadata["document_id"] == "doc-001"
        assert chunks[0].domain_metadata["title"] == "Technical Architecture Guide"
        assert chunks[0].domain_metadata["document_type"] == "text/markdown"
        assert chunks[0].domain_metadata["source_type"] == "filesystem"
        assert "date_first_observed" in chunks[0].domain_metadata

    def test_chunk_type_is_standard(self, documents_domain, sample_document_metadata):
        """All chunks have chunk_type = ChunkType.STANDARD."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_document_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Document data.",
            source_id="doc_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = documents_domain.chunk(content)

        assert all(chunk.chunk_type == ChunkType.STANDARD for chunk in chunks)


class TestContextHeaderFormat:
    """Tests for context header formatting across different document types."""

    @pytest.mark.parametrize(
        "title,document_type",
        [
            ("User Manual", "text/markdown"),
            ("Financial Report Q1 2026", "application/pdf"),
            ("Meeting Notes", "text/plain"),
            ("Architecture Specification", "application/json"),
            ("Design System", "text/html"),
        ],
    )
    def test_context_header_format_for_various_documents(
        self, documents_domain, title, document_type
    ):
        """Context header is correctly formatted for various document types."""
        meta = DocumentMetadata(
            document_id="doc-001",
            title=title,
            document_type=document_type,
            source_type="filesystem",
            date_first_observed="2026-03-07T08:00:00Z",
        )

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=meta.model_dump(),
        )

        content = NormalizedContent(
            markdown="Document data.",
            source_id="doc_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = documents_domain.chunk(content)

        assert chunks[0].context_header == f"{title} — {document_type}"


class TestLongDocumentSplitting:
    """Tests for splitting oversized documents."""

    def test_short_document_not_split(self, documents_domain, sample_document_metadata):
        """Documents under hard_limit are not split."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_document_metadata.model_dump(),
        )

        # Create content with ~500 tokens (under 1024)
        short_content = " ".join(["word"] * 500)

        content = NormalizedContent(
            markdown=short_content,
            source_id="doc_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = documents_domain.chunk(content)

        assert len(chunks) == 1

    def test_long_document_split_at_sentence_boundaries(
        self, sample_document_metadata
    ):
        """Documents exceeding hard_limit are split at sentence boundaries."""
        domain = DocumentsDomain(hard_limit=30)  # Small limit for testing

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_document_metadata.model_dump(),
        )

        # Create content with multiple sentences totaling ~70 tokens
        markdown = (
            "First sentence with some content and additional details here. "
            "Second sentence also with some content and more information. "
            "Third sentence continues the description with even more details. "
            "Fourth sentence adds more information to the document. "
            "Fifth sentence wraps up the document."
        )

        content = NormalizedContent(
            markdown=markdown,
            source_id="doc_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = domain.chunk(content)

        assert len(chunks) > 1
        # All chunks should have content and be under hard_limit
        for chunk in chunks:
            assert len(chunk.content.split()) <= 30

    def test_long_document_chunks_have_sequential_indices(
        self, sample_document_metadata
    ):
        """Split documents have sequential chunk_index values."""
        domain = DocumentsDomain(hard_limit=30)

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_document_metadata.model_dump(),
        )

        markdown = "word " * 100  # 100 words total

        content = NormalizedContent(
            markdown=markdown,
            source_id="doc_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = domain.chunk(content)

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i


class TestChunkHash:
    """Tests for chunk hash computation."""

    def test_chunk_hash_computed_from_content_only(
        self, documents_domain, sample_document_metadata
    ):
        """chunk_hash is computed from content, not context_header."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_document_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="The document data description.",
            source_id="doc_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = documents_domain.chunk(content)

        # Compute expected hash from content only
        expected_hash = compute_chunk_hash("The document data description.")

        assert chunks[0].chunk_hash == expected_hash

    def test_chunk_hash_determinism_across_calls(
        self, documents_domain, sample_document_metadata
    ):
        """Chunk hashes are deterministic across multiple calls with same input."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_document_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="The document data description.",
            source_id="doc_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks1 = documents_domain.chunk(content)
        chunks2 = documents_domain.chunk(content)

        assert chunks1[0].chunk_hash == chunks2[0].chunk_hash

    def test_chunk_hash_same_regardless_of_title(self, documents_domain):
        """Changing title (context_header) does not change chunk_hash."""
        meta1 = DocumentMetadata(
            document_id="doc-001",
            title="First Title",
            document_type="text/markdown",
            source_type="filesystem",
            date_first_observed="2026-03-07T08:00:00Z",
        )

        meta2 = DocumentMetadata(
            document_id="doc-001",
            title="Different Title",  # Different title
            document_type="text/markdown",
            source_type="filesystem",
            date_first_observed="2026-03-07T08:00:00Z",
        )

        hints1 = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=meta1.model_dump(),
        )

        hints2 = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=meta2.model_dump(),
        )

        content1 = NormalizedContent(
            markdown="The document content.",
            source_id="doc_1",
            structural_hints=hints1,
            normalizer_version="1.0.0",
        )

        content2 = NormalizedContent(
            markdown="The document content.",
            source_id="doc_1",
            structural_hints=hints2,
            normalizer_version="1.0.0",
        )

        chunks1 = documents_domain.chunk(content1)
        chunks2 = documents_domain.chunk(content2)

        # Same content => same hash, even with different titles
        assert chunks1[0].chunk_hash == chunks2[0].chunk_hash


class TestDocumentMetadataValidation:
    """Tests for DocumentMetadata validation."""

    def test_chunk_raises_on_invalid_document_id(self, documents_domain):
        """chunk() raises ValueError when document_id is empty."""
        with pytest.raises(ValueError, match="document_id must be a non-empty string"):
            DocumentMetadata(
                document_id="",  # Invalid: empty
                title="Some Title",
                document_type="text/markdown",
                source_type="filesystem",
                date_first_observed="2026-03-07T08:00:00Z",
            )

    def test_chunk_raises_on_invalid_title(self, documents_domain):
        """chunk() raises ValueError when title is empty."""
        with pytest.raises(ValueError, match="title must be a non-empty string"):
            DocumentMetadata(
                document_id="doc-001",
                title="",  # Invalid: empty
                document_type="text/markdown",
                source_type="filesystem",
                date_first_observed="2026-03-07T08:00:00Z",
            )

    def test_chunk_raises_on_invalid_document_type(self, documents_domain):
        """chunk() raises ValueError when document_type is empty."""
        with pytest.raises(ValueError, match="document_type must be a non-empty string"):
            DocumentMetadata(
                document_id="doc-001",
                title="Some Title",
                document_type="",  # Invalid: empty
                source_type="filesystem",
                date_first_observed="2026-03-07T08:00:00Z",
            )

    def test_chunk_raises_on_invalid_source_type(self, documents_domain):
        """chunk() raises ValueError when source_type is empty."""
        with pytest.raises(ValueError, match="source_type must be a non-empty string"):
            DocumentMetadata(
                document_id="doc-001",
                title="Some Title",
                document_type="text/markdown",
                source_type="",  # Invalid: empty
                date_first_observed="2026-03-07T08:00:00Z",
            )

    def test_chunk_raises_on_invalid_date_first_observed(self, documents_domain):
        """chunk() raises ValueError when date_first_observed is not valid ISO 8601."""
        with pytest.raises(ValueError, match="ISO 8601"):
            DocumentMetadata(
                document_id="doc-001",
                title="Some Title",
                document_type="text/markdown",
                source_type="filesystem",
                date_first_observed="invalid-date",  # Invalid format
            )

    def test_chunk_raises_on_invalid_created_at(self, documents_domain):
        """chunk() raises ValueError when created_at is not valid ISO 8601."""
        with pytest.raises(ValueError, match="ISO 8601"):
            DocumentMetadata(
                document_id="doc-001",
                title="Some Title",
                document_type="text/markdown",
                source_type="filesystem",
                date_first_observed="2026-03-07T08:00:00Z",
                created_at="not-a-date",  # Invalid format
            )

    def test_chunk_raises_on_invalid_file_size_bytes(self, documents_domain):
        """chunk() raises ValueError when file_size_bytes is negative."""
        with pytest.raises(ValueError, match="file_size_bytes must be non-negative"):
            DocumentMetadata(
                document_id="doc-001",
                title="Some Title",
                document_type="text/markdown",
                source_type="filesystem",
                date_first_observed="2026-03-07T08:00:00Z",
                file_size_bytes=-100,  # Invalid: negative
            )

    def test_chunk_raises_on_missing_required_field(self, documents_domain, base_structural_hints):
        """chunk() raises ValueError when required DocumentMetadata field is missing."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata={
                "document_id": "doc-001",
                "title": "Some Title",
                # Missing 'document_type', 'source_type', 'date_first_observed'
            },
        )

        content = NormalizedContent(
            markdown="Document data.",
            source_id="doc_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        with pytest.raises(ValueError, match="Invalid DocumentMetadata"):
            documents_domain.chunk(content)


class TestDocumentSourceTypeVariations:
    """Tests for different document source types."""

    @pytest.mark.parametrize(
        "source_type",
        ["filesystem", "s3", "google_drive", "dropbox", "apple_music"],
    )
    def test_all_source_types_produce_valid_chunks(
        self, documents_domain, source_type
    ):
        """All document source types produce valid chunks with domain_metadata."""
        meta = DocumentMetadata(
            document_id="doc-001",
            title="Sample Document",
            document_type="text/markdown",
            source_type=source_type,
            date_first_observed="2026-03-07T08:00:00Z",
        )

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=meta.model_dump(),
        )

        content = NormalizedContent(
            markdown="Document content description.",
            source_id="doc_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = documents_domain.chunk(content)

        assert len(chunks) == 1
        assert chunks[0].domain_metadata["source_type"] == source_type


class TestDocumentMetadataFields:
    """Tests for document-specific metadata fields validation and preservation."""

    def test_document_metadata_with_all_optional_fields(self, documents_domain):
        """DocumentMetadata with all optional fields produces valid chunks."""
        meta = DocumentMetadata(
            document_id="doc-comprehensive-001",
            title="Comprehensive Document",
            document_type="application/pdf",
            source_type="filesystem",
            date_first_observed="2026-03-07T08:00:00Z",
            created_at="2026-03-01T10:00:00Z",
            modified_at="2026-03-07T12:00:00Z",
            file_size_bytes=2048576,
            author="Jane Doe",
            tags=("important", "technical", "2026-Q1"),
        )

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=meta.model_dump(),
        )

        content = NormalizedContent(
            markdown="Comprehensive document content.",
            source_id="doc_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = documents_domain.chunk(content)

        assert len(chunks) == 1
        chunk = chunks[0]

        # All fields should be in domain_metadata
        assert chunk.domain_metadata["document_id"] == "doc-comprehensive-001"
        assert chunk.domain_metadata["title"] == "Comprehensive Document"
        assert chunk.domain_metadata["document_type"] == "application/pdf"
        assert chunk.domain_metadata["source_type"] == "filesystem"
        assert chunk.domain_metadata["created_at"] == "2026-03-01T10:00:00Z"
        assert chunk.domain_metadata["modified_at"] == "2026-03-07T12:00:00Z"
        assert chunk.domain_metadata["file_size_bytes"] == 2048576
        assert chunk.domain_metadata["author"] == "Jane Doe"
        assert chunk.domain_metadata["tags"] == ("important", "technical", "2026-Q1")

    def test_document_metadata_with_minimal_fields(self, documents_domain):
        """DocumentMetadata with only required fields produces valid chunks."""
        meta = DocumentMetadata(
            document_id="doc-minimal-001",
            title="Minimal Document",
            document_type="text/plain",
            source_type="filesystem",
            date_first_observed="2026-03-07T08:00:00Z",
        )

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=meta.model_dump(),
        )

        content = NormalizedContent(
            markdown="Minimal document.",
            source_id="doc_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = documents_domain.chunk(content)

        assert len(chunks) == 1
        chunk = chunks[0]

        # Required fields should be present
        assert chunk.domain_metadata["document_id"] == "doc-minimal-001"
        assert chunk.domain_metadata["title"] == "Minimal Document"
        assert chunk.domain_metadata["document_type"] == "text/plain"
        assert chunk.domain_metadata["source_type"] == "filesystem"

    def test_document_metadata_preserves_all_fields_in_domain_metadata(
        self, documents_domain
    ):
        """DocumentsDomain preserves all validated document fields in domain_metadata."""
        meta = DocumentMetadata(
            document_id="doc-002",
            title="Architecture Document",
            document_type="text/markdown",
            source_type="filesystem",
            date_first_observed="2026-03-07T08:00:00Z",
            author="Bob Smith",
            file_size_bytes=65536,
        )

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=meta.model_dump(),
        )

        content = NormalizedContent(
            markdown="Document content here.",
            source_id="doc_001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = documents_domain.chunk(content)

        assert len(chunks) == 1
        chunk = chunks[0]

        # Validated fields should be in domain_metadata
        assert chunk.domain_metadata["document_id"] == "doc-002"
        assert chunk.domain_metadata["title"] == "Architecture Document"
        assert chunk.domain_metadata["document_type"] == "text/markdown"
        assert chunk.domain_metadata["source_type"] == "filesystem"
        assert chunk.domain_metadata["author"] == "Bob Smith"
        assert chunk.domain_metadata["file_size_bytes"] == 65536

    def test_document_metadata_rejects_negative_file_size(self):
        """DocumentMetadata rejects negative file_size_bytes."""
        with pytest.raises(ValueError, match="file_size_bytes must be non-negative"):
            DocumentMetadata(
                document_id="doc-001",
                title="Some Title",
                document_type="text/markdown",
                source_type="filesystem",
                date_first_observed="2026-03-07T08:00:00Z",
                file_size_bytes=-1024,  # Invalid: negative
            )


class TestCrossReferences:
    """Tests for cross-reference detection in chunks."""

    def test_cross_reference_detection_applied_to_chunks(
        self, documents_domain, sample_document_metadata
    ):
        """Cross-reference detection is applied to document chunks."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_document_metadata.model_dump(),
        )

        # Create content that will be split, with cross-referencing content
        markdown = (
            "See section two for more details. "
            "First section describes the basics. "
            "Second section provides advanced concepts. "
            "Third section references the first section. "
            "Fourth section concludes the document."
        )

        content = NormalizedContent(
            markdown=markdown,
            source_id="doc_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = documents_domain.chunk(content)

        # Verify cross_refs field exists (as a tuple)
        for chunk in chunks:
            assert hasattr(chunk, 'cross_refs')
            assert isinstance(chunk.cross_refs, tuple)
