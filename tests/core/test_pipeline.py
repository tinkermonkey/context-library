"""Tests for the pipeline module."""

import tempfile
from pathlib import Path

import lancedb
import pytest

from context_library.adapters.filesystem import FilesystemAdapter
from context_library.core.differ import Differ
from context_library.core.embedder import Embedder
from context_library.core.pipeline import IngestionPipeline
from context_library.domains.notes import NotesDomain
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
    """Create a pipeline instance with temp LanceDB directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pipeline_obj = IngestionPipeline(
            document_store=document_store,
            embedder=embedder,
            differ=differ,
            vector_store_path=tmpdir,
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

    def test_first_ingest_writes_to_lancedb(
        self, pipeline, temp_markdown_dir, domain_chunker
    ):
        """First ingest should write vectors to LanceDB."""
        adapter = FilesystemAdapter(temp_markdown_dir)
        result = pipeline.ingest(adapter, domain_chunker)

        # Open LanceDB and verify vectors were written
        db = lancedb.connect(str(pipeline.vector_store_path))
        tables = db.list_tables().tables
        assert "chunk_vectors" in tables

        # Verify row count matches chunks_added
        table = db.open_table("chunk_vectors")
        assert table.count_rows() == result["chunks_added"]


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
        """Re-ingest after removing a section should retire old chunks and remove from LanceDB."""
        adapter = FilesystemAdapter(temp_markdown_dir)

        # First ingest
        result_first = pipeline.ingest(adapter, domain_chunker)
        assert result_first["chunks_added"] > 0

        # Get chunks from file1.md before modification
        chunks_before = pipeline.document_store.get_chunks_by_source("file1.md")
        num_chunks_before = len(chunks_before)
        assert num_chunks_before > 0

        # Get LanceDB row count before modification
        db = lancedb.connect(str(pipeline.vector_store_path))
        table = db.open_table("chunk_vectors")
        lancedb_count_before = table.count_rows()
        assert lancedb_count_before > 0

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

        # Verify LanceDB row count decreased (removed vectors)
        db = lancedb.connect(str(pipeline.vector_store_path))
        table = db.open_table("chunk_vectors")
        lancedb_count_after = table.count_rows()
        assert lancedb_count_after < lancedb_count_before

        # Verify sync log was updated: removed chunks are deleted from sync_log
        cursor.execute("SELECT COUNT(*) FROM lancedb_sync_log")
        sync_log_count_after = cursor.fetchone()[0]
        # The key invariant: sync log entries for removed chunks are deleted
        # Since we removed chunks and added fewer replacements, sync log should shrink
        assert sync_log_count_after < sync_log_count_before, \
            f"Sync log should shrink when chunks are removed (before: {sync_log_count_before}, after: {sync_log_count_after})"

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

        # Create query vector
        embedder = pipeline.embedder
        query_text = "file content section"
        query_vector = embedder.embed_query(query_text)

        # Search LanceDB
        db = lancedb.connect(str(pipeline.vector_store_path))
        table = db.open_table("chunk_vectors")
        results = table.search(query_vector).limit(3).to_list()

        # Verify results
        assert len(results) > 0, "Should return results for query"
        for result in results:
            assert "content" in result, "Result should contain content"
            assert "chunk_hash" in result, "Result should contain chunk_hash"
            assert "source_id" in result, "Result should contain source_id"
            assert "_distance" in result or "score" in result, (
                "Result should contain relevance score"
            )


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

        # Search LanceDB
        db = lancedb.connect(str(pipeline.vector_store_path))
        table = db.open_table("chunk_vectors")
        results = table.search(query_vector).limit(5).to_list()

        # Verify results exist and have required fields
        assert len(results) > 0, "Should return search results"

        for result in results:
            # LanceDB returns these exact field names
            assert "content" in result, "Result must contain 'content' field"
            assert "chunk_hash" in result, "Result must contain 'chunk_hash' field"
            assert "source_id" in result, "Result must contain 'source_id' field"
            # LanceDB returns similarity as "_distance" for vector search
            assert "_distance" in result, "Result must contain '_distance' score field"
