"""Integration tests for the vector store.

Tests write chunk vectors to LanceDB, search, and verify results.
"""

import pytest
import lancedb

from context_library.storage.models import Domain


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
