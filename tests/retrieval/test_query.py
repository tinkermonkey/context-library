"""Tests for the query module."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from context_library.core.embedder import Embedder
from context_library.retrieval.query import get_lineage, retrieve
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import Domain, LineageRecord
from context_library.storage.vector_store import ChunkVector


class MockEmbedder(Embedder):
    """Mock embedder for testing."""

    def __init__(self, use_content_based: bool = False):
        """Initialize embedder.

        Args:
            use_content_based: If True, generate different vectors for different texts
                             based on text content hash. Useful for semantic search tests.
        """
        self.use_content_based = use_content_based

    @property
    def model_id(self) -> str:
        return "test-model"

    def _text_to_vector(self, text: str) -> list[float]:
        """Generate a deterministic vector based on text content."""
        if not self.use_content_based:
            # Return a fixed vector for all texts
            return [0.1 * i for i in range(384)]

        # Generate different vectors based on text hash for semantic differentiation
        hash_val = hash(text)
        # Use hash to seed different but deterministic vectors
        base_val = float((hash_val % 100) / 100.0)
        return [base_val + (0.001 * i) for i in range(384)]

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return deterministic embeddings for testing."""
        return [self._text_to_vector(text) for text in texts]

    def embed_query(self, query: str) -> list[float]:
        """Return a deterministic query embedding."""
        return self._text_to_vector(query)


class MockDocumentStore(DocumentStore):
    """Mock document store for testing."""

    def __init__(self):
        self.lineages: dict[str, LineageRecord] = {}

    def add_lineage(self, chunk_hash: str, lineage: LineageRecord) -> None:
        """Add a lineage record for testing."""
        self.lineages[chunk_hash] = lineage

    def get_lineage(self, chunk_hash: str) -> LineageRecord | None:
        """Return a lineage record or None."""
        return self.lineages.get(chunk_hash)


@pytest.fixture
def mock_embedder() -> MockEmbedder:
    """Provide a mock embedder."""
    return MockEmbedder()


@pytest.fixture
def mock_document_store() -> MockDocumentStore:
    """Provide a mock document store."""
    return MockDocumentStore()


@pytest.fixture
def temp_lancedb() -> Path:
    """Create a temporary LanceDB directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_retrieve_returns_correct_fields(
    mock_embedder: MockEmbedder,
    mock_document_store: MockDocumentStore,
    temp_lancedb: Path,
) -> None:
    """Test that retrieve returns results with required fields."""
    import lancedb

    # Create a LanceDB database and table
    db = lancedb.connect(str(temp_lancedb))

    # Create test data
    test_chunks = [
        ChunkVector(
            chunk_hash="hash1",
            content="This is the first test chunk about machine learning",
            vector=[0.1 * i for i in range(384)],
            domain="notes",
            source_id="source1",
            source_version=1,
            created_at="2025-01-01T12:00:00Z",
        ),
        ChunkVector(
            chunk_hash="hash2",
            content="This is the second test chunk about neural networks",
            vector=[0.2 * i for i in range(384)],
            domain="notes",
            source_id="source2",
            source_version=1,
            created_at="2025-01-01T12:00:00Z",
        ),
    ]

    # Create the table
    db.create_table("chunk_vectors", data=test_chunks, mode="overwrite")

    # Perform retrieval
    results = retrieve(
        query="machine learning",
        embedder=mock_embedder,
        lance_db_path=temp_lancedb,
        document_store=mock_document_store,
        top_k=10,
    )

    # Verify results have correct fields
    assert len(results) > 0
    for result in results:
        assert "chunk_text" in result
        assert "chunk_hash" in result
        assert "source_id" in result
        assert "score" in result


def test_retrieve_returns_correct_number_of_results(
    mock_embedder: MockEmbedder,
    mock_document_store: MockDocumentStore,
    temp_lancedb: Path,
) -> None:
    """Test that retrieve returns at most top_k results."""
    import lancedb

    db = lancedb.connect(str(temp_lancedb))

    # Create 15 test chunks
    test_chunks = [
        ChunkVector(
            chunk_hash=f"hash{i}",
            content=f"Test chunk {i} with content",
            vector=[0.1 * i for i in range(384)],
            domain="notes",
            source_id=f"source{i}",
            source_version=1,
            created_at="2025-01-01T12:00:00Z",
        )
        for i in range(15)
    ]

    db.create_table("chunk_vectors", data=test_chunks, mode="overwrite")

    # Test with top_k=10
    results = retrieve(
        query="test",
        embedder=mock_embedder,
        lance_db_path=temp_lancedb,
        document_store=mock_document_store,
        top_k=10,
    )

    assert len(results) == 10

    # Test with top_k=5
    results = retrieve(
        query="test",
        embedder=mock_embedder,
        lance_db_path=temp_lancedb,
        document_store=mock_document_store,
        top_k=5,
    )

    assert len(results) == 5


def test_retrieve_returns_fewer_results_when_fewer_chunks_exist(
    mock_embedder: MockEmbedder,
    mock_document_store: MockDocumentStore,
    temp_lancedb: Path,
) -> None:
    """Test that retrieve returns fewer than top_k results if fewer chunks exist."""
    import lancedb

    db = lancedb.connect(str(temp_lancedb))

    # Create only 3 test chunks
    test_chunks = [
        ChunkVector(
            chunk_hash=f"hash{i}",
            content=f"Test chunk {i}",
            vector=[0.1 * i for i in range(384)],
            domain="notes",
            source_id=f"source{i}",
            source_version=1,
            created_at="2025-01-01T12:00:00Z",
        )
        for i in range(3)
    ]

    db.create_table("chunk_vectors", data=test_chunks, mode="overwrite")

    # Request top_k=10 but only 3 chunks exist
    results = retrieve(
        query="test",
        embedder=mock_embedder,
        lance_db_path=temp_lancedb,
        document_store=mock_document_store,
        top_k=10,
    )

    assert len(results) == 3


def test_retrieve_orders_by_descending_score(
    mock_embedder: MockEmbedder,
    mock_document_store: MockDocumentStore,
    temp_lancedb: Path,
) -> None:
    """Test that retrieve results are ordered by descending relevance score."""
    import lancedb

    db = lancedb.connect(str(temp_lancedb))

    # Create test chunks with varying content
    test_chunks = [
        ChunkVector(
            chunk_hash="hash1",
            content="machine learning deep learning neural networks",
            vector=[0.1 * i for i in range(384)],
            domain="notes",
            source_id="source1",
            source_version=1,
            created_at="2025-01-01T12:00:00Z",
        ),
        ChunkVector(
            chunk_hash="hash2",
            content="unrelated content about cooking recipes",
            vector=[0.2 * i for i in range(384)],
            domain="notes",
            source_id="source2",
            source_version=1,
            created_at="2025-01-01T12:00:00Z",
        ),
        ChunkVector(
            chunk_hash="hash3",
            content="machine learning algorithm optimization",
            vector=[0.3 * i for i in range(384)],
            domain="notes",
            source_id="source3",
            source_version=1,
            created_at="2025-01-01T12:00:00Z",
        ),
    ]

    db.create_table("chunk_vectors", data=test_chunks, mode="overwrite")

    results = retrieve(
        query="machine learning",
        embedder=mock_embedder,
        lance_db_path=temp_lancedb,
        document_store=mock_document_store,
        top_k=10,
    )

    # Verify results are ordered by score (descending)
    scores = [result["score"] for result in results]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_maps_fields_correctly(
    mock_embedder: MockEmbedder,
    mock_document_store: MockDocumentStore,
    temp_lancedb: Path,
) -> None:
    """Test that retrieve correctly maps ChunkVector fields to output format."""
    import lancedb

    db = lancedb.connect(str(temp_lancedb))

    test_chunks = [
        ChunkVector(
            chunk_hash="test-hash-123",
            content="Original chunk content text",
            vector=[0.1 * i for i in range(384)],
            domain="messages",
            source_id="test-source-456",
            source_version=2,
            created_at="2025-01-01T12:00:00Z",
        ),
    ]

    db.create_table("chunk_vectors", data=test_chunks, mode="overwrite")

    results = retrieve(
        query="test",
        embedder=mock_embedder,
        lance_db_path=temp_lancedb,
        document_store=mock_document_store,
        top_k=10,
    )

    assert len(results) == 1
    result = results[0]

    # Verify field mapping
    assert result["chunk_text"] == "Original chunk content text"
    assert result["chunk_hash"] == "test-hash-123"
    assert result["source_id"] == "test-source-456"
    assert isinstance(result["score"], float)


def test_get_lineage_returns_correct_record(
    mock_document_store: MockDocumentStore,
) -> None:
    """Test that get_lineage returns the correct LineageRecord."""
    lineage = LineageRecord(
        adapter_id="gmail_adapter",
        source_id="user@example.com",
        source_version=1,
        fetch_timestamp=datetime(2025, 1, 1, 12, 0, 0),
        normalizer_version="1.0",
        domain=Domain.MESSAGES,
        chunk_hash="test-hash",
        chunk_index=0,
    )

    mock_document_store.add_lineage("test-hash", lineage)

    result = get_lineage("test-hash", mock_document_store)

    assert result is not None
    assert result.chunk_hash == "test-hash"
    assert result.source_id == "user@example.com"
    assert result.adapter_id == "gmail_adapter"
    assert result.domain == Domain.MESSAGES


def test_get_lineage_returns_none_for_unknown_chunk(
    mock_document_store: MockDocumentStore,
) -> None:
    """Test that get_lineage returns None for unknown chunk hash."""
    result = get_lineage("unknown-hash", mock_document_store)

    assert result is None


def test_get_lineage_with_parent_chunk_hash(
    mock_document_store: MockDocumentStore,
) -> None:
    """Test that get_lineage correctly retrieves lineage with parent chunk reference."""
    lineage = LineageRecord(
        adapter_id="obsidian_adapter",
        source_id="notes.md",
        source_version=2,
        fetch_timestamp=datetime(2025, 1, 2, 12, 0, 0),
        normalizer_version="1.0",
        domain=Domain.NOTES,
        chunk_hash="child-hash",
        chunk_index=1,
        parent_chunk_hash="parent-hash",
    )

    mock_document_store.add_lineage("child-hash", lineage)

    result = get_lineage("child-hash", mock_document_store)

    assert result is not None
    assert result.parent_chunk_hash == "parent-hash"
    assert result.chunk_index == 1


def test_retrieve_semantic_search_finds_most_relevant(
    temp_lancedb: Path,
    mock_document_store: MockDocumentStore,
) -> None:
    """Test that retrieve finds the most semantically relevant chunk for a query.

    This test uses content-based embeddings to enable true semantic differentiation
    between chunks, verifying that querying "machine learning" returns the
    ML-related chunk as the top result.
    """
    import lancedb

    db = lancedb.connect(str(temp_lancedb))

    # Create embedder that generates different vectors for different texts
    semantic_embedder = MockEmbedder(use_content_based=True)

    # Create test chunks with different content
    test_chunks = [
        ChunkVector(
            chunk_hash="ml-chunk",
            content="machine learning algorithms and neural networks",
            vector=semantic_embedder.embed(["machine learning algorithms and neural networks"])[0],
            domain="notes",
            source_id="ml-source",
            source_version=1,
            created_at="2025-01-01T12:00:00Z",
        ),
        ChunkVector(
            chunk_hash="cooking-chunk",
            content="recipes and cooking techniques for beginners",
            vector=semantic_embedder.embed(["recipes and cooking techniques for beginners"])[0],
            domain="notes",
            source_id="cooking-source",
            source_version=1,
            created_at="2025-01-01T12:00:00Z",
        ),
        ChunkVector(
            chunk_hash="music-chunk",
            content="music theory and composition fundamentals",
            vector=semantic_embedder.embed(["music theory and composition fundamentals"])[0],
            domain="notes",
            source_id="music-source",
            source_version=1,
            created_at="2025-01-01T12:00:00Z",
        ),
    ]

    db.create_table("chunk_vectors", data=test_chunks, mode="overwrite")

    # Query for "machine learning"
    results = retrieve(
        query="machine learning",
        embedder=semantic_embedder,
        lance_db_path=temp_lancedb,
        document_store=mock_document_store,
        top_k=10,
    )

    # Verify the ML chunk is returned as the top result
    assert len(results) >= 1
    assert results[0]["chunk_hash"] == "ml-chunk"
    assert results[0]["source_id"] == "ml-source"
    # Verify ordering by score (highest first)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
