"""Integration tests for the vector store abstraction.

Tests write chunk vectors, search, and verify results using ChromaDB.
"""

import pytest

from context_library.storage.chromadb_store import ChromaDBVectorStore
from context_library.storage.models import Domain
from context_library.storage.vector_store import VectorSearchResult, VectorStore


@pytest.fixture(scope="session")
def embedder():
    """Session-scoped embedder to avoid repeated model downloads."""
    from context_library.core.embedder import Embedder

    return Embedder("all-MiniLM-L6-v2")


@pytest.fixture
def vector_store(tmp_path) -> ChromaDBVectorStore:
    """Create a ChromaDB vector store in a temp directory."""
    store = ChromaDBVectorStore(tmp_path / "chromadb")
    store.initialize(384)  # all-MiniLM-L6-v2 dimension
    return store


class TestVectorStoreIntegration:
    """Integration tests for writing and searching chunk vectors."""

    def test_write_and_search_chunk_vectors(self, vector_store, embedder):
        """Test writing chunk vectors and searching for similar vectors."""
        test_chunks = [
            {
                "content": "The storage layer uses SQLite for transactional integrity and vector search.",
                "source_id": "test_doc_1",
                "source_version": 1,
                "domain": Domain.NOTES,
            },
            {
                "content": "Our markdown-aware chunker respects heading hierarchies and code blocks.",
                "source_id": "test_doc_1",
                "source_version": 1,
                "domain": Domain.NOTES,
            },
            {
                "content": "Configuration is managed through adapter configs stored in the database.",
                "source_id": "test_doc_2",
                "source_version": 1,
                "domain": Domain.NOTES,
            },
        ]

        texts = [chunk["content"] for chunk in test_chunks]
        embeddings = embedder.embed(texts)

        chunk_vector_dicts = []
        for i, (chunk, embedding) in enumerate(zip(test_chunks, embeddings)):
            chunk_hash = f"{'a' * 63}{i}"
            chunk_vector_dicts.append({
                "chunk_hash": chunk_hash,
                "content": chunk["content"],
                "vector": embedding,
                "domain": chunk["domain"].value,
                "source_id": chunk["source_id"],
                "source_version": chunk["source_version"],
                "created_at": "2026-03-04T12:00:00Z",
            })

        vector_store.add_vectors(chunk_vector_dicts)
        assert vector_store.count() == 3

        # Search for similar vectors
        query_text = "storage database SQLite transactional"
        query_vector = embedder.embed_query(query_text)

        results = vector_store.search(query_vector, top_k=2)
        assert len(results) <= 2
        assert len(results) > 0
        assert all(isinstance(r, VectorSearchResult) for r in results)
        assert all(0.0 <= r.similarity_score <= 1.0 for r in results)

    def test_vector_insertion_and_deletion(self, vector_store, embedder):
        """Test inserting and deleting chunk vectors."""
        embeddings = embedder.embed([
            "First chunk about architecture",
            "Second chunk about storage",
        ])

        chunk_vector_dicts = [
            {
                "chunk_hash": "a" * 64,
                "content": "First chunk about architecture",
                "vector": embeddings[0],
                "domain": Domain.NOTES.value,
                "source_id": "doc1",
                "source_version": 1,
                "created_at": "2026-03-04T12:00:00Z",
            },
            {
                "chunk_hash": "b" * 64,
                "content": "Second chunk about storage",
                "vector": embeddings[1],
                "domain": Domain.NOTES.value,
                "source_id": "doc1",
                "source_version": 1,
                "created_at": "2026-03-04T12:00:00Z",
            },
        ]

        vector_store.add_vectors(chunk_vector_dicts)
        assert vector_store.count() == 2

        # Delete one vector
        vector_store.delete_vectors({"b" * 64})
        assert vector_store.count() == 1

    def test_search_with_domain_filter(self, vector_store, embedder):
        """Test that domain filter works in search."""
        embeddings = embedder.embed([
            "A note about architecture",
            "An email about meetings",
        ])

        vector_store.add_vectors([
            {
                "chunk_hash": "a" * 64,
                "content": "A note about architecture",
                "vector": embeddings[0],
                "domain": Domain.NOTES.value,
                "source_id": "doc1",
                "source_version": 1,
                "created_at": "2026-03-04T12:00:00Z",
            },
            {
                "chunk_hash": "b" * 64,
                "content": "An email about meetings",
                "vector": embeddings[1],
                "domain": Domain.MESSAGES.value,
                "source_id": "doc2",
                "source_version": 1,
                "created_at": "2026-03-04T12:00:00Z",
            },
        ])

        query_vector = embedder.embed_query("architecture notes")
        results = vector_store.search(query_vector, top_k=10, domain_filter=Domain.NOTES)

        # Should only return notes, not messages
        assert len(results) > 0
        for r in results:
            assert r.chunk_hash == "a" * 64

    def test_empty_store_count(self, vector_store):
        """Test that empty store returns count 0."""
        assert vector_store.count() == 0

    def test_delete_nonexistent_hash(self, vector_store):
        """Test that deleting nonexistent hashes does not raise."""
        vector_store.delete_vectors({"z" * 64})  # Should not raise

    def test_add_empty_list(self, vector_store):
        """Test that adding empty list does not raise."""
        vector_store.add_vectors([])
        assert vector_store.count() == 0

    def test_count_logs_and_raises_on_error(self, vector_store, caplog):
        """Test that count() logs and raises RuntimeError on ChromaDB failures."""
        import logging
        caplog.set_level(logging.ERROR)

        # Mock the collection to raise an error
        vector_store._collection = None
        original_get_client = vector_store._get_client

        def mock_get_client_error():
            raise RuntimeError("ChromaDB connection failed")

        vector_store._get_client = mock_get_client_error

        # count() should raise RuntimeError and log the error
        with pytest.raises(RuntimeError, match="Vector store count failed"):
            vector_store.count()

        assert "Failed to count vectors in store" in caplog.text
        assert "RuntimeError" in caplog.text

        # Restore original method
        vector_store._get_client = original_get_client


class TestVectorStoreABC:
    """Tests for the VectorStore abstract interface."""

    def test_chromadb_implements_interface(self, tmp_path):
        """ChromaDBVectorStore should be a valid VectorStore implementation."""
        store = ChromaDBVectorStore(tmp_path / "test")
        assert isinstance(store, VectorStore)
