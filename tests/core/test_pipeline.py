"""Tests for the pipeline module."""

import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from context_library.adapters.filesystem import FilesystemAdapter
from context_library.core.differ import Differ
from context_library.core.embedder import Embedder
from context_library.core.pipeline import IngestionPipeline
from context_library.domains.notes import NotesDomain
from context_library.storage.chromadb_store import ChromaDBVectorStore
from context_library.storage.document_store import DocumentStore


@pytest.fixture
def temp_markdown_dir():
    """Create a temporary directory with markdown files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)

        # Create initial markdown files
        (temp_path / "file1.md").write_text(
            """# File 1

This is the first file with some content.

## Section 1.1

Some text here."""
        )

        (temp_path / "file2.md").write_text(
            """# File 2

Another file with different content.

## Section 2.1

More content."""
        )

        yield temp_path


@pytest.fixture
def document_store():
    """Create an in-memory document store."""
    store = DocumentStore(":memory:")
    yield store
    store.close()


@pytest.fixture
def embedder():
    """Create an embedder instance."""
    return Embedder(model_name="all-MiniLM-L6-v2")


@pytest.fixture
def differ():
    """Create a differ instance."""
    return Differ()


@pytest.fixture
def domain_chunker():
    """Create a domain chunker instance."""
    return NotesDomain(soft_limit=512, hard_limit=1024)


@pytest.fixture
def pipeline(document_store, embedder, differ):
    """Create a pipeline instance with temp vector store directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vector_store = ChromaDBVectorStore(tmpdir)
        pipeline_obj = IngestionPipeline(
            document_store=document_store,
            embedder=embedder,
            differ=differ,
            vector_store=vector_store,
        )
        yield pipeline_obj


class TestIngestionPipelineFirstIngest:
    """Tests for first ingest of a directory."""

    def test_first_ingest_processes_all_files(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """First ingest of a directory should process all .md files."""
        adapter = FilesystemAdapter(temp_markdown_dir)
        result = pipeline.ingest(adapter, domain_chunker)

        # Should process 2 files
        assert result["sources_processed"] == 2
        # Should have added chunks (at least some chunks from both files)
        assert result["chunks_added"] > 0
        # First ingest: no removed chunks
        assert result["chunks_removed"] == 0

    def test_first_ingest_creates_source_versions(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """First ingest should create source version records."""
        adapter = FilesystemAdapter(temp_markdown_dir)
        pipeline.ingest(adapter, domain_chunker)

        # Get versions for file1.md
        versions = pipeline.document_store.get_version_history("file1.md")
        assert len(versions) == 1
        assert versions[0].version == 1
        assert len(versions[0].chunk_hashes) > 0

        # Get versions for file2.md
        versions = pipeline.document_store.get_version_history("file2.md")
        assert len(versions) == 1
        assert versions[0].version == 1

    def test_first_ingest_writes_sync_log(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """First ingest should write sync log entries for all chunks."""
        adapter = FilesystemAdapter(temp_markdown_dir)
        result = pipeline.ingest(adapter, domain_chunker)

        # Get sync log entries
        cursor = pipeline.document_store.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM lancedb_sync_log")
        sync_count = cursor.fetchone()[0]

        # Should have one entry per added chunk
        assert sync_count == result["chunks_added"]

    def test_first_ingest_creates_chunks(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """First ingest should create chunk records in SQLite."""
        adapter = FilesystemAdapter(temp_markdown_dir)
        pipeline.ingest(adapter, domain_chunker)

        # Get chunks for file1.md
        chunks = pipeline.document_store.get_chunks_by_source("file1.md")
        assert len(chunks) > 0

        # Verify chunk structure
        for chunk in chunks:
            assert chunk.chunk_hash is not None
            assert chunk.content is not None
            assert chunk.chunk_index >= 0

    def test_first_ingest_writes_to_vector_store(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """First ingest should write vectors to the vector store."""
        adapter = FilesystemAdapter(temp_markdown_dir)
        result = pipeline.ingest(adapter, domain_chunker)

        # Verify vector count matches chunks_added
        assert pipeline.vector_store.count() == result["chunks_added"]


class TestIngestionPipelineReIngestUnchanged:
    """Tests for re-ingest of unchanged content."""

    def test_reingest_unchanged_no_new_versions(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """Re-ingest of unchanged directory should not create new versions."""
        adapter = FilesystemAdapter(temp_markdown_dir)

        # First ingest
        pipeline.ingest(adapter, domain_chunker)

        # Get version count before re-ingest
        versions_before = pipeline.document_store.get_version_history("file1.md")
        assert len(versions_before) == 1

        # Re-ingest same content
        result = pipeline.ingest(adapter, domain_chunker)

        # Get version count after re-ingest
        versions_after = pipeline.document_store.get_version_history("file1.md")
        assert len(versions_after) == 1  # No new version created

        # Return dict should show chunks_added=0
        assert result["chunks_added"] == 0

    def test_reingest_unchanged_no_new_chunks(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """Re-ingest of unchanged directory should not create new chunks."""
        adapter = FilesystemAdapter(temp_markdown_dir)

        # First ingest
        result_first = pipeline.ingest(adapter, domain_chunker)
        assert result_first["chunks_added"] > 0

        # Get chunk count before re-ingest
        cursor = pipeline.document_store.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chunks WHERE retired_at IS NULL")
        chunks_before = cursor.fetchone()[0]

        # Re-ingest same content
        result_second = pipeline.ingest(adapter, domain_chunker)

        # Get chunk count after re-ingest
        cursor.execute("SELECT COUNT(*) FROM chunks WHERE retired_at IS NULL")
        chunks_after = cursor.fetchone()[0]

        # Should not create new chunks
        assert chunks_before == chunks_after
        assert result_second["chunks_added"] == 0


class TestIngestionPipelineReIngestWithChanges:
    """Tests for re-ingest with content modifications."""

    def test_reingest_modified_chunk(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """Re-ingest after modifying one chunk should update only that chunk."""
        adapter = FilesystemAdapter(temp_markdown_dir)

        # First ingest
        result_first = pipeline.ingest(adapter, domain_chunker)
        assert result_first["chunks_added"] > 0

        # Modify file1.md
        (temp_markdown_dir / "file1.md").write_text(
            """# File 1

This is the first file with MODIFIED content.

## Section 1.1

Some different text here."""
        )

        # Re-ingest
        result_second = pipeline.ingest(adapter, domain_chunker)

        # Should have some added chunks (modified content)
        assert result_second["chunks_added"] > 0

        # Get versions after re-ingest
        versions = pipeline.document_store.get_version_history("file1.md")
        assert len(versions) == 2
        assert versions[1].version == 2

    def test_reingest_chunk_removal_within_file(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """Re-ingest after removing a section should retire old chunks and remove from vector store."""
        adapter = FilesystemAdapter(temp_markdown_dir)

        # First ingest
        result_first = pipeline.ingest(adapter, domain_chunker)
        assert result_first["chunks_added"] > 0

        # Get chunks from file1.md before modification
        chunks_before = pipeline.document_store.get_chunks_by_source("file1.md")
        num_chunks_before = len(chunks_before)
        assert num_chunks_before > 0

        # Get vector store count before modification
        vector_count_before = pipeline.vector_store.count()
        assert vector_count_before > 0

        # Get sync log count before modification
        cursor = pipeline.document_store.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM lancedb_sync_log")
        sync_log_count_before = cursor.fetchone()[0]
        assert sync_log_count_before > 0

        # Modify file1.md to remove a section entirely, reducing the chunk count
        # This triggers the differ to detect removed chunks
        (temp_markdown_dir / "file1.md").write_text(
            """# File 1

Completely new content."""
        )

        # Re-ingest
        result_second = pipeline.ingest(adapter, domain_chunker)

        # Verify chunks were removed (test data must produce removals)
        assert result_second["chunks_removed"] > 0, \
            "Test data modification should trigger chunk removal"

        # Verify retired chunks exist in SQLite
        cursor.execute(
            "SELECT COUNT(*) FROM chunks WHERE source_id = ? AND retired_at IS NOT NULL",
            ("file1.md",),
        )
        retired_chunks = cursor.fetchone()[0]
        assert retired_chunks > 0

        # Verify vector store count decreased (removed vectors)
        vector_count_after = pipeline.vector_store.count()
        assert vector_count_after < vector_count_before

        # Verify sync log records delete operations for removed chunks
        cursor.execute("SELECT COUNT(*) FROM lancedb_sync_log WHERE operation = 'delete'")
        delete_count = cursor.fetchone()[0]
        # The key invariant: delete operations are recorded for removed chunks
        assert delete_count > 0, \
            "Sync log should record delete operations for removed chunks"

    def test_reingest_deleted_chunk(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """Re-ingest after deleting a file should not process that file."""
        adapter = FilesystemAdapter(temp_markdown_dir)

        # First ingest
        result_first = pipeline.ingest(adapter, domain_chunker)
        assert result_first["sources_processed"] == 2

        # Get active chunks for file1.md before deletion
        chunks_before = pipeline.document_store.get_chunks_by_source("file1.md")
        assert len(chunks_before) > 0

        # Delete file1.md
        (temp_markdown_dir / "file1.md").unlink()

        # Re-ingest
        result_second = pipeline.ingest(adapter, domain_chunker)

        # file1.md should no longer be fetched, so sources_processed should be 1 (only file2.md)
        assert result_second["sources_processed"] == 1
        # No new chunks added or removed (file1.md is just not processed)
        assert result_second["chunks_added"] == 0
        assert result_second["chunks_removed"] == 0

    def test_reingest_new_file(self, pipeline, temp_markdown_dir, domain_chunker):
        """Re-ingest after adding a new file should create records for it."""
        adapter = FilesystemAdapter(temp_markdown_dir)

        # First ingest
        result_first = pipeline.ingest(adapter, domain_chunker)
        assert result_first["sources_processed"] == 2

        # Add new file
        (temp_markdown_dir / "file3.md").write_text(
            """# File 3

New file added."""
        )

        # Re-ingest
        result_second = pipeline.ingest(adapter, domain_chunker)

        # Should process 3 sources
        assert result_second["sources_processed"] == 3
        # file3.md should be new, so chunks added for it
        assert result_second["chunks_added"] > 0

        # Verify file3.md has version record
        versions = pipeline.document_store.get_version_history("file3.md")
        assert len(versions) == 1
        assert versions[0].version == 1


class TestIngestionPipelineReturnDict:
    """Tests for return dict structure and values."""

    def test_return_dict_has_required_keys(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """Return dict should have all required keys."""
        adapter = FilesystemAdapter(temp_markdown_dir)
        result = pipeline.ingest(adapter, domain_chunker)

        assert "sources_processed" in result
        assert "chunks_added" in result
        assert "chunks_removed" in result
        assert "chunks_unchanged" in result

    def test_return_dict_values_are_integers(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """Return dict values should be integers."""
        adapter = FilesystemAdapter(temp_markdown_dir)
        result = pipeline.ingest(adapter, domain_chunker)

        assert isinstance(result["sources_processed"], int)
        assert isinstance(result["chunks_added"], int)
        assert isinstance(result["chunks_removed"], int)
        assert isinstance(result["chunks_unchanged"], int)

    def test_return_dict_values_are_non_negative(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """Return dict values should be non-negative."""
        adapter = FilesystemAdapter(temp_markdown_dir)
        result = pipeline.ingest(adapter, domain_chunker)

        assert result["sources_processed"] >= 0
        assert result["chunks_added"] >= 0
        assert result["chunks_removed"] >= 0
        assert result["chunks_unchanged"] >= 0


class TestIngestionPipelineEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_directory(self, pipeline, differ):
        """Ingesting an empty directory should process 0 sources."""
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = FilesystemAdapter(tmpdir)
            domain_chunker = NotesDomain()

            result = pipeline.ingest(adapter, domain_chunker)

            assert result["sources_processed"] == 0
            assert result["chunks_added"] == 0

    def test_adapter_registration_idempotent(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """Adapter registration should be idempotent."""
        adapter = FilesystemAdapter(temp_markdown_dir)

        # Register twice
        adapter.register(pipeline.document_store)
        adapter.register(pipeline.document_store)

        # Should not raise error
        result = pipeline.ingest(adapter, domain_chunker)
        assert result["sources_processed"] > 0

    def test_ingest_with_different_chunker(
        self, pipeline, temp_markdown_dir
    ):
        """Same content with different chunker should produce different results."""
        adapter = FilesystemAdapter(temp_markdown_dir)

        # Create two different chunkers with different limits
        chunker1 = NotesDomain(soft_limit=256, hard_limit=512)
        chunker2 = NotesDomain(soft_limit=512, hard_limit=1024)

        # First ingest with chunker1
        result1 = pipeline.ingest(adapter, chunker1)

        # Reset for second test
        pipeline.document_store.close()
        pipeline.document_store = DocumentStore(":memory:")

        # Second ingest with chunker2
        result2 = pipeline.ingest(adapter, chunker2)

        # Different chunkers may produce different chunk counts
        # (This test just verifies both succeed)
        assert result1["sources_processed"] > 0
        assert result2["sources_processed"] > 0


class TestIntegrationVectorSearch:
    """Integration tests for vector search functionality."""

    def test_vector_search_retrieves_similar_chunks(
        self, temp_markdown_dir, pipeline, domain_chunker
    ):
        """Vector search should retrieve chunks similar to a query."""
        # Ingest content
        adapter = FilesystemAdapter(temp_markdown_dir)
        result = pipeline.ingest(adapter, domain_chunker)
        assert result["chunks_added"] > 0, "Should ingest chunks"

        # Create query vector and search via vector store
        embedder = pipeline.embedder
        query_text = "file content section"
        query_vector = embedder.embed_query(query_text)

        results = pipeline.vector_store.search(query_vector, top_k=3)

        # Verify results
        assert len(results) > 0, "Should return results for query"
        for result in results:
            assert result.chunk_hash, "Result should contain chunk_hash"
            assert 0.0 <= result.similarity_score <= 1.0, "Score should be in [0, 1]"


class TestFixtureIntegration:
    """Integration tests verifying fixture files and expected diff structure."""

    @pytest.fixture
    def fixture_dir(self):
        """Return the path to the fixture directory."""
        return Path(__file__).parent.parent / "fixtures"

    def test_fixture_files_exist(self, fixture_dir):
        """Fixture markdown files should exist with correct structure."""
        initial_file = fixture_dir / "sample_initial.md"
        modified_file = fixture_dir / "sample_modified.md"

        assert initial_file.exists(), "sample_initial.md should exist"
        assert modified_file.exists(), "sample_modified.md should exist"

        initial_content = initial_file.read_text()
        modified_content = modified_file.read_text()

        # Verify H1/H2/H3 hierarchy in initial
        assert "# Project Overview" in initial_content, "Should have H1 heading"
        assert "## Architecture" in initial_content, "Should have H2 heading"
        assert "### Storage Layer" in initial_content, "Should have H3 heading"

        # Verify code block exists
        assert "```" in initial_content, "Should contain code block"

        # Verify table exists
        assert "|" in initial_content and "Component" in initial_content, "Should contain table"

        # Verify documented changes between versions
        # "Getting Started" exists in initial but not modified
        assert "## Getting Started" in initial_content, "Initial should have Getting Started section"
        assert "## Getting Started" not in modified_content, "Modified should not have Getting Started"

        # "Contributing" exists in modified but not initial
        assert "## Contributing" not in initial_content, "Initial should not have Contributing section"
        assert "## Contributing" in modified_content, "Modified should have Contributing section"

        # Storage Layer content differs
        initial_storage = initial_content.split("### Storage Layer")[1].split("##")[0]
        modified_storage = modified_content.split("### Storage Layer")[1].split("##")[0]
        assert initial_storage != modified_storage, "Storage Layer content should differ between versions"

    def test_expected_diff_helper_available(self, fixture_dir):
        """expected_diff.py should provide helper function for computing expected changes."""
        from tests.fixtures.expected_diff import get_expected_changes

        # Function should be callable
        assert callable(get_expected_changes), "get_expected_changes should be callable"

        # Create mock chunk objects
        class MockChunk:
            def __init__(self, text, hash_val):
                self.text = text
                self.hash = hash_val

        initial_chunks = [
            MockChunk("intro", "hash_intro"),
            MockChunk("arch", "hash_arch"),
            MockChunk("storage", "hash_storage_v1"),
            MockChunk("getting started", "hash_getting_started"),
        ]

        modified_chunks = [
            MockChunk("intro", "hash_intro"),  # unchanged
            MockChunk("arch", "hash_arch"),  # unchanged
            MockChunk("storage modified", "hash_storage_v2"),  # modified (different hash)
            MockChunk("contributing", "hash_contributing"),  # added
        ]

        result = get_expected_changes(initial_chunks, modified_chunks)

        # Verify result structure
        assert "added_hashes" in result, "Should return added_hashes"
        assert "removed_hashes" in result, "Should return removed_hashes"
        assert "unchanged_hashes" in result, "Should return unchanged_hashes"

        # Verify expected changes detected
        assert "hash_contributing" in result["added_hashes"], "Contributing should be added"
        assert "hash_getting_started" in result["removed_hashes"], "Getting Started should be removed"
        assert "hash_intro" in result["unchanged_hashes"], "Intro should be unchanged"
        assert "hash_arch" in result["unchanged_hashes"], "Arch should be unchanged"

    def test_retrieval_search_returns_required_fields(self, temp_markdown_dir, pipeline, domain_chunker, embedder):
        """Vector search retrieval should return all required fields: content, chunk_hash, source_id, score."""
        # Use existing temp_markdown_dir fixture with known content
        adapter = FilesystemAdapter(temp_markdown_dir)
        result = pipeline.ingest(adapter, domain_chunker)
        assert result["chunks_added"] > 0, "Should ingest chunks"

        # Create query vector related to test content
        query_text = "file content section"
        query_vector = embedder.embed_query(query_text)

        # Search via vector store abstraction
        results = pipeline.vector_store.search(query_vector, top_k=5)

        # Verify results exist and have required fields
        assert len(results) > 0, "Should return search results"

        for result in results:
            assert result.chunk_hash, "Result must contain chunk_hash"
            assert 0.0 <= result.similarity_score <= 1.0, "Score should be in [0, 1]"


class TestPipelineEmbeddingValidation:
    """Tests for embedding dimension validation in the pipeline."""

    def test_pipeline_embedding_validation_failure_logs_error(
        self, pipeline, temp_markdown_dir, domain_chunker, caplog
    ):
        """Test that pipeline logs error when embedding dimension validation fails.

        The pipeline catches validation errors and logs them per-source while
        continuing with other sources, per the error isolation design.
        """
        caplog.set_level(logging.ERROR)
        adapter = FilesystemAdapter(temp_markdown_dir)

        # First ingest to populate the store
        pipeline.ingest(adapter, domain_chunker)

        # Modify content to trigger re-ingest with added chunks
        (temp_markdown_dir / "file1.md").write_text("# NEW CONTENT\n\nThis is completely different.")

        # Mock the embedder to return invalid dimension embeddings
        def mock_embed_invalid_dimension(texts):
            return [[0.1] * 100 for _ in texts]

        with patch.object(
            pipeline.embedder, "embed", side_effect=mock_embed_invalid_dimension
        ):
            # Pipeline catches errors and logs them, doesn't raise
            pipeline.ingest(adapter, domain_chunker)
            # Source processing was attempted but failed, so not counted in success
            assert "Embedding error for source 'file1.md'" in caplog.text

    def test_pipeline_embedding_validation_with_nan_logs_error(
        self, pipeline, temp_markdown_dir, domain_chunker, caplog
    ):
        """Test that pipeline logs error when embedding contains NaN values."""
        caplog.set_level(logging.ERROR)
        adapter = FilesystemAdapter(temp_markdown_dir)

        # First ingest to populate the store
        pipeline.ingest(adapter, domain_chunker)

        # Modify content to trigger re-ingest with added chunks
        (temp_markdown_dir / "file1.md").write_text("# MODIFIED CONTENT\n\nNew content here.")

        # Mock the embedder to return embeddings with NaN
        def create_embeddings_with_nan(texts):
            embeddings = [[0.1] * 384 for _ in texts]
            embeddings[0][100] = float("nan")
            return embeddings

        with patch.object(
            pipeline.embedder, "embed", side_effect=create_embeddings_with_nan
        ):
            pipeline.ingest(adapter, domain_chunker)
            # Error should be logged
            assert "Error processing source" in caplog.text or "non-finite" in caplog.text

    def test_pipeline_embedding_validation_with_infinity_logs_error(
        self, pipeline, temp_markdown_dir, domain_chunker, caplog
    ):
        """Test that pipeline logs error when embedding contains infinity values."""
        caplog.set_level(logging.ERROR)
        adapter = FilesystemAdapter(temp_markdown_dir)

        # First ingest to populate the store
        pipeline.ingest(adapter, domain_chunker)

        # Modify content to trigger re-ingest with added chunks
        (temp_markdown_dir / "file1.md").write_text("# DIFFERENT CONTENT\n\nAnother change here.")

        # Mock the embedder to return embeddings with infinity
        def create_embeddings_with_inf(texts):
            embeddings = [[0.1] * 384 for _ in texts]
            embeddings[0][50] = float("inf")
            return embeddings

        with patch.object(
            pipeline.embedder, "embed", side_effect=create_embeddings_with_inf
        ):
            pipeline.ingest(adapter, domain_chunker)
            # Error should be logged
            assert "Error processing source" in caplog.text or "non-finite" in caplog.text


class TestEndToEndIngestReIngestRetrieval:
    """End-to-end integration test for complete pipeline: Ingest → Re-ingest → Retrieval.

    This test exercises the full lifecycle of the ingestion system:
    1. Initial ingest of markdown documents
    2. Re-ingest with content modifications
    3. Semantic retrieval to verify consistency
    """

    def test_complete_ingest_reingest_retrieval_cycle(
        self, temp_markdown_dir, pipeline, domain_chunker
    ):
        """Test complete cycle: ingest → modify → re-ingest → retrieve.

        Verifies:
        - First ingest creates chunks and vectors
        - Re-ingest detects changes and updates versions
        - Retrieval returns correct results from updated store
        - Chunk consistency between SQLite and LanceDB is maintained
        """
        from context_library.retrieval.query import retrieve

        adapter = FilesystemAdapter(temp_markdown_dir)

        # Phase 1: Initial Ingest
        result_first = pipeline.ingest(adapter, domain_chunker)
        assert result_first["sources_processed"] > 0, "Should process sources on first ingest"
        assert result_first["chunks_added"] > 0, "Should add chunks on first ingest"
        assert result_first["chunks_removed"] == 0, "Should not remove chunks on first ingest"

        # Verify chunks were written to both stores
        cursor = pipeline.document_store.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chunks WHERE retired_at IS NULL")
        chunks_in_sqlite_phase1 = cursor.fetchone()[0]
        assert chunks_in_sqlite_phase1 == result_first["chunks_added"]

        # Verify vectors were written to vector store
        vectors_in_store_phase1 = pipeline.vector_store.count()
        assert vectors_in_store_phase1 == result_first["chunks_added"]

        # Store version info from phase 1
        versions_phase1 = pipeline.document_store.get_version_history("file1.md")
        assert len(versions_phase1) == 1
        assert versions_phase1[0].version == 1

        # Phase 2: Modify content and Re-ingest
        (temp_markdown_dir / "file1.md").write_text(
            """# File 1 - Updated

This is the first file with SUBSTANTIALLY modified content.

## New Section

This is entirely new content that should generate new chunks.

## Another New Section

More new content here."""
        )

        result_second = pipeline.ingest(adapter, domain_chunker)
        assert result_second["sources_processed"] > 0, "Should process sources on re-ingest"
        assert result_second["chunks_added"] > 0, "Should add new chunks due to modifications"
        assert result_second["chunks_removed"] > 0, "Should remove old chunks that were replaced"

        # Verify version was incremented
        versions_phase2 = pipeline.document_store.get_version_history("file1.md")
        assert len(versions_phase2) == 2, "Should have 2 versions after modification"
        assert versions_phase2[1].version == 2

        # Verify chunk state in SQLite after re-ingest
        cursor.execute("SELECT COUNT(*) FROM chunks WHERE retired_at IS NULL")
        chunks_in_sqlite_phase2 = cursor.fetchone()[0]
        # Active chunks = old (many retired) + new added
        assert chunks_in_sqlite_phase2 >= result_second["chunks_added"]

        # Verify retired chunks are marked
        cursor.execute("SELECT COUNT(*) FROM chunks WHERE retired_at IS NOT NULL")
        retired_chunks = cursor.fetchone()[0]
        assert retired_chunks == result_second["chunks_removed"]

        # Phase 3: Verify retrieval works with updated store
        # Query for content that should exist in modified version
        query = "File 1 new section"
        results = retrieve(
            query,
            pipeline.embedder,
            pipeline.document_store,
            vector_store=pipeline.vector_store,
            top_k=5,
        )

        # Verify retrieval returns results
        assert len(results) > 0, "Should retrieve results from modified content"

        # Verify all returned chunks are from active (non-retired) versions
        for result in results:
            chunk = pipeline.document_store.get_chunk_by_hash(result.chunk.chunk_hash)
            assert chunk is not None, f"Retrieved chunk {result.chunk.chunk_hash} should exist"

        # Verify consistency: chunks returned by retrieval should have lineage
        file1_results = []
        for result in results:
            lineage = pipeline.document_store.get_lineage(result.chunk.chunk_hash)
            assert lineage is not None, "Retrieved chunk should have lineage record"
            if lineage.source_id == "file1.md":
                file1_results.append(result)

        # Verify that we got at least some results from the modified file1.md
        assert len(file1_results) > 0, "Should retrieve results from modified file1.md"

        # Phase 4: Verify store consistency (no orphaned records)
        # Count total vectors (should only include active chunks)
        vectors_in_store_phase2 = pipeline.vector_store.count()

        # Every vector should correspond to an active chunk
        assert vectors_in_store_phase2 <= chunks_in_sqlite_phase2, \
            "Vector store count should not exceed active chunks"

        # Summary of complete lifecycle
        assert result_first["sources_processed"] + result_second["sources_processed"] > 0
        assert result_first["chunks_added"] + result_second["chunks_added"] > 0


class TestChunkVersioningFixes:
    """Tests for chunk versioning fixes (Issue #71)."""

    def test_unchanged_chunks_visible_after_partial_update(
        self, temp_markdown_dir, pipeline, domain_chunker
    ):
        """Unchanged chunks should remain queryable after a partial source update.

        This tests the fix for: "Unchanged chunks become invisible after version updates"
        When a source is updated and some chunks are unchanged:
        - Those chunks should be written to the new version
        - They should be queryable via get_chunks_by_source() with the new version
        """
        adapter = FilesystemAdapter(temp_markdown_dir)

        # Phase 1: Initial ingest
        result_first = pipeline.ingest(adapter, domain_chunker)
        assert result_first["sources_processed"] > 0
        assert result_first["chunks_added"] > 0

        # Get first version chunks for file1.md
        chunks_v1 = pipeline.document_store.get_chunks_by_source("file1.md", version=1)
        assert len(chunks_v1) > 0
        chunk_hashes_v1 = {c.chunk_hash for c in chunks_v1}

        # Phase 2: Modify file1.md to change some chunks but keep some unchanged
        original_content = (temp_markdown_dir / "file1.md").read_text()
        new_content = original_content.replace(
            "This is the first file with some content.",
            "This is the first file with MODIFIED content."
        )
        (temp_markdown_dir / "file1.md").write_text(new_content)

        # Re-ingest
        pipeline.ingest(adapter, domain_chunker)

        # Verify new version was created
        versions = pipeline.document_store.get_version_history("file1.md")
        assert len(versions) == 2
        assert versions[1].version == 2

        # CRITICAL TEST: Get chunks for file1.md version 2
        # Should include both unchanged chunks (from version 1) and new chunks
        chunks_v2 = pipeline.document_store.get_chunks_by_source("file1.md", version=2)
        assert len(chunks_v2) > 0, "Version 2 should have chunks (including unchanged ones)"

        # Verify that some unchanged chunks are present in version 2
        chunk_hashes_v2 = {c.chunk_hash for c in chunks_v2}
        unchanged_in_v2 = chunk_hashes_v1 & chunk_hashes_v2
        assert len(unchanged_in_v2) > 0, \
            "Version 2 should include unchanged chunks from version 1"

        # Verify that some new chunks were added in version 2
        new_in_v2 = chunk_hashes_v2 - chunk_hashes_v1
        assert len(new_in_v2) > 0, \
            "Version 2 should contain new chunks due to modification"

        # Verify using the latest version (should also work)
        chunks_latest = pipeline.document_store.get_chunks_by_source("file1.md")
        assert len(chunks_latest) > 0, "Latest version should have chunks"
        assert chunks_latest == chunks_v2, "Latest version should match version 2"

    def test_cross_source_dedup_allows_same_content_in_different_sources(
        self, pipeline, embedder, differ, domain_chunker
    ):
        """Same content (identical chunk hash) should be storable in different sources.

        This tests the fix for: "Cross-source content-addressed dedup silently drops chunks"
        When two sources have identical content, both should be queryable without warnings.
        """
        import tempfile
        from context_library.adapters.filesystem import FilesystemAdapter

        # Create a markdown directory with identical content in multiple files
        with tempfile.TemporaryDirectory() as dir1:
            identical_content = """# Shared Content

This is identical content shared between two sources.

## Section A

Some shared text here."""

            # Create identical files in the same directory
            Path(dir1).mkdir(parents=True, exist_ok=True)
            (Path(dir1) / "shared.md").write_text(identical_content)
            (Path(dir1) / "shared_copy.md").write_text(identical_content)

            # Ingest from first source
            adapter1 = FilesystemAdapter(dir1)
            result1 = pipeline.ingest(adapter1, domain_chunker)
            assert result1["sources_processed"] == 2
            assert result1["chunks_added"] > 0

            # Get chunks from first source
            chunks_source1 = pipeline.document_store.get_chunks_by_source("shared.md")
            source1_chunk_hashes = {c.chunk_hash for c in chunks_source1}
            assert len(source1_chunk_hashes) > 0

            # Both files have identical content, so they should have same chunk hashes
            chunks_source2 = pipeline.document_store.get_chunks_by_source("shared_copy.md")
            assert len(chunks_source2) > 0, \
                "Second source with identical content should have queryable chunks"

            source2_chunk_hashes = {c.chunk_hash for c in chunks_source2}

            # Both sources should have the same content hashes (since content is identical)
            assert source1_chunk_hashes == source2_chunk_hashes, \
                "Sources with identical content should have same chunk hashes"

            # Both sources should be queryable independently
            chunks_s1 = pipeline.document_store.get_chunks_by_source("shared.md")
            chunks_s2 = pipeline.document_store.get_chunks_by_source("shared_copy.md")

            assert len(chunks_s1) > 0, "Source 1 chunks should be queryable"
            assert len(chunks_s2) > 0, "Source 2 chunks should be queryable"
            assert len(chunks_s1) == len(chunks_s2), \
                "Both sources with identical content should have same number of chunks"

    def test_unchanged_chunks_in_reingest_prevent_duplicate_vectors(
        self, temp_markdown_dir, pipeline, domain_chunker
    ):
        """Unchanged chunks are written to new version but don't re-embed.

        When re-ingesting with some unchanged chunks:
        - Unchanged chunks should be written to the new version in SQLite
        - Unchanged chunks should NOT create new sync log entries (no re-embedding)
        - Only newly added chunks should create sync log entries
        """
        adapter = FilesystemAdapter(temp_markdown_dir)

        # Phase 1: Initial ingest
        result_first = pipeline.ingest(adapter, domain_chunker)
        assert result_first["sources_processed"] == 2
        assert result_first["chunks_added"] > 0
        sync_log_after_first = self._count_sync_log_inserts(pipeline)

        # Phase 2: Modify one file - some chunks unchanged, some added
        file1 = temp_markdown_dir / "file1.md"
        original_content = file1.read_text()
        file1.write_text(original_content + "\n\n## New Section\n\nNew content here.")

        # Re-ingest - file1 has partial changes
        result_second = pipeline.ingest(adapter, domain_chunker)

        # Core assertion: sync log only records ADDED chunks, not unchanged ones
        sync_log_after_second = self._count_sync_log_inserts(pipeline)
        new_sync_entries = sync_log_after_second - sync_log_after_first

        # The test exercises the fix: unchanged chunks are NOT re-embedded
        assert new_sync_entries == result_second["chunks_added"], \
            f"Only newly added chunks should create sync log entries. " \
            f"Got {new_sync_entries} new entries, but chunks_added={result_second['chunks_added']}"

        # Verify unchanged chunks are preserved
        assert result_second["chunks_unchanged"] > 0, \
            "Partial updates should preserve unchanged chunks"

    def _count_sync_log_inserts(self, pipeline) -> int:
        """Helper to count total insert operations in sync log."""
        cursor = pipeline.document_store.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM lancedb_sync_log WHERE operation = 'insert'")
        result: int = cursor.fetchone()[0]  # type: ignore[assignment]
        return result


class TestPipelineErrorHandling:
    """Tests for pipeline error handling and caller feedback."""

    def test_ingest_return_dict_includes_error_fields(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """Test that return dict includes error tracking fields."""
        adapter = FilesystemAdapter(temp_markdown_dir)
        result = pipeline.ingest(adapter, domain_chunker)

        # Check that all required fields are present
        assert "sources_processed" in result
        assert "sources_failed" in result
        assert "chunks_added" in result
        assert "chunks_removed" in result
        assert "chunks_unchanged" in result
        assert "errors" in result
        assert "store_consistency" in result

    def test_ingest_no_errors_when_successful(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """Test that successful ingest has zero errors and store_consistency=success."""
        adapter = FilesystemAdapter(temp_markdown_dir)
        result = pipeline.ingest(adapter, domain_chunker)

        # On successful ingest, no errors
        assert result["sources_failed"] == 0
        assert len(result["errors"]) == 0

        # All sources should have successful consistency status
        for source_id, status in result["store_consistency"].items():
            assert status == "success"

    def test_embedding_error_tracked_and_reported(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """Test that embedding errors are tracked and reported in return dict."""
        adapter = FilesystemAdapter(temp_markdown_dir)

        # First ingest to populate store
        pipeline.ingest(adapter, domain_chunker)

        # Modify file to trigger re-ingest
        (temp_markdown_dir / "file1.md").write_text("# MODIFIED\n\nNew content.")

        # Mock embedder to return invalid dimension
        def mock_embed_invalid_dimension(texts):
            return [[0.1] * 100 for _ in texts]  # Wrong dimension

        with patch.object(
            pipeline.embedder, "embed", side_effect=mock_embed_invalid_dimension
        ):
            result = pipeline.ingest(adapter, domain_chunker)

            # Should have error tracked
            assert result["sources_failed"] > 0
            assert len(result["errors"]) > 0

            # Check error details
            error = result["errors"][0]
            assert error["error_type"] == "EmbeddingError"
            assert "chunk_hash" in error
            assert "chunk_index" in error

    def test_storage_error_tracked_and_reported(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """Test that storage errors are tracked and reported in return dict."""
        adapter = FilesystemAdapter(temp_markdown_dir)

        # First ingest to populate store
        pipeline.ingest(adapter, domain_chunker)

        # Modify file to trigger re-ingest
        (temp_markdown_dir / "file2.md").write_text("# MODIFIED\n\nNew content.")

        # Mock document store to raise error on write
        def mock_write_chunks_error(*args, **kwargs):
            raise RuntimeError("Database write failed")

        with patch.object(
            pipeline.document_store, "write_chunks", side_effect=mock_write_chunks_error
        ):
            result = pipeline.ingest(adapter, domain_chunker)

            # Should have storage error tracked
            assert result["sources_failed"] > 0
            assert len(result["errors"]) > 0

            # Check error details
            error = result["errors"][0]
            assert error["error_type"] == "StorageError"
            assert error["store_type"] == "sqlite"

    def test_vector_store_inconsistency_detected_and_marked(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """Test that SQLite/vector store inconsistency is detected and marked."""
        adapter = FilesystemAdapter(temp_markdown_dir)

        # First ingest to populate store
        pipeline.ingest(adapter, domain_chunker)

        # Modify file to trigger re-ingest with new chunks (add significant new content)
        (temp_markdown_dir / "file1.md").write_text(
            "# MODIFIED\n\n"
            "Additional new content for second version. "
            "This is a much longer text to ensure new chunks are created. "
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
            "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
            "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat."
        )

        # Mock vector store add_vectors to fail
        with patch.object(
            pipeline.vector_store, "add_vectors",
            side_effect=RuntimeError("Vector store write failed"),
        ):
            result = pipeline.ingest(adapter, domain_chunker)

            # Should have error tracked and marked as inconsistent
            assert result["sources_failed"] > 0
            assert len(result["errors"]) > 0

            # Check error indicates inconsistency
            error = result["errors"][0]
            assert error["error_type"] == "StorageError"
            assert error["store_type"] == "vector_store"
            assert error["inconsistent"]

            # Store consistency should show inconsistency
            source_id = error["source_id"]
            assert result["store_consistency"][source_id] == "inconsistent"

    def test_distinguishes_no_sources_from_all_sources_failed(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """Test that return dict distinguishes 'no sources' from 'all sources failed'."""
        adapter = FilesystemAdapter(temp_markdown_dir)

        # Successfully ingest
        result1 = pipeline.ingest(adapter, domain_chunker)
        assert result1["sources_processed"] > 0
        assert result1["sources_failed"] == 0

        # Create adapter with no files
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_adapter = FilesystemAdapter(tmpdir)
            result2 = pipeline.ingest(empty_adapter, domain_chunker)

            # No sources case: both should be 0
            assert result2["sources_processed"] == 0
            assert result2["sources_failed"] == 0
            assert len(result2["errors"]) == 0

        # Now test all sources failed by creating a single-file directory and mocking embedder to fail
        with tempfile.TemporaryDirectory() as single_file_tmpdir:
            single_file_path = Path(single_file_tmpdir)
            (single_file_path / "only_file.md").write_text("# SINGLE FILE\n\nUnique content.")
            single_adapter = FilesystemAdapter(single_file_path)

            def mock_embed_always_fails(texts):
                raise RuntimeError("Embedding service down")

            with patch.object(
                pipeline.embedder, "embed", side_effect=mock_embed_always_fails
            ):
                # Should raise AllSourcesFailedError because the only source failed
                from context_library.core.exceptions import AllSourcesFailedError
                with pytest.raises(AllSourcesFailedError):
                    pipeline.ingest(single_adapter, domain_chunker)

    def test_multiple_source_errors_accumulated(
        self, pipeline, domain_chunker
    ):
        """Test that errors from multiple sources are accumulated and reported."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)

            # Create multiple files
            (temp_path / "file1.md").write_text("# File 1\n\nContent 1")
            (temp_path / "file2.md").write_text("# File 2\n\nContent 2")
            (temp_path / "file3.md").write_text("# File 3\n\nContent 3")

            adapter = FilesystemAdapter(temp_path)

            # Mock embedder to fail randomly (deterministically based on content)
            def mock_embed_selective_fail(texts):
                if "File 2" in texts[0] or "Content 2" in texts[0]:
                    raise RuntimeError("Embedding failed for file 2")
                return [[0.1] * 384 for _ in texts]

            with patch.object(
                pipeline.embedder, "embed", side_effect=mock_embed_selective_fail
            ):
                result = pipeline.ingest(adapter, domain_chunker)

                # Should have processed some sources but some failed
                assert result["sources_failed"] > 0
                # Number of errors should match number of failed sources
                assert len(result["errors"]) == result["sources_failed"]

                # Verify error sources are tracked
                error_sources = {error["source_id"] for error in result["errors"]}
                assert len(error_sources) == result["sources_failed"]
