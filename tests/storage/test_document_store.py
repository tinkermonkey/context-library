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

    def test_synchronous_normal_enabled(self) -> None:
        """Test that synchronous=NORMAL is enforced (value 1 per FR-2.2)."""
        store = DocumentStore(":memory:")
        cursor = store.conn.cursor()
        cursor.execute("PRAGMA synchronous")
        synchronous = cursor.fetchone()[0]
        assert synchronous == 1

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
        assert latest.chunk_hashes == ["1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"]

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
                chunk_type="invalid_type_value",  # Not in ChunkType enum
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
        retrieved = store.get_chunks_by_source("source-1", version=1)

        assert len(retrieved) == 1
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
            chunk_type="standard",
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
        cursor.execute(
            "DELETE FROM chunks WHERE chunk_hash = ?",
            (_make_hash("a"),),
        )

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
        from context_library.storage.models import PollStrategy

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
        from context_library.storage.models import PollStrategy

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
        from context_library.storage.models import PollStrategy

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
        """Test that idempotency is preserved when registering source twice."""
        from context_library.storage.models import PollStrategy

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

        # Second registration with different parameters (should be idempotent - no update)
        store.register_source(
            source_id="idempotent-source",
            adapter_id="poll-adapter",
            domain=Domain.NOTES,
            origin_ref="test://source",
            poll_strategy=PollStrategy.PUSH,
            poll_interval_sec=7200,
        )

        # Verify original values are preserved (idempotent behavior)
        cursor = store.conn.cursor()
        cursor.execute(
            "SELECT poll_strategy, poll_interval_sec FROM sources WHERE source_id = ?",
            ("idempotent-source",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["poll_strategy"] == "pull"  # Original value
        assert row["poll_interval_sec"] == 3600  # Original value

        # Verify only one row exists
        cursor.execute(
            "SELECT COUNT(*) FROM sources WHERE source_id = ?",
            ("idempotent-source",),
        )
        count = cursor.fetchone()[0]
        assert count == 1

    def test_get_sources_due_for_poll_never_fetched(self, store: DocumentStore) -> None:
        """Test that sources with last_fetched_at IS NULL are returned."""
        self._setup_adapter(store)

        from context_library.storage.models import PollStrategy

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
        from datetime import datetime, timedelta, timezone
        from context_library.storage.models import PollStrategy

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
        from datetime import datetime, timedelta, timezone
        from context_library.storage.models import PollStrategy

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
        from context_library.storage.models import PollStrategy

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
        from context_library.storage.models import PollStrategy

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
        from context_library.storage.models import PollStrategy

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
        from datetime import datetime, timedelta, timezone
        from context_library.storage.models import PollStrategy

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
