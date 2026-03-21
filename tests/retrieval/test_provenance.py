"""Tests for the provenance module.

Covers:
- get_version_diff: hash-set diffing between source versions
- get_source_timeline: complete version history for a source
- trace_chunk_provenance: complete provenance tracing with lineage, source info, and version chain
- Error handling for missing chunks, sources, and lineage
- Version chain ordering (oldest-first)
"""

import os
import tempfile
import pytest
import time

from context_library.retrieval.provenance import (
    get_version_diff,
    get_source_timeline,
    trace_chunk_provenance,
)
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import (
    AdapterConfig,
    Chunk,
    ChunkProvenance,
    ChunkType,
    Domain,
    LineageRecord,
    SourceTimeline,
    VersionDiff,
)


@pytest.fixture
def store() -> DocumentStore:
    """Create an in-memory DocumentStore for testing."""
    # Use file-based DB to support multi-threaded access
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_path = temp_file.name
    temp_file.close()
    store_obj = DocumentStore(temp_path)
    yield store_obj
    store_obj.close()
    try:
        os.unlink(temp_path)
    except OSError:
        pass


def _make_hash(char: str) -> str:
    """Create a valid SHA-256 hex hash by repeating a hex character.

    Args:
        char: A single hex character (0-9, a-f).

    Returns:
        A 64-character valid SHA-256 hex string.
    """
    return char * 64


class TestGetVersionDiff:
    """Tests for get_version_diff function."""

    def test_get_version_diff_basic(self, store: DocumentStore) -> None:
        """Test basic version diff between two versions."""
        # Register adapter and source
        adapter_config = AdapterConfig(
            adapter_id="test-adapter",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0",
        )
        store.register_adapter(adapter_config)
        store.register_source(
            source_id="test-source",
            adapter_id="test-adapter",
            domain=Domain.NOTES,
            origin_ref="test://origin",
        )

        # Create version 1 with chunks a, b, c
        hash_a = _make_hash("a")
        hash_b = _make_hash("b")
        hash_c = _make_hash("c")
        store.create_source_version(
            source_id="test-source",
            version=1,
            markdown="content v1",
            chunk_hashes=[hash_a, hash_b, hash_c],
            adapter_id="test-adapter",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-01T00:00:00Z",
        )

        # Create version 2 with chunks b, c, d (added d, removed a)
        hash_d = _make_hash("d")
        store.create_source_version(
            source_id="test-source",
            version=2,
            markdown="content v2",
            chunk_hashes=[hash_b, hash_c, hash_d],
            adapter_id="test-adapter",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-02T00:00:00Z",
        )

        # Test diff
        diff = get_version_diff(store, "test-source", 1, 2)
        assert isinstance(diff, VersionDiff)
        assert diff.source_id == "test-source"
        assert diff.from_version == 1
        assert diff.to_version == 2
        assert diff.added_hashes == frozenset({hash_d})
        assert diff.removed_hashes == frozenset({hash_a})
        assert diff.unchanged_hashes == frozenset({hash_b, hash_c})

    def test_get_version_diff_no_changes(self, store: DocumentStore) -> None:
        """Test diff when versions are identical."""
        adapter_config = AdapterConfig(
            adapter_id="test-adapter",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0",
        )
        store.register_adapter(adapter_config)
        store.register_source(
            source_id="test-source",
            adapter_id="test-adapter",
            domain=Domain.NOTES,
            origin_ref="test://origin",
        )

        hash_a = _make_hash("a")
        hash_b = _make_hash("b")

        # Create version 1
        store.create_source_version(
            source_id="test-source",
            version=1,
            markdown="content",
            chunk_hashes=[hash_a, hash_b],
            adapter_id="test-adapter",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-01T00:00:00Z",
        )

        # Create version 2 with same content
        store.create_source_version(
            source_id="test-source",
            version=2,
            markdown="content",
            chunk_hashes=[hash_a, hash_b],
            adapter_id="test-adapter",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-02T00:00:00Z",
        )

        diff = get_version_diff(store, "test-source", 1, 2)
        assert diff.added_hashes == frozenset()
        assert diff.removed_hashes == frozenset()
        assert diff.unchanged_hashes == frozenset({hash_a, hash_b})


class TestGetSourceTimeline:
    """Tests for get_source_timeline function."""

    def test_get_source_timeline_multiple_versions(self, store: DocumentStore) -> None:
        """Test timeline with multiple versions in order."""
        adapter_config = AdapterConfig(
            adapter_id="test-adapter",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0",
        )
        store.register_adapter(adapter_config)
        store.register_source(
            source_id="test-source",
            adapter_id="test-adapter",
            domain=Domain.NOTES,
            origin_ref="test://origin",
        )

        # Create three versions
        for i in range(1, 4):
            hash_val = _make_hash(str(i % 16))
            store.create_source_version(
                source_id="test-source",
                version=i,
                markdown=f"content v{i}",
                chunk_hashes=[hash_val],
                adapter_id="test-adapter",
                normalizer_version="1.0",
                fetch_timestamp=f"2024-01-0{i}T00:00:00Z",
            )

        timeline = get_source_timeline(store, "test-source")
        assert isinstance(timeline, SourceTimeline)
        assert timeline.source_id == "test-source"
        assert len(timeline.versions) == 3
        # Verify ordering: versions should be chronological
        assert timeline.versions[0].version == 1
        assert timeline.versions[1].version == 2
        assert timeline.versions[2].version == 3

    def test_get_source_timeline_nonexistent_source(self, store: DocumentStore) -> None:
        """Test timeline for nonexistent source raises ValueError."""
        with pytest.raises(ValueError):
            get_source_timeline(store, "nonexistent-source")

    def test_get_source_timeline_single_version(self, store: DocumentStore) -> None:
        """Test timeline with single version."""
        adapter_config = AdapterConfig(
            adapter_id="test-adapter",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0",
        )
        store.register_adapter(adapter_config)
        store.register_source(
            source_id="test-source",
            adapter_id="test-adapter",
            domain=Domain.NOTES,
            origin_ref="test://origin",
        )

        hash_a = _make_hash("a")
        store.create_source_version(
            source_id="test-source",
            version=1,
            markdown="content",
            chunk_hashes=[hash_a],
            adapter_id="test-adapter",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-01T00:00:00Z",
        )

        timeline = get_source_timeline(store, "test-source")
        assert len(timeline.versions) == 1
        assert timeline.versions[0].version == 1


class TestTraceChunkProvenance:
    """Tests for trace_chunk_provenance function."""

    def test_trace_chunk_provenance_basic(self, store: DocumentStore) -> None:
        """Test basic chunk provenance tracing."""
        # Setup
        adapter_config = AdapterConfig(
            adapter_id="test-adapter",
            adapter_type="gmail",
            domain=Domain.MESSAGES,
            normalizer_version="1.0",
        )
        store.register_adapter(adapter_config)
        store.register_source(
            source_id="test-source",
            adapter_id="test-adapter",
            domain=Domain.MESSAGES,
            origin_ref="user@gmail.com",
        )

        hash_a = _make_hash("a")
        version_id = store.create_source_version(
            source_id="test-source",
            version=1,
            markdown="test content",
            chunk_hashes=[hash_a],
            adapter_id="test-adapter",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-01T00:00:00Z",
        )

        chunk_a = Chunk(
            chunk_hash=hash_a,
            content="test content",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
        )

        lineage = [
            LineageRecord(
                chunk_hash=hash_a,
                source_id="test-source",
                source_version_id=version_id,
                adapter_id="test-adapter",
                domain=Domain.MESSAGES,
                normalizer_version="1.0",
                embedding_model_id="test-model",
            ),
        ]

        store.write_chunks([chunk_a], lineage)

        # Trace provenance
        provenance = trace_chunk_provenance(store, hash_a)
        assert isinstance(provenance, ChunkProvenance)
        assert provenance.chunk.chunk_hash == hash_a
        assert provenance.lineage.source_id == "test-source"
        assert provenance.source_origin_ref == "user@gmail.com"
        assert provenance.adapter_type == "gmail"
        assert len(provenance.version_chain) > 0

    def test_trace_chunk_provenance_version_chain_single_chunk(
        self, store: DocumentStore
    ) -> None:
        """Test provenance version chain for single chunk (no ancestry)."""
        adapter_config = AdapterConfig(
            adapter_id="test-adapter",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0",
        )
        store.register_adapter(adapter_config)
        store.register_source(
            source_id="test-source",
            adapter_id="test-adapter",
            domain=Domain.NOTES,
            origin_ref="test://origin",
        )

        hash_a = _make_hash("a")

        # Version 1: chunk A
        version_id = store.create_source_version(
            source_id="test-source",
            version=1,
            markdown="content a",
            chunk_hashes=[hash_a],
            adapter_id="test-adapter",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-01T00:00:00Z",
        )

        chunk_a = Chunk(
            chunk_hash=hash_a,
            content="content a",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
        )

        lineage = [
            LineageRecord(
                chunk_hash=hash_a,
                source_id="test-source",
                source_version_id=version_id,
                adapter_id="test-adapter",
                domain=Domain.NOTES,
                normalizer_version="1.0",
                embedding_model_id="test-model",
            ),
        ]

        store.write_chunks([chunk_a], lineage)

        # Trace provenance
        provenance = trace_chunk_provenance(store, hash_a)
        assert provenance.chunk.chunk_hash == hash_a
        # Version chain should contain at least the chunk itself
        assert len(provenance.version_chain) >= 1
        assert provenance.version_chain[-1].chunk_hash == hash_a

    def test_trace_chunk_provenance_two_chunk_version_chain(
        self, store: DocumentStore
    ) -> None:
        """Test provenance version chain with ancestor-descendant relationship.

        Creates chunk A in version 1, then chunk B in version 2 with parent_chunk_hash=A,
        verifies the version_chain walks correctly and is ordered oldest-ancestor-first.
        """
        adapter_config = AdapterConfig(
            adapter_id="test-adapter",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0",
        )
        store.register_adapter(adapter_config)
        store.register_source(
            source_id="test-source",
            adapter_id="test-adapter",
            domain=Domain.NOTES,
            origin_ref="test://origin",
        )

        hash_a = _make_hash("a")
        hash_b = _make_hash("b")

        # Version 1: chunk A (ancestor)
        version_id_1 = store.create_source_version(
            source_id="test-source",
            version=1,
            markdown="content a",
            chunk_hashes=[hash_a],
            adapter_id="test-adapter",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-01T00:00:00Z",
        )

        chunk_a = Chunk(
            chunk_hash=hash_a,
            content="content a",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
        )

        lineage_a = [
            LineageRecord(
                chunk_hash=hash_a,
                source_id="test-source",
                source_version_id=version_id_1,
                adapter_id="test-adapter",
                domain=Domain.NOTES,
                normalizer_version="1.0",
                embedding_model_id="test-model",
            ),
        ]

        store.write_chunks([chunk_a], lineage_a)

        # Delay at least 1 second to ensure chunk B has a later created_at timestamp
        # (SQLite datetime precision is to the second)
        time.sleep(1.0)

        # Version 2: chunk B (descendant with parent_chunk_hash=A)
        version_id_2 = store.create_source_version(
            source_id="test-source",
            version=2,
            markdown="content b",
            chunk_hashes=[hash_b],
            adapter_id="test-adapter",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-02T00:00:00Z",
        )

        chunk_b = Chunk(
            chunk_hash=hash_b,
            content="content b (evolved from a)",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
        )

        lineage_b = [
            LineageRecord(
                chunk_hash=hash_b,
                source_id="test-source",
                source_version_id=version_id_2,
                adapter_id="test-adapter",
                domain=Domain.NOTES,
                normalizer_version="1.0",
                embedding_model_id="test-model",
            ),
        ]

        store.write_chunks([chunk_b], lineage_b)

        # Manually set parent_chunk_hash for B -> A via SQL
        # (write_chunks doesn't support this directly)
        store.conn.execute(
            """
            UPDATE chunks
            SET parent_chunk_hash = ?
            WHERE chunk_hash = ? AND source_id = ? AND source_version = ?
            """,
            (hash_a, hash_b, "test-source", 2),
        )
        store.conn.commit()

        # Trace provenance for chunk B (descendant)
        provenance = trace_chunk_provenance(store, hash_b)
        assert provenance.chunk.chunk_hash == hash_b

        # Version chain should contain both chunks, ordered oldest-ancestor first
        assert len(provenance.version_chain) == 2
        assert provenance.version_chain[0].chunk_hash == hash_a  # ancestor first
        assert provenance.version_chain[1].chunk_hash == hash_b  # descendant second

    def test_trace_chunk_provenance_unknown_hash_raises(
        self, store: DocumentStore
    ) -> None:
        """Test that unknown chunk hash raises ValueError."""
        with pytest.raises(ValueError, match="Chunk with hash .* not found"):
            trace_chunk_provenance(store, _make_hash("x"))

    def test_trace_chunk_provenance_with_source_id_filter(
        self, store: DocumentStore
    ) -> None:
        """Test tracing with source_id filter."""
        adapter_config = AdapterConfig(
            adapter_id="test-adapter",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0",
        )
        store.register_adapter(adapter_config)
        store.register_source(
            source_id="test-source",
            adapter_id="test-adapter",
            domain=Domain.NOTES,
            origin_ref="test://origin",
        )

        hash_a = _make_hash("a")
        version_id = store.create_source_version(
            source_id="test-source",
            version=1,
            markdown="test content",
            chunk_hashes=[hash_a],
            adapter_id="test-adapter",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-01T00:00:00Z",
        )

        chunk_a = Chunk(
            chunk_hash=hash_a,
            content="test content",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
        )

        lineage = [
            LineageRecord(
                chunk_hash=hash_a,
                source_id="test-source",
                source_version_id=version_id,
                adapter_id="test-adapter",
                domain=Domain.NOTES,
                normalizer_version="1.0",
                embedding_model_id="test-model",
            ),
        ]

        store.write_chunks([chunk_a], lineage)

        # Trace with source_id filter
        provenance = trace_chunk_provenance(
            store, hash_a, source_id="test-source"
        )
        assert provenance.lineage.source_id == "test-source"

    def test_trace_chunk_provenance_immutability(self, store: DocumentStore) -> None:
        """Test that returned ChunkProvenance is frozen."""
        adapter_config = AdapterConfig(
            adapter_id="test-adapter",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0",
        )
        store.register_adapter(adapter_config)
        store.register_source(
            source_id="test-source",
            adapter_id="test-adapter",
            domain=Domain.NOTES,
            origin_ref="test://origin",
        )

        hash_a = _make_hash("a")
        version_id = store.create_source_version(
            source_id="test-source",
            version=1,
            markdown="test content",
            chunk_hashes=[hash_a],
            adapter_id="test-adapter",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-01T00:00:00Z",
        )

        chunk_a = Chunk(
            chunk_hash=hash_a,
            content="test content",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
        )

        lineage = [
            LineageRecord(
                chunk_hash=hash_a,
                source_id="test-source",
                source_version_id=version_id,
                adapter_id="test-adapter",
                domain=Domain.NOTES,
                normalizer_version="1.0",
                embedding_model_id="test-model",
            ),
        ]

        store.write_chunks([chunk_a], lineage)

        provenance = trace_chunk_provenance(store, hash_a)
        # Frozen models should raise when attempting to modify
        with pytest.raises(Exception):  # FrozenInstanceError
            provenance.source_origin_ref = "modified"  # type: ignore

    def test_trace_chunk_provenance_lineage_not_found_without_source_id(
        self, store: DocumentStore
    ) -> None:
        """Test error path: lineage record not found (no source_id provided).

        Tests the error message when a chunk exists but no lineage record
        can be found for it (no source_id filter applied). This is isolated
        by mocking get_lineage to return None, ensuring get_chunk_by_hash
        succeeds but get_lineage returns None.
        """
        from unittest.mock import patch

        adapter_config = AdapterConfig(
            adapter_id="test-adapter",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0",
        )
        store.register_adapter(adapter_config)
        store.register_source(
            source_id="test-source",
            adapter_id="test-adapter",
            domain=Domain.NOTES,
            origin_ref="test://origin",
        )

        hash_a = _make_hash("a")

        # Create a chunk by writing it directly without a matching lineage record
        # This simulates a data inconsistency (chunk exists but no lineage)
        chunk_a = Chunk(
            chunk_hash=hash_a,
            content="test",
            chunk_index=0,
        )

        # Create a temporary lineage just to write the chunk
        temp_version_id = store.create_source_version(
            source_id="test-source",
            version=1,
            markdown="content",
            chunk_hashes=[hash_a],
            adapter_id="test-adapter",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-01T00:00:00Z",
        )

        temp_lineage = [
            LineageRecord(
                chunk_hash=hash_a,
                source_id="test-source",
                source_version_id=temp_version_id,
                adapter_id="test-adapter",
                domain=Domain.NOTES,
                normalizer_version="1.0",
                embedding_model_id="test-model",
            ),
        ]

        store.write_chunks([chunk_a], temp_lineage)

        # Mock get_lineage to return None to simulate missing lineage lookup
        # without deleting the chunk itself. This ensures get_chunk_by_hash
        # succeeds but get_lineage returns None, properly triggering the
        # lineage-not-found error path at provenance.py:92-95.
        with patch.object(store, 'get_lineage', return_value=None):
            with pytest.raises(ValueError) as exc_info:
                trace_chunk_provenance(store, hash_a)

        error_msg = str(exc_info.value)
        # Validate the exact error message for the lineage-not-found path
        assert error_msg == f"Lineage record not found for chunk {hash_a}"

    def test_trace_chunk_provenance_lineage_not_found_with_source_id(
        self, store: DocumentStore
    ) -> None:
        """Test error path: lineage record not found (source_id provided in error msg).

        Tests that when source_id is provided to trace_chunk_provenance,
        and no matching lineage is found, the error message includes the source_id.
        """
        adapter_config = AdapterConfig(
            adapter_id="test-adapter",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0",
        )
        store.register_adapter(adapter_config)
        store.register_source(
            source_id="source-1",
            adapter_id="test-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )
        store.register_source(
            source_id="source-2",
            adapter_id="test-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source-2",
        )

        hash_b = _make_hash("b")

        # Create chunk in source-1 only
        version_id_1 = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="content",
            chunk_hashes=[hash_b],
            adapter_id="test-adapter",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-01T00:00:00Z",
        )

        chunk_b = Chunk(
            chunk_hash=hash_b,
            content="test",
            chunk_index=0,
        )

        lineage_1 = LineageRecord(
            chunk_hash=hash_b,
            source_id="source-1",
            source_version_id=version_id_1,
            adapter_id="test-adapter",
            domain=Domain.NOTES,
            normalizer_version="1.0",
            embedding_model_id="test-model",
        )

        store.write_chunks([chunk_b], [lineage_1])

        # Try to trace with a different source_id that has no chunk for this hash
        # With source_id scoping, the chunk lookup fails first (not in source-2)
        with pytest.raises(ValueError) as exc_info:
            trace_chunk_provenance(store, hash_b, source_id="source-2")

        error_msg = str(exc_info.value)
        # Should report chunk not found in the requested source
        assert "Chunk with hash" in error_msg
        assert "in source source-2" in error_msg

    def test_trace_chunk_provenance_source_info_not_found(
        self, store: DocumentStore
    ) -> None:
        """Test error path: source info not found for lineage's source_id.

        Tests the error when a lineage record exists but the corresponding
        source (and its adapter info) cannot be retrieved, simulated by having
        a chunk's lineage reference a source_id that doesn't exist in the
        sources table.
        """
        adapter_config = AdapterConfig(
            adapter_id="test-adapter",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0",
        )
        store.register_adapter(adapter_config)
        store.register_source(
            source_id="test-source",
            adapter_id="test-adapter",
            domain=Domain.NOTES,
            origin_ref="test://origin",
        )

        hash_c = _make_hash("c")
        version_id = store.create_source_version(
            source_id="test-source",
            version=1,
            markdown="content",
            chunk_hashes=[hash_c],
            adapter_id="test-adapter",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-01T00:00:00Z",
        )

        chunk_c = Chunk(
            chunk_hash=hash_c,
            content="test",
            chunk_index=0,
        )

        # Create a lineage record pointing to test-source
        lineage = [
            LineageRecord(
                chunk_hash=hash_c,
                source_id="test-source",
                source_version_id=version_id,
                adapter_id="test-adapter",
                domain=Domain.NOTES,
                normalizer_version="1.0",
                embedding_model_id="test-model",
            ),
        ]

        store.write_chunks([chunk_c], lineage)

        # Simulate missing source info by directly updating the chunk to reference
        # a source that doesn't exist, bypassing FK checks via temporary disable
        store.conn.execute("PRAGMA foreign_keys=OFF")
        store.conn.execute(
            "UPDATE chunks SET source_id = ? WHERE chunk_hash = ?",
            ("missing-source", hash_c),
        )
        store.conn.execute("PRAGMA foreign_keys=ON")
        store.conn.commit()

        # Try to trace - should fail with source_info not found error
        # (get_source_info will return None for missing source)
        with pytest.raises(ValueError) as exc_info:
            trace_chunk_provenance(store, hash_c)

        error_msg = str(exc_info.value)
        assert "Source info not found for source_id" in error_msg
        assert "missing-source" in error_msg
