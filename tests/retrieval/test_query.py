"""Tests for the query module.

Covers:
- Query embedding and vector search
- Lineage lookup and enrichment
- Filtering by domain and source
- Similarity score calculation
- Error handling for missing vector store or empty results
"""

import os
import tempfile
from typing import Generator
from unittest.mock import MagicMock

import pytest

from context_library.core.embedder import Embedder
from context_library.retrieval.query import RetrievalResult, retrieve
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import AdapterConfig, Chunk, ChunkType, Domain, LineageRecord
from context_library.storage.vector_store import VectorSearchResult, VectorStore


@pytest.fixture
def embedder() -> Embedder:
    """Create an Embedder instance for testing."""
    return Embedder()


@pytest.fixture
def document_store() -> Generator[DocumentStore, None, None]:
    """Create an in-memory DocumentStore for testing."""
    # Use file-based DB to support multi-threaded access
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_path = temp_file.name
    temp_file.close()
    store = DocumentStore(temp_path)
    yield store
    store.close()
    try:
        os.unlink(temp_path)
    except OSError:
        pass


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
        chunk_type=ChunkType.STANDARD,
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


def _create_mock_vector_store(search_results: list[VectorSearchResult] | None = None) -> MagicMock:
    """Create a mock VectorStore with configurable search results."""
    mock = MagicMock(spec=VectorStore)
    if search_results is None:
        search_results = []
    mock.search.return_value = search_results
    return mock


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

    def test_to_dict_excludes_domain_metadata(self) -> None:
        """Test that to_dict() never includes domain_metadata (especially for people domain).

        Per FR-6.3 spec, contact domain_metadata containing sensitive information
        (emails, phones) must not be exposed in retrieval result output.
        """
        # Create a chunk with sensitive people domain metadata (emails, phones)
        people_metadata = {
            "contact_id": "contact_123",
            "display_name": "John Doe",
            "emails": ("john@example.com", "johndoe@work.com"),
            "phones": ("+1-555-0100", "+1-555-0200"),
            "organization": "ACME Corp",
            "job_title": "Engineer",
            "source_type": "contacts",
        }
        chunk_with_metadata = Chunk(
            chunk_hash=_make_hash("0"),
            content="Contact description",
            context_header="Contact: John Doe",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
            domain_metadata=people_metadata,
        )
        lineage = LineageRecord(
            chunk_hash=_make_hash("0"),
            source_id="people_source",
            source_version_id=1,
            adapter_id="people-adapter",
            domain=Domain.PEOPLE,
            normalizer_version="1.0.0",
            embedding_model_id="all-MiniLM-L6-v2",
        )
        result = RetrievalResult(chunk=chunk_with_metadata, lineage=lineage, similarity_score=0.85)

        result_dict = result.to_dict()

        # Verify domain_metadata is NOT in the output
        assert "domain_metadata" not in result_dict, (
            "domain_metadata must not be included in to_dict() output for security reasons"
        )

        # Verify sensitive contact information is not exposed in serialized output
        result_str = str(result_dict)
        assert "john@example.com" not in result_str, "Email addresses must not be exposed"
        assert "+1-555-0100" not in result_str, "Phone numbers must not be exposed"

        # Verify expected fields are still present
        assert result_dict["chunk_text"] == "Contact description"
        assert result_dict["domain"] == "people"
        assert result_dict["context_header"] == "Contact: John Doe"


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
            chunk_hashes=["a" * 64, "b" * 64],
            adapter_id="test-adapter",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        return "source_1", "test-adapter", version_id

    def test_retrieve_validation_negative_top_k(self, embedder, document_store) -> None:
        """Test that retrieve() raises ValueError for negative top_k."""
        mock_vs = _create_mock_vector_store()
        with pytest.raises(ValueError, match="top_k must be positive"):
            retrieve("test query", embedder, document_store, vector_store=mock_vs, top_k=-1)

    def test_retrieve_validation_zero_top_k(self, embedder, document_store) -> None:
        """Test that retrieve() raises ValueError for zero top_k."""
        mock_vs = _create_mock_vector_store()
        with pytest.raises(ValueError, match="top_k must be positive"):
            retrieve("test query", embedder, document_store, vector_store=mock_vs, top_k=0)

    def test_retrieve_missing_vector_table(self, embedder, document_store) -> None:
        """Test that retrieve() raises RuntimeError when vector store search fails."""
        mock_vs = _create_mock_vector_store()
        mock_vs.search.side_effect = RuntimeError("Table not found")

        with pytest.raises(RuntimeError, match="Table not found"):
            retrieve("test query", embedder, document_store, vector_store=mock_vs)

    def test_retrieve_empty_results(self, embedder, document_store) -> None:
        """Test that retrieve() returns empty list when no results found."""
        mock_vs = _create_mock_vector_store([])

        results = retrieve("test query", embedder, document_store, vector_store=mock_vs)
        assert results == []

    def test_retrieve_with_results(self, embedder, document_store) -> None:
        """Test retrieve() with successful vector search and enrichment."""
        source_id, adapter_id, version_id = self._setup_document_store(document_store)

        # Mock vector store search results
        search_results = [
            VectorSearchResult(chunk_hash=_make_hash("a"), similarity_score=0.95),
            VectorSearchResult(chunk_hash=_make_hash("b"), similarity_score=0.90),
        ]
        mock_vs = _create_mock_vector_store(search_results)

        # Set up chunks with correct lineage and unique indices
        chunk_a = _create_test_chunk("a", chunk_index=0)
        chunk_b = _create_test_chunk("b", chunk_index=1)
        lineage_a = LineageRecord(
            chunk_hash=_make_hash("a"), source_id=source_id,
            source_version_id=version_id, adapter_id=adapter_id,
            domain=Domain.NOTES, normalizer_version="1.0.0",
            embedding_model_id="all-MiniLM-L6-v2",
        )
        lineage_b = LineageRecord(
            chunk_hash=_make_hash("b"), source_id=source_id,
            source_version_id=version_id, adapter_id=adapter_id,
            domain=Domain.NOTES, normalizer_version="1.0.0",
            embedding_model_id="all-MiniLM-L6-v2",
        )
        document_store.write_chunks([chunk_a, chunk_b], [lineage_a, lineage_b])

        results = retrieve("test query", embedder, document_store, vector_store=mock_vs)

        assert len(results) == 2
        assert results[0].similarity_score > results[1].similarity_score
        assert results[0].chunk.chunk_hash == _make_hash("a")
        assert results[1].chunk.chunk_hash == _make_hash("b")

    def test_retrieve_domain_filter(self, embedder, document_store) -> None:
        """Test that domain_filter is passed to vector store search."""
        mock_vs = _create_mock_vector_store([])

        retrieve(
            "test query", embedder, document_store,
            vector_store=mock_vs, domain_filter=Domain.NOTES,
        )

        mock_vs.search.assert_called_once()
        call_kwargs = mock_vs.search.call_args
        assert call_kwargs.kwargs.get("domain_filter") == Domain.NOTES or \
            (len(call_kwargs.args) > 2 and call_kwargs.args[2] == Domain.NOTES)

    def test_retrieve_source_filter(self, embedder, document_store) -> None:
        """Test that source_filter is passed to vector store search."""
        mock_vs = _create_mock_vector_store([])

        retrieve(
            "test query", embedder, document_store,
            vector_store=mock_vs, source_filter="my_source",
        )

        mock_vs.search.assert_called_once()
        call_kwargs = mock_vs.search.call_args
        assert call_kwargs.kwargs.get("source_filter") == "my_source" or \
            (len(call_kwargs.args) > 3 and call_kwargs.args[3] == "my_source")

    def test_retrieve_source_filter_with_double_quote_raises_error(
        self, embedder, document_store
    ) -> None:
        """Test that source_filter containing double quote raises ValueError."""
        mock_vs = _create_mock_vector_store()
        with pytest.raises(ValueError, match="source_filter contains invalid characters"):
            retrieve(
                "test query", embedder, document_store,
                vector_store=mock_vs, source_filter='my"source',
            )

    def test_retrieve_source_filter_with_single_quote_raises_error(
        self, embedder, document_store
    ) -> None:
        """Test that source_filter containing single quote raises ValueError."""
        mock_vs = _create_mock_vector_store()
        with pytest.raises(ValueError, match="source_filter contains invalid characters"):
            retrieve(
                "test query", embedder, document_store,
                vector_store=mock_vs, source_filter="my'source",
            )

    def test_retrieve_source_filter_with_semicolon_raises_error(
        self, embedder, document_store
    ) -> None:
        """Test that source_filter containing semicolon raises ValueError."""
        mock_vs = _create_mock_vector_store()
        with pytest.raises(ValueError, match="source_filter contains invalid characters"):
            retrieve(
                "test query", embedder, document_store,
                vector_store=mock_vs, source_filter="my;source",
            )

    def test_retrieve_source_filter_with_backslash_raises_error(
        self, embedder, document_store
    ) -> None:
        """Test that source_filter containing backslash raises ValueError."""
        mock_vs = _create_mock_vector_store()
        with pytest.raises(ValueError, match="source_filter contains invalid characters"):
            retrieve(
                "test query", embedder, document_store,
                vector_store=mock_vs, source_filter="my\\source",
            )

    def test_retrieve_source_filter_valid_characters(
        self, embedder, document_store
    ) -> None:
        """Test that source_filter allows valid characters."""
        mock_vs = _create_mock_vector_store([])

        # This should not raise an error
        retrieve(
            "test query", embedder, document_store,
            vector_store=mock_vs, source_filter="my_source-123.test/path",
        )

        mock_vs.search.assert_called_once()

    def test_retrieve_domain_and_source_filters_combined(
        self, embedder, document_store
    ) -> None:
        """Test that both domain_filter and source_filter are passed together."""
        mock_vs = _create_mock_vector_store([])

        retrieve(
            "test query", embedder, document_store,
            vector_store=mock_vs,
            domain_filter=Domain.NOTES, source_filter="my_source",
        )

        mock_vs.search.assert_called_once()
        call_kwargs = mock_vs.search.call_args
        assert call_kwargs.kwargs.get("domain_filter") == Domain.NOTES
        assert call_kwargs.kwargs.get("source_filter") == "my_source"

    def test_retrieve_skips_missing_chunk(self, embedder, document_store) -> None:
        """Test that retrieve() skips chunks not found in document store."""
        search_results = [
            VectorSearchResult(chunk_hash=_make_hash("z"), similarity_score=0.95),
        ]
        mock_vs = _create_mock_vector_store(search_results)

        results = retrieve("test query", embedder, document_store, vector_store=mock_vs)
        assert results == []

    def test_retrieve_similarity_score_calculation(
        self, embedder, document_store
    ) -> None:
        """Test that similarity scores are correctly passed through from vector store."""
        source_id, adapter_id, version_id = self._setup_document_store(document_store)

        search_results = [
            VectorSearchResult(chunk_hash=_make_hash("a"), similarity_score=1.0),
            VectorSearchResult(chunk_hash=_make_hash("b"), similarity_score=0.75),
            VectorSearchResult(chunk_hash=_make_hash("c"), similarity_score=0.0),
        ]
        mock_vs = _create_mock_vector_store(search_results)

        for i, char in enumerate(["a", "b", "c"]):
            chunk = _create_test_chunk(char, chunk_index=i)
            lineage = LineageRecord(
                chunk_hash=_make_hash(char), source_id=source_id,
                source_version_id=version_id, adapter_id=adapter_id,
                domain=Domain.NOTES, normalizer_version="1.0.0",
                embedding_model_id="all-MiniLM-L6-v2",
            )
            document_store.write_chunks([chunk], [lineage])

        results = retrieve("test query", embedder, document_store, vector_store=mock_vs)

        assert len(results) == 3
        assert results[0].similarity_score == 1.0
        assert results[1].similarity_score == 0.75
        assert abs(results[2].similarity_score - 0.0) < 0.01

    def test_retrieve_top_k_limit(self, embedder, document_store) -> None:
        """Test that retrieve() passes top_k parameter to vector store."""
        source_id, adapter_id, version_id = self._setup_document_store(document_store)

        search_results = [
            VectorSearchResult(chunk_hash=_make_hash(chr(ord("a") + i)), similarity_score=1.0 - i * 0.1)
            for i in range(3)
        ]
        mock_vs = _create_mock_vector_store(search_results)

        for i in range(3):
            char = chr(ord("a") + i)
            chunk = _create_test_chunk(char, chunk_index=i)
            lineage = LineageRecord(
                chunk_hash=_make_hash(char), source_id=source_id,
                source_version_id=version_id, adapter_id=adapter_id,
                domain=Domain.NOTES, normalizer_version="1.0.0",
                embedding_model_id="all-MiniLM-L6-v2",
            )
            document_store.write_chunks([chunk], [lineage])

        results = retrieve(
            "test query", embedder, document_store,
            vector_store=mock_vs, top_k=3,
        )

        # Verify top_k was passed
        call_kwargs = mock_vs.search.call_args
        assert call_kwargs.kwargs.get("top_k") == 3 or \
            (len(call_kwargs.args) > 1 and call_kwargs.args[1] == 3)
        assert len(results) == 3
        assert results[0].similarity_score >= results[1].similarity_score >= results[2].similarity_score

    def test_retrieve_empty_query_raises_error(self, embedder, document_store) -> None:
        """Test that retrieve() raises ValueError for empty query string."""
        mock_vs = _create_mock_vector_store()
        with pytest.raises(ValueError, match="query must be a non-empty string"):
            retrieve("", embedder, document_store, vector_store=mock_vs)

    def test_retrieve_whitespace_only_query_raises_error(self, embedder, document_store) -> None:
        """Test that retrieve() raises ValueError for whitespace-only query string."""
        mock_vs = _create_mock_vector_store()
        with pytest.raises(ValueError, match="query must be a non-empty string"):
            retrieve("   ", embedder, document_store, vector_store=mock_vs)

    def test_retrieve_whitespace_and_newline_query_raises_error(self, embedder, document_store) -> None:
        """Test that retrieve() raises ValueError for query with only whitespace and newlines."""
        mock_vs = _create_mock_vector_store()
        with pytest.raises(ValueError, match="query must be a non-empty string"):
            retrieve("\t\n  \r\n", embedder, document_store, vector_store=mock_vs)

    def test_retrieve_missing_chunk_in_sqlite_logs_warning(
        self, embedder, document_store, caplog
    ) -> None:
        """Test that retrieve() logs warning when chunk exists in vector store but not in SQLite."""
        import logging
        caplog.set_level(logging.WARNING)

        search_results = [
            VectorSearchResult(chunk_hash=_make_hash("z"), similarity_score=0.95),
        ]
        mock_vs = _create_mock_vector_store(search_results)

        results = retrieve("test query", embedder, document_store, vector_store=mock_vs)

        assert results == []
        assert "Store inconsistency" in caplog.text
        assert _make_hash("z") in caplog.text

    def test_retrieve_missing_lineage_in_sqlite_logs_warning(
        self, embedder, document_store, caplog
    ) -> None:
        """Test that retrieve() logs warning when lineage is missing (mocked scenario)."""
        import logging
        caplog.set_level(logging.WARNING)

        source_id, adapter_id, version_id = self._setup_document_store(document_store)

        chunk = _create_test_chunk("a", chunk_index=0)
        document_store.get_lineage = MagicMock(return_value=None)
        document_store.get_chunk_by_hash = MagicMock(return_value=chunk)

        search_results = [
            VectorSearchResult(chunk_hash=_make_hash("a"), similarity_score=0.95),
        ]
        mock_vs = _create_mock_vector_store(search_results)

        results = retrieve("test query", embedder, document_store, vector_store=mock_vs)

        assert results == []
        assert "Store inconsistency" in caplog.text
        assert "lineage record" in caplog.text

    def test_retrieve_skips_retired_chunks_without_warning(
        self, embedder, document_store, caplog
    ) -> None:
        """Test that retrieve() skips retired chunks without logging warning."""
        import logging
        caplog.set_level(logging.WARNING)

        source_id, adapter_id, version_id = self._setup_document_store(document_store)
        chunk = _create_test_chunk("a", chunk_index=0)
        lineage = _create_test_lineage("a", source_id=source_id)
        document_store.write_chunks([chunk], [lineage])

        # Retire the chunk
        document_store.retire_chunks({_make_hash("a")}, source_id, 1)

        search_results = [
            VectorSearchResult(chunk_hash=_make_hash("a"), similarity_score=0.95),
        ]
        mock_vs = _create_mock_vector_store(search_results)

        results = retrieve("test query", embedder, document_store, vector_store=mock_vs)

        assert results == []
        assert "Store inconsistency" not in caplog.text

    def test_retrieve_search_error_raises_runtime_error(
        self, embedder, document_store
    ) -> None:
        """Test that retrieve() propagates RuntimeError from vector store search."""
        mock_vs = _create_mock_vector_store()
        mock_vs.search.side_effect = RuntimeError("Vector search failed: TypeError: Invalid filter type")

        with pytest.raises(RuntimeError, match="Vector search failed"):
            retrieve("test query", embedder, document_store, vector_store=mock_vs)
