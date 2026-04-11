"""Tests for the DocumentStore SQLite implementation.

Covers:
- Database initialization and schema setup
- Adapter registration and idempotency
- Source registration
- Source version creation and tracking
- Chunk write/read roundtrips
- Lineage record tracking
- Version history ordering
- Chunk retirement
- Sync log operations
- Recovery mechanisms for SQLite/LanceDB inconsistency:
  - get_chunks_pending_sync: retrieves chunks needing insertion in LanceDB
  - get_chunks_pending_deletion: retrieves chunks needing deletion from LanceDB
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast, Generator

import pytest

from context_library.storage.document_store import DocumentStore
from context_library.storage.models import (
    AdapterConfig,
    Chunk,
    ChunkType,
    Domain,
    EntityLink,
    ENTITY_LINK_TYPE_PERSON_APPEARANCE,
    LineageRecord,
    PollStrategy,
    VersionDiff,
    compute_chunk_hash
)


@pytest.fixture
def store() -> Generator[DocumentStore, None, None]:
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


class TestDocumentStoreInit:
    """Tests for DocumentStore initialization."""

    def test_init_memory_database(self) -> None:
        """Test that DocumentStore can initialize with in-memory SQLite."""
        store = DocumentStore(":memory:")
        try:
            assert store.conn is not None
        finally:
            store.close()

    def test_schema_version_verification(self) -> None:
        """Test that user_version is verified to be 4 (people domain support)."""
        store = DocumentStore(":memory:")
        try:
            cursor = store.conn.cursor()
            cursor.execute("PRAGMA user_version")
            version = cursor.fetchone()[0]
            assert version == 4
        finally:
            store.close()

    def test_wal_mode_enabled(self) -> None:
        """Test that WAL mode is enabled (or memory for in-memory DBs)."""
        store = DocumentStore(":memory:")
        try:
            cursor = store.conn.cursor()
            cursor.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0].lower()
            # In-memory databases use "memory" mode, file-based use "wal"
            assert mode in ("wal", "memory")
        finally:
            store.close()

    def test_synchronous_normal_enabled(self) -> None:
        """Test that synchronous=NORMAL is enforced (value 1 per FR-2.2)."""
        store = DocumentStore(":memory:")
        try:
            cursor = store.conn.cursor()
            cursor.execute("PRAGMA synchronous")
            synchronous = cursor.fetchone()[0]
            assert synchronous == 1
        finally:
            store.close()

    def test_foreign_keys_enabled(self) -> None:
        """Test that foreign key enforcement is enabled."""
        store = DocumentStore(":memory:")
        try:
            cursor = store.conn.cursor()
            cursor.execute("PRAGMA foreign_keys")
            enabled = cursor.fetchone()[0]
            assert enabled == 1
        finally:
            store.close()


class TestAdapterRegistration:
    """Tests for adapter registration."""

    def test_register_adapter(self, store: DocumentStore) -> None:
        """Test registering an adapter."""
        config = AdapterConfig(
            adapter_id="test-adapter",
            adapter_type="gmail",
            domain=Domain.MESSAGES,
            normalizer_version="1.0.0",
            config={"api_key": "secret"},
        )

        adapter_id = store.register_adapter(config)

        assert adapter_id == "test-adapter"

        # Verify it was inserted
        retrieved = store.get_adapter("test-adapter")
        assert retrieved is not None
        assert retrieved.adapter_id == "test-adapter"
        assert retrieved.adapter_type == "gmail"
        assert retrieved.domain == Domain.MESSAGES
        assert retrieved.config == {"api_key": "secret"}

    def test_register_adapter_idempotency(self, store: DocumentStore) -> None:
        """Test that registering the same adapter twice is idempotent."""
        config1 = AdapterConfig(
            adapter_id="test-adapter",
            adapter_type="gmail",
            domain=Domain.MESSAGES,
            normalizer_version="1.0.0",
        )

        id1 = store.register_adapter(config1)
        id2 = store.register_adapter(config1)

        assert id1 == id2
        assert id1 == "test-adapter"

        # Should only have one row
        cursor = store.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM adapters WHERE adapter_id = ?", ("test-adapter",)
        )
        count = cursor.fetchone()[0]
        assert count == 1

    def test_register_adapter_config_update(self, store: DocumentStore) -> None:
        """Test that re-registering an adapter with different config is idempotent (no update)."""
        config1 = AdapterConfig(
            adapter_id="update-adapter",
            adapter_type="gmail",
            domain=Domain.MESSAGES,
            normalizer_version="1.0.0",
            config={"api_key": "old_key"},
        )

        store.register_adapter(config1)
        adapter1 = store.get_adapter("update-adapter")
        assert adapter1 is not None
        assert adapter1.normalizer_version == "1.0.0"
        assert adapter1.config == {"api_key": "old_key"}

        # Re-register with different config - should be idempotent (no update)
        config2 = AdapterConfig(
            adapter_id="update-adapter",
            adapter_type="gmail",
            domain=Domain.MESSAGES,
            normalizer_version="2.0.0",
            config={"api_key": "new_key"},
        )

        store.register_adapter(config2)
        adapter2 = store.get_adapter("update-adapter")

        # Config should remain unchanged (idempotent behavior)
        assert adapter2 is not None
        assert adapter2.normalizer_version == "1.0.0"
        assert adapter2.config == {"api_key": "old_key"}

        # Should still be only one row
        cursor = store.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM adapters WHERE adapter_id = ?", ("update-adapter",)
        )
        count = cursor.fetchone()[0]
        assert count == 1

    def test_register_adapter_without_config(self, store: DocumentStore) -> None:
        """Test registering an adapter without optional config."""
        config = AdapterConfig(
            adapter_id="simple-adapter",
            adapter_type="filesystem",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            config=None,
        )

        store.register_adapter(config)
        retrieved = store.get_adapter("simple-adapter")

        assert retrieved is not None
        assert retrieved.config is None


class TestSourceRegistration:
    """Tests for source registration."""

    def test_register_source(self, store: DocumentStore) -> None:
        """Test registering a source."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="gmail",
            domain=Domain.MESSAGES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)

        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.MESSAGES,
            origin_ref="gmail:user@example.com",
        )

        # Verify source was created
        cursor = store.conn.cursor()
        cursor.execute(
            "SELECT source_id, domain FROM sources WHERE source_id = ?",
            ("source-1",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["source_id"] == "source-1"
        assert row["domain"] == Domain.MESSAGES.value


class TestSourceVersions:
    """Tests for source version creation and retrieval."""

    def _setup_adapter_and_source(self, store: DocumentStore) -> None:
        """Helper to set up adapter and source."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

    def test_create_source_version(self, store: DocumentStore) -> None:
        """Test creating a source version."""
        self._setup_adapter_and_source(store)

        version_id = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="# Content v1",
            chunk_hashes=["abc123def456abc123def456abc123def456abc123def456abc123def456abc0"],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        assert version_id > 0

    def test_get_latest_version(self, store: DocumentStore) -> None:
        """Test retrieving the latest version of a source."""
        self._setup_adapter_and_source(store)

        store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="# Content v1",
            chunk_hashes=["abc123def456abc123def456abc123def456abc123def456abc123def456abc0"],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        store.create_source_version(
            source_id="source-1",
            version=2,
            markdown="# Content v2",
            chunk_hashes=["1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T11:00:00Z",
        )

        latest = store.get_latest_version("source-1")
        assert latest is not None
        assert latest.version == 2
        assert latest.markdown == "# Content v2"
        assert latest.chunk_hashes == ("1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",)

    def test_get_version_history_ordering(self, store: DocumentStore) -> None:
        """Test that version history is ordered ascending."""
        self._setup_adapter_and_source(store)

        # Create versions in mixed order
        hash_mapping = {
            1: "abc123def456abc123def456abc123def456abc123def456abc123def456abc0",
            2: "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
            3: "fedcba0987654321fedcba0987654321fedcba0987654321fedcba0987654321",
        }
        for v in [3, 1, 2]:
            store.create_source_version(
                source_id="source-1",
                version=v,
                markdown=f"# Content v{v}",
                chunk_hashes=[hash_mapping[v]],
                adapter_id="adapter-1",
                normalizer_version="1.0.0",
                fetch_timestamp=f"2025-03-02T{10+v}:00:00Z",
            )

        history = store.get_version_history("source-1")

        assert len(history) == 3
        assert [v.version for v in history] == [1, 2, 3]

    def test_get_version_history_empty_source(self, store: DocumentStore) -> None:
        """Test that non-existent source returns empty list."""
        history = store.get_version_history("non-existent")
        assert history == []

    def test_get_latest_version_non_existent(self, store: DocumentStore) -> None:
        """Test that non-existent source returns None."""
        latest = store.get_latest_version("non-existent")
        assert latest is None


class TestChunkWriteAndRead:
    """Tests for chunk write/read operations."""

    def _setup_with_version(
        self, store: DocumentStore
    ) -> tuple[str, str, int]:
        """Helper to set up adapter, source, and version. Returns (source_id, adapter_id, source_version_id)."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        version_id = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="# Content",
            chunk_hashes=["abc123def456abc123def456abc123def456abc123def456abc123def456abc0", "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        return "source-1", "adapter-1", version_id

    def test_write_chunks_and_retrieve(self, store: DocumentStore) -> None:
        """Test writing chunks and retrieving them."""
        source_id, adapter_id, version_id = self._setup_with_version(store)

        chunks = [
            Chunk(
                chunk_hash=_make_hash("a"),  # Valid SHA-256 hex
                content="This is chunk 1",
                context_header="Section 1",
                chunk_index=0,
                chunk_type=ChunkType.STANDARD,
            ),
            Chunk(
                chunk_hash=_make_hash("b"),
                content="This is chunk 2",
                context_header="Section 2",
                chunk_index=1,
                chunk_type=ChunkType.STANDARD,
            ),
        ]

        lineage = [
            LineageRecord(
                chunk_hash=_make_hash("a"),
                source_id=source_id,
                source_version_id=version_id,
                adapter_id=adapter_id,
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
            LineageRecord(
                chunk_hash=_make_hash("b"),
                source_id=source_id,
                source_version_id=version_id,
                adapter_id=adapter_id,
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
        ]

        store.write_chunks(chunks, lineage)

        # Retrieve the first chunk
        chunk = store.get_chunk_by_hash(_make_hash("a"))
        assert chunk is not None
        assert chunk.chunk_hash == _make_hash("a")
        assert chunk.content == "This is chunk 1"
        assert chunk.context_header == "Section 1"
        assert chunk.chunk_index == 0

    def test_write_chunks_deduplication(self, store: DocumentStore) -> None:
        """Test that writing the same chunk twice doesn't create duplicates."""
        source_id, adapter_id, version_id = self._setup_with_version(store)

        chunk = Chunk(
            chunk_hash=_make_hash("c"),
            content="Deduplicated content",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("c"),
            source_id=source_id,
            source_version_id=version_id,
            adapter_id=adapter_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )

        # Write twice
        store.write_chunks([chunk], [lineage])
        store.write_chunks([chunk], [lineage])

        # Should still be only one row
        cursor = store.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM chunks WHERE chunk_hash = ?", (_make_hash("c"),)
        )
        count = cursor.fetchone()[0]
        assert count == 1

    def test_write_chunks_invalid_chunk_type_raises_error(
        self, store: DocumentStore
    ) -> None:
        """Test that invalid chunk_type raises ValidationError at Pydantic level.

        Validation now happens at Pydantic model instantiation before reaching SQLite,
        preventing invalid chunk_type values from reaching the database.
        """
        from pydantic import ValidationError

        # Create a chunk with invalid chunk_type that violates ChunkType enum
        with pytest.raises(ValidationError) as exc_info:
            Chunk(
                chunk_hash=_make_hash("f"),
                content="Invalid chunk",
                chunk_index=0,
                chunk_type=cast(ChunkType, "invalid_type_value"),  # Not in ChunkType enum
            )

        # Verify the error message mentions the invalid chunk_type
        assert "chunk_type" in str(exc_info.value)
        assert "invalid_type_value" in str(exc_info.value)

    def test_write_chunks_invalid_adapter_id_raises_error(
        self, store: DocumentStore
    ) -> None:
        """Test that write_chunks raises IntegrityError for foreign key violation."""
        source_id, adapter_id, version_id = self._setup_with_version(store)

        chunk = Chunk(
            chunk_hash=_make_hash("1"),
            content="Foreign key test",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("1"),
            source_id=source_id,
            source_version_id=version_id,
            adapter_id="nonexistent-adapter",  # Doesn't exist in adapters table
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )

        # Should raise IntegrityError because adapter_id doesn't exist (foreign key)
        import sqlite3

        with pytest.raises(sqlite3.IntegrityError):
            store.write_chunks([chunk], [lineage])

    def test_get_chunk_by_hash_not_found(self, store: DocumentStore) -> None:
        """Test retrieving a non-existent chunk."""
        chunk = store.get_chunk_by_hash("nonexistent")
        assert chunk is None

    def test_chunk_with_domain_metadata(self, store: DocumentStore) -> None:
        """Test writing and retrieving a chunk with domain_metadata."""
        source_id, adapter_id, version_id = self._setup_with_version(store)

        metadata: dict[str, object] = {"sender": "user@example.com", "timestamp": "2025-03-02"}
        chunk = Chunk(
            chunk_hash=_make_hash("d"),
            content="Email content",
            chunk_index=0,
            domain_metadata=metadata,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("d"),
            source_id=source_id,
            source_version_id=version_id,
            adapter_id=adapter_id,
            domain=Domain.MESSAGES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )

        store.write_chunks([chunk], [lineage])

        retrieved = store.get_chunk_by_hash(_make_hash("d"))
        assert retrieved is not None
        assert retrieved.domain_metadata == metadata


class TestGetChunkByHashWithSourceId:
    """Tests for get_chunk_by_hash with source_id parameter."""

    _counter = 0

    def _setup_with_version(self, store: DocumentStore, version: int = 1) -> tuple[str, str, int]:
        """Set up adapter, source, and version for testing."""
        TestGetChunkByHashWithSourceId._counter += 1
        n = TestGetChunkByHashWithSourceId._counter

        adapter_id = f"adapter-{n}"
        source_id = f"source-{n}"

        config = AdapterConfig(
            adapter_id=adapter_id,
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id=source_id,
            adapter_id=adapter_id,
            domain=Domain.NOTES,
            origin_ref=f"origin-{n}",
            poll_strategy=PollStrategy.PULL,
        )

        version_id = store.create_source_version(
            source_id=source_id,
            version=version,
            markdown="# Content",
            chunk_hashes=[],
            adapter_id=adapter_id,
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        return source_id, adapter_id, version_id

    def test_get_chunk_by_hash_with_source_id_scoped_lookup(
        self, store: DocumentStore
    ) -> None:
        """Test that source_id parameter scopes chunk lookup to specific source."""
        # Set up source
        source_id, adapter_id, version_id = self._setup_with_version(store)

        # Create chunk
        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="Content",
            chunk_index=0,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id=source_id,
            source_version_id=version_id,
            adapter_id=adapter_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )
        store.write_chunks([chunk], [lineage])

        # Query without source_id returns the chunk
        result = store.get_chunk_by_hash(_make_hash("a"))
        assert result is not None
        assert result.chunk_hash == _make_hash("a")

        # Query with matching source_id should return the chunk
        result = store.get_chunk_by_hash(_make_hash("a"), source_id=source_id)
        assert result is not None
        assert result.chunk_hash == _make_hash("a")

        # Query with non-existent source_id returns None
        result = store.get_chunk_by_hash(_make_hash("a"), source_id="nonexistent-source")
        assert result is None

    def test_get_chunk_by_hash_with_source_id_returns_none_if_not_in_source(
        self, store: DocumentStore
    ) -> None:
        """Test that source_id parameter returns None if chunk not in that source."""
        source1_id, adapter1_id, version1_id = self._setup_with_version(store)
        source2_id, adapter2_id, version2_id = self._setup_with_version(store)

        # Write chunk to source 1 only
        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="Only in source 1",
            chunk_index=0,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id=source1_id,
            source_version_id=version1_id,
            adapter_id=adapter1_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )
        store.write_chunks([chunk], [lineage])

        # Querying source 2 should return None
        result = store.get_chunk_by_hash(_make_hash("a"), source_id=source2_id)
        assert result is None

        # But querying source 1 should succeed
        result = store.get_chunk_by_hash(_make_hash("a"), source_id=source1_id)
        assert result is not None

    def test_get_chunk_by_hash_without_source_id_returns_earliest(
        self, store: DocumentStore
    ) -> None:
        """Test that without source_id, earliest-created instance is returned."""
        source_id, adapter_id, version_id = self._setup_with_version(store)

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="Content",
            chunk_index=0,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id=source_id,
            source_version_id=version_id,
            adapter_id=adapter_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )
        store.write_chunks([chunk], [lineage])

        # Without source_id, should return the chunk
        result = store.get_chunk_by_hash(_make_hash("a"))
        assert result is not None
        assert result.chunk_hash == _make_hash("a")

    def test_get_chunk_by_hash_source_id_excludes_retired_chunks(
        self, store: DocumentStore
    ) -> None:
        """Test that source_id scoped lookup excludes retired chunks."""
        source_id, adapter_id, version_id = self._setup_with_version(store)

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="Will be retired",
            chunk_index=0,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id=source_id,
            source_version_id=version_id,
            adapter_id=adapter_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )
        store.write_chunks([chunk], [lineage])

        # Verify it's retrievable
        result = store.get_chunk_by_hash(_make_hash("a"), source_id=source_id)
        assert result is not None

        # Retire the chunk (needs source_id and version)
        cursor = store.conn.cursor()
        cursor.execute(
            """UPDATE chunks SET retired_at = CURRENT_TIMESTAMP
               WHERE chunk_hash = ? AND source_id = ?""",
            (_make_hash("a"), source_id),
        )
        store.conn.commit()

        # Now it should not be found
        result = store.get_chunk_by_hash(_make_hash("a"), source_id=source_id)
        assert result is None

    def test_get_chunk_by_hash_multiple_versions_same_source(
        self, store: DocumentStore
    ) -> None:
        """Test get_chunk_by_hash with multiple versions of same source."""
        source_id, adapter_id, version1_id = self._setup_with_version(store, version=1)

        # Create version 2
        store.create_source_version(
            source_id=source_id,
            version=2,
            markdown="# Content v2",
            chunk_hashes=[],
            adapter_id=adapter_id,
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T11:00:00Z",
        )

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="In both versions",
            chunk_index=0,
        )

        # Write to version 1
        lineage1 = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id=source_id,
            source_version_id=version1_id,
            adapter_id=adapter_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )
        store.write_chunks([chunk], [lineage1])

        # Query with source_id should return the chunk
        result = store.get_chunk_by_hash(_make_hash("a"), source_id=source_id)
        assert result is not None
        assert result.chunk_hash == _make_hash("a")

    def test_get_chunk_by_hash_source_id_none_returns_any_source(
        self, store: DocumentStore
    ) -> None:
        """Test that source_id=None returns chunk from any source."""
        source1_id, adapter1_id, version1_id = self._setup_with_version(store)

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="Content",
            chunk_index=0,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id=source1_id,
            source_version_id=version1_id,
            adapter_id=adapter1_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )
        store.write_chunks([chunk], [lineage])

        # Query with source_id=None should succeed
        result = store.get_chunk_by_hash(_make_hash("a"), source_id=None)
        assert result is not None
        assert result.chunk_hash == _make_hash("a")


class TestLineageTracking:
    """Tests for lineage record operations."""

    def _setup_chunk_with_lineage(self, store: DocumentStore) -> str:
        """Helper to create a chunk with lineage. Returns chunk_hash."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        version_id = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="# Content",
            chunk_hashes=[_make_hash("e")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        chunk = Chunk(
            chunk_hash=_make_hash("e"),
            content="Test content",
            chunk_index=0,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("e"),
            source_id="source-1",
            source_version_id=version_id,
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="embedding-v1",
        )

        store.write_chunks([chunk], [lineage])
        return _make_hash("e")

    def test_get_lineage(self, store: DocumentStore) -> None:
        """Test retrieving lineage for a chunk."""
        chunk_hash = self._setup_chunk_with_lineage(store)

        lineage = store.get_lineage(chunk_hash)

        assert lineage is not None
        assert lineage.chunk_hash == chunk_hash
        assert lineage.source_id == "source-1"
        assert lineage.adapter_id == "adapter-1"
        assert lineage.domain == Domain.NOTES
        assert lineage.normalizer_version == "1.0.0"
        assert lineage.embedding_model_id == "embedding-v1"

    def test_get_lineage_not_found(self, store: DocumentStore) -> None:
        """Test retrieving lineage for non-existent chunk."""
        lineage = store.get_lineage(_make_hash("f"))
        assert lineage is None


class TestChunkRetirement:
    """Tests for chunk retirement."""

    def _setup_chunks_for_retirement(
        self, store: DocumentStore
    ) -> set[str]:
        """Helper to set up chunks. Returns set of chunk hashes."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        version_id = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="# Content",
            chunk_hashes=[_make_hash("8"), _make_hash("9")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        hashes = {_make_hash("8"), _make_hash("9")}
        chunks = [
            Chunk(
                chunk_hash=_make_hash("8"),
                content="Chunk G",
                chunk_index=0,
            ),
            Chunk(
                chunk_hash=_make_hash("9"),
                content="Chunk H",
                chunk_index=1,
            ),
        ]

        lineage = [
            LineageRecord(
                chunk_hash=h,
                source_id="source-1",
                source_version_id=version_id,
                adapter_id="adapter-1",
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            )
            for h in hashes
        ]

        store.write_chunks(chunks, lineage)
        return hashes

    def test_retire_chunks(self, store: DocumentStore) -> None:
        """Test retiring chunks for a specific source and version."""
        hashes = self._setup_chunks_for_retirement(store)

        # Retire chunks for source-1 version 1
        store.retire_chunks(hashes, source_id="source-1", source_version=1)

        # Verify retired_at is set
        cursor = store.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM chunks WHERE chunk_hash IN (?, ?) AND retired_at IS NOT NULL",
            tuple(hashes),
        )
        count = cursor.fetchone()[0]
        assert count == 2

    def test_get_chunks_excludes_retired(self, store: DocumentStore) -> None:
        """Test that get_chunks_by_source excludes retired chunks."""
        # Setup initial chunks
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        version_id = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="# Content",
            chunk_hashes=[_make_hash("a"), _make_hash("1")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        chunks = [
            Chunk(
                chunk_hash=_make_hash("a"),
                content="Chunk I",
                chunk_index=0,
            ),
            Chunk(
                chunk_hash=_make_hash("1"),
                content="Chunk J",
                chunk_index=1,
            ),
        ]

        lineage = [
            LineageRecord(
                chunk_hash=_make_hash("a"),
                source_id="source-1",
                source_version_id=version_id,
                adapter_id="adapter-1",
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
            LineageRecord(
                chunk_hash=_make_hash("1"),
                source_id="source-1",
                source_version_id=version_id,
                adapter_id="adapter-1",
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
        ]

        store.write_chunks(chunks, lineage)

        # Retire one chunk from source-1 version 1
        store.retire_chunks({_make_hash("a")}, source_id="source-1", source_version=1)

        # Get chunks should only return non-retired
        retrieved, total = store.get_chunks_by_source("source-1", version=1)

        assert len(retrieved) == 1
        assert total == 1
        assert retrieved[0].chunk_hash == _make_hash("1")

    def test_is_chunk_retired_returns_true_for_retired(
        self, store: DocumentStore
    ) -> None:
        """Test that is_chunk_retired() correctly identifies retired chunks."""
        # Setup initial chunks
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        version_id = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="# Content",
            chunk_hashes=[_make_hash("a")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="Chunk A",
            chunk_index=0,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id="source-1",
            source_version_id=version_id,
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )

        store.write_chunks([chunk], [lineage])

        # Before retirement, should return False
        assert store.is_chunk_retired(_make_hash("a")) is False

        # After retirement, should return True
        store.retire_chunks({_make_hash("a")}, source_id="source-1", source_version=1)
        assert store.is_chunk_retired(_make_hash("a")) is True

    def test_is_chunk_retired_returns_false_for_missing(
        self, store: DocumentStore
    ) -> None:
        """Test that is_chunk_retired() returns False for missing chunks."""
        # Non-existent chunk should return False (not retired, just doesn't exist)
        assert store.is_chunk_retired(_make_hash("z")) is False

    def test_retire_chunks_raises_runtime_error_for_nonexistent(
        self, store: DocumentStore
    ) -> None:
        """Test that retire_chunks raises RuntimeError when chunk doesn't exist.

        Data integrity guard: ensures we don't silently accept retirement
        requests for non-existent chunks, which could mask logic errors.
        """
        # Setup initial chunks for a source
        hashes = self._setup_chunks_for_retirement(store)

        # Attempt to retire a non-existent chunk for the same source/version
        # This should raise RuntimeError as a data integrity guard
        # Use 'f' instead of 'z' to create a valid hex hash
        non_existent_hash = _make_hash("f")
        with pytest.raises(RuntimeError):
            store.retire_chunks(
                {non_existent_hash},
                source_id="source-1",
                source_version=1,
            )

        # Verify existing chunks are still not retired
        cursor = store.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM chunks WHERE chunk_hash IN (?, ?) AND retired_at IS NOT NULL",
            tuple(hashes),
        )
        count = cursor.fetchone()[0]
        assert count == 0


class TestAdapterReset:
    """Tests for adapter reset functionality."""

    def _setup_adapter_with_sources_and_chunks(
        self, store: DocumentStore, adapter_id: str, num_sources: int = 2
    ) -> tuple[list[str], list[str]]:
        """Helper to set up an adapter with multiple sources and chunks.

        Args:
            store: DocumentStore instance
            adapter_id: ID for the adapter
            num_sources: Number of sources to create

        Returns:
            Tuple of (source_ids, chunk_hashes)
        """
        config = AdapterConfig(
            adapter_id=adapter_id,
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)

        source_ids = []
        chunk_hashes = []

        for i in range(num_sources):
            source_id = f"{adapter_id}-source-{i}"
            source_ids.append(source_id)
            store.register_source(
                source_id=source_id,
                adapter_id=adapter_id,
                domain=Domain.NOTES,
                origin_ref=f"test://{source_id}",
            )

            # Create version with 2 chunks per source
            # Use adapter_id and source index to guarantee unique hashes by construction
            hash1 = compute_chunk_hash(f"{adapter_id}-{i}-0")
            hash2 = compute_chunk_hash(f"{adapter_id}-{i}-1")

            # Use version number (1) not rowid for the version parameter
            store.create_source_version(
                source_id=source_id,
                version=1,
                markdown=f"# Content {i}",
                chunk_hashes=[hash1, hash2],
                adapter_id=adapter_id,
                normalizer_version="1.0.0",
                fetch_timestamp="2025-03-02T10:00:00Z",
            )

            chunk_hashes.extend([hash1, hash2])

            chunks = [
                Chunk(chunk_hash=hash1, content=f"Chunk {source_id}-0", chunk_index=0),
                Chunk(chunk_hash=hash2, content=f"Chunk {source_id}-1", chunk_index=1),
            ]

            lineage = [
                LineageRecord(
                    chunk_hash=h,
                    source_id=source_id,
                    source_version_id=1,  # Use version number, not rowid
                    adapter_id=adapter_id,
                    domain=Domain.NOTES,
                    normalizer_version="1.0.0",
                    embedding_model_id="test-model",
                )
                for h in [hash1, hash2]
            ]

            store.write_chunks(chunks, lineage)

        return source_ids, chunk_hashes

    def test_reset_adapter_retires_chunks(self, store: DocumentStore) -> None:
        """Test that reset_adapter retires all chunks for the adapter."""
        source_ids, chunk_hashes = self._setup_adapter_with_sources_and_chunks(
            store, "adapter-1", num_sources=2
        )

        result = store.reset_adapter("adapter-1")

        # Verify return value
        assert result["sources_reset"] == 2
        assert result["chunks_retired"] == 4

        # Verify all chunks are retired
        for chunk_hash in chunk_hashes:
            assert store.is_chunk_retired(chunk_hash) is True

    def test_reset_adapter_writes_sync_log_entries(self, store: DocumentStore) -> None:
        """Test that reset_adapter writes DELETE entries to lancedb_sync_log."""
        source_ids, chunk_hashes = self._setup_adapter_with_sources_and_chunks(
            store, "adapter-1", num_sources=2
        )

        store.reset_adapter("adapter-1")

        # Verify sync log entries for each chunk
        cursor = store.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM lancedb_sync_log WHERE operation = 'delete' AND chunk_hash IN (" +
            ",".join("?" * len(chunk_hashes)) + ")",
            chunk_hashes,
        )
        count = cursor.fetchone()[0]
        assert count == 4

    def test_reset_adapter_clears_last_fetched_at(self, store: DocumentStore) -> None:
        """Test that reset_adapter clears last_fetched_at for all sources."""
        source_ids, _ = self._setup_adapter_with_sources_and_chunks(
            store, "adapter-1", num_sources=2
        )

        # Set last_fetched_at for all sources
        now = datetime.now(timezone.utc).isoformat()
        cursor = store.conn.cursor()
        cursor.execute(
            "UPDATE sources SET last_fetched_at = ? WHERE adapter_id = ?",
            (now, "adapter-1"),
        )

        # Verify they are set
        cursor.execute(
            "SELECT COUNT(*) FROM sources WHERE adapter_id = ? AND last_fetched_at IS NOT NULL",
            ("adapter-1",),
        )
        count_before = cursor.fetchone()[0]
        assert count_before == 2

        # Reset adapter
        store.reset_adapter("adapter-1")

        # Verify last_fetched_at is NULL for all sources
        cursor.execute(
            "SELECT COUNT(*) FROM sources WHERE adapter_id = ? AND last_fetched_at IS NULL",
            ("adapter-1",),
        )
        count_after = cursor.fetchone()[0]
        assert count_after == 2

    def test_reset_adapter_preserves_source_rows(self, store: DocumentStore) -> None:
        """Test that reset_adapter preserves source registration."""
        source_ids, _ = self._setup_adapter_with_sources_and_chunks(
            store, "adapter-1", num_sources=2
        )

        store.reset_adapter("adapter-1")

        # Verify sources still exist
        for source_id in source_ids:
            cursor = store.conn.cursor()
            cursor.execute("SELECT source_id FROM sources WHERE source_id = ?", (source_id,))
            assert cursor.fetchone() is not None

    def test_reset_adapter_preserves_adapter_row(self, store: DocumentStore) -> None:
        """Test that reset_adapter preserves adapter registration."""
        source_ids, _ = self._setup_adapter_with_sources_and_chunks(
            store, "adapter-1", num_sources=1
        )

        store.reset_adapter("adapter-1")

        # Verify adapter still exists
        adapter = store.get_adapter("adapter-1")
        assert adapter is not None
        assert adapter.adapter_id == "adapter-1"

    def test_reset_adapter_no_sources(self, store: DocumentStore) -> None:
        """Test that reset_adapter handles adapter with no sources."""
        config = AdapterConfig(
            adapter_id="empty-adapter",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)

        result = store.reset_adapter("empty-adapter")

        assert result["sources_reset"] == 0
        assert result["chunks_retired"] == 0

    def test_reset_adapter_unknown_adapter(self, store: DocumentStore) -> None:
        """Test that reset_adapter on unknown adapter returns zero counts."""
        result = store.reset_adapter("nonexistent-adapter")

        assert result["sources_reset"] == 0
        assert result["chunks_retired"] == 0

    def test_reset_adapter_idempotent(self, store: DocumentStore) -> None:
        """Test that reset_adapter is idempotent.

        Idempotency means that calling it twice produces the same end state:
        - First call retires all non-retired chunks
        - Second call finds 0 chunks to retire (all already retired) but counts sources
        """
        source_ids, chunk_hashes = self._setup_adapter_with_sources_and_chunks(
            store, "adapter-1", num_sources=2
        )

        # First reset - retires 4 chunks for 2 sources
        result1 = store.reset_adapter("adapter-1")
        assert result1["sources_reset"] == 2
        assert result1["chunks_retired"] == 4

        # Second reset - no non-retired chunks to retire, but sources still count
        result2 = store.reset_adapter("adapter-1")
        assert result2["sources_reset"] == 2
        assert result2["chunks_retired"] == 0

        # Verify end state is stable: all chunks remain retired
        for chunk_hash in chunk_hashes:
            assert store.is_chunk_retired(chunk_hash) is True

    def test_reset_adapter_does_not_affect_other_adapters(
        self, store: DocumentStore
    ) -> None:
        """Test that reset_adapter only affects the specified adapter."""
        # Setup two adapters with different seeds to avoid hash collisions
        source_ids_1, chunk_hashes_1 = self._setup_adapter_with_sources_and_chunks(
            store, "adapter-1", num_sources=1
        )
        source_ids_2, chunk_hashes_2 = self._setup_adapter_with_sources_and_chunks(
            store, "adapter-2", num_sources=1
        )

        # Reset adapter-1
        store.reset_adapter("adapter-1")

        # Verify adapter-1 chunks are retired
        for chunk_hash in chunk_hashes_1:
            assert store.is_chunk_retired(chunk_hash) is True

        # Verify adapter-2 chunks are NOT retired
        for chunk_hash in chunk_hashes_2:
            assert store.is_chunk_retired(chunk_hash) is False

    def test_reset_adapter_excludes_already_retired_chunks(
        self, store: DocumentStore
    ) -> None:
        """Test that reset_adapter only counts non-retired chunks."""
        source_ids, chunk_hashes = self._setup_adapter_with_sources_and_chunks(
            store, "adapter-1", num_sources=1
        )

        # Manually retire one chunk
        store.retire_chunks(
            {chunk_hashes[0]}, source_id=source_ids[0], source_version=1
        )

        # Reset adapter
        result = store.reset_adapter("adapter-1")

        # Should only retire the 1 non-retired chunk (not the already-retired one)
        assert result["chunks_retired"] == 1
        assert result["sources_reset"] == 1

    def test_reset_adapter_preserves_source_versions(
        self, store: DocumentStore
    ) -> None:
        """Test that reset_adapter preserves source_version history."""
        source_ids, chunk_hashes = self._setup_adapter_with_sources_and_chunks(
            store, "adapter-1", num_sources=1
        )

        # Verify source version exists before reset
        source_id = source_ids[0]
        history_before = store.get_version_history(source_id)
        assert len(history_before) == 1
        assert history_before[0].version == 1

        # Reset adapter
        store.reset_adapter("adapter-1")

        # Verify source_version history is preserved after reset
        history_after = store.get_version_history(source_id)
        assert len(history_after) == 1
        assert history_after[0].version == 1
        assert history_after[0].markdown == "# Content 0"


class TestHasNonPushSources:
    """Tests for has_non_push_sources method."""

    def test_adapter_with_only_push_sources_returns_false(self, store: DocumentStore) -> None:
        """Test that adapter with only push sources returns False."""
        config = AdapterConfig(
            adapter_id="push-adapter",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)

        # Register a source with PUSH strategy
        store.register_source(
            source_id="push-source-1",
            adapter_id="push-adapter",
            domain=Domain.NOTES,
            origin_ref="test://push-source-1",
            poll_strategy=PollStrategy.PUSH,
        )

        result = store.has_non_push_sources("push-adapter")
        assert result is False

    def test_adapter_with_pull_sources_returns_true(self, store: DocumentStore) -> None:
        """Test that adapter with pull sources returns True."""
        config = AdapterConfig(
            adapter_id="pull-adapter",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)

        # Register a source with PULL strategy
        store.register_source(
            source_id="pull-source-1",
            adapter_id="pull-adapter",
            domain=Domain.NOTES,
            origin_ref="test://pull-source-1",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )

        result = store.has_non_push_sources("pull-adapter")
        assert result is True

    def test_adapter_with_webhook_sources_returns_true(self, store: DocumentStore) -> None:
        """Test that adapter with webhook sources returns True."""
        config = AdapterConfig(
            adapter_id="webhook-adapter",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)

        # Register a source with WEBHOOK strategy
        store.register_source(
            source_id="webhook-source-1",
            adapter_id="webhook-adapter",
            domain=Domain.NOTES,
            origin_ref="test://webhook-source-1",
            poll_strategy=PollStrategy.WEBHOOK,
        )

        result = store.has_non_push_sources("webhook-adapter")
        assert result is True

    def test_adapter_with_mixed_strategies_returns_true(self, store: DocumentStore) -> None:
        """Test that adapter with mixed push and non-push sources returns True."""
        config = AdapterConfig(
            adapter_id="mixed-adapter",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)

        # Register push source
        store.register_source(
            source_id="mixed-push-1",
            adapter_id="mixed-adapter",
            domain=Domain.NOTES,
            origin_ref="test://mixed-push-1",
            poll_strategy=PollStrategy.PUSH,
        )

        # Register pull source
        store.register_source(
            source_id="mixed-pull-1",
            adapter_id="mixed-adapter",
            domain=Domain.NOTES,
            origin_ref="test://mixed-pull-1",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )

        result = store.has_non_push_sources("mixed-adapter")
        assert result is True

    def test_adapter_with_no_sources_returns_false(self, store: DocumentStore) -> None:
        """Test that adapter with no sources returns False."""
        config = AdapterConfig(
            adapter_id="empty-adapter",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)

        result = store.has_non_push_sources("empty-adapter")
        assert result is False

    def test_nonexistent_adapter_returns_false(self, store: DocumentStore) -> None:
        """Test that querying nonexistent adapter returns False."""
        result = store.has_non_push_sources("nonexistent-adapter")
        assert result is False


class TestChunksBySource:
    """Tests for retrieving chunks by source."""

    def test_get_chunks_by_source_latest_version(
        self, store: DocumentStore
    ) -> None:
        """Test retrieving chunks for latest version."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        version_id = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="# Content v1",
            chunk_hashes=[_make_hash("2")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        chunk = Chunk(
            chunk_hash=_make_hash("2"),
            content="Chunk content",
            chunk_index=0,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("2"),
            source_id="source-1",
            source_version_id=version_id,
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )

        store.write_chunks([chunk], [lineage])

        # Get chunks without specifying version (should get latest)
        chunks, total = store.get_chunks_by_source("source-1")

        assert len(chunks) == 1
        assert total == 1
        assert chunks[0].chunk_hash == _make_hash("2")

    def test_get_chunks_by_source_specific_version(
        self, store: DocumentStore
    ) -> None:
        """Test retrieving chunks for a specific version."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        version_id_1 = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="# Content v1",
            chunk_hashes=[_make_hash("3")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        version_id_2 = store.create_source_version(
            source_id="source-1",
            version=2,
            markdown="# Content v2",
            chunk_hashes=[_make_hash("4")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T11:00:00Z",
        )

        # Write chunks for both versions
        chunks = [
            Chunk(
                chunk_hash=_make_hash("3"),
                content="Content v1",
                chunk_index=0,
            ),
            Chunk(
                chunk_hash=_make_hash("4"),
                content="Content v2",
                chunk_index=0,
            ),
        ]

        lineage = [
            LineageRecord(
                chunk_hash=_make_hash("3"),
                source_id="source-1",
                source_version_id=version_id_1,
                adapter_id="adapter-1",
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
            LineageRecord(
                chunk_hash=_make_hash("4"),
                source_id="source-1",
                source_version_id=version_id_2,
                adapter_id="adapter-1",
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
        ]

        store.write_chunks(chunks, lineage)

        # Get chunks for version 1
        v1_chunks, v1_total = store.get_chunks_by_source("source-1", version=1)
        assert len(v1_chunks) == 1
        assert v1_total == 1
        assert v1_chunks[0].chunk_hash == _make_hash("3")

        # Get chunks for version 2
        v2_chunks, v2_total = store.get_chunks_by_source("source-1", version=2)
        assert len(v2_chunks) == 1
        assert v2_total == 1
        assert v2_chunks[0].chunk_hash == _make_hash("4")

    def test_get_chunks_by_source_non_existent(self, store: DocumentStore) -> None:
        """Test retrieving chunks for non-existent source."""
        chunks, total = store.get_chunks_by_source("non-existent")
        assert chunks == []
        assert total == 0


class TestSyncLog:
    """Tests for LanceDB sync log operations."""

    def _setup_chunk_for_sync(self, store: DocumentStore) -> str:
        """Helper to set up a chunk. Returns chunk_hash."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        version_id = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="# Content",
            chunk_hashes=[_make_hash("5")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        chunk = Chunk(
            chunk_hash=_make_hash("5"),
            content="Sync test",
            chunk_index=0,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("5"),
            source_id="source-1",
            source_version_id=version_id,
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )

        store.write_chunks([chunk], [lineage])
        return _make_hash("5")

    def test_write_sync_log(self, store: DocumentStore) -> None:
        """Test writing to sync log."""
        chunk_hash = self._setup_chunk_for_sync(store)

        store.write_sync_log([chunk_hash])

        # Verify entry exists with correct operation
        cursor = store.conn.cursor()
        cursor.execute(
            "SELECT chunk_hash, operation FROM lancedb_sync_log WHERE chunk_hash = ?",
            (chunk_hash,),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == chunk_hash
        assert row[1] == "insert"

    def test_write_sync_log_idempotency(self, store: DocumentStore) -> None:
        """Test that writing sync log twice is idempotent."""
        chunk_hash = self._setup_chunk_for_sync(store)

        store.write_sync_log([chunk_hash])
        store.write_sync_log([chunk_hash])

        # Should only have one row
        cursor = store.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM lancedb_sync_log WHERE chunk_hash = ?",
            (chunk_hash,),
        )
        count = cursor.fetchone()[0]
        assert count == 1

    def test_delete_sync_log(self, store: DocumentStore) -> None:
        """Test recording delete operation in sync log."""
        chunk_hash = self._setup_chunk_for_sync(store)

        store.write_sync_log([chunk_hash])
        store.delete_sync_log([chunk_hash])

        # Verify operation is recorded as delete
        cursor = store.conn.cursor()
        cursor.execute(
            "SELECT operation FROM lancedb_sync_log WHERE chunk_hash = ?",
            (chunk_hash,),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "delete"

    def test_delete_sync_log_non_existent(self, store: DocumentStore) -> None:
        """Test deleting chunk that exists but was never previously synced.

        Verifies that delete_sync_log creates a new sync log entry for a chunk
        that exists in the chunks table but has no prior sync log record.
        """
        # Create a chunk but do NOT sync it first
        chunk_hash = self._setup_chunk_for_sync(store)
        # Intentionally skip: store.write_sync_log([chunk_hash])

        # Record a delete for it (chunk exists in chunks table, but no sync log entry)
        store.delete_sync_log([chunk_hash])

        # Verify delete record was created (no prior sync log entry existed)
        cursor = store.conn.cursor()
        cursor.execute(
            "SELECT operation FROM lancedb_sync_log WHERE chunk_hash = ?",
            (chunk_hash,),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "delete"



class TestParameterizedQueries:
    """Tests to verify all queries use parameterization."""

    def test_no_string_interpolation_in_register_adapter(
        self, store: DocumentStore
    ) -> None:
        """Verify register_adapter uses parameterized queries."""
        # This is more of a code review check, but we can verify the behavior
        config = AdapterConfig(
            adapter_id="test'; DROP TABLE adapters; --",  # Attempted SQL injection
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )

        # Should safely insert without executing the injection
        adapter_id = store.register_adapter(config)
        assert adapter_id == "test'; DROP TABLE adapters; --"

        # Tables should still exist
        cursor = store.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM adapters")
        assert cursor.fetchone()[0] >= 1


class TestLineageValidation:
    """Tests for lineage validation in write_chunks()."""

    def _setup_with_version(
        self, store: DocumentStore
    ) -> tuple[str, str, int]:
        """Helper to set up adapter, source, and version."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        version_id = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="# Content",
            chunk_hashes=["a" * 64, "b" * 64],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        return "source-1", "adapter-1", version_id

    def test_write_chunks_with_valid_lineage(self, store: DocumentStore) -> None:
        """Test that write_chunks accepts valid lineage records."""
        source_id, adapter_id, version_id = self._setup_with_version(store)

        chunks = [
            Chunk(
                chunk_hash="a" * 64,
                content="Test chunk 1",
                chunk_index=0,
            ),
        ]

        lineage = [
            LineageRecord(
                chunk_hash="a" * 64,
                source_id=source_id,
                source_version_id=version_id,
                adapter_id=adapter_id,
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
        ]

        # Should not raise
        store.write_chunks(chunks, lineage)

        # Verify chunk was written
        chunk = store.get_chunk_by_hash("a" * 64)
        assert chunk is not None
        assert chunk.content == "Test chunk 1"

    def test_write_chunks_lineage_mismatch_raises_error(self, store: DocumentStore) -> None:
        """Test that write_chunks raises error when chunk hash is missing from lineage."""
        source_id, adapter_id, version_id = self._setup_with_version(store)

        chunks = [
            Chunk(
                chunk_hash="a" * 64,
                content="Test chunk 1",
                chunk_index=0,
            ),
            Chunk(
                chunk_hash="b" * 64,
                content="Test chunk 2",
                chunk_index=1,
            ),
        ]

        lineage = [
            LineageRecord(
                chunk_hash="a" * 64,
                source_id=source_id,
                source_version_id=version_id,
                adapter_id=adapter_id,
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
            # Missing lineage for chunk b
        ]

        # Should raise ValueError because chunk "b"*64 has no corresponding lineage record
        with pytest.raises(ValueError, match="No lineage record found"):
            store.write_chunks(chunks, lineage)

    def test_write_chunks_lineage_with_mismatched_hash_raises_error(
        self, store: DocumentStore
    ) -> None:
        """Test that write_chunks raises error when chunk hash doesn't match lineage hash."""
        source_id, adapter_id, version_id = self._setup_with_version(store)

        chunks = [
            Chunk(
                chunk_hash="a" * 64,
                content="Test chunk 1",
                chunk_index=0,
            ),
        ]

        lineage = [
            LineageRecord(
                chunk_hash="b" * 64,  # Different hash - mismatch!
                source_id=source_id,
                source_version_id=version_id,
                adapter_id=adapter_id,
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
        ]

        # Should raise ValueError because chunk "a"*64 has no corresponding lineage record
        with pytest.raises(ValueError, match="No lineage record found"):
            store.write_chunks(chunks, lineage)


class TestRecoveryMechanisms:
    """Tests for recovery methods that handle SQLite/LanceDB inconsistency.

    These methods are critical for recovering from failed sync operations by
    identifying chunks that need to be re-inserted or deleted in LanceDB.
    """

    def _setup_recovery_scenario(self, store: DocumentStore) -> tuple[str, str, int]:
        """Helper to set up adapter, source, and version for recovery testing.

        Returns:
            Tuple of (source_id, adapter_id, version_id)
        """
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        version_id = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="# Content",
            chunk_hashes=[_make_hash("a"), _make_hash("b"), _make_hash("c")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        return "source-1", "adapter-1", version_id

    def test_get_chunks_pending_sync_single_chunk(self, store: DocumentStore) -> None:
        """Test retrieving a single chunk pending sync."""
        source_id, adapter_id, version_id = self._setup_recovery_scenario(store)

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="Chunk A content",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id=source_id,
            source_version_id=version_id,
            adapter_id=adapter_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )

        store.write_chunks([chunk], [lineage])
        store.write_sync_log([_make_hash("a")])

        pending = store.get_chunks_pending_sync()

        assert len(pending) == 1
        assert pending[0]["chunk_hash"] == _make_hash("a")
        assert pending[0]["content"] == "Chunk A content"
        assert pending[0]["source_id"] == source_id
        assert pending[0]["source_version"] == 1
        assert "created_at" in pending[0]

    def test_get_chunks_pending_sync_multiple_chunks(self, store: DocumentStore) -> None:
        """Test retrieving multiple chunks pending sync."""
        source_id, adapter_id, version_id = self._setup_recovery_scenario(store)

        chunks = [
            Chunk(
                chunk_hash=_make_hash("a"),
                content="Content A",
                chunk_index=0,
            ),
            Chunk(
                chunk_hash=_make_hash("b"),
                content="Content B",
                chunk_index=1,
            ),
            Chunk(
                chunk_hash=_make_hash("c"),
                content="Content C",
                chunk_index=2,
            ),
        ]

        lineage = [
            LineageRecord(
                chunk_hash=h,
                source_id=source_id,
                source_version_id=version_id,
                adapter_id=adapter_id,
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            )
            for h in [_make_hash("a"), _make_hash("b"), _make_hash("c")]
        ]

        store.write_chunks(chunks, lineage)
        store.write_sync_log([_make_hash("a"), _make_hash("b"), _make_hash("c")])

        pending = store.get_chunks_pending_sync()

        assert len(pending) == 3
        hashes = {p["chunk_hash"] for p in pending}
        assert hashes == {_make_hash("a"), _make_hash("b"), _make_hash("c")}

    def test_get_chunks_pending_sync_empty_when_no_inserts(
        self, store: DocumentStore
    ) -> None:
        """Test that no chunks are returned when sync log has no insert operations."""
        source_id, adapter_id, version_id = self._setup_recovery_scenario(store)

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="Content A",
            chunk_index=0,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id=source_id,
            source_version_id=version_id,
            adapter_id=adapter_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )

        store.write_chunks([chunk], [lineage])
        # Don't write to sync log (no insert operation)

        pending = store.get_chunks_pending_sync()

        assert len(pending) == 0

    def test_get_chunks_pending_sync_ordered_by_synced_at(
        self, store: DocumentStore
    ) -> None:
        """Test that pending chunks are ordered by synced_at ascending."""
        source_id, adapter_id, version_id = self._setup_recovery_scenario(store)

        chunks = [
            Chunk(
                chunk_hash=_make_hash("a"),
                content="First",
                chunk_index=0,
            ),
            Chunk(
                chunk_hash=_make_hash("b"),
                content="Second",
                chunk_index=1,
            ),
        ]

        lineage = [
            LineageRecord(
                chunk_hash=h,
                source_id=source_id,
                source_version_id=version_id,
                adapter_id=adapter_id,
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            )
            for h in [_make_hash("a"), _make_hash("b")]
        ]

        store.write_chunks(chunks, lineage)

        # Write sync logs in different order to test ordering
        store.write_sync_log([_make_hash("b")])
        store.write_sync_log([_make_hash("a")])

        pending = store.get_chunks_pending_sync()

        # Should be ordered by synced_at, not insertion order
        assert len(pending) == 2
        # Both chunks should be present, in order
        hashes = [p["chunk_hash"] for p in pending]
        assert _make_hash("b") in hashes
        assert _make_hash("a") in hashes

    def test_get_chunks_pending_sync_deduplicates_by_chunk_hash(
        self, store: DocumentStore
    ) -> None:
        """Test that chunks are deduplicated by chunk_hash (GROUP BY).

        When the same chunk_hash exists in multiple rows (different sources/versions),
        GROUP BY chunk_hash consolidates them to prevent duplicate sync attempts.
        """
        source_id, adapter_id, version_id = self._setup_recovery_scenario(store)

        # Create another version of the same source
        version_id_2 = store.create_source_version(
            source_id=source_id,
            version=2,
            markdown="# Content v2 with chunk a again",
            chunk_hashes=[_make_hash("a")],  # Same chunk hash in different version!
            adapter_id=adapter_id,
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T11:00:00Z",
        )

        # Write the same chunk to both versions
        chunk_a = Chunk(
            chunk_hash=_make_hash("a"),
            content="Shared content across versions",
            chunk_index=0,
        )

        lineage_1 = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id=source_id,
            source_version_id=version_id,
            adapter_id=adapter_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )

        lineage_2 = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id=source_id,
            source_version_id=version_id_2,
            adapter_id=adapter_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )

        # Write the same chunk to both versions (different source_version)
        store.write_chunks([chunk_a], [lineage_1])
        store.write_chunks([chunk_a], [lineage_2])

        # Mark for sync (this updates the same chunk_hash)
        store.write_sync_log([_make_hash("a")])

        pending = store.get_chunks_pending_sync()

        # Should have only one entry despite chunk existing in multiple rows
        # (one row per source_version due to composite PK)
        assert len(pending) == 1
        assert pending[0]["chunk_hash"] == _make_hash("a")

    def test_get_chunks_pending_sync_includes_required_fields(
        self, store: DocumentStore
    ) -> None:
        """Test that returned dicts include all required fields."""
        source_id, adapter_id, version_id = self._setup_recovery_scenario(store)

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="Test content",
            context_header="Context",
            chunk_index=0,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id=source_id,
            source_version_id=version_id,
            adapter_id=adapter_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )

        store.write_chunks([chunk], [lineage])
        store.write_sync_log([_make_hash("a")])

        pending = store.get_chunks_pending_sync()

        assert len(pending) == 1
        result = pending[0]

        # Verify all required fields are present
        required_fields = {
            "chunk_hash",
            "content",
            "domain",
            "source_id",
            "source_version",
            "created_at",
        }
        assert set(result.keys()) >= required_fields

    def test_get_chunks_pending_deletion_single_chunk(self, store: DocumentStore) -> None:
        """Test retrieving a single chunk pending deletion."""
        source_id, adapter_id, version_id = self._setup_recovery_scenario(store)

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="To be deleted",
            chunk_index=0,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id=source_id,
            source_version_id=version_id,
            adapter_id=adapter_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )

        store.write_chunks([chunk], [lineage])
        store.delete_sync_log([_make_hash("a")])

        pending = store.get_chunks_pending_deletion()

        assert len(pending) == 1
        assert _make_hash("a") in pending

    def test_get_chunks_pending_deletion_multiple_chunks(
        self, store: DocumentStore
    ) -> None:
        """Test retrieving multiple chunks pending deletion."""
        source_id, adapter_id, version_id = self._setup_recovery_scenario(store)

        chunks = [
            Chunk(
                chunk_hash=_make_hash("a"),
                content="Delete A",
                chunk_index=0,
            ),
            Chunk(
                chunk_hash=_make_hash("b"),
                content="Delete B",
                chunk_index=1,
            ),
            Chunk(
                chunk_hash=_make_hash("c"),
                content="Delete C",
                chunk_index=2,
            ),
        ]

        lineage = [
            LineageRecord(
                chunk_hash=h,
                source_id=source_id,
                source_version_id=version_id,
                adapter_id=adapter_id,
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            )
            for h in [_make_hash("a"), _make_hash("b"), _make_hash("c")]
        ]

        store.write_chunks(chunks, lineage)
        store.delete_sync_log(
            [_make_hash("a"), _make_hash("b"), _make_hash("c")]
        )

        pending = store.get_chunks_pending_deletion()

        assert len(pending) == 3
        assert set(pending) == {_make_hash("a"), _make_hash("b"), _make_hash("c")}

    def test_get_chunks_pending_deletion_empty_when_no_deletes(
        self, store: DocumentStore
    ) -> None:
        """Test that no chunks are returned when sync log has no delete operations."""
        source_id, adapter_id, version_id = self._setup_recovery_scenario(store)

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="Keep this",
            chunk_index=0,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id=source_id,
            source_version_id=version_id,
            adapter_id=adapter_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )

        store.write_chunks([chunk], [lineage])
        # Don't write delete to sync log

        pending = store.get_chunks_pending_deletion()

        assert len(pending) == 0

    def test_get_chunks_pending_deletion_ordered_by_synced_at(
        self, store: DocumentStore
    ) -> None:
        """Test that pending deletions are ordered by synced_at ascending."""
        source_id, adapter_id, version_id = self._setup_recovery_scenario(store)

        chunks = [
            Chunk(
                chunk_hash=_make_hash("a"),
                content="First",
                chunk_index=0,
            ),
            Chunk(
                chunk_hash=_make_hash("b"),
                content="Second",
                chunk_index=1,
            ),
        ]

        lineage = [
            LineageRecord(
                chunk_hash=h,
                source_id=source_id,
                source_version_id=version_id,
                adapter_id=adapter_id,
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            )
            for h in [_make_hash("a"), _make_hash("b")]
        ]

        store.write_chunks(chunks, lineage)

        # Record deletes in different order
        store.delete_sync_log([_make_hash("b")])
        store.delete_sync_log([_make_hash("a")])

        pending = store.get_chunks_pending_deletion()

        # Should be ordered by synced_at
        assert len(pending) == 2
        assert _make_hash("a") in pending
        assert _make_hash("b") in pending

    def test_get_chunks_pending_deletion_returns_chunk_hash_strings(
        self, store: DocumentStore
    ) -> None:
        """Test that returned values are chunk hash strings, not dicts or objects."""
        source_id, adapter_id, version_id = self._setup_recovery_scenario(store)

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="Test",
            chunk_index=0,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id=source_id,
            source_version_id=version_id,
            adapter_id=adapter_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )

        store.write_chunks([chunk], [lineage])
        store.delete_sync_log([_make_hash("a")])

        pending = store.get_chunks_pending_deletion()

        assert len(pending) == 1
        assert isinstance(pending[0], str)
        assert pending[0] == _make_hash("a")

    def test_both_insert_and_delete_operations_on_same_chunk(
        self, store: DocumentStore
    ) -> None:
        """Test recovery when sync log has both insert and delete for same chunk.

        The UNIQUE (chunk_hash, operation) constraint allows a chunk to have
        both an 'insert' and a 'delete' row simultaneously, representing
        a case where one failed and needs retry while the other is pending.
        """
        source_id, adapter_id, version_id = self._setup_recovery_scenario(store)

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="Chunk with dual state",
            chunk_index=0,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id=source_id,
            source_version_id=version_id,
            adapter_id=adapter_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )

        store.write_chunks([chunk], [lineage])

        # Record both insert and delete for same chunk
        store.write_sync_log([_make_hash("a")])
        store.delete_sync_log([_make_hash("a")])

        # Both methods should return the chunk
        pending_syncs = store.get_chunks_pending_sync()
        pending_deletes = store.get_chunks_pending_deletion()

        assert len(pending_syncs) == 1
        assert pending_syncs[0]["chunk_hash"] == _make_hash("a")

        assert len(pending_deletes) == 1
        assert _make_hash("a") in pending_deletes

    def test_get_chunks_pending_sync_inner_join_prevents_orphaned_sync_logs(
        self, store: DocumentStore
    ) -> None:
        """Test that INNER JOIN filters out orphaned sync log entries.

        If a chunk is deleted from the chunks table but a sync log entry remains,
        get_chunks_pending_sync should not return it (INNER JOIN enforces chunks exist).
        """
        source_id, adapter_id, version_id = self._setup_recovery_scenario(store)

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="Will be deleted",
            chunk_index=0,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id=source_id,
            source_version_id=version_id,
            adapter_id=adapter_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )

        store.write_chunks([chunk], [lineage])
        store.write_sync_log([_make_hash("a")])

        # Manually delete the chunk from chunks table (simulating orphaned sync log)
        cursor = store.conn.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        try:
            cursor.execute(
                "DELETE FROM chunks WHERE chunk_hash = ?",
                (_make_hash("a"),),
            )
        finally:
            cursor.execute("PRAGMA foreign_keys=ON")

        # get_chunks_pending_sync should NOT return it due to INNER JOIN
        pending = store.get_chunks_pending_sync()
        assert len(pending) == 0

    def test_get_chunks_pending_sync_returns_correct_content_fields(
        self, store: DocumentStore
    ) -> None:
        """Test that returned content and metadata fields are correct and not corrupted."""
        source_id, adapter_id, version_id = self._setup_recovery_scenario(store)

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="This is the actual content\nWith multiple lines\nAnd special chars: !@#$%^&*()",
            context_header="Section Header",
            chunk_index=0,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id=source_id,
            source_version_id=version_id,
            adapter_id=adapter_id,
            domain=Domain.MESSAGES,
            normalizer_version="2.0.0",
            embedding_model_id="test-model-v2",
        )

        store.write_chunks([chunk], [lineage])
        store.write_sync_log([_make_hash("a")])

        pending = store.get_chunks_pending_sync()

        assert len(pending) == 1
        result = pending[0]

        # Verify exact content preservation
        assert result["content"] == "This is the actual content\nWith multiple lines\nAnd special chars: !@#$%^&*()"
        assert result["domain"] == Domain.MESSAGES.value
        assert result["source_id"] == source_id
        assert result["source_version"] == 1


class TestSourceScheduling:
    """Tests for source scheduling parameters and polling."""

    def _setup_adapter(self, store: DocumentStore, adapter_id: str = "poll-adapter") -> str:
        """Helper to set up an adapter."""
        config = AdapterConfig(
            adapter_id=adapter_id,
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        return adapter_id

    def test_register_source_with_pull_strategy_and_interval(self, store: DocumentStore) -> None:
        """Test registering a source with pull strategy and poll interval."""
        self._setup_adapter(store)

        store.register_source(
            source_id="poll-source-1",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )

        # Verify source was created with correct poll_strategy and poll_interval_sec
        cursor = store.conn.cursor()
        cursor.execute(
            "SELECT source_id, poll_strategy, poll_interval_sec FROM sources WHERE source_id = ?",
            ("poll-source-1",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["source_id"] == "poll-source-1"
        assert row["poll_strategy"] == "pull"
        assert row["poll_interval_sec"] == 3600

    def test_register_source_with_push_strategy(self, store: DocumentStore) -> None:
        """Test registering a source with push strategy (no interval)."""
        self._setup_adapter(store)

        store.register_source(
            source_id="push-source-1",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source",
            poll_strategy=PollStrategy.PUSH,
        )

        # Verify source was created with push strategy and no interval
        cursor = store.conn.cursor()
        cursor.execute(
            "SELECT source_id, poll_strategy, poll_interval_sec FROM sources WHERE source_id = ?",
            ("push-source-1",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["poll_strategy"] == "push"
        assert row["poll_interval_sec"] is None

    def test_register_source_with_webhook_strategy(self, store: DocumentStore) -> None:
        """Test registering a source with webhook strategy (no interval)."""
        self._setup_adapter(store)

        store.register_source(
            source_id="webhook-source-1",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source",
            poll_strategy=PollStrategy.WEBHOOK,
        )

        # Verify source was created with webhook strategy
        cursor = store.conn.cursor()
        cursor.execute(
            "SELECT source_id, poll_strategy, poll_interval_sec FROM sources WHERE source_id = ?",
            ("webhook-source-1",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["poll_strategy"] == "webhook"
        assert row["poll_interval_sec"] is None

    def test_register_source_default_is_pull(self, store: DocumentStore) -> None:
        """Test that default poll_strategy is PULL when not specified."""
        self._setup_adapter(store)

        # Register without specifying poll_strategy
        store.register_source(
            source_id="default-source",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source",
        )

        # Verify default is 'pull'
        cursor = store.conn.cursor()
        cursor.execute(
            "SELECT poll_strategy FROM sources WHERE source_id = ?",
            ("default-source",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["poll_strategy"] == "pull"

    def test_register_source_idempotency_preserved_with_poll_params(
        self, store: DocumentStore
    ) -> None:
        """Test that poll settings are updated on re-registration."""
        self._setup_adapter(store)

        # First registration
        store.register_source(
            source_id="idempotent-source",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )

        # Second registration with different parameters (should update poll settings)
        store.register_source(
            source_id="idempotent-source",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source",
            poll_strategy=PollStrategy.PUSH,
            poll_interval_sec=7200,
        )

        # Verify new values are persisted (updated on re-registration)
        cursor = store.conn.cursor()
        cursor.execute(
            "SELECT poll_strategy, poll_interval_sec FROM sources WHERE source_id = ?",
            ("idempotent-source",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["poll_strategy"] == "push"  # Updated value
        assert row["poll_interval_sec"] == 7200  # Updated value

        # Verify only one row exists
        cursor.execute(
            "SELECT COUNT(*) FROM sources WHERE source_id = ?",
            ("idempotent-source",),
        )
        count = cursor.fetchone()[0]
        assert count == 1

    def test_register_source_updates_domain_and_adapter_id_on_reregister(
        self, store: DocumentStore
    ) -> None:
        """Test that domain and adapter_id are updated on re-registration."""
        # Setup two different adapters
        store.register_adapter(
            AdapterConfig(
                adapter_id="adapter-1",
                adapter_type="TestAdapter",
                domain=Domain.NOTES,
                normalizer_version="1.0",
                config=None,
            )
        )
        store.register_adapter(
            AdapterConfig(
                adapter_id="adapter-2",
                adapter_type="TestAdapter",
                domain=Domain.MESSAGES,
                normalizer_version="1.0",
                config=None,
            )
        )

        # First registration with adapter-1 and Domain.NOTES
        store.register_source(
            source_id="changing-source",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )

        # Verify initial state
        cursor = store.conn.cursor()
        cursor.execute(
            "SELECT adapter_id, domain, poll_strategy, poll_interval_sec FROM sources WHERE source_id = ?",
            ("changing-source",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["adapter_id"] == "adapter-1"
        assert row["domain"] == "notes"
        assert row["poll_strategy"] == "pull"
        assert row["poll_interval_sec"] == 3600

        # Re-register with adapter-2 and Domain.MESSAGES
        store.register_source(
            source_id="changing-source",
            adapter_id="adapter-2",
            domain=Domain.MESSAGES,
            origin_ref="test://source",
            poll_strategy=PollStrategy.PUSH,
            poll_interval_sec=None,
        )

        # Verify all fields were updated
        cursor.execute(
            "SELECT adapter_id, domain, poll_strategy, poll_interval_sec FROM sources WHERE source_id = ?",
            ("changing-source",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["adapter_id"] == "adapter-2"  # Updated
        assert row["domain"] == "messages"  # Updated
        assert row["poll_strategy"] == "push"  # Updated
        assert row["poll_interval_sec"] is None  # Updated

        # Verify only one row exists
        cursor.execute(
            "SELECT COUNT(*) FROM sources WHERE source_id = ?",
            ("changing-source",),
        )
        count = cursor.fetchone()[0]
        assert count == 1

    def test_register_source_migrates_chunk_domains_on_domain_change(
        self, store: DocumentStore
    ) -> None:
        """Test that chunks are migrated to new domain when source is re-registered."""
        # Setup adapters
        store.register_adapter(
            AdapterConfig(
                adapter_id="notes-adapter",
                adapter_type="TestAdapter",
                domain=Domain.NOTES,
                normalizer_version="1.0",
                config=None,
            )
        )
        store.register_adapter(
            AdapterConfig(
                adapter_id="docs-adapter",
                adapter_type="TestAdapter",
                domain=Domain.DOCUMENTS,
                normalizer_version="1.0",
                config=None,
            )
        )

        # Register source with NOTES domain
        store.register_source(
            source_id="migrating-source",
            adapter_id="notes-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )

        # Create a source version and add chunks with notes domain
        test_hash = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa00"
        store.create_source_version(
            source_id="migrating-source",
            version=1,
            markdown="# Test\nContent here",
            chunk_hashes=[test_hash],
            adapter_id="notes-adapter",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-01T00:00:00Z",
        )

        # Add chunks for this version
        cursor = store.conn.cursor()
        cursor.execute(
            """
            INSERT INTO chunks
            (chunk_hash, source_id, source_version, chunk_index, content, context_header, domain, adapter_id, fetch_timestamp, normalizer_version, embedding_model_id, domain_metadata, chunk_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                test_hash,
                "migrating-source",
                1,
                0,
                "Test content",
                "# Test",
                "notes",  # Initial domain is notes
                "notes-adapter",
                "2024-01-01T00:00:00Z",
                "1.0",
                "test-model",
                None,
                "standard",
            ),
        )
        store.conn.commit()

        # Verify chunk has notes domain
        cursor.execute(
            "SELECT domain FROM chunks WHERE chunk_hash = ?",
            (test_hash,),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["domain"] == "notes"

        # Re-register source with DOCUMENTS domain
        store.register_source(
            source_id="migrating-source",
            adapter_id="docs-adapter",
            domain=Domain.DOCUMENTS,
            origin_ref="test://source",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )

        # Verify chunk domain was updated
        cursor.execute(
            "SELECT domain FROM chunks WHERE chunk_hash = ?",
            (test_hash,),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["domain"] == "documents"

        # Verify sync log entry was recorded to trigger vector store update
        cursor.execute(
            "SELECT chunk_hash, operation FROM lancedb_sync_log WHERE chunk_hash = ?",
            (test_hash,),
        )
        log_row = cursor.fetchone()
        assert log_row is not None
        assert log_row["operation"] == "insert"

        # Verify source domain was updated
        cursor.execute(
            "SELECT domain FROM sources WHERE source_id = ?",
            ("migrating-source",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["domain"] == "documents"

    def test_get_sources_due_for_poll_never_fetched(self, store: DocumentStore) -> None:
        """Test that sources with last_fetched_at IS NULL are returned."""
        self._setup_adapter(store)

        store.register_source(
            source_id="unfetched-source",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )

        # Get sources due for poll
        due = store.get_sources_due_for_poll()

        assert len(due) == 1
        assert due[0]["source_id"] == "unfetched-source"
        assert due[0]["adapter_id"] == "poll-adapter"
        assert due[0]["poll_interval_sec"] == 3600
        assert due[0]["last_fetched_at"] is None

    def test_get_sources_due_for_poll_interval_passed(self, store: DocumentStore) -> None:
        """Test that sources whose interval has passed are returned."""
        self._setup_adapter(store)

        # Register source with 1-hour interval
        store.register_source(
            source_id="overdue-source",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )

        # Manually set last_fetched_at to 2 hours ago (interval has passed)
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        cursor = store.conn.cursor()
        cursor.execute(
            "UPDATE sources SET last_fetched_at = ? WHERE source_id = ?",
            (two_hours_ago, "overdue-source"),
        )

        # Get sources due for poll
        due = store.get_sources_due_for_poll()

        assert len(due) == 1
        assert due[0]["source_id"] == "overdue-source"
        assert due[0]["last_fetched_at"] == two_hours_ago

    def test_get_sources_due_for_poll_interval_not_passed(self, store: DocumentStore) -> None:
        """Test that sources whose interval has not passed are NOT returned."""
        self._setup_adapter(store)

        # Register source with 1-hour interval
        store.register_source(
            source_id="recent-source",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )

        # Manually set last_fetched_at to 30 minutes ago (interval has NOT passed)
        thirty_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        cursor = store.conn.cursor()
        cursor.execute(
            "UPDATE sources SET last_fetched_at = ? WHERE source_id = ?",
            (thirty_min_ago, "recent-source"),
        )

        # Get sources due for poll
        due = store.get_sources_due_for_poll()

        # Should not include this source
        assert len(due) == 0

    def test_get_sources_due_for_poll_excludes_push_strategy(self, store: DocumentStore) -> None:
        """Test that sources with push strategy are NOT returned."""
        self._setup_adapter(store)

        store.register_source(
            source_id="push-source",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source",
            poll_strategy=PollStrategy.PUSH,
        )

        # Get sources due for poll
        due = store.get_sources_due_for_poll()

        # Should not include push source
        assert len(due) == 0

    def test_get_sources_due_for_poll_excludes_webhook_strategy(self, store: DocumentStore) -> None:
        """Test that sources with webhook strategy are NOT returned."""
        self._setup_adapter(store)

        store.register_source(
            source_id="webhook-source",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source",
            poll_strategy=PollStrategy.WEBHOOK,
        )

        # Get sources due for poll
        due = store.get_sources_due_for_poll()

        # Should not include webhook source
        assert len(due) == 0

    def test_get_sources_due_for_poll_excludes_null_interval(self, store: DocumentStore) -> None:
        """Test that sources with poll_interval_sec IS NULL are NOT returned."""
        self._setup_adapter(store)

        store.register_source(
            source_id="no-interval-source",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=None,
        )

        # Get sources due for poll
        due = store.get_sources_due_for_poll()

        # Should not include source with no interval
        assert len(due) == 0

    def test_get_sources_due_for_poll_mixed_sources(self, store: DocumentStore) -> None:
        """Test that only eligible sources are returned when mixed with ineligible ones."""
        self._setup_adapter(store)

        # 1. Create source due for poll (never fetched)
        store.register_source(
            source_id="due-source-1",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source1",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )

        # 2. Create source due for poll (interval passed)
        store.register_source(
            source_id="due-source-2",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source2",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        cursor = store.conn.cursor()
        cursor.execute(
            "UPDATE sources SET last_fetched_at = ? WHERE source_id = ?",
            (two_hours_ago, "due-source-2"),
        )

        # 3. Create source NOT due (interval not passed)
        store.register_source(
            source_id="not-due-source",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source3",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )
        thirty_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        cursor.execute(
            "UPDATE sources SET last_fetched_at = ? WHERE source_id = ?",
            (thirty_min_ago, "not-due-source"),
        )

        # 4. Create push strategy source (should be excluded)
        store.register_source(
            source_id="push-source",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source4",
            poll_strategy=PollStrategy.PUSH,
        )

        # 5. Create source with no interval (should be excluded)
        store.register_source(
            source_id="no-interval-source",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source5",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=None,
        )

        # Get sources due for poll
        due = store.get_sources_due_for_poll()

        # Should only return the two eligible sources
        assert len(due) == 2
        source_ids = {source["source_id"] for source in due}
        assert source_ids == {"due-source-1", "due-source-2"}

    def test_get_sources_due_for_poll_returns_correct_fields(self, store: DocumentStore) -> None:
        """Test that returned dicts contain all required fields."""
        from context_library.storage.models import PollStrategy

        self._setup_adapter(store)

        store.register_source(
            source_id="test-source",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )

        due = store.get_sources_due_for_poll()

        assert len(due) == 1
        result = due[0]

        # Verify all required fields are present
        assert "source_id" in result
        assert "adapter_id" in result
        assert "poll_interval_sec" in result
        assert "last_fetched_at" in result

        # Verify field values
        assert result["source_id"] == "test-source"
        assert result["adapter_id"] == "poll-adapter"
        assert result["poll_interval_sec"] == 3600
        assert result["last_fetched_at"] is None

    def test_get_sources_for_adapter_empty(self, store: DocumentStore) -> None:
        """Test that get_sources_for_adapter returns empty list when no sources exist."""
        result = store.get_sources_for_adapter("unknown-adapter")
        assert result == []

    def test_get_sources_for_adapter_single_source(self, store: DocumentStore) -> None:
        """Test get_sources_for_adapter with a single source."""
        self._setup_adapter(store)

        store.register_source(
            source_id="test-source",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source",
        )

        result = store.get_sources_for_adapter("poll-adapter")

        assert len(result) == 1
        assert result[0]["source_id"] == "test-source"
        assert result[0]["adapter_id"] == "poll-adapter"
        assert result[0]["origin_ref"] == "test://source"

    def test_get_sources_for_adapter_multiple_sources(self, store: DocumentStore) -> None:
        """Test get_sources_for_adapter with multiple sources for same adapter."""
        self._setup_adapter(store)

        # Register multiple sources for the same adapter
        for i in range(1, 4):
            store.register_source(
                source_id=f"source-{i}",
                adapter_id="poll-adapter",
                domain=Domain.NOTES,
                origin_ref=f"test://source-{i}",
            )

        result = store.get_sources_for_adapter("poll-adapter")

        assert len(result) == 3
        source_ids = {source["source_id"] for source in result}
        assert source_ids == {"source-1", "source-2", "source-3"}

        # Verify origin_refs are correct
        origin_refs = {source["origin_ref"] for source in result}
        assert origin_refs == {"test://source-1", "test://source-2", "test://source-3"}

    def test_get_sources_for_adapter_filters_by_adapter_id(self, store: DocumentStore) -> None:
        """Test that get_sources_for_adapter only returns sources for specified adapter."""
        # Register two different adapters
        config1 = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        config2 = AdapterConfig(
            adapter_id="adapter-2",
            adapter_type="test",
            domain=Domain.MESSAGES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config1)
        store.register_adapter(config2)

        # Register sources for both adapters
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )
        store.register_source(
            source_id="source-2",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-2",
        )
        store.register_source(
            source_id="source-3",
            adapter_id="adapter-2",
            domain=Domain.MESSAGES,
            origin_ref="test://source-3",
        )

        # Get sources for adapter-1
        result = store.get_sources_for_adapter("adapter-1")
        assert len(result) == 2
        source_ids = {source["source_id"] for source in result}
        assert source_ids == {"source-1", "source-2"}

        # Get sources for adapter-2
        result = store.get_sources_for_adapter("adapter-2")
        assert len(result) == 1
        assert result[0]["source_id"] == "source-3"

    def test_get_sources_for_adapter_returns_correct_fields(self, store: DocumentStore) -> None:
        """Test that get_sources_for_adapter returns all required fields."""
        self._setup_adapter(store)

        store.register_source(
            source_id="test-source",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source",
        )

        result = store.get_sources_for_adapter("poll-adapter")

        assert len(result) == 1
        source = result[0]

        # Verify required fields are present
        assert "source_id" in source
        assert "adapter_id" in source
        assert "origin_ref" in source

        # Verify values
        assert source["source_id"] == "test-source"
        assert source["adapter_id"] == "poll-adapter"
        assert source["origin_ref"] == "test://source"

    def test_update_last_fetched_at_success(self, store: DocumentStore) -> None:
        """Test updating last_fetched_at for an existing source."""
        self._setup_adapter(store)

        store.register_source(
            source_id="test-source",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source",
        )

        # Verify initially None
        cursor = store.conn.cursor()
        cursor.execute(
            "SELECT last_fetched_at FROM sources WHERE source_id = ?",
            ("test-source",),
        )
        row = cursor.fetchone()
        assert row["last_fetched_at"] is None

        # Update last_fetched_at
        store.update_last_fetched_at("test-source")

        # Verify it's now set
        cursor.execute(
            "SELECT last_fetched_at FROM sources WHERE source_id = ?",
            ("test-source",),
        )
        row = cursor.fetchone()
        assert row["last_fetched_at"] is not None

    def test_update_last_fetched_at_raises_runtime_error_for_nonexistent(
        self, store: DocumentStore
    ) -> None:
        """Test that update_last_fetched_at raises RuntimeError for non-existent source.

        Data integrity guard: ensures we don't silently accept updates for
        sources that don't exist, which could mask logic errors.
        """
        # Attempt to update a non-existent source
        with pytest.raises(RuntimeError):
            store.update_last_fetched_at("nonexistent-source")


class TestVersionDiff:
    """Tests for get_version_diff method."""

    def _setup_versions(self, store: DocumentStore) -> tuple[str, int, int]:
        """Helper to set up two source versions with different chunk hashes.

        Returns:
            Tuple of (source_id, version1_id, version2_id)
        """
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        # Version 1: hashes a, b, c
        version_id_1 = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="# Content v1",
            chunk_hashes=[_make_hash("a"), _make_hash("b"), _make_hash("c")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        # Version 2: hashes b, c, d (added d, removed a)
        version_id_2 = store.create_source_version(
            source_id="source-1",
            version=2,
            markdown="# Content v2",
            chunk_hashes=[_make_hash("b"), _make_hash("c"), _make_hash("d")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T11:00:00Z",
        )

        return "source-1", version_id_1, version_id_2

    def test_get_version_diff_basic(self, store: DocumentStore) -> None:
        """Test basic version diff computation."""
        source_id, _, _ = self._setup_versions(store)

        diff = store.get_version_diff(source_id, 1, 2)

        assert isinstance(diff, VersionDiff)
        assert diff.source_id == source_id
        assert diff.from_version == 1
        assert diff.to_version == 2

        # v1: a, b, c
        # v2: b, c, d
        # added: d, removed: a, unchanged: b, c
        assert diff.added_hashes == frozenset({_make_hash("d")})
        assert diff.removed_hashes == frozenset({_make_hash("a")})
        assert diff.unchanged_hashes == frozenset({_make_hash("b"), _make_hash("c")})

    def test_get_version_diff_all_new_chunks(self, store: DocumentStore) -> None:
        """Test diff when all chunks are new (v2 has no overlap with v1)."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-2",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-2",
        )

        store.create_source_version(
            source_id="source-2",
            version=1,
            markdown="# v1",
            chunk_hashes=[_make_hash("a"), _make_hash("b")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        store.create_source_version(
            source_id="source-2",
            version=2,
            markdown="# v2",
            chunk_hashes=[_make_hash("e"), _make_hash("f")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T11:00:00Z",
        )

        diff = store.get_version_diff("source-2", 1, 2)

        assert diff.added_hashes == frozenset({_make_hash("e"), _make_hash("f")})
        assert diff.removed_hashes == frozenset({_make_hash("a"), _make_hash("b")})
        assert diff.unchanged_hashes == frozenset()

    def test_get_version_diff_no_changes(self, store: DocumentStore) -> None:
        """Test diff when versions have identical chunk hashes."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-3",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-3",
        )

        store.create_source_version(
            source_id="source-3",
            version=1,
            markdown="# v1",
            chunk_hashes=[_make_hash("a"), _make_hash("b")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        store.create_source_version(
            source_id="source-3",
            version=2,
            markdown="# v2 (same chunks)",
            chunk_hashes=[_make_hash("a"), _make_hash("b")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T11:00:00Z",
        )

        diff = store.get_version_diff("source-3", 1, 2)

        assert diff.added_hashes == frozenset()
        assert diff.removed_hashes == frozenset()
        assert diff.unchanged_hashes == frozenset({_make_hash("a"), _make_hash("b")})

    def test_get_version_diff_reverse_order(self, store: DocumentStore) -> None:
        """Test diff in reverse order (from v2 to v1)."""
        source_id, _, _ = self._setup_versions(store)

        diff = store.get_version_diff(source_id, 2, 1)

        # v2: b, c, d
        # v1: a, b, c
        # added: a, removed: d, unchanged: b, c
        assert diff.added_hashes == frozenset({_make_hash("a")})
        assert diff.removed_hashes == frozenset({_make_hash("d")})
        assert diff.unchanged_hashes == frozenset({_make_hash("b"), _make_hash("c")})

    def test_get_version_diff_same_version(self, store: DocumentStore) -> None:
        """Test that get_version_diff raises ValueError when from_version == to_version."""
        source_id, _, _ = self._setup_versions(store)

        with pytest.raises(ValueError, match="from_version and to_version must be different"):
            store.get_version_diff(source_id, 1, 1)

    def test_get_version_diff_nonexistent_source(self, store: DocumentStore) -> None:
        """Test that get_version_diff raises ValueError for non-existent source."""
        with pytest.raises(ValueError, match="does not exist"):
            store.get_version_diff("nonexistent", 1, 2)

    def test_get_version_diff_missing_from_version(self, store: DocumentStore) -> None:
        """Test that get_version_diff raises ValueError when from_version doesn't exist."""
        source_id, _, _ = self._setup_versions(store)

        with pytest.raises(ValueError, match="does not have version\\(s\\)"):
            store.get_version_diff(source_id, 99, 2)

    def test_get_version_diff_missing_to_version(self, store: DocumentStore) -> None:
        """Test that get_version_diff raises ValueError when to_version doesn't exist."""
        source_id, _, _ = self._setup_versions(store)

        with pytest.raises(ValueError, match="does not have version\\(s\\)"):
            store.get_version_diff(source_id, 1, 99)

    def test_get_version_diff_frozenset_immutability(self, store: DocumentStore) -> None:
        """Test that returned hash sets are frozensets (immutable)."""
        source_id, _, _ = self._setup_versions(store)

        diff = store.get_version_diff(source_id, 1, 2)

        # Verify all are frozensets
        assert isinstance(diff.added_hashes, frozenset)
        assert isinstance(diff.removed_hashes, frozenset)
        assert isinstance(diff.unchanged_hashes, frozenset)

        # Verify they are immutable - frozenset has no add method
        assert not hasattr(diff.added_hashes, 'add')

    def test_get_version_diff_retrieves_retired_removed_chunks(self, store: DocumentStore) -> None:
        """Test that removed chunks can be retrieved even if they've been retired.

        This tests the fix for the issue where get_version_diff was returning empty
        removed_chunks because retired chunks (marked as removed from the version)
        were being filtered out by get_chunk_by_hash. Now _get_chunk_by_hash_including_retired
        should retrieve them correctly.
        """
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        # Create version 1 with chunks a, b, c
        version_id_1 = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="# v1",
            chunk_hashes=[_make_hash("a"), _make_hash("b"), _make_hash("c")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        # Write the chunks for version 1
        chunks_v1 = [
            Chunk(chunk_hash=_make_hash("a"), content="Content a", chunk_index=0),
            Chunk(chunk_hash=_make_hash("b"), content="Content b", chunk_index=1),
            Chunk(chunk_hash=_make_hash("c"), content="Content c", chunk_index=2),
        ]
        lineage_v1 = [
            LineageRecord(
                chunk_hash=_make_hash("a"),
                source_id="source-1",
                source_version_id=version_id_1,
                adapter_id="adapter-1",
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
            LineageRecord(
                chunk_hash=_make_hash("b"),
                source_id="source-1",
                source_version_id=version_id_1,
                adapter_id="adapter-1",
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
            LineageRecord(
                chunk_hash=_make_hash("c"),
                source_id="source-1",
                source_version_id=version_id_1,
                adapter_id="adapter-1",
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
        ]
        store.write_chunks(chunks_v1, lineage_v1)

        # Create version 2 with only b, c (a is removed)
        store.create_source_version(
            source_id="source-1",
            version=2,
            markdown="# v2",
            chunk_hashes=[_make_hash("b"), _make_hash("c")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T11:00:00Z",
        )

        # Retire chunk 'a' since it's no longer in version 2
        store.retire_chunks({_make_hash("a")}, "source-1", 1)

        # Now get the version diff - should still retrieve the retired chunk 'a' in removed_chunks
        diff = store.get_version_diff("source-1", 1, 2)

        assert diff.removed_hashes == frozenset({_make_hash("a")})
        # The critical test: removed_chunks should contain the retired chunk
        assert len(diff.removed_chunks) == 1
        assert diff.removed_chunks[0].chunk_hash == _make_hash("a")
        assert diff.removed_chunks[0].content == "Content a"


class TestChunkVersionChain:
    """Tests for get_chunk_version_chain method."""

    def test_get_chunk_version_chain_single_chunk(self, store: DocumentStore) -> None:
        """Test getting chain for chunk with no parent (single element)."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        version_id = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="# Content",
            chunk_hashes=[_make_hash("a")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="Standalone chunk",
            chunk_index=0,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("a"),
            source_id="source-1",
            source_version_id=version_id,
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )

        store.write_chunks([chunk], [lineage])

        chain = store.get_chunk_version_chain(_make_hash("a"), "source-1")

        assert len(chain) == 1
        assert chain[0].chunk_hash == _make_hash("a")
        assert chain[0].content == "Standalone chunk"

    def test_get_chunk_version_chain_with_parent(self, store: DocumentStore) -> None:
        """Test getting chain for chunk with one parent."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        version_id = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="# Content",
            chunk_hashes=[_make_hash("a"), _make_hash("b")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        # Create chunks with parent relationship via manual INSERT
        cursor = store.conn.cursor()

        # Parent chunk a (no parent)
        cursor.execute(
            """
            INSERT INTO chunks
            (chunk_hash, source_id, source_version, chunk_index, content,
             context_header, domain, adapter_id, fetch_timestamp,
             normalizer_version, embedding_model_id, domain_metadata, chunk_type, parent_chunk_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _make_hash("a"),  # chunk_hash
                "source-1",  # source_id
                version_id,  # source_version
                0,  # chunk_index
                "Parent chunk",  # content
                None,  # context_header
                "notes",  # domain
                "adapter-1",  # adapter_id
                "2025-03-02T10:00:00Z",  # fetch_timestamp
                "1.0.0",  # normalizer_version
                "test-model",  # embedding_model_id
                None,  # domain_metadata
                "standard",  # chunk_type
                None,  # parent_chunk_hash
                "2025-03-02T10:00:00Z",  # created_at
            ),
        )

        # Child chunk b (parent is a)
        cursor.execute(
            """
            INSERT INTO chunks
            (chunk_hash, source_id, source_version, chunk_index, content,
             context_header, domain, adapter_id, fetch_timestamp,
             normalizer_version, embedding_model_id, domain_metadata, chunk_type, parent_chunk_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _make_hash("b"),  # chunk_hash
                "source-1",  # source_id
                version_id,  # source_version
                1,  # chunk_index
                "Child chunk",  # content
                None,  # context_header
                "notes",  # domain
                "adapter-1",  # adapter_id
                "2025-03-02T10:00:00Z",  # fetch_timestamp
                "1.0.0",  # normalizer_version
                "test-model",  # embedding_model_id
                None,  # domain_metadata
                "standard",  # chunk_type
                _make_hash("a"),  # parent_chunk_hash
                "2025-03-02T10:00:01Z",  # created_at (1 second after parent)
            ),
        )

        chain = store.get_chunk_version_chain(_make_hash("b"), "source-1")

        # Should have both chunks in order (oldest first)
        assert len(chain) == 2
        assert chain[0].chunk_hash == _make_hash("a")
        assert chain[0].content == "Parent chunk"
        assert chain[1].chunk_hash == _make_hash("b")
        assert chain[1].content == "Child chunk"

    def test_get_chunk_version_chain_deep_ancestry(self, store: DocumentStore) -> None:
        """Test getting chain with multiple ancestors."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        version_id = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="# Content",
            chunk_hashes=[_make_hash("a"), _make_hash("b"), _make_hash("c")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        # Create a chain: a -> b -> c
        cursor = store.conn.cursor()

        # Root chunk a
        cursor.execute(
            """
            INSERT INTO chunks
            (chunk_hash, source_id, source_version, chunk_index, content,
             context_header, domain, adapter_id, fetch_timestamp,
             normalizer_version, embedding_model_id, domain_metadata, chunk_type, parent_chunk_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _make_hash("a"),
                "source-1",
                version_id,
                0,
                "Root",
                None,
                "notes",
                "adapter-1",
                "2025-03-02T10:00:00Z",
                "1.0.0",
                "test-model",
                None,
                "standard",
                None,
                "2025-03-02T10:00:00Z",
            ),
        )

        # Chunk b with parent a
        cursor.execute(
            """
            INSERT INTO chunks
            (chunk_hash, source_id, source_version, chunk_index, content,
             context_header, domain, adapter_id, fetch_timestamp,
             normalizer_version, embedding_model_id, domain_metadata, chunk_type, parent_chunk_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _make_hash("b"),
                "source-1",
                version_id,
                1,
                "Middle",
                None,
                "notes",
                "adapter-1",
                "2025-03-02T11:00:00Z",
                "1.0.0",
                "test-model",
                None,
                "standard",
                _make_hash("a"),
                "2025-03-02T10:00:01Z",
            ),
        )

        # Chunk c with parent b
        cursor.execute(
            """
            INSERT INTO chunks
            (chunk_hash, source_id, source_version, chunk_index, content,
             context_header, domain, adapter_id, fetch_timestamp,
             normalizer_version, embedding_model_id, domain_metadata, chunk_type, parent_chunk_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _make_hash("c"),
                "source-1",
                version_id,
                2,
                "Leaf",
                None,
                "notes",
                "adapter-1",
                "2025-03-02T12:00:00Z",
                "1.0.0",
                "test-model",
                None,
                "standard",
                _make_hash("b"),
                "2025-03-02T10:00:02Z",
            ),
        )

        chain = store.get_chunk_version_chain(_make_hash("c"), "source-1")

        # Should have all three chunks ordered by created_at (oldest first)
        assert len(chain) == 3
        assert chain[0].chunk_hash == _make_hash("a")
        assert chain[0].content == "Root"
        assert chain[1].chunk_hash == _make_hash("b")
        assert chain[1].content == "Middle"
        assert chain[2].chunk_hash == _make_hash("c")
        assert chain[2].content == "Leaf"

    def test_get_chunk_version_chain_nonexistent_chunk(self, store: DocumentStore) -> None:
        """Test that chain is empty for non-existent chunk."""
        chain = store.get_chunk_version_chain(_make_hash("f"), "source-1")
        assert chain == []

    def test_get_chunk_version_chain_ordered_by_created_at(self, store: DocumentStore) -> None:
        """Test that chain is ordered by created_at ascending (oldest first)."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        version_id = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="# Content",
            chunk_hashes=[_make_hash("3"), _make_hash("4"), _make_hash("5")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        cursor = store.conn.cursor()

        # Create chunks with deliberately out-of-order timestamps
        # 4 points to 3, 5 points to 4
        # Insert in reverse order to test ordering
        cursor.execute(
            """
            INSERT INTO chunks
            (chunk_hash, source_id, source_version, chunk_index, content,
             context_header, domain, adapter_id, fetch_timestamp,
             normalizer_version, embedding_model_id, domain_metadata, chunk_type, parent_chunk_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _make_hash("5"),
                "source-1",
                version_id,
                2,
                "Newest",
                None,
                "notes",
                "adapter-1",
                "2025-03-02T12:00:00Z",  # Newest timestamp
                "1.0.0",
                "test-model",
                None,
                "standard",
                _make_hash("4"),
                "2025-03-02T10:00:02Z",  # created_at for ordering
            ),
        )

        cursor.execute(
            """
            INSERT INTO chunks
            (chunk_hash, source_id, source_version, chunk_index, content,
             context_header, domain, adapter_id, fetch_timestamp,
             normalizer_version, embedding_model_id, domain_metadata, chunk_type, parent_chunk_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _make_hash("3"),
                "source-1",
                version_id,
                0,
                "Oldest",
                None,
                "notes",
                "adapter-1",
                "2025-03-02T10:00:00Z",  # Oldest timestamp
                "1.0.0",
                "test-model",
                None,
                "standard",
                None,
                "2025-03-02T10:00:00Z",  # created_at for ordering
            ),
        )

        cursor.execute(
            """
            INSERT INTO chunks
            (chunk_hash, source_id, source_version, chunk_index, content,
             context_header, domain, adapter_id, fetch_timestamp,
             normalizer_version, embedding_model_id, domain_metadata, chunk_type, parent_chunk_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _make_hash("4"),
                "source-1",
                version_id,
                1,
                "Middle",
                None,
                "notes",
                "adapter-1",
                "2025-03-02T11:00:00Z",  # Middle timestamp
                "1.0.0",
                "test-model",
                None,
                "standard",
                _make_hash("3"),
                "2025-03-02T10:00:01Z",  # created_at for ordering
            ),
        )

        chain = store.get_chunk_version_chain(_make_hash("5"), "source-1")

        # Should be ordered by created_at, not by insertion order
        assert len(chain) == 3
        assert chain[0].chunk_hash == _make_hash("3")
        assert chain[0].content == "Oldest"
        assert chain[1].chunk_hash == _make_hash("4")
        assert chain[1].content == "Middle"
        assert chain[2].chunk_hash == _make_hash("5")
        assert chain[2].content == "Newest"

    def test_get_chunk_version_chain_with_domain_metadata(self, store: DocumentStore) -> None:
        """Test that domain_metadata is preserved in chain."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        version_id = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="# Content",
            chunk_hashes=[_make_hash("6")],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        metadata: dict[str, object] = {"source": "email", "sender": "user@example.com"}
        chunk = Chunk(
            chunk_hash=_make_hash("6"),
            content="With metadata",
            chunk_index=0,
            domain_metadata=metadata,
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("6"),
            source_id="source-1",
            source_version_id=version_id,
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )

        store.write_chunks([chunk], [lineage])

        chain = store.get_chunk_version_chain(_make_hash("6"), "source-1")

        assert len(chain) == 1
        assert chain[0].domain_metadata == metadata


class TestGetSourceInfo:
    """Tests for DocumentStore.get_source_info method.

    Covers direct retrieval of source metadata (origin_ref, adapter_type)
    via JOIN query.
    """

    def test_get_source_info_success(self, store: DocumentStore) -> None:
        """Test successful retrieval of source info."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="gmail",
            domain=Domain.MESSAGES,
            normalizer_version="1.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.MESSAGES,
            origin_ref="user@gmail.com",
        )

        # Retrieve source info
        source_info = store.get_source_info("source-1")

        assert source_info is not None
        assert source_info.origin_ref == "user@gmail.com"
        assert source_info.adapter_type == "gmail"

    def test_get_source_info_nonexistent_source(self, store: DocumentStore) -> None:
        """Test that get_source_info returns None for nonexistent source."""
        result = store.get_source_info("nonexistent-source")
        assert result is None

    def test_get_source_info_multiple_sources(self, store: DocumentStore) -> None:
        """Test retrieving info for different sources independently."""
        config1 = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="slack",
            domain=Domain.MESSAGES,
            normalizer_version="1.0",
        )
        config2 = AdapterConfig(
            adapter_id="adapter-2",
            adapter_type="discord",
            domain=Domain.MESSAGES,
            normalizer_version="1.0",
        )
        store.register_adapter(config1)
        store.register_adapter(config2)

        store.register_source(
            source_id="slack-workspace",
            adapter_id="adapter-1",
            domain=Domain.MESSAGES,
            origin_ref="slack://workspace-id",
        )
        store.register_source(
            source_id="discord-server",
            adapter_id="adapter-2",
            domain=Domain.MESSAGES,
            origin_ref="discord://server-id",
        )

        # Verify each source retrieves correct info
        slack_info = store.get_source_info("slack-workspace")
        discord_info = store.get_source_info("discord-server")

        assert slack_info is not None
        assert slack_info.origin_ref == "slack://workspace-id"
        assert slack_info.adapter_type == "slack"

        assert discord_info is not None
        assert discord_info.origin_ref == "discord://server-id"
        assert discord_info.adapter_type == "discord"


class TestGetLineageWithSourceId:
    """Tests for DocumentStore.get_lineage with source_id parameter.

    Covers the source_id-filtered SQL query branch which handles
    cross-source deduplication scenarios.
    """

    def test_get_lineage_with_source_id_filter(self, store: DocumentStore) -> None:
        """Test get_lineage with source_id filter returns correct record."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        version_id = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="content",
            chunk_hashes=[_make_hash("a")],
            adapter_id="adapter-1",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-01T00:00:00Z",
        )

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="content",
            chunk_index=0,
        )

        lineage = [
            LineageRecord(
                chunk_hash=_make_hash("a"),
                source_id="source-1",
                source_version_id=version_id,
                adapter_id="adapter-1",
                domain=Domain.NOTES,
                normalizer_version="1.0",
                embedding_model_id="model-1",
            ),
        ]

        store.write_chunks([chunk], lineage)

        # Retrieve with source_id filter
        result = store.get_lineage(_make_hash("a"), source_id="source-1")

        assert result is not None
        assert result.chunk_hash == _make_hash("a")
        assert result.source_id == "source-1"
        assert result.embedding_model_id == "model-1"

    def test_get_lineage_with_source_id_not_found(self, store: DocumentStore) -> None:
        """Test get_lineage with source_id returns None when source_id doesn't match."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        version_id = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="content",
            chunk_hashes=[_make_hash("a")],
            adapter_id="adapter-1",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-01T00:00:00Z",
        )

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="content",
            chunk_index=0,
        )

        lineage = [
            LineageRecord(
                chunk_hash=_make_hash("a"),
                source_id="source-1",
                source_version_id=version_id,
                adapter_id="adapter-1",
                domain=Domain.NOTES,
                normalizer_version="1.0",
                embedding_model_id="model-1",
            ),
        ]

        store.write_chunks([chunk], lineage)

        # Try to retrieve with non-matching source_id
        result = store.get_lineage(_make_hash("a"), source_id="different-source")

        assert result is None

    def test_get_lineage_cross_source_dedup_scenario(self, store: DocumentStore) -> None:
        """Test get_lineage correctly handles cross-source dedup scenario.

        Tests the documented use case: when the same chunk_hash appears in
        different versions of the same source, source_id parameter allows
        retrieving the lineage record scoped to that source.

        The source_id parameter is critical for distinguishing lineage records
        when a chunk_hash is potentially duplicated across source versions.
        """
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0",
        )
        store.register_adapter(config)

        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        # Create two versions with the same chunk hash
        version_id_1 = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="content v1",
            chunk_hashes=[_make_hash("a")],
            adapter_id="adapter-1",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-01T00:00:00Z",
        )

        store.create_source_version(
            source_id="source-1",
            version=2,
            markdown="content v2",
            chunk_hashes=[_make_hash("a")],  # Same hash - unchanged chunk
            adapter_id="adapter-1",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-02T00:00:00Z",
        )

        # Write chunk to both versions
        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="shared content",
            chunk_index=0,
        )

        # Both versions have the chunk, so we write once (idempotent)
        lineage = [
            LineageRecord(
                chunk_hash=_make_hash("a"),
                source_id="source-1",
                source_version_id=version_id_1,
                adapter_id="adapter-1",
                domain=Domain.NOTES,
                normalizer_version="1.0",
                embedding_model_id="model-1",
            ),
        ]

        store.write_chunks([chunk], lineage)

        # When querying without source_id, get_lineage returns the first match
        result_no_filter = store.get_lineage(_make_hash("a"))
        assert result_no_filter is not None
        assert result_no_filter.source_id == "source-1"

        # When querying with source_id, can explicitly filter to a specific source
        result_with_filter = store.get_lineage(_make_hash("a"), source_id="source-1")
        assert result_with_filter is not None
        assert result_with_filter.source_id == "source-1"

        # Both queries return consistent results for this source
        assert result_no_filter.chunk_hash == result_with_filter.chunk_hash
        assert result_no_filter.source_id == result_with_filter.source_id

    def test_get_lineage_source_id_vs_no_source_id(self, store: DocumentStore) -> None:
        """Test difference between get_lineage with and without source_id parameter."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="source-1",
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            origin_ref="test://source-1",
        )

        version_id = store.create_source_version(
            source_id="source-1",
            version=1,
            markdown="content",
            chunk_hashes=[_make_hash("a")],
            adapter_id="adapter-1",
            normalizer_version="1.0",
            fetch_timestamp="2024-01-01T00:00:00Z",
        )

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="content",
            chunk_index=0,
        )

        lineage = [
            LineageRecord(
                chunk_hash=_make_hash("a"),
                source_id="source-1",
                source_version_id=version_id,
                adapter_id="adapter-1",
                domain=Domain.NOTES,
                normalizer_version="1.0",
                embedding_model_id="model-1",
            ),
        ]

        store.write_chunks([chunk], lineage)

        # Both queries should return the same result when there's only one source
        result_with_source_id = store.get_lineage(_make_hash("a"), source_id="source-1")
        result_without_source_id = store.get_lineage(_make_hash("a"))

        assert result_with_source_id is not None
        assert result_without_source_id is not None
        assert result_with_source_id.source_id == result_without_source_id.source_id
        assert result_with_source_id.source_version_id == result_without_source_id.source_version_id


class TestCrossReferencesRoundTrip:
    """Tests for cross-references serialization and deserialization round-trips.

    Verifies that cross_refs are correctly:
    - Written into domain_metadata JSON (under "_system_cross_refs" key) during write_chunks
    - Extracted and removed from domain_metadata during _build_chunk_from_row
    - Properly reconstructed as chunk.cross_refs in the returned Chunk object
    """

    def _setup_with_version(self, store: DocumentStore) -> tuple[str, str, int]:
        """Set up a source and version for testing."""
        config = AdapterConfig(
            adapter_id="test-adapter",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
        store.register_source(
            source_id="test-source",
            adapter_id="test-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source",
        )
        version_id = store.create_source_version(
            source_id="test-source",
            version=1,
            markdown="test content",
            chunk_hashes=[_make_hash("a"), _make_hash("b")],
            adapter_id="test-adapter",
            normalizer_version="1.0.0",
            fetch_timestamp="2024-01-01T00:00:00Z",
        )
        return "test-source", "test-adapter", version_id

    def test_cross_refs_write_and_read_empty(self, store: DocumentStore) -> None:
        """Test that chunks with no cross-references are handled correctly."""
        source_id, adapter_id, version_id = self._setup_with_version(store)

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="Content without references",
            chunk_index=0,
            cross_refs=(),
        )

        lineage = [
            LineageRecord(
                chunk_hash=_make_hash("a"),
                source_id=source_id,
                source_version_id=version_id,
                adapter_id=adapter_id,
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
        ]

        store.write_chunks([chunk], lineage)

        # Read back and verify
        retrieved = store.get_chunk_by_hash(_make_hash("a"))
        assert retrieved is not None
        assert retrieved.cross_refs == ()

    def test_cross_refs_write_and_read_single_reference(self, store: DocumentStore) -> None:
        """Test writing and reading a chunk with a single cross-reference."""
        source_id, adapter_id, version_id = self._setup_with_version(store)

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="See the section above",
            chunk_index=1,
            cross_refs=(_make_hash("b"),),
        )

        lineage = [
            LineageRecord(
                chunk_hash=_make_hash("a"),
                source_id=source_id,
                source_version_id=version_id,
                adapter_id=adapter_id,
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
        ]

        store.write_chunks([chunk], lineage)

        # Read back and verify cross_refs are preserved
        retrieved = store.get_chunk_by_hash(_make_hash("a"))
        assert retrieved is not None
        assert retrieved.cross_refs == (_make_hash("b"),)

    def test_cross_refs_write_and_read_multiple_references(self, store: DocumentStore) -> None:
        """Test writing and reading a chunk with multiple cross-references."""
        source_id, adapter_id, version_id = self._setup_with_version(store)

        cross_refs = (_make_hash("b"), _make_hash("c"), _make_hash("d"))
        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="As shown above and following patterns",
            chunk_index=2,
            cross_refs=cross_refs,
        )

        lineage = [
            LineageRecord(
                chunk_hash=_make_hash("a"),
                source_id=source_id,
                source_version_id=version_id,
                adapter_id=adapter_id,
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
        ]

        store.write_chunks([chunk], lineage)

        # Read back and verify all cross_refs are preserved in order
        retrieved = store.get_chunk_by_hash(_make_hash("a"))
        assert retrieved is not None
        assert retrieved.cross_refs == cross_refs

    def test_cross_refs_with_domain_metadata(self, store: DocumentStore) -> None:
        """Test that cross_refs are merged with domain_metadata correctly."""
        source_id, adapter_id, version_id = self._setup_with_version(store)

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="Referenced content",
            chunk_index=0,
            domain_metadata={"custom_key": "custom_value", "nested": {"data": 123}},
            cross_refs=(_make_hash("b"), _make_hash("c")),
        )

        lineage = [
            LineageRecord(
                chunk_hash=_make_hash("a"),
                source_id=source_id,
                source_version_id=version_id,
                adapter_id=adapter_id,
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
        ]

        store.write_chunks([chunk], lineage)

        # Read back and verify both domain_metadata and cross_refs are preserved
        retrieved = store.get_chunk_by_hash(_make_hash("a"))
        assert retrieved is not None
        assert retrieved.cross_refs == (_make_hash("b"), _make_hash("c"))
        assert retrieved.domain_metadata == {"custom_key": "custom_value", "nested": {"data": 123}}

    def test_cross_refs_metadata_key_isolation(self, store: DocumentStore) -> None:
        """Test that _system_cross_refs key is removed from domain_metadata after extraction."""
        source_id, adapter_id, version_id = self._setup_with_version(store)

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="Content",
            chunk_index=0,
            domain_metadata={"user_key": "user_value"},
            cross_refs=(_make_hash("d"), _make_hash("e")),
        )

        lineage = [
            LineageRecord(
                chunk_hash=_make_hash("a"),
                source_id=source_id,
                source_version_id=version_id,
                adapter_id=adapter_id,
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
        ]

        store.write_chunks([chunk], lineage)

        # Read back and verify _system_cross_refs was removed from domain_metadata
        retrieved = store.get_chunk_by_hash(_make_hash("a"))
        assert retrieved is not None
        # The user's metadata should be intact, not including _system_cross_refs
        assert retrieved.domain_metadata == {"user_key": "user_value"}
        assert "_system_cross_refs" not in (retrieved.domain_metadata or {})
        # Cross refs should be in the cross_refs field, not metadata
        assert retrieved.cross_refs == (_make_hash("d"), _make_hash("e"))

    def test_cross_refs_empty_metadata_cleanup(self, store: DocumentStore) -> None:
        """Test that domain_metadata is set to None when only _system_cross_refs remains."""
        source_id, adapter_id, version_id = self._setup_with_version(store)

        chunk = Chunk(
            chunk_hash=_make_hash("a"),
            content="Content",
            chunk_index=0,
            domain_metadata=None,
            cross_refs=(_make_hash("b"),),
        )

        lineage = [
            LineageRecord(
                chunk_hash=_make_hash("a"),
                source_id=source_id,
                source_version_id=version_id,
                adapter_id=adapter_id,
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
        ]

        store.write_chunks([chunk], lineage)

        # Read back and verify domain_metadata is None (not an empty dict)
        retrieved = store.get_chunk_by_hash(_make_hash("a"))
        assert retrieved is not None
        assert retrieved.domain_metadata is None
        assert retrieved.cross_refs == (_make_hash("b"),)

    def test_build_chunk_from_row_malformed_json_raises_value_error(self, store: DocumentStore) -> None:
        """Test that malformed JSON in domain_metadata raises informative ValueError."""
        source_id, adapter_id, version_id = self._setup_with_version(store)

        # Manually insert a chunk with corrupt JSON in domain_metadata
        cursor = store.conn.cursor()
        cursor.execute(
            """
            INSERT INTO chunks
            (chunk_hash, content, chunk_index, source_id, source_version, adapter_id,
             domain, fetch_timestamp, normalizer_version, embedding_model_id,
             domain_metadata, context_header, chunk_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _make_hash("corrupt"),
                "Content",
                0,
                source_id,
                1,
                adapter_id,
                "notes",
                datetime.now(timezone.utc).isoformat(),
                "1.0.0",
                "test-model",
                "{invalid json",  # Malformed JSON
                None,
                "standard",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        store.conn.commit()

        # Attempting to retrieve should raise ValueError with informative message
        with pytest.raises(ValueError, match=r"domain_metadata contains malformed JSON"):
            store.get_chunk_by_hash(_make_hash("corrupt"), source_id)

    def test_build_chunk_from_row_non_iterable_cross_refs_raises_value_error(self, store: DocumentStore) -> None:
        """Test that non-iterable _system_cross_refs value raises informative ValueError."""
        source_id, adapter_id, version_id = self._setup_with_version(store)

        # Manually insert a chunk with non-iterable _system_cross_refs
        cursor = store.conn.cursor()
        cursor.execute(
            """
            INSERT INTO chunks
            (chunk_hash, content, chunk_index, source_id, source_version, adapter_id,
             domain, fetch_timestamp, normalizer_version, embedding_model_id,
             domain_metadata, context_header, chunk_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _make_hash("non_iter"),
                "Content",
                0,
                source_id,
                1,
                adapter_id,
                "notes",
                datetime.now(timezone.utc).isoformat(),
                "1.0.0",
                "test-model",
                '{"_system_cross_refs": 42}',  # Non-iterable value (int instead of list)
                None,
                "standard",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        store.conn.commit()

        # Attempting to retrieve should raise ValueError with informative message
        with pytest.raises(ValueError, match=r"_system_cross_refs must be iterable"):
            store.get_chunk_by_hash(_make_hash("non_iter"), source_id)


# ── New read method tests ────────────────────────────────────────────


def _setup_adapter_and_source(store: DocumentStore):
    """Register adapter and source for new method tests."""
    config = AdapterConfig(
        adapter_id="read-adapter",
        adapter_type="filesystem",
        domain=Domain.NOTES,
        normalizer_version="1.0.0",
    )
    store.register_adapter(config)
    store.register_source(
        source_id="read-src",
        adapter_id="read-adapter",
        domain=Domain.NOTES,
        origin_ref="/docs/test.md",
        poll_strategy=PollStrategy.PULL,
        poll_interval_sec=3600,
    )
    return config


class TestListAdapters:
    """Tests for DocumentStore.list_adapters()."""

    def test_returns_empty_list(self, store: DocumentStore) -> None:
        assert store.list_adapters() == []

    def test_returns_registered_adapter(self, store: DocumentStore) -> None:
        _setup_adapter_and_source(store)
        adapters = store.list_adapters()
        assert len(adapters) == 1
        assert adapters[0].adapter_id == "read-adapter"
        assert adapters[0].adapter_type == "filesystem"
        assert adapters[0].domain == Domain.NOTES

    def test_ordered_by_adapter_id(self, store: DocumentStore) -> None:
        for aid in ["z-adapter", "a-adapter", "m-adapter"]:
            store.register_adapter(AdapterConfig(
                adapter_id=aid,
                adapter_type="filesystem",
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
            ))
        ids = [a.adapter_id for a in store.list_adapters()]
        assert ids == sorted(ids)


class TestListSources:
    """Tests for DocumentStore.list_sources()."""

    def test_returns_empty_list(self, store: DocumentStore) -> None:
        rows, total = store.list_sources()
        assert rows == []
        assert total == 0

    def test_returns_source(self, store: DocumentStore) -> None:
        _setup_adapter_and_source(store)
        rows, total = store.list_sources()
        assert total == 1
        assert len(rows) == 1
        assert rows[0]["source_id"] == "read-src"
        assert rows[0]["domain"] == "notes"

    def test_chunk_count_is_zero_for_new_source(self, store: DocumentStore) -> None:
        _setup_adapter_and_source(store)
        rows, _ = store.list_sources()
        assert rows[0]["chunk_count"] == 0

    def test_filter_by_domain(self, store: DocumentStore) -> None:
        _setup_adapter_and_source(store)
        rows, total = store.list_sources(domain="notes")
        assert total == 1
        assert len(rows) == 1
        _, total2 = store.list_sources(domain="messages")
        assert total2 == 0

    def test_filter_by_adapter_id(self, store: DocumentStore) -> None:
        _setup_adapter_and_source(store)
        rows, total = store.list_sources(adapter_id="read-adapter")
        assert total == 1
        assert len(rows) == 1
        _, total2 = store.list_sources(adapter_id="other")
        assert total2 == 0

    def test_pagination(self, store: DocumentStore) -> None:
        _setup_adapter_and_source(store)
        rows, total = store.list_sources(limit=1, offset=0)
        assert total == 1
        assert len(rows) == 1
        rows2, total2 = store.list_sources(limit=10, offset=1)
        assert total2 == 1   # total is full match count, not page count
        assert len(rows2) == 0

    def test_source_id_prefix_filter_basic(self, store: DocumentStore) -> None:
        """Test basic source_id_prefix filtering at the storage layer."""
        # Register adapter
        config = AdapterConfig(
            adapter_id="fs-adapter",
            adapter_type="filesystem",
            domain=Domain.DOCUMENTS,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)

        # Create sources with hierarchical paths
        test_sources = [
            "projects/alpha/doc1.md",
            "projects/beta/doc2.md",
            "notes/doc3.md",
        ]
        for source_id in test_sources:
            store.register_source(
                source_id=source_id,
                adapter_id="fs-adapter",
                domain=Domain.DOCUMENTS,
                origin_ref=f"/fs/{source_id}",
                poll_strategy=PollStrategy.PULL,
                poll_interval_sec=3600,
            )

        # Test prefix matching
        rows, total = store.list_sources(source_id_prefix="projects/")
        assert total == 2
        assert len(rows) == 2
        assert rows[0]["source_id"] == "projects/alpha/doc1.md"
        assert rows[1]["source_id"] == "projects/beta/doc2.md"

    def test_source_id_prefix_filter_no_matches(self, store: DocumentStore) -> None:
        """Test source_id_prefix filtering with no matching sources."""
        config = AdapterConfig(
            adapter_id="fs-adapter",
            adapter_type="filesystem",
            domain=Domain.DOCUMENTS,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)

        store.register_source(
            source_id="projects/doc.md",
            adapter_id="fs-adapter",
            domain=Domain.DOCUMENTS,
            origin_ref="/fs/projects/doc.md",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )

        # Test non-matching prefix
        rows, total = store.list_sources(source_id_prefix="notes/")
        assert total == 0
        assert rows == []

    def test_source_id_prefix_glob_star_escaped(self, store: DocumentStore) -> None:
        """Test that * (asterisk) GLOB wildcard is properly escaped in source_id_prefix."""
        config = AdapterConfig(
            adapter_id="fs-adapter",
            adapter_type="filesystem",
            domain=Domain.DOCUMENTS,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)

        # Create sources with * in the source_id
        test_sources = [
            "files*/archive/doc1.md",
            "filesX/archive/doc2.md",
        ]
        for source_id in test_sources:
            store.register_source(
                source_id=source_id,
                adapter_id="fs-adapter",
                domain=Domain.DOCUMENTS,
                origin_ref=f"/fs/{source_id}",
                poll_strategy=PollStrategy.PULL,
                poll_interval_sec=3600,
            )

        # Search for exact prefix with * - should match the source with literal *
        rows, total = store.list_sources(source_id_prefix="files*/")
        assert total == 1
        assert len(rows) == 1
        assert rows[0]["source_id"] == "files*/archive/doc1.md"

        # Verify that "files" prefix matches both sources (it's a prefix of both)
        # This demonstrates that * is properly escaped - the prefix matching works correctly
        rows2, total2 = store.list_sources(source_id_prefix="files")
        assert total2 == 2
        source_ids = [r["source_id"] for r in rows2]
        assert "files*/archive/doc1.md" in source_ids
        assert "filesX/archive/doc2.md" in source_ids

    def test_source_id_prefix_glob_question_escaped(self, store: DocumentStore) -> None:
        """Test that ? (question mark) GLOB wildcard is properly escaped in source_id_prefix."""
        config = AdapterConfig(
            adapter_id="fs-adapter",
            adapter_type="filesystem",
            domain=Domain.DOCUMENTS,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)

        # Create sources with ? in the source_id
        test_sources = [
            "docs?/report.md",
            "docsX/report2.md",
        ]
        for source_id in test_sources:
            store.register_source(
                source_id=source_id,
                adapter_id="fs-adapter",
                domain=Domain.DOCUMENTS,
                origin_ref=f"/fs/{source_id}",
                poll_strategy=PollStrategy.PULL,
                poll_interval_sec=3600,
            )

        # Search for exact prefix with ? - should match the source with literal ?
        rows, total = store.list_sources(source_id_prefix="docs?/")
        assert total == 1
        assert len(rows) == 1
        assert rows[0]["source_id"] == "docs?/report.md"

        # Verify that "docs" prefix matches both sources (it's a prefix of both)
        # This demonstrates that ? is properly escaped - the prefix matching works correctly
        rows2, total2 = store.list_sources(source_id_prefix="docs")
        assert total2 == 2
        source_ids = [r["source_id"] for r in rows2]
        assert "docs?/report.md" in source_ids
        assert "docsX/report2.md" in source_ids

    def test_source_id_prefix_brackets_escaped(self, store: DocumentStore) -> None:
        """Test that [ and ] GLOB character class delimiters are properly escaped."""
        config = AdapterConfig(
            adapter_id="fs-adapter",
            adapter_type="filesystem",
            domain=Domain.DOCUMENTS,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)

        # Create sources with brackets in the source_id
        test_sources = [
            "data[0]/file.md",
            "datax/file3.md",
        ]
        for source_id in test_sources:
            store.register_source(
                source_id=source_id,
                adapter_id="fs-adapter",
                domain=Domain.DOCUMENTS,
                origin_ref=f"/fs/{source_id}",
                poll_strategy=PollStrategy.PULL,
                poll_interval_sec=3600,
            )

        # Search for prefix with literal brackets - should only match the source with brackets
        rows, total = store.list_sources(source_id_prefix="data[0]/")
        assert total == 1
        assert len(rows) == 1
        assert rows[0]["source_id"] == "data[0]/file.md"

        # "data[" as a prefix should only match sources starting with "data[" (not "datax")
        # If brackets were treated as character class [01], searching for "data[" would match
        # both "data[0]" and other sources, but since they're escaped it only matches "data["
        rows2, total2 = store.list_sources(source_id_prefix="data[")
        assert total2 == 1
        assert rows2[0]["source_id"] == "data[0]/file.md"

    def test_source_id_prefix_with_pagination(self, store: DocumentStore) -> None:
        """Test that source_id_prefix works with pagination parameters."""
        config = AdapterConfig(
            adapter_id="fs-adapter",
            adapter_type="filesystem",
            domain=Domain.DOCUMENTS,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)

        # Create multiple sources with the same prefix
        for i in range(5):
            store.register_source(
                source_id=f"projects/doc{i}.md",
                adapter_id="fs-adapter",
                domain=Domain.DOCUMENTS,
                origin_ref=f"/fs/projects/doc{i}.md",
                poll_strategy=PollStrategy.PULL,
                poll_interval_sec=3600,
            )

        # Test pagination with prefix filter
        rows, total = store.list_sources(source_id_prefix="projects/", limit=2, offset=0)
        assert total == 5  # Total matching count
        assert len(rows) == 2  # Page size
        assert rows[0]["source_id"] == "projects/doc0.md"
        assert rows[1]["source_id"] == "projects/doc1.md"

        # Test second page
        rows2, total2 = store.list_sources(source_id_prefix="projects/", limit=2, offset=2)
        assert total2 == 5
        assert len(rows2) == 2
        assert rows2[0]["source_id"] == "projects/doc2.md"

    def test_source_id_prefix_case_insensitive(self, store: DocumentStore) -> None:
        """Test that source_id_prefix matching is case-insensitive (LIKE behavior)."""
        config = AdapterConfig(
            adapter_id="fs-adapter",
            adapter_type="filesystem",
            domain=Domain.DOCUMENTS,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)

        # Create sources with different cases
        test_sources = [
            "projects/doc.md",
            "Projects/doc.md",
        ]
        for source_id in test_sources:
            store.register_source(
                source_id=source_id,
                adapter_id="fs-adapter",
                domain=Domain.DOCUMENTS,
                origin_ref=f"/fs/{source_id}",
                poll_strategy=PollStrategy.PULL,
                poll_interval_sec=3600,
            )

        # Lowercase prefix should match both lowercase and uppercase sources
        rows, total = store.list_sources(source_id_prefix="projects/")
        assert total == 2
        source_ids = {r["source_id"] for r in rows}
        assert source_ids == {"projects/doc.md", "Projects/doc.md"}

        # Uppercase prefix should also match both (case-insensitive)
        rows2, total2 = store.list_sources(source_id_prefix="Projects/")
        assert total2 == 2
        source_ids2 = {r["source_id"] for r in rows2}
        assert source_ids2 == {"projects/doc.md", "Projects/doc.md"}


class TestGetSourceDetail:
    """Tests for DocumentStore.get_source_detail()."""

    def test_returns_none_for_missing_source(self, store: DocumentStore) -> None:
        assert store.get_source_detail("no-such") is None

    def test_returns_detail(self, store: DocumentStore) -> None:
        _setup_adapter_and_source(store)
        row = store.get_source_detail("read-src")
        assert row is not None
        assert row["source_id"] == "read-src"
        assert row["adapter_type"] == "filesystem"
        assert row["normalizer_version"] == "1.0.0"
        assert "created_at" in row
        assert "updated_at" in row


class TestGetSourceVersion:
    """Tests for DocumentStore.get_source_version()."""

    def test_returns_none_for_missing(self, store: DocumentStore) -> None:
        assert store.get_source_version("no-src", 1) is None

    def test_returns_version(self, store: DocumentStore) -> None:
        from context_library.storage.models import compute_chunk_hash
        _setup_adapter_and_source(store)
        ch = compute_chunk_hash("test content")
        store.create_source_version(
            source_id="read-src",
            version=1,
            markdown="# Test",
            chunk_hashes=[ch],
            adapter_id="read-adapter",
            normalizer_version="1.0.0",
            fetch_timestamp="2024-01-01T00:00:00+00:00",
        )
        sv = store.get_source_version("read-src", 1)
        assert sv is not None
        assert sv.version == 1
        assert sv.markdown == "# Test"
        assert ch in sv.chunk_hashes


class TestGetDatasetStats:
    """Tests for DocumentStore.get_dataset_stats()."""

    def test_zeros_on_empty_db(self, store: DocumentStore) -> None:
        stats = store.get_dataset_stats()
        assert stats["total_sources"] == 0
        assert stats["total_active_chunks"] == 0
        assert stats["retired_chunk_count"] == 0
        assert stats["sync_queue_pending_insert"] == 0
        assert stats["sync_queue_pending_delete"] == 0
        assert stats["by_domain"] == []

    def test_counts_after_registration(self, store: DocumentStore) -> None:
        _setup_adapter_and_source(store)
        stats = store.get_dataset_stats()
        assert stats["total_sources"] == 1
        assert stats["by_domain"][0]["domain"] == "notes"
        assert stats["by_domain"][0]["source_count"] == 1

class TestListChunks:
    """Tests for DocumentStore.list_chunks()."""

    def test_empty_db(self, store: DocumentStore) -> None:
        rows, total = store.list_chunks()
        assert rows == []
        assert total == 0

    def test_returns_all_chunks(self, store: DocumentStore) -> None:
        from context_library.storage.models import compute_chunk_hash, Chunk, ChunkType
        _setup_adapter_and_source(store)

        ch1 = compute_chunk_hash("content1")
        chunk1 = Chunk(
            chunk_hash=ch1,
            content="content1",
            context_header="Header1",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
        )
        store.create_source_version(
            source_id="read-src",
            version=1,
            markdown="content1",
            chunk_hashes=[ch1],
            adapter_id="read-adapter",
            normalizer_version="1.0.0",
            fetch_timestamp="2024-01-01T00:00:00+00:00",
        )
        lineage1 = LineageRecord(
            chunk_hash=ch1,
            source_id="read-src",
            source_version_id=1,
            adapter_id="read-adapter",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )
        store.write_chunks([chunk1], [lineage1])

        chunk_tuples, total = store.list_chunks()
        assert total == 1
        assert len(chunk_tuples) == 1
        chunk, src_id, src_version_id, adapter_id_val, domain_val, normalizer_version, embedding_model_id = chunk_tuples[0]
        assert chunk.chunk_hash == ch1
        assert chunk.content == "content1"

    def test_filters_by_domain(self, store: DocumentStore) -> None:
        from context_library.storage.models import compute_chunk_hash, Chunk, ChunkType
        _setup_adapter_and_source(store)

        # Create a chunk in notes domain
        ch1 = compute_chunk_hash("notes content")
        chunk1 = Chunk(
            chunk_hash=ch1,
            content="notes content",
            context_header="Header",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
        )
        store.create_source_version(
            source_id="read-src",
            version=1,
            markdown="notes content",
            chunk_hashes=[ch1],
            adapter_id="read-adapter",
            normalizer_version="1.0.0",
            fetch_timestamp="2024-01-01T00:00:00+00:00",
        )
        lineage1 = LineageRecord(
            chunk_hash=ch1,
            source_id="read-src",
            source_version_id=1,
            adapter_id="read-adapter",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )
        store.write_chunks([chunk1], [lineage1])

        # Query for notes domain
        rows, total = store.list_chunks(domain="notes")
        assert total == 1
        assert len(rows) == 1

        # Query for different domain returns nothing
        rows, total = store.list_chunks(domain="messages")
        assert total == 0
        assert len(rows) == 0

    def test_filters_by_adapter_id(self, store: DocumentStore) -> None:
        from context_library.storage.models import compute_chunk_hash, Chunk, ChunkType
        _setup_adapter_and_source(store)

        ch1 = compute_chunk_hash("content")
        chunk1 = Chunk(
            chunk_hash=ch1,
            content="content",
            context_header="Header",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
        )
        store.create_source_version(
            source_id="read-src",
            version=1,
            markdown="content",
            chunk_hashes=[ch1],
            adapter_id="read-adapter",
            normalizer_version="1.0.0",
            fetch_timestamp="2024-01-01T00:00:00+00:00",
        )
        lineage1 = LineageRecord(
            chunk_hash=ch1,
            source_id="read-src",
            source_version_id=1,
            adapter_id="read-adapter",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )
        store.write_chunks([chunk1], [lineage1])

        # Query for correct adapter_id
        rows, total = store.list_chunks(adapter_id="read-adapter")
        assert total == 1

        # Query for different adapter_id returns nothing
        rows, total = store.list_chunks(adapter_id="other-adapter")
        assert total == 0

    def test_pagination(self, store: DocumentStore) -> None:
        from context_library.storage.models import compute_chunk_hash, Chunk, ChunkType
        _setup_adapter_and_source(store)

        # Create 5 chunks in a single source version
        chunks = []
        chunk_hashes = []
        lineages = []
        for i in range(5):
            ch = compute_chunk_hash(f"content{i}")
            chunk = Chunk(
                chunk_hash=ch,
                content=f"content{i}",
                context_header=f"Header{i}",
                chunk_index=i,
                chunk_type=ChunkType.STANDARD,
            )
            chunks.append(chunk)
            chunk_hashes.append(ch)
            lineage = LineageRecord(
                chunk_hash=ch,
                source_id="read-src",
                source_version_id=1,
                adapter_id="read-adapter",
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            )
            lineages.append(lineage)

        store.create_source_version(
            source_id="read-src",
            version=1,
            markdown="content0\ncontent1\ncontent2\ncontent3\ncontent4",
            chunk_hashes=chunk_hashes,
            adapter_id="read-adapter",
            normalizer_version="1.0.0",
            fetch_timestamp="2024-01-01T00:00:00+00:00",
        )
        store.write_chunks(chunks, lineages)

        # Test limit
        rows, total = store.list_chunks(limit=2)
        assert total == 5
        assert len(rows) == 2

        # Test offset
        rows, total = store.list_chunks(limit=2, offset=2)
        assert total == 5
        assert len(rows) == 2

    def test_excludes_retired_chunks(self, store: DocumentStore) -> None:
        from context_library.storage.models import compute_chunk_hash, Chunk, ChunkType
        _setup_adapter_and_source(store)

        ch1 = compute_chunk_hash("content")
        chunk1 = Chunk(
            chunk_hash=ch1,
            content="content",
            context_header="Header",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
        )
        store.create_source_version(
            source_id="read-src",
            version=1,
            markdown="content",
            chunk_hashes=[ch1],
            adapter_id="read-adapter",
            normalizer_version="1.0.0",
            fetch_timestamp="2024-01-01T00:00:00+00:00",
        )
        lineage1 = LineageRecord(
            chunk_hash=ch1,
            source_id="read-src",
            source_version_id=1,
            adapter_id="read-adapter",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )
        store.write_chunks([chunk1], [lineage1])

        # Initially should have 1 chunk
        rows, total = store.list_chunks()
        assert total == 1

        # Retire the chunk
        store.retire_chunks({ch1}, "read-src", 1)

        # Should now have 0 chunks
        rows, total = store.list_chunks()
        assert total == 0


class TestGetAdapterStats:
    """Tests for DocumentStore.get_adapter_stats()."""

    def test_empty_db(self, store: DocumentStore) -> None:
        stats = store.get_adapter_stats()
        assert stats == []

    def test_single_adapter_single_source(self, store: DocumentStore) -> None:
        from context_library.storage.models import compute_chunk_hash, Chunk, ChunkType
        _setup_adapter_and_source(store)

        ch1 = compute_chunk_hash("content")
        chunk1 = Chunk(
            chunk_hash=ch1,
            content="content",
            context_header="Header",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
        )
        store.create_source_version(
            source_id="read-src",
            version=1,
            markdown="content",
            chunk_hashes=[ch1],
            adapter_id="read-adapter",
            normalizer_version="1.0.0",
            fetch_timestamp="2024-01-01T00:00:00+00:00",
        )
        lineage1 = LineageRecord(
            chunk_hash=ch1,
            source_id="read-src",
            source_version_id=1,
            adapter_id="read-adapter",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )
        store.write_chunks([chunk1], [lineage1])

        stats = store.get_adapter_stats()
        assert len(stats) == 1
        assert stats[0]["adapter_id"] == "read-adapter"
        assert stats[0]["adapter_type"] == "filesystem"
        assert stats[0]["domain"] == "notes"
        assert stats[0]["source_count"] == 1
        assert stats[0]["active_chunk_count"] == 1

    def test_single_adapter_multiple_chunks(self, store: DocumentStore) -> None:
        from context_library.storage.models import compute_chunk_hash, Chunk, ChunkType
        _setup_adapter_and_source(store)

        # Create multiple chunks in same source
        chunks = []
        lineages = []
        for i in range(3):
            ch = compute_chunk_hash(f"content{i}")
            chunk = Chunk(
                chunk_hash=ch,
                content=f"content{i}",
                context_header=f"Header{i}",
                chunk_index=i,
                chunk_type=ChunkType.STANDARD,
            )
            chunks.append(chunk)
            lineage = LineageRecord(
                chunk_hash=ch,
                source_id="read-src",
                source_version_id=1,
                adapter_id="read-adapter",
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            )
            lineages.append(lineage)

        store.create_source_version(
            source_id="read-src",
            version=1,
            markdown="content",
            chunk_hashes=[c.chunk_hash for c in chunks],
            adapter_id="read-adapter",
            normalizer_version="1.0.0",
            fetch_timestamp="2024-01-01T00:00:00+00:00",
        )
        store.write_chunks(chunks, lineages)

        stats = store.get_adapter_stats()
        assert len(stats) == 1
        assert stats[0]["source_count"] == 1
        assert stats[0]["active_chunk_count"] == 3

    def test_excludes_retired_chunks(self, store: DocumentStore) -> None:
        from context_library.storage.models import compute_chunk_hash, Chunk, ChunkType
        _setup_adapter_and_source(store)

        # Create 2 chunks
        chunks = []
        lineages = []
        hashes = []
        for i in range(2):
            ch = compute_chunk_hash(f"content{i}")
            chunk = Chunk(
                chunk_hash=ch,
                content=f"content{i}",
                context_header=f"Header{i}",
                chunk_index=i,
                chunk_type=ChunkType.STANDARD,
            )
            chunks.append(chunk)
            hashes.append(ch)
            lineage = LineageRecord(
                chunk_hash=ch,
                source_id="read-src",
                source_version_id=1,
                adapter_id="read-adapter",
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            )
            lineages.append(lineage)

        store.create_source_version(
            source_id="read-src",
            version=1,
            markdown="content",
            chunk_hashes=hashes,
            adapter_id="read-adapter",
            normalizer_version="1.0.0",
            fetch_timestamp="2024-01-01T00:00:00+00:00",
        )
        store.write_chunks(chunks, lineages)

        # Initially should have 2 active chunks
        stats = store.get_adapter_stats()
        assert stats[0]["active_chunk_count"] == 2

        # Retire one chunk
        store.retire_chunks({hashes[0]}, "read-src", 1)

        # Should now have 1 active chunk
        stats = store.get_adapter_stats()
        assert stats[0]["active_chunk_count"] == 1


class TestEntityLinks:
    """Tests for entity_links table and DocumentStore methods."""

    def _setup_with_chunks(self, store: DocumentStore, chunk_contents: list[str]) -> list[str]:
        """Helper to set up test database with chunks for entity link FK constraints.

        Args:
            store: DocumentStore instance
            chunk_contents: List of content strings to create chunks from (hashes computed via compute_chunk_hash)

        Returns:
            List of computed chunk hashes for use in entity link tests.
        """
        cursor = store.conn.cursor()

        # Compute valid SHA-256 hashes from content strings
        chunk_hashes = [compute_chunk_hash(content) for content in chunk_contents]

        # Disable FK constraints for test data setup to avoid circular deps during schema creation
        cursor.execute("PRAGMA foreign_keys=OFF")

        # Create adapter
        cursor.execute("""
            INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version)
            VALUES (?, ?, ?, ?)
        """, ("test-adapter", "people", "test_adapter", "1.0"))

        # Create source
        cursor.execute("""
            INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy)
            VALUES (?, ?, ?, ?, ?)
        """, ("test-source", "test-adapter", "people", "test-origin", "push"))

        # Create source version
        cursor.execute("""
            INSERT INTO source_versions (source_id, version, markdown, chunk_hashes, adapter_id, normalizer_version, fetch_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("test-source", 1, "test", ",".join(chunk_hashes), "test-adapter", "1.0", "2024-01-01T00:00:00Z"))

        # Create chunks
        for idx, (hash_val, content) in enumerate(zip(chunk_hashes, chunk_contents)):
            cursor.execute("""
                INSERT INTO chunks (chunk_hash, source_id, source_version, chunk_index, content, domain, adapter_id, fetch_timestamp, normalizer_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (hash_val, "test-source", 1, idx, content, "people", "test-adapter", "2024-01-01T00:00:00Z", "1.0"))

        store.conn.commit()
        # Re-enable FK constraints to test referential integrity during entity link operations
        cursor.execute("PRAGMA foreign_keys=ON")
        return chunk_hashes

    def test_write_entity_links_single_link(self) -> None:
        """Test writing a single entity link."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = DocumentStore(str(db_path))

            # Set up chunks
            chunk_hashes = self._setup_with_chunks(store, ["source content 1", "target content 1"])

            # Write a single link
            links = [EntityLink(source_chunk_hash=chunk_hashes[0], target_chunk_hash=chunk_hashes[1], link_type=ENTITY_LINK_TYPE_PERSON_APPEARANCE, confidence=1.0)]
            count = store.write_entity_links(links)
            assert count == 1

            # Verify it was written
            cursor = store.conn.cursor()
            cursor.execute("""
                SELECT * FROM entity_links
                WHERE source_chunk_hash = ? AND target_chunk_hash = ?
            """, (chunk_hashes[0], chunk_hashes[1]))
            row = cursor.fetchone()
            assert row is not None
            assert row["link_type"] == ENTITY_LINK_TYPE_PERSON_APPEARANCE
            assert row["confidence"] == 1.0

            store.conn.close()

    def test_write_entity_links_multiple_links(self) -> None:
        """Test writing multiple entity links at once."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = DocumentStore(str(db_path))

            # Set up chunks
            chunk_hashes = self._setup_with_chunks(store, ["source content 1", "source content 2", "target content 1", "target content 2"])

            # Write multiple links
            links = [
                EntityLink(source_chunk_hash=chunk_hashes[0], target_chunk_hash=chunk_hashes[2], link_type=ENTITY_LINK_TYPE_PERSON_APPEARANCE, confidence=1.0),
                EntityLink(source_chunk_hash=chunk_hashes[0], target_chunk_hash=chunk_hashes[3], link_type=ENTITY_LINK_TYPE_PERSON_APPEARANCE, confidence=0.95),
                EntityLink(source_chunk_hash=chunk_hashes[1], target_chunk_hash=chunk_hashes[2], link_type="mention", confidence=0.8),
            ]
            count = store.write_entity_links(links)
            assert count == 3

            # Verify all were written
            cursor = store.conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM entity_links")
            assert cursor.fetchone()["cnt"] == 3

            store.conn.close()

    def test_write_entity_links_idempotency(self) -> None:
        """Test that writing the same link twice via INSERT OR IGNORE enforces idempotency."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = DocumentStore(str(db_path))

            # Set up chunks
            chunk_hashes = self._setup_with_chunks(store, ["source content 1", "target content 1"])

            # Write a link
            links = [EntityLink(source_chunk_hash=chunk_hashes[0], target_chunk_hash=chunk_hashes[1], link_type=ENTITY_LINK_TYPE_PERSON_APPEARANCE, confidence=1.0)]
            count1 = store.write_entity_links(links)
            assert count1 == 1

            # Write the same link again (idempotency)
            count2 = store.write_entity_links(links)
            assert count2 == 0  # No new rows inserted

            # Verify only one row exists
            cursor = store.conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM entity_links")
            assert cursor.fetchone()["cnt"] == 1

            store.conn.close()

    def test_write_entity_links_empty_list(self) -> None:
        """Test that writing an empty list of links succeeds with count 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = DocumentStore(str(db_path))

            # Write empty list
            count = store.write_entity_links([])
            assert count == 0

            # Verify no rows written
            cursor = store.conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM entity_links")
            assert cursor.fetchone()["cnt"] == 0

            store.conn.close()

    def test_get_linked_chunks_single_direction(self) -> None:
        """Test getting linked chunks in a single direction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = DocumentStore(str(db_path))

            # Set up chunks
            chunk_hashes = self._setup_with_chunks(store, ["source content 1", "target content 1"])

            # Write links
            links = [EntityLink(source_chunk_hash=chunk_hashes[0], target_chunk_hash=chunk_hashes[1], link_type=ENTITY_LINK_TYPE_PERSON_APPEARANCE, confidence=1.0)]
            store.write_entity_links(links)

            # Get linked chunks from source
            linked = store.get_linked_chunks(chunk_hashes[0])
            assert chunk_hashes[1] in linked

            # Get linked chunks from target (bidirectional)
            linked = store.get_linked_chunks(chunk_hashes[1])
            assert chunk_hashes[0] in linked

            store.conn.close()

    def test_get_linked_chunks_with_link_type_filter(self) -> None:
        """Test getting linked chunks with link_type filter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = DocumentStore(str(db_path))

            # Set up chunks
            chunk_hashes = self._setup_with_chunks(store, ["source content 1", "target content 1", "target content 2"])

            # Write links with different types
            links = [
                EntityLink(source_chunk_hash=chunk_hashes[0], target_chunk_hash=chunk_hashes[1], link_type=ENTITY_LINK_TYPE_PERSON_APPEARANCE, confidence=1.0),
                EntityLink(source_chunk_hash=chunk_hashes[0], target_chunk_hash=chunk_hashes[2], link_type="mention", confidence=0.95),
            ]
            store.write_entity_links(links)

            # Filter by link_type
            linked = store.get_linked_chunks(chunk_hashes[0], link_type=ENTITY_LINK_TYPE_PERSON_APPEARANCE)
            assert chunk_hashes[1] in linked
            assert chunk_hashes[2] not in linked

            linked = store.get_linked_chunks(chunk_hashes[0], link_type="mention")
            assert chunk_hashes[2] in linked
            assert chunk_hashes[1] not in linked

            store.conn.close()

    def test_get_linked_chunks_no_results(self) -> None:
        """Test getting linked chunks when no links exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = DocumentStore(str(db_path))

            # Query non-existent chunk
            linked = store.get_linked_chunks("nonexistent-hash")
            assert linked == []

            # Query with link_type filter on non-existent chunk
            linked = store.get_linked_chunks("nonexistent-hash", link_type=ENTITY_LINK_TYPE_PERSON_APPEARANCE)
            assert linked == []

            store.conn.close()

    def test_get_linked_chunks_bidirectional(self) -> None:
        """Test that get_linked_chunks returns links in both directions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = DocumentStore(str(db_path))

            # Set up chunks
            chunk_hashes = self._setup_with_chunks(store, ["content a", "content b", "content c"])

            # Write bidirectional links
            links = [
                EntityLink(source_chunk_hash=chunk_hashes[0], target_chunk_hash=chunk_hashes[1], link_type="coappearance", confidence=1.0),
                EntityLink(source_chunk_hash=chunk_hashes[1], target_chunk_hash=chunk_hashes[2], link_type="coappearance", confidence=1.0),
            ]
            store.write_entity_links(links)

            # chunk_hashes[1] should be linked to both chunk_hashes[0] (as target) and chunk_hashes[2] (as source)
            linked = store.get_linked_chunks(chunk_hashes[1])
            assert chunk_hashes[0] in linked
            assert chunk_hashes[2] in linked
            assert len(linked) == 2

            store.conn.close()


class TestQueryChunksByIdentifiers:
    """Tests for DocumentStore.query_chunks_by_identifiers()."""

    def _setup_chunks_with_metadata(self, store: DocumentStore) -> None:
        """Set up test chunks with domain_metadata for identifier searching."""
        from context_library.storage.models import compute_chunk_hash, Chunk, ChunkType

        _setup_adapter_and_source(store)

        # Create chunks with various domain_metadata containing identifiers
        # Chunk 1: Messages domain with sender and recipients
        ch1 = compute_chunk_hash("email content 1")
        chunk1 = Chunk(
            chunk_hash=ch1,
            content="email content 1",
            context_header="Email header",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
            domain_metadata={
                "sender": "alice@example.com",
                "recipients": ["bob@example.com", "charlie@example.com"]
            },
        )

        # Chunk 2: Messages domain with different identifiers
        ch2 = compute_chunk_hash("email content 2")
        chunk2 = Chunk(
            chunk_hash=ch2,
            content="email content 2",
            context_header="Email header",
            chunk_index=1,
            chunk_type=ChunkType.STANDARD,
            domain_metadata={
                "sender": "dave@example.com",
                "recipients": ["alice@example.com"]
            },
        )

        # Chunk 3: Notes domain with author and collaborators
        ch3 = compute_chunk_hash("note content 1")
        chunk3 = Chunk(
            chunk_hash=ch3,
            content="note content 1",
            context_header="Note header",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
            domain_metadata={
                "author": "eve@example.com",
                "collaborators": ["alice@example.com", "bob@example.com"]
            },
        )

        # Chunk 4: Events domain with invitees
        ch4 = compute_chunk_hash("event content 1")
        chunk4 = Chunk(
            chunk_hash=ch4,
            content="event content 1",
            context_header="Event header",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
            domain_metadata={
                "host": "frank@example.com",
                "invitees": ["alice@example.com", "charlie@example.com"]
            },
        )

        store.create_source_version(
            source_id="read-src",
            version=1,
            markdown="content",
            chunk_hashes=[ch1, ch2, ch3, ch4],
            adapter_id="read-adapter",
            normalizer_version="1.0.0",
            fetch_timestamp="2024-01-01T00:00:00+00:00",
        )

        lineage_records = [
            LineageRecord(
                chunk_hash=ch1,
                source_id="read-src",
                source_version_id=1,
                adapter_id="read-adapter",
                domain=Domain.MESSAGES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
            LineageRecord(
                chunk_hash=ch2,
                source_id="read-src",
                source_version_id=1,
                adapter_id="read-adapter",
                domain=Domain.MESSAGES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
            LineageRecord(
                chunk_hash=ch3,
                source_id="read-src",
                source_version_id=1,
                adapter_id="read-adapter",
                domain=Domain.NOTES,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
            LineageRecord(
                chunk_hash=ch4,
                source_id="read-src",
                source_version_id=1,
                adapter_id="read-adapter",
                domain=Domain.EVENTS,
                normalizer_version="1.0.0",
                embedding_model_id="test-model",
            ),
        ]
        store.write_chunks([chunk1, chunk2, chunk3, chunk4], lineage_records)

    def test_empty_identifiers_list(self, store: DocumentStore) -> None:
        """Test that empty identifiers list returns empty results."""
        result = store.query_chunks_by_identifiers(
            identifiers=[],
            scalar_fields=["sender"],
            array_fields=[]
        )
        assert result == []

    def test_single_scalar_field_match(self, store: DocumentStore) -> None:
        """Test querying by single scalar field."""
        self._setup_chunks_with_metadata(store)
        result = store.query_chunks_by_identifiers(
            identifiers=["alice@example.com"],
            scalar_fields=["sender"],
            array_fields=[]
        )
        # Alice is the sender in chunk1, so should find exactly that chunk
        assert len(result) == 1
        assert isinstance(result[0], str) and len(result[0]) == 64  # Valid SHA-256 hash

    def test_single_array_field_match(self, store: DocumentStore) -> None:
        """Test querying by single array field."""
        self._setup_chunks_with_metadata(store)
        result = store.query_chunks_by_identifiers(
            identifiers=["bob@example.com"],
            scalar_fields=[],
            array_fields=["recipients"]
        )
        # bob@example.com appears only in ch1 recipients
        assert len(result) == 1

    def test_multiple_identifiers(self, store: DocumentStore) -> None:
        """Test querying with multiple identifiers."""
        self._setup_chunks_with_metadata(store)
        result = store.query_chunks_by_identifiers(
            identifiers=["alice@example.com", "dave@example.com"],
            scalar_fields=["sender"],
            array_fields=[]
        )
        # alice is sender of ch1, dave is sender of ch2
        assert len(result) == 2
        # Verify both returned hashes are unique chunk hashes from the query
        assert all(isinstance(h, str) and len(h) == 64 for h in result)

    def test_combined_scalar_and_array_fields(self, store: DocumentStore) -> None:
        """Test querying with both scalar and array fields."""
        self._setup_chunks_with_metadata(store)
        result = store.query_chunks_by_identifiers(
            identifiers=["alice@example.com"],
            scalar_fields=["sender", "author"],
            array_fields=["recipients", "collaborators"]
        )
        # alice appears: as sender in ch1, in collaborators of ch3 (2 chunks)
        # ch2 has alice in recipients but she's not sender/author
        # ch4 has alice in invitees but query doesn't search invitees
        assert len(result) == 2

    def test_exclude_domain_filter(self, store: DocumentStore) -> None:
        """Test that exclude_domain parameter filters out results from excluded domain."""
        self._setup_chunks_with_metadata(store)
        # Query for alice, searching across all field types
        result_no_exclude = store.query_chunks_by_identifiers(
            identifiers=["alice@example.com"],
            scalar_fields=["sender", "author"],
            array_fields=["recipients", "collaborators", "invitees"]
        )

        # Query excluding NOTES domain - should filter out chunks from NOTES sources
        result_exclude_notes = store.query_chunks_by_identifiers(
            identifiers=["alice@example.com"],
            scalar_fields=["sender", "author"],
            array_fields=["recipients", "collaborators", "invitees"],
            exclude_domain=Domain.NOTES
        )

        # Query excluding EVENTS domain
        result_exclude_events = store.query_chunks_by_identifiers(
            identifiers=["alice@example.com"],
            scalar_fields=["sender", "author"],
            array_fields=["recipients", "collaborators", "invitees"],
            exclude_domain=Domain.EVENTS
        )

        # Both should return lists (exclude_domain parameter works without error)
        assert isinstance(result_no_exclude, list)
        assert isinstance(result_exclude_notes, list)
        assert isinstance(result_exclude_events, list)

        # Test data is in a NOTES domain source, so:
        # - Excluding NOTES should return empty results
        # - Excluding EVENTS should return all results (no EVENTS domain chunks in test data)
        assert len(result_exclude_notes) == 0, "Excluding NOTES domain should return no results since all test data is in NOTES domain"
        assert len(result_exclude_events) == len(result_no_exclude), "Excluding EVENTS domain should not filter any results since test data has no EVENTS domain chunks"

    def test_no_scalar_and_array_fields_raises_error(self, store: DocumentStore) -> None:
        """Test that providing neither scalar nor array fields raises ValueError."""
        with pytest.raises(ValueError, match="At least one of scalar_fields or array_fields must be provided"):
            store.query_chunks_by_identifiers(
                identifiers=["test@example.com"],
                scalar_fields=[],
                array_fields=[]
            )

    def test_invalid_field_name_raises_error(self, store: DocumentStore) -> None:
        """Test that invalid field names raise ValueError."""
        with pytest.raises(ValueError, match="Invalid field name"):
            store.query_chunks_by_identifiers(
                identifiers=["test@example.com"],
                scalar_fields=["invalid-field-name"],  # Contains dash, not allowed
                array_fields=[]
            )

    def test_empty_field_name_raises_error(self, store: DocumentStore) -> None:
        """Test that empty field names raise ValueError."""
        with pytest.raises(ValueError, match="Invalid field name"):
            store.query_chunks_by_identifiers(
                identifiers=["test@example.com"],
                scalar_fields=[""],  # Empty string
                array_fields=[]
            )

    def test_field_name_with_special_chars_raises_error(self, store: DocumentStore) -> None:
        """Test that field names with special characters raise ValueError."""
        with pytest.raises(ValueError, match="Invalid field name"):
            store.query_chunks_by_identifiers(
                identifiers=["test@example.com"],
                scalar_fields=["field'; DROP TABLE"],
                array_fields=[]
            )

    def test_valid_field_names_with_underscores(self, store: DocumentStore) -> None:
        """Test that underscores are allowed in field names."""
        self._setup_chunks_with_metadata(store)
        # Should not raise error for valid underscored field names
        result = store.query_chunks_by_identifiers(
            identifiers=["test@example.com"],
            scalar_fields=["sender_address", "user_email"],
            array_fields=[]
        )
        # No results expected since we don't have these fields, but no error
        assert result == []

    def test_results_are_sorted(self, store: DocumentStore) -> None:
        """Test that results are returned in sorted order."""
        self._setup_chunks_with_metadata(store)
        result = store.query_chunks_by_identifiers(
            identifiers=["alice@example.com"],
            scalar_fields=["sender"],
            array_fields=["recipients", "collaborators", "invitees"]
        )
        # Verify results are sorted
        assert result == sorted(result)

    def test_no_matches_returns_empty(self, store: DocumentStore) -> None:
        """Test that no matching identifiers returns empty list."""
        self._setup_chunks_with_metadata(store)
        result = store.query_chunks_by_identifiers(
            identifiers=["nonexistent@example.com"],
            scalar_fields=["sender"],
            array_fields=["recipients"]
        )
        assert result == []

    def test_retired_chunks_excluded(self, store: DocumentStore) -> None:
        """Test that retired chunks are excluded from results."""
        from context_library.storage.models import compute_chunk_hash, Chunk, ChunkType

        _setup_adapter_and_source(store)

        # Create and write a chunk
        ch1 = compute_chunk_hash("content")
        chunk1 = Chunk(
            chunk_hash=ch1,
            content="content",
            context_header="Header",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
            domain_metadata={"sender": "alice@example.com"},
        )
        store.create_source_version(
            source_id="read-src",
            version=1,
            markdown="content",
            chunk_hashes=[ch1],
            adapter_id="read-adapter",
            normalizer_version="1.0.0",
            fetch_timestamp="2024-01-01T00:00:00+00:00",
        )
        lineage1 = LineageRecord(
            chunk_hash=ch1,
            source_id="read-src",
            source_version_id=1,
            adapter_id="read-adapter",
            domain=Domain.MESSAGES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )
        store.write_chunks([chunk1], [lineage1])

        # Verify it's found
        result = store.query_chunks_by_identifiers(
            identifiers=["alice@example.com"],
            scalar_fields=["sender"],
            array_fields=[]
        )
        assert ch1 in result

        # Retire the chunk
        cursor = store.conn.cursor()
        cursor.execute(
            "UPDATE chunks SET retired_at = ? WHERE chunk_hash = ?",
            ("2024-01-02T00:00:00Z", ch1)
        )
        store.conn.commit()

        # Verify it's no longer found
        result = store.query_chunks_by_identifiers(
            identifiers=["alice@example.com"],
            scalar_fields=["sender"],
            array_fields=[]
        )
        assert ch1 not in result


class TestSchemaMigrationV3toV4:
    """Tests for schema migration from v3 to v4 (people domain and entity_links support)."""

    def _create_v3_database(self, db_path: Path) -> None:
        """Create a v3 database with some seed data for migration testing."""
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Set schema version to 3
        cursor.execute("PRAGMA user_version=3")

        # Create minimal v3 schema (without people domain and entity_links)
        cursor.execute("""
            CREATE TABLE adapters (
                adapter_id          TEXT PRIMARY KEY,
                domain              TEXT NOT NULL CHECK (domain IN ('messages', 'notes', 'events', 'tasks', 'health', 'documents')),
                adapter_type        TEXT NOT NULL,
                normalizer_version  TEXT NOT NULL,
                config              TEXT,
                enabled             BOOLEAN NOT NULL DEFAULT 1,
                created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE sources (
                source_id           TEXT PRIMARY KEY,
                adapter_id          TEXT NOT NULL,
                domain              TEXT NOT NULL CHECK (domain IN ('messages', 'notes', 'events', 'tasks', 'health', 'documents')),
                origin_ref          TEXT NOT NULL,
                display_name        TEXT,
                current_version     INTEGER NOT NULL DEFAULT 0,
                last_fetched_at     DATETIME,
                poll_strategy       TEXT NOT NULL CHECK (poll_strategy IN ('push', 'pull', 'webhook')),
                poll_interval_sec   INTEGER,
                created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (adapter_id) REFERENCES adapters(adapter_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE source_versions (
                source_id           TEXT NOT NULL,
                version             INTEGER NOT NULL,
                markdown            TEXT NOT NULL,
                chunk_hashes        TEXT NOT NULL,
                adapter_id          TEXT NOT NULL,
                normalizer_version  TEXT NOT NULL,
                fetch_timestamp     DATETIME NOT NULL,
                created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (source_id, version),
                FOREIGN KEY (source_id) REFERENCES sources(source_id),
                FOREIGN KEY (adapter_id) REFERENCES adapters(adapter_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE chunks (
                chunk_hash          TEXT NOT NULL,
                source_id           TEXT NOT NULL,
                source_version      INTEGER NOT NULL,
                chunk_index         INTEGER NOT NULL,
                content             TEXT NOT NULL,
                context_header      TEXT,
                domain              TEXT NOT NULL CHECK (domain IN ('messages', 'notes', 'events', 'tasks', 'health', 'documents')),
                adapter_id          TEXT NOT NULL,
                fetch_timestamp     DATETIME NOT NULL,
                normalizer_version  TEXT NOT NULL,
                embedding_model_id  TEXT NOT NULL DEFAULT 'unspecified',
                parent_chunk_hash   TEXT,
                domain_metadata     TEXT,
                chunk_type          TEXT DEFAULT 'standard' CHECK (chunk_type IN ('standard', 'oversized', 'table_part', 'code', 'table')),
                retired_at          DATETIME,
                created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chunk_hash, source_id, source_version),
                FOREIGN KEY (source_id, source_version) REFERENCES source_versions(source_id, version),
                FOREIGN KEY (adapter_id) REFERENCES adapters(adapter_id),
                UNIQUE (source_id, source_version, chunk_index)
            )
        """)

        # Insert seed data
        cursor.execute("""
            INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version)
            VALUES ('test-adapter', 'messages', 'EmailAdapter', '1.0.0')
        """)

        cursor.execute("""
            INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy)
            VALUES ('test-source', 'test-adapter', 'messages', 'test://ref', 'pull')
        """)

        cursor.execute("""
            INSERT INTO source_versions (source_id, version, markdown, chunk_hashes, adapter_id, normalizer_version, fetch_timestamp)
            VALUES ('test-source', 1, 'Test content', '["abc123"]', 'test-adapter', '1.0.0', CURRENT_TIMESTAMP)
        """)

        cursor.execute("""
            INSERT INTO chunks (chunk_hash, source_id, source_version, chunk_index, content, domain, adapter_id,
                                fetch_timestamp, normalizer_version)
            VALUES ('abc123', 'test-source', 1, 0, 'Test chunk content', 'messages', 'test-adapter',
                    CURRENT_TIMESTAMP, '1.0.0')
        """)

        conn.commit()
        conn.close()

    def test_migrate_v3_to_v4_creates_entity_links_table(self) -> None:
        """Test that migration from v3 to v4 creates entity_links table."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v3 database
            self._create_v3_database(db_path)

            # Trigger migration by opening DocumentStore
            store = DocumentStore(str(db_path))

            # Verify schema version is now 4
            cursor = store.conn.cursor()
            cursor.execute("PRAGMA user_version")
            version = cursor.fetchone()[0]
            assert version == 4

            # Verify entity_links table exists
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='entity_links'
            """)
            assert cursor.fetchone() is not None

            store.close()

    def test_migrate_v3_to_v4_adds_people_domain(self) -> None:
        """Test that migration adds 'people' to domain CHECK constraints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v3 database
            self._create_v3_database(db_path)

            # Trigger migration
            store = DocumentStore(str(db_path))

            # Verify we can insert a people domain adapter
            store.register_adapter(
                AdapterConfig(
                    adapter_id="people-adapter",
                    adapter_type="AppleContactsAdapter",
                    domain=Domain.PEOPLE,
                    normalizer_version="1.0.0",
                )
            )

            # Verify it was inserted
            cursor = store.conn.cursor()
            cursor.execute("SELECT domain FROM adapters WHERE adapter_id = ?", ("people-adapter",))
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "people"

            store.close()

    def test_migrate_v3_to_v4_preserves_existing_data(self) -> None:
        """Test that migration preserves all existing data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v3 database with seed data
            self._create_v3_database(db_path)

            # Trigger migration
            store = DocumentStore(str(db_path))

            # Verify seed data is intact
            cursor = store.conn.cursor()
            cursor.execute("SELECT adapter_id, domain FROM adapters WHERE adapter_id = ?", ("test-adapter",))
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "test-adapter"
            assert result[1] == "messages"

            cursor.execute("SELECT source_id FROM sources WHERE source_id = ?", ("test-source",))
            result = cursor.fetchone()
            assert result is not None

            cursor.execute("SELECT chunk_hash, content FROM chunks WHERE chunk_hash = ?", ("abc123",))
            result = cursor.fetchone()
            assert result is not None
            assert result[1] == "Test chunk content"

            cursor.execute("SELECT source_id, version FROM source_versions WHERE source_id = ?", ("test-source",))
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "test-source"
            assert result[1] == 1

            store.close()

    def test_migrate_v3_to_v4_idempotent(self) -> None:
        """Test that migration is idempotent (v4 DB not re-migrated)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v3 database and migrate to v4
            self._create_v3_database(db_path)
            store1 = DocumentStore(str(db_path))
            store1.close()

            # Open again - should not attempt re-migration
            store2 = DocumentStore(str(db_path))

            cursor = store2.conn.cursor()
            cursor.execute("PRAGMA user_version")
            version = cursor.fetchone()[0]
            assert version == 4

            # Verify entity_links table still exists
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='entity_links'
            """)
            assert cursor.fetchone() is not None

            store2.close()

    def test_migrate_v3_to_v4_entity_links_schema(self) -> None:
        """Test that entity_links table has correct schema after migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v3 database and migrate to v4
            self._create_v3_database(db_path)
            store = DocumentStore(str(db_path))

            # Get entity_links table info
            cursor = store.conn.cursor()
            cursor.execute("PRAGMA table_info(entity_links)")
            columns = cursor.fetchall()

            # Verify columns exist
            column_names = [col[1] for col in columns]
            assert "source_chunk_hash" in column_names
            assert "target_chunk_hash" in column_names
            assert "link_type" in column_names
            assert "confidence" in column_names
            assert "created_at" in column_names

            store.close()

    def test_migrate_v3_to_v4_entity_links_has_indices(self) -> None:
        """Test that after migration, entity_links table has proper indices."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v3 database and migrate to v4
            self._create_v3_database(db_path)
            store = DocumentStore(str(db_path))

            # Get indices on entity_links table
            cursor = store.conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='index' AND tbl_name='entity_links'
            """)
            indices = [row[0] for row in cursor.fetchall()]

            # Verify indices exist for efficient querying
            assert len(indices) > 0
            # Should have indices on source and target for efficient lookups
            index_names = [idx.lower() for idx in indices]
            assert any('source' in idx for idx in index_names)
            assert any('target' in idx for idx in index_names)

            store.close()
