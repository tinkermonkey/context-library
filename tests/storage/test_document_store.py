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
"""

import pytest

from context_library.storage.document_store import DocumentStore
from context_library.storage.models import (
    AdapterConfig,
    Chunk,
    Domain,
    LineageRecord,
)


@pytest.fixture
def store() -> DocumentStore:
    """Create an in-memory DocumentStore for testing."""
    return DocumentStore(":memory:")


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
        assert store.conn is not None

    def test_schema_version_verification(self) -> None:
        """Test that user_version is verified to be 1."""
        store = DocumentStore(":memory:")
        cursor = store.conn.cursor()
        cursor.execute("PRAGMA user_version")
        version = cursor.fetchone()[0]
        assert version == 1

    def test_wal_mode_enabled(self) -> None:
        """Test that WAL mode is enabled (or memory for in-memory DBs)."""
        store = DocumentStore(":memory:")
        cursor = store.conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0].lower()
        # In-memory databases use "memory" mode, file-based use "wal"
        assert mode in ("wal", "memory")

    def test_foreign_keys_enabled(self) -> None:
        """Test that foreign key enforcement is enabled."""
        store = DocumentStore(":memory:")
        cursor = store.conn.cursor()
        cursor.execute("PRAGMA foreign_keys")
        enabled = cursor.fetchone()[0]
        assert enabled == 1


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
        """Test that re-registering an adapter with updated config actually updates it."""
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

        # Re-register with updated config
        config2 = AdapterConfig(
            adapter_id="update-adapter",
            adapter_type="gmail",
            domain=Domain.MESSAGES,
            normalizer_version="2.0.0",
            config={"api_key": "new_key"},
        )

        store.register_adapter(config2)
        adapter2 = store.get_adapter("update-adapter")

        assert adapter2 is not None
        assert adapter2.normalizer_version == "2.0.0"
        assert adapter2.config == {"api_key": "new_key"}

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
            chunk_hashes=["abc123def456"],
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
            chunk_hashes=["hash1"],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        store.create_source_version(
            source_id="source-1",
            version=2,
            markdown="# Content v2",
            chunk_hashes=["hash2"],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T11:00:00Z",
        )

        latest = store.get_latest_version("source-1")
        assert latest is not None
        assert latest.version == 2
        assert latest.markdown == "# Content v2"
        assert latest.chunk_hashes == ["hash2"]

    def test_get_version_history_ordering(self, store: DocumentStore) -> None:
        """Test that version history is ordered ascending."""
        self._setup_adapter_and_source(store)

        # Create versions in mixed order
        for v in [3, 1, 2]:
            store.create_source_version(
                source_id="source-1",
                version=v,
                markdown=f"# Content v{v}",
                chunk_hashes=[f"hash{v}"],
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
            chunk_hashes=["hash1", "hash2"],
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
                chunk_type="standard",
            ),
            Chunk(
                chunk_hash=_make_hash("b"),
                content="This is chunk 2",
                context_header="Section 2",
                chunk_index=1,
                chunk_type="standard",
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
            chunk_type="standard",
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
        """Test that write_chunks raises IntegrityError for invalid chunk_type."""
        source_id, adapter_id, version_id = self._setup_with_version(store)

        # Create a chunk with invalid chunk_type that violates CHECK constraint
        chunk = Chunk(
            chunk_hash=_make_hash("f"),
            content="Invalid chunk",
            chunk_index=0,
            chunk_type="invalid_type_value",  # Not in ('standard', 'oversized', 'table_part', 'code', 'table')
        )

        lineage = LineageRecord(
            chunk_hash=_make_hash("f"),
            source_id=source_id,
            source_version_id=version_id,
            adapter_id=adapter_id,
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )

        # Should raise IntegrityError because chunk_type violates CHECK constraint
        import sqlite3

        with pytest.raises(sqlite3.IntegrityError):
            store.write_chunks([chunk], [lineage])

    def test_write_chunks_invalid_adapter_id_raises_error(
        self, store: DocumentStore
    ) -> None:
        """Test that write_chunks raises IntegrityError for foreign key violation."""
        source_id, adapter_id, version_id = self._setup_with_version(store)

        chunk = Chunk(
            chunk_hash=_make_hash("1"),
            content="Foreign key test",
            chunk_index=0,
            chunk_type="standard",
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

        metadata = {"sender": "user@example.com", "timestamp": "2025-03-02"}
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
        """Test retiring chunks."""
        hashes = self._setup_chunks_for_retirement(store)

        store.retire_chunks(hashes)

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

        # Retire one chunk
        store.retire_chunks({_make_hash("a")})

        # Get chunks should only return non-retired
        retrieved = store.get_chunks_by_source("source-1", version=1)

        assert len(retrieved) == 1
        assert retrieved[0].chunk_hash == _make_hash("1")


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
        chunks = store.get_chunks_by_source("source-1")

        assert len(chunks) == 1
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
        v1_chunks = store.get_chunks_by_source("source-1", version=1)
        assert len(v1_chunks) == 1
        assert v1_chunks[0].chunk_hash == _make_hash("3")

        # Get chunks for version 2
        v2_chunks = store.get_chunks_by_source("source-1", version=2)
        assert len(v2_chunks) == 1
        assert v2_chunks[0].chunk_hash == _make_hash("4")

    def test_get_chunks_by_source_non_existent(self, store: DocumentStore) -> None:
        """Test retrieving chunks for non-existent source."""
        chunks = store.get_chunks_by_source("non-existent")
        assert chunks == []


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
        """Test writing to sync log with operation type."""
        chunk_hash = self._setup_chunk_for_sync(store)

        store.write_sync_log([chunk_hash], "insert")

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

        store.write_sync_log([chunk_hash], "insert")
        store.write_sync_log([chunk_hash], "insert")

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

        store.write_sync_log([chunk_hash], "insert")
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
        # Intentionally skip: store.write_sync_log([chunk_hash], "insert")

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

    def test_write_sync_log_invalid_operation(self, store: DocumentStore) -> None:
        """Test that invalid operation type raises ValueError."""
        chunk_hash = self._setup_chunk_for_sync(store)

        with pytest.raises(ValueError, match="Invalid operation"):
            store.write_sync_log([chunk_hash], "invalid")


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
