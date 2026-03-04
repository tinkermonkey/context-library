"""Tests for the query module.

Covers:
- Query embedding and vector search
- Lineage lookup and enrichment
- Filtering by domain and source
- Similarity score calculation
- Error handling for missing vector store or empty results
"""

from unittest.mock import MagicMock, patch

import pytest

from context_library.core.embedder import Embedder
from context_library.retrieval.query import RetrievalResult, retrieve
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import AdapterConfig, Chunk, Domain, LineageRecord


@pytest.fixture
def embedder() -> Embedder:
    """Create an Embedder instance for testing."""
    return Embedder()


@pytest.fixture
def document_store() -> DocumentStore:
    """Create an in-memory DocumentStore for testing."""
    return DocumentStore(":memory:")


def _make_hash(char: str) -> str:
    """Create a valid SHA-256 hex hash."""
    return char * 64


def _create_test_chunk(hash_char: str, chunk_index: int = 0) -> Chunk:
    """Create a test chunk with given hash character."""
    return Chunk(
        chunk_hash=_make_hash(hash_char),
        content=f"Test chunk {hash_char}",
        context_header=f"Context for {hash_char}",
        chunk_index=chunk_index,
        chunk_type="standard",
        domain_metadata=None,
    )


def _create_test_lineage(hash_char: str, source_id: str = "source_1") -> LineageRecord:
    """Create a test lineage record."""
    return LineageRecord(
        chunk_hash=_make_hash(hash_char),
        source_id=source_id,
        source_version_id=1,
        adapter_id="test-adapter",
        domain=Domain.NOTES,
        normalizer_version="1.0.0",
        embedding_model_id="all-MiniLM-L6-v2",
    )


class TestRetrievalResult:
    """Tests for the RetrievalResult class."""

    def test_initialization(self) -> None:
        """Test RetrievalResult initialization."""
        chunk = _create_test_chunk("a")
        lineage = _create_test_lineage("a")
        score = 0.85

        result = RetrievalResult(chunk=chunk, lineage=lineage, similarity_score=score)

        assert result.chunk == chunk
        assert result.lineage == lineage
        assert result.similarity_score == 0.85

    def test_to_dict(self) -> None:
        """Test RetrievalResult.to_dict() conversion."""
        chunk = _create_test_chunk("a")
        lineage = _create_test_lineage("a")
        result = RetrievalResult(chunk=chunk, lineage=lineage, similarity_score=0.9)

        result_dict = result.to_dict()

        assert result_dict["chunk_text"] == "Test chunk a"
        assert result_dict["chunk_hash"] == _make_hash("a")
        assert result_dict["context_header"] == "Context for a"
        assert result_dict["chunk_index"] == 0
        assert result_dict["chunk_type"] == "standard"
        assert result_dict["source_id"] == "source_1"
        assert result_dict["source_version_id"] == 1
        assert result_dict["domain"] == "notes"
        assert result_dict["adapter_id"] == "test-adapter"
        assert result_dict["embedding_model"] == "all-MiniLM-L6-v2"
        assert result_dict["similarity_score"] == 0.9


class TestRetrieve:
    """Tests for the retrieve() function."""

    def _setup_document_store(self, store: DocumentStore) -> tuple[str, str, int]:
        """Set up adapter, source, and version. Returns (source_id, adapter_id, source_version_id)."""
        config = AdapterConfig(
            adapter_id="test-adapter",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source_1",
            adapter_id="test-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        version_id = store.create_source_version(
            source_id="source_1",
            version=1,
            markdown="# Content",
            chunk_hashes=["hash1", "hash2"],
            adapter_id="test-adapter",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        return "source_1", "test-adapter", version_id

    def test_retrieve_validation_negative_top_k(self, embedder, document_store, tmp_path) -> None:
        """Test that retrieve() raises ValueError for negative top_k."""
        with pytest.raises(ValueError, match="top_k must be positive"):
            retrieve(
                "test query",
                embedder,
                document_store,
                vector_store_path=tmp_path,
                top_k=-1,
            )

    def test_retrieve_validation_zero_top_k(self, embedder, document_store, tmp_path) -> None:
        """Test that retrieve() raises ValueError for zero top_k."""
        with pytest.raises(ValueError, match="top_k must be positive"):
            retrieve(
                "test query",
                embedder,
                document_store,
                vector_store_path=tmp_path,
                top_k=0,
            )

    @patch("context_library.retrieval.query.lancedb.connect")
    def test_retrieve_missing_vector_table(
        self, mock_connect, embedder, document_store, tmp_path
    ) -> None:
        """Test that retrieve() raises RuntimeError when vector table is missing."""
        mock_db = MagicMock()
        mock_db.open_table.side_effect = Exception("Table not found")
        mock_connect.return_value = mock_db

        with pytest.raises(RuntimeError, match="Failed to open chunk_vectors table"):
            retrieve(
                "test query",
                embedder,
                document_store,
                vector_store_path=tmp_path,
            )

    @patch("context_library.retrieval.query.lancedb.connect")
    def test_retrieve_empty_results(self, mock_connect, embedder, document_store, tmp_path) -> None:
        """Test that retrieve() returns empty list when no results found."""
        mock_db = MagicMock()
        mock_table = MagicMock()
        mock_search = MagicMock()
        mock_search.limit.return_value.to_list.return_value = []

        mock_table.search.return_value = mock_search
        mock_db.open_table.return_value = mock_table
        mock_connect.return_value = mock_db

        results = retrieve(
            "test query",
            embedder,
            document_store,
            vector_store_path=tmp_path,
        )

        assert results == []

    @patch("context_library.retrieval.query.lancedb.connect")
    def test_retrieve_with_results(
        self, mock_connect, embedder, document_store, tmp_path
    ) -> None:
        """Test retrieve() with successful vector search and enrichment."""
        # Set up document store
        source_id, adapter_id, version_id = self._setup_document_store(document_store)

        # Set up mock LanceDB
        mock_db = MagicMock()
        mock_table = MagicMock()
        mock_search = MagicMock()

        # Mock search results from LanceDB
        search_results = [
            {
                "chunk_hash": _make_hash("a"),
                "_distance": 0.1,  # Low distance = high similarity
            },
            {
                "chunk_hash": _make_hash("b"),
                "_distance": 0.2,
            },
        ]
        mock_search.limit.return_value.to_list.return_value = search_results

        mock_table.search.return_value = mock_search
        mock_db.open_table.return_value = mock_table
        mock_connect.return_value = mock_db

        # Set up chunks with correct lineage and unique indices
        chunk_a = _create_test_chunk("a", chunk_index=0)
        chunk_b = _create_test_chunk("b", chunk_index=1)
        lineage_a = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id=source_id,
            source_version_id=version_id,
            adapter_id=adapter_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="all-MiniLM-L6-v2",
        )
        lineage_b = LineageRecord(
            chunk_hash=_make_hash("b"),
            source_id=source_id,
            source_version_id=version_id,
            adapter_id=adapter_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="all-MiniLM-L6-v2",
        )

        # Register chunks in the store (for get_chunk_by_hash and get_lineage)
        document_store.write_chunks([chunk_a, chunk_b], [lineage_a, lineage_b])

        results = retrieve(
            "test query",
            embedder,
            document_store,
            vector_store_path=tmp_path,
        )

        assert len(results) == 2

        # Results should be sorted by similarity (highest first)
        # Distance 0.1 => similarity 0.95
        # Distance 0.2 => similarity 0.90
        assert results[0].similarity_score > results[1].similarity_score
        assert results[0].chunk.chunk_hash == _make_hash("a")
        assert results[1].chunk.chunk_hash == _make_hash("b")

    @patch("context_library.retrieval.query.lancedb.connect")
    def test_retrieve_domain_filter(
        self, mock_connect, embedder, document_store, tmp_path
    ) -> None:
        """Test that domain_filter is applied to search query."""
        mock_db = MagicMock()
        mock_table = MagicMock()
        mock_search = MagicMock()
        mock_search.where.return_value.limit.return_value.to_list.return_value = []

        mock_table.search.return_value = mock_search
        mock_db.open_table.return_value = mock_table
        mock_connect.return_value = mock_db

        retrieve(
            "test query",
            embedder,
            document_store,
            vector_store_path=tmp_path,
            domain_filter=Domain.NOTES,
        )

        # Verify that where() was called with domain filter
        mock_search.where.assert_called_once()
        assert 'domain = "notes"' in mock_search.where.call_args[0][0]

    @patch("context_library.retrieval.query.lancedb.connect")
    def test_retrieve_source_filter(
        self, mock_connect, embedder, document_store, tmp_path
    ) -> None:
        """Test that source_filter is applied to search query."""
        mock_db = MagicMock()
        mock_table = MagicMock()
        mock_search = MagicMock()
        mock_search.where.return_value.limit.return_value.to_list.return_value = []

        mock_table.search.return_value = mock_search
        mock_db.open_table.return_value = mock_table
        mock_connect.return_value = mock_db

        retrieve(
            "test query",
            embedder,
            document_store,
            vector_store_path=tmp_path,
            source_filter="my_source",
        )

        # Verify that where() was called with source filter
        mock_search.where.assert_called_once()
        assert 'source_id = "my_source"' in mock_search.where.call_args[0][0]

    @patch("context_library.retrieval.query.lancedb.connect")
    def test_retrieve_domain_and_source_filters_combined(
        self, mock_connect, embedder, document_store, tmp_path
    ) -> None:
        """Test that both domain_filter and source_filter are applied together with AND logic."""
        mock_db = MagicMock()
        mock_table = MagicMock()
        mock_search = MagicMock()
        mock_where_1 = MagicMock()
        mock_search.where.return_value = mock_where_1
        mock_where_1.where.return_value.limit.return_value.to_list.return_value = []

        mock_table.search.return_value = mock_search
        mock_db.open_table.return_value = mock_table
        mock_connect.return_value = mock_db

        retrieve(
            "test query",
            embedder,
            document_store,
            vector_store_path=tmp_path,
            domain_filter=Domain.NOTES,
            source_filter="my_source",
        )

        # Verify that where() was called with a combined filter using AND logic
        mock_search.where.assert_called_once()
        filter_expr = mock_search.where.call_args[0][0]
        assert 'domain = "notes"' in filter_expr
        assert 'source_id = "my_source"' in filter_expr
        assert " AND " in filter_expr

    @patch("context_library.retrieval.query.lancedb.connect")
    def test_retrieve_skips_missing_chunk(
        self, mock_connect, embedder, document_store, tmp_path
    ) -> None:
        """Test that retrieve() skips chunks not found in document store."""
        mock_db = MagicMock()
        mock_table = MagicMock()
        mock_search = MagicMock()

        # Return result with hash that won't be in document store
        search_results = [
            {
                "chunk_hash": _make_hash("z"),  # Not registered in store
                "_distance": 0.1,
            },
        ]
        mock_search.limit.return_value.to_list.return_value = search_results

        mock_table.search.return_value = mock_search
        mock_db.open_table.return_value = mock_table
        mock_connect.return_value = mock_db

        results = retrieve(
            "test query",
            embedder,
            document_store,
            vector_store_path=tmp_path,
        )

        # Should skip the chunk and return empty results
        assert results == []

    @patch("context_library.retrieval.query.lancedb.connect")
    def test_retrieve_similarity_score_calculation(
        self, mock_connect, embedder, document_store, tmp_path
    ) -> None:
        """Test that similarity scores are correctly calculated from Euclidean distance."""
        # Set up document store
        source_id, adapter_id, version_id = self._setup_document_store(document_store)

        mock_db = MagicMock()
        mock_table = MagicMock()
        mock_search = MagicMock()

        # Test various distance values
        search_results = [
            {"chunk_hash": _make_hash("a"), "_distance": 0.0},  # Perfect match: similarity = 1.0
            {"chunk_hash": _make_hash("b"), "_distance": 0.5},  # Medium: similarity = 0.75
            {"chunk_hash": _make_hash("c"), "_distance": 2.0},  # Far: similarity ≈ 0.0
        ]
        mock_search.limit.return_value.to_list.return_value = search_results

        mock_table.search.return_value = mock_search
        mock_db.open_table.return_value = mock_table
        mock_connect.return_value = mock_db

        # Register chunks with proper lineage and unique indices
        for i, char in enumerate(["a", "b", "c"]):
            chunk = _create_test_chunk(char, chunk_index=i)
            lineage = LineageRecord(
                chunk_hash=_make_hash(char),
                source_id=source_id,
                source_version_id=version_id,
                adapter_id=adapter_id,
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="all-MiniLM-L6-v2",
            )
            document_store.write_chunks([chunk], [lineage])

        results = retrieve(
            "test query",
            embedder,
            document_store,
            vector_store_path=tmp_path,
        )

        assert len(results) == 3
        # Check similarity score calculations
        assert results[0].similarity_score == 1.0  # distance 0
        assert results[1].similarity_score == 0.75  # distance 0.5
        assert abs(results[2].similarity_score - 0.0) < 0.01  # distance 2.0, clamped to ~0

    @patch("context_library.retrieval.query.lancedb.connect")
    def test_retrieve_top_k_limit(
        self, mock_connect, embedder, document_store, tmp_path
    ) -> None:
        """Test that retrieve() passes top_k parameter to the limit() call."""
        # Set up document store
        source_id, adapter_id, version_id = self._setup_document_store(document_store)

        mock_db = MagicMock()
        mock_table = MagicMock()
        mock_search = MagicMock()

        # Mock only 3 results (matching top_k=3)
        search_results = [
            {"chunk_hash": _make_hash(chr(ord("a") + i)), "_distance": float(i) * 0.1}
            for i in range(3)
        ]
        mock_search.limit.return_value.to_list.return_value = search_results

        mock_table.search.return_value = mock_search
        mock_db.open_table.return_value = mock_table
        mock_connect.return_value = mock_db

        # Register chunks with proper lineage and unique indices
        for i in range(3):
            char = chr(ord("a") + i)
            chunk = _create_test_chunk(char, chunk_index=i)
            lineage = LineageRecord(
                chunk_hash=_make_hash(char),
                source_id=source_id,
                source_version_id=version_id,
                adapter_id=adapter_id,
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="all-MiniLM-L6-v2",
            )
            document_store.write_chunks([chunk], [lineage])

        results = retrieve(
            "test query",
            embedder,
            document_store,
            vector_store_path=tmp_path,
            top_k=3,
        )

        # Verify that limit(3) was called
        mock_search.limit.assert_called_with(3)
        # Verify that exactly 3 results are returned
        assert len(results) == 3
        # Verify results are sorted by similarity (lowest distance first = highest similarity)
        assert results[0].similarity_score >= results[1].similarity_score >= results[2].similarity_score
