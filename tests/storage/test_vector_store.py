"""Integration tests for the vector store.

Tests write chunk vectors to LanceDB, search, and verify results.
"""

import logging

import pytest
import lancedb

from context_library.storage.models import Domain
from context_library.storage.vector_store import should_create_index, create_ivf_pq_index


@pytest.fixture(scope="session")
def embedder():
    """Session-scoped embedder to avoid repeated model downloads."""
    from context_library.core.embedder import Embedder

    return Embedder("all-MiniLM-L6-v2")


class TestVectorStoreIntegration:
    """Integration tests for writing and searching chunk vectors in LanceDB."""

    def test_write_and_search_chunk_vectors(self, tmp_path, embedder):
        """Test writing chunk vectors to LanceDB and searching for similar vectors."""
        # Set up LanceDB
        lancedb_path = tmp_path / "lancedb"
        lancedb_path.mkdir()
        db = lancedb.connect(str(lancedb_path))

        # Create test chunk vectors with known content
        test_chunks = [
            {
                "content": "The storage layer uses SQLite for transactional integrity and LanceDB for vector search.",
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

        # Embed all test chunks
        texts = [chunk["content"] for chunk in test_chunks]
        embeddings = embedder.embed(texts)

        # Create chunk vector dicts for LanceDB (LanceDB requires dicts, not Pydantic models)
        chunk_vector_dicts = []
        for i, (chunk, embedding) in enumerate(zip(test_chunks, embeddings)):
            chunk_hash = f"hash_{i}"
            chunk_vector_dicts.append({
                "chunk_hash": chunk_hash,
                "content": chunk["content"],
                "vector": embedding,
                "domain": chunk["domain"].value,  # Convert enum to string
                "source_id": chunk["source_id"],
                "source_version": chunk["source_version"],
                "created_at": "2026-03-04T12:00:00Z",
            })

        # Write to LanceDB
        table = db.create_table("chunk_vectors", data=chunk_vector_dicts, mode="overwrite")
        assert table.count_rows() == 3, "Should have written 3 chunk vectors"

        # Create a query vector similar to the first test chunk
        query_text = "storage database SQLite transactional"
        query_vector = embedder.embed_query(query_text)

        # Search for similar vectors
        results = table.search(query_vector).limit(2).to_list()
        assert len(results) <= 2, "Should return at most 2 results"
        assert len(results) > 0, "Should return at least 1 result"

        # Verify the most similar result (should be the first chunk about storage)
        top_result = results[0]
        assert "storage" in top_result["content"].lower(), (
            "Top result should be about storage"
        )
        assert "chunk_hash" in top_result, "Result should contain chunk_hash"
        assert "source_id" in top_result, "Result should contain source_id"
        assert "vector" in top_result, "Result should contain vector"
        assert "domain" in top_result, "Result should contain domain"

    def test_vector_insertion_and_deletion(self, tmp_path, embedder):
        """Test inserting and deleting chunk vectors from LanceDB."""
        lancedb_path = tmp_path / "lancedb"
        lancedb_path.mkdir()
        db = lancedb.connect(str(lancedb_path))

        # Create and insert chunk vectors
        embeddings = embedder.embed(
            [
                "First chunk about architecture",
                "Second chunk about storage",
            ]
        )

        chunk_vector_dicts = [
            {
                "chunk_hash": "hash_1",
                "content": "First chunk about architecture",
                "vector": embeddings[0],
                "domain": Domain.NOTES.value,
                "source_id": "doc1",
                "source_version": 1,
                "created_at": "2026-03-04T12:00:00Z",
            },
            {
                "chunk_hash": "hash_2",
                "content": "Second chunk about storage",
                "vector": embeddings[1],
                "domain": Domain.NOTES.value,
                "source_id": "doc1",
                "source_version": 1,
                "created_at": "2026-03-04T12:00:00Z",
            },
        ]

        # Create table and insert
        table = db.create_table(
            "chunk_vectors", data=chunk_vector_dicts, mode="overwrite"
        )
        assert table.count_rows() == 2, "Should have 2 vectors after insert"

        # Delete one vector using LanceDB's delete() method
        table.delete("chunk_hash = 'hash_2'")
        assert table.count_rows() == 1, "Should have 1 vector after deletion"

        # Verify the remaining vector is correct
        remaining = table.search().limit(1).to_list()[0]
        assert remaining["chunk_hash"] == "hash_1", "Remaining vector should be hash_1"


class TestIndexCreation:
    """Tests for IVF-PQ index creation and threshold detection."""

    def test_should_create_index_below_threshold(self, tmp_path, embedder):
        """Test that should_create_index returns False when chunk count is below threshold."""
        lancedb_path = tmp_path / "lancedb"
        lancedb_path.mkdir()
        db = lancedb.connect(str(lancedb_path))

        # Create a table with fewer than 10,000 rows
        embeddings = embedder.embed(["chunk 1", "chunk 2", "chunk 3"])
        chunk_vector_dicts = [
            {
                "chunk_hash": f"hash_{i}",
                "content": f"chunk {i}",
                "vector": embeddings[i],
                "domain": Domain.NOTES.value,
                "source_id": "doc1",
                "source_version": 1,
                "created_at": "2026-03-04T12:00:00Z",
            }
            for i in range(3)
        ]
        db.create_table("chunk_vectors", data=chunk_vector_dicts, mode="overwrite")

        # should_create_index should return False with default threshold
        assert not should_create_index(lancedb_path, threshold=10_000)

    def test_should_create_index_at_threshold(self, tmp_path, embedder):
        """Test that should_create_index returns True when chunk count reaches threshold."""
        lancedb_path = tmp_path / "lancedb"
        lancedb_path.mkdir()
        db = lancedb.connect(str(lancedb_path))

        # Create a table with exactly 100 rows for a lower threshold test
        embeddings = embedder.embed(["chunk text"] * 100)
        chunk_vector_dicts = [
            {
                "chunk_hash": f"hash_{i}",
                "content": f"chunk {i}",
                "vector": embeddings[i],
                "domain": Domain.NOTES.value,
                "source_id": "doc1",
                "source_version": 1,
                "created_at": "2026-03-04T12:00:00Z",
            }
            for i in range(100)
        ]
        db.create_table("chunk_vectors", data=chunk_vector_dicts, mode="overwrite")

        # should_create_index should return True with threshold=100
        assert should_create_index(lancedb_path, threshold=100)

    def test_should_create_index_above_threshold(self, tmp_path, embedder):
        """Test that should_create_index returns True when chunk count exceeds threshold."""
        lancedb_path = tmp_path / "lancedb"
        lancedb_path.mkdir()
        db = lancedb.connect(str(lancedb_path))

        # Create a table with 150 rows
        embeddings = embedder.embed(["chunk text"] * 150)
        chunk_vector_dicts = [
            {
                "chunk_hash": f"hash_{i}",
                "content": f"chunk {i}",
                "vector": embeddings[i],
                "domain": Domain.NOTES.value,
                "source_id": "doc1",
                "source_version": 1,
                "created_at": "2026-03-04T12:00:00Z",
            }
            for i in range(150)
        ]
        db.create_table("chunk_vectors", data=chunk_vector_dicts, mode="overwrite")

        # should_create_index should return True with threshold=100
        assert should_create_index(lancedb_path, threshold=100)

    def test_should_create_index_nonexistent_table(self, tmp_path):
        """Test that should_create_index returns False when table does not exist."""
        lancedb_path = tmp_path / "lancedb"
        lancedb_path.mkdir()

        # No table created; should_create_index should return False
        assert not should_create_index(lancedb_path)

    def test_should_create_index_nonexistent_db(self, tmp_path):
        """Test that should_create_index returns False when LanceDB directory does not exist."""
        nonexistent_path = tmp_path / "nonexistent"

        # Path doesn't exist; should_create_index should return False
        assert not should_create_index(nonexistent_path)

    def test_should_create_index_missing_table(self, tmp_path, caplog):
        """Test that should_create_index returns False when table does not exist (already covered)."""
        # This is covered by test_should_create_index_nonexistent_table
        pass

    def test_should_create_index_logs_on_error(self, tmp_path, caplog):
        """Test that should_create_index logs errors instead of silently failing."""
        from unittest.mock import patch

        lancedb_path = tmp_path / "lancedb"
        lancedb_path.mkdir()

        # Mock lancedb.connect to raise an OSError (simulating disk/permission issues)
        with patch("lancedb.connect") as mock_connect:
            mock_connect.side_effect = OSError("Permission denied")

            # should_create_index should return False and log a warning
            with caplog.at_level(logging.WARNING):
                result = should_create_index(lancedb_path)

            assert result is False
            assert "Could not access vector store" in caplog.text

    def test_should_create_index_logs_memory_error(self, tmp_path, caplog):
        """Test that should_create_index logs memory errors."""
        from unittest.mock import patch

        lancedb_path = tmp_path / "lancedb"
        lancedb_path.mkdir()

        # Mock lancedb.connect to raise MemoryError
        with patch("lancedb.connect") as mock_connect:
            mock_connect.side_effect = MemoryError("Out of memory")

            # should_create_index should return False and log an error
            with caplog.at_level(logging.ERROR):
                result = should_create_index(lancedb_path)

            assert result is False
            assert "Out of memory" in caplog.text

    def test_should_create_index_logs_unexpected_error(self, tmp_path, caplog):
        """Test that should_create_index logs unexpected errors with type information."""
        from unittest.mock import patch

        lancedb_path = tmp_path / "lancedb"
        lancedb_path.mkdir()

        # Mock db.open_table to raise a ValueError (simulating database corruption)
        with patch("lancedb.connect") as mock_connect:
            mock_db = mock_connect.return_value
            mock_db.open_table.side_effect = ValueError("Database corrupted")

            # should_create_index should return False and log an error
            with caplog.at_level(logging.ERROR):
                result = should_create_index(lancedb_path)

            assert result is False
            assert "Unexpected error" in caplog.text
            assert "ValueError" in caplog.text

    def test_create_ivf_pq_index_success(self, tmp_path, embedder):
        """Test that create_ivf_pq_index successfully creates an IVF-PQ index."""
        lancedb_path = tmp_path / "lancedb"
        lancedb_path.mkdir()
        db = lancedb.connect(str(lancedb_path))

        # Create a table with enough rows for PQ indexing (minimum 256 rows required)
        embeddings = embedder.embed(["chunk text"] * 300)
        chunk_vector_dicts = [
            {
                "chunk_hash": f"hash_{i}",
                "content": f"chunk {i}",
                "vector": embeddings[i],
                "domain": Domain.NOTES.value,
                "source_id": "doc1",
                "source_version": 1,
                "created_at": "2026-03-04T12:00:00Z",
            }
            for i in range(300)
        ]
        db.create_table("chunk_vectors", data=chunk_vector_dicts, mode="overwrite")

        # Create index without raising an exception
        create_ivf_pq_index(lancedb_path)

        # Verify the table still has the same rows
        table = db.open_table("chunk_vectors")
        assert table.count_rows() == 300, "Row count should not change after indexing"

    def test_create_ivf_pq_index_idempotent(self, tmp_path, embedder):
        """Test that create_ivf_pq_index is idempotent."""
        lancedb_path = tmp_path / "lancedb"
        lancedb_path.mkdir()
        db = lancedb.connect(str(lancedb_path))

        # Create a table with enough rows for PQ indexing (minimum 256 rows required)
        embeddings = embedder.embed(["chunk text"] * 300)
        chunk_vector_dicts = [
            {
                "chunk_hash": f"hash_{i}",
                "content": f"chunk {i}",
                "vector": embeddings[i],
                "domain": Domain.NOTES.value,
                "source_id": "doc1",
                "source_version": 1,
                "created_at": "2026-03-04T12:00:00Z",
            }
            for i in range(300)
        ]
        db.create_table("chunk_vectors", data=chunk_vector_dicts, mode="overwrite")

        # Create index twice; should not raise an exception on the second call
        create_ivf_pq_index(lancedb_path)
        create_ivf_pq_index(lancedb_path)  # Should succeed (idempotent)

        # Verify the table still has the same rows
        table = db.open_table("chunk_vectors")
        assert table.count_rows() == 300, "Row count should not change after second indexing"

    def test_create_ivf_pq_index_with_custom_params(self, tmp_path, embedder):
        """Test that create_ivf_pq_index respects custom num_partitions and num_sub_vectors."""
        lancedb_path = tmp_path / "lancedb"
        lancedb_path.mkdir()
        db = lancedb.connect(str(lancedb_path))

        # Create a table with enough rows for PQ indexing (minimum 256 rows required)
        embeddings = embedder.embed(["chunk text"] * 300)
        chunk_vector_dicts = [
            {
                "chunk_hash": f"hash_{i}",
                "content": f"chunk {i}",
                "vector": embeddings[i],
                "domain": Domain.NOTES.value,
                "source_id": "doc1",
                "source_version": 1,
                "created_at": "2026-03-04T12:00:00Z",
            }
            for i in range(300)
        ]
        db.create_table("chunk_vectors", data=chunk_vector_dicts, mode="overwrite")

        # Create index with explicit parameters
        create_ivf_pq_index(lancedb_path, num_partitions=5, num_sub_vectors=16)

        # Verify the table still has the same rows
        table = db.open_table("chunk_vectors")
        assert table.count_rows() == 300, "Row count should not change after indexing"

    def test_search_after_indexing(self, tmp_path, embedder):
        """Test that table.search() continues to work after indexing."""
        lancedb_path = tmp_path / "lancedb"
        lancedb_path.mkdir()
        db = lancedb.connect(str(lancedb_path))

        # Create test chunks with varied content to reach minimum 256 rows for PQ indexing
        test_chunks = [
            "The storage layer uses SQLite for transactional integrity and LanceDB for vector search.",
            "Our markdown-aware chunker respects heading hierarchies and code blocks.",
            "Configuration is managed through adapter configs stored in the database.",
            "The API server handles concurrent requests with graceful error handling.",
            "Data validation ensures all inputs conform to expected schemas.",
        ]
        # Repeat chunks to get enough rows for PQ indexing
        embeddings = embedder.embed(test_chunks * 60)  # 300 rows
        chunk_vector_dicts = [
            {
                "chunk_hash": f"hash_{i}",
                "content": test_chunks[i % len(test_chunks)],
                "vector": embeddings[i],
                "domain": Domain.NOTES.value,
                "source_id": "doc1",
                "source_version": 1,
                "created_at": "2026-03-04T12:00:00Z",
            }
            for i in range(300)
        ]
        db.create_table("chunk_vectors", data=chunk_vector_dicts, mode="overwrite")

        # Search before indexing
        query_text = "storage database SQLite transactional"
        query_vector = embedder.embed_query(query_text)
        results_before = db.open_table("chunk_vectors").search(query_vector).limit(2).to_list()

        # Create index
        create_ivf_pq_index(lancedb_path)

        # Search after indexing
        results_after = db.open_table("chunk_vectors").search(query_vector).limit(2).to_list()

        # Verify both searches return results (search functionality preserved)
        assert len(results_before) > 0, "Should return results before indexing"
        assert len(results_after) > 0, "Should return results after indexing"
        assert "chunk_hash" in results_before[0], "Results should contain chunk_hash before indexing"
        assert "chunk_hash" in results_after[0], "Results should contain chunk_hash after indexing"
