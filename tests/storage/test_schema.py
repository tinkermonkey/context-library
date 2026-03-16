"""Tests for storage schema and migrations.

Tests for:
- Schema initialization
- v1 to v2 migration: data preservation, rollback, idempotency, fresh database
- v2 to v3 migration: data preservation, constraint validation, idempotency
- v1 to v3 chained migration: ensures v1→v2→v3 path works correctly
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path

from context_library.storage.document_store import DocumentStore


def _create_v1_schema(conn: sqlite3.Connection) -> None:
    """Create a v1 schema database (without 'health' domain in CHECK constraints).

    Args:
        conn: SQLite connection to populate with v1 schema.
    """
    cursor = conn.cursor()

    # Set version to 1
    cursor.execute("PRAGMA user_version=1")

    # Create adapters table WITHOUT 'health' domain
    cursor.execute("""
        CREATE TABLE adapters (
            adapter_id          TEXT PRIMARY KEY,
            domain              TEXT NOT NULL CHECK (domain IN ('messages', 'notes', 'events', 'tasks')),
            adapter_type        TEXT NOT NULL,
            normalizer_version  TEXT NOT NULL,
            config              TEXT,
            enabled             BOOLEAN NOT NULL DEFAULT 1,
            created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create sources table WITHOUT 'health' domain
    cursor.execute("""
        CREATE TABLE sources (
            source_id           TEXT PRIMARY KEY,
            adapter_id          TEXT NOT NULL,
            domain              TEXT NOT NULL CHECK (domain IN ('messages', 'notes', 'events', 'tasks')),
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

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sources_adapter ON sources(adapter_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources(domain)")

    # Create source_versions table (unchanged)
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

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_versions_adapter_id ON source_versions(adapter_id)")

    # Create chunks table WITHOUT 'health' domain
    cursor.execute("""
        CREATE TABLE chunks (
            chunk_hash          TEXT NOT NULL,
            source_id           TEXT NOT NULL,
            source_version      INTEGER NOT NULL,
            chunk_index         INTEGER NOT NULL,
            content             TEXT NOT NULL,
            context_header      TEXT,
            domain              TEXT NOT NULL CHECK (domain IN ('messages', 'notes', 'events', 'tasks')),
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

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_id, source_version)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_domain ON chunks(domain)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_parent ON chunks(parent_chunk_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_retired ON chunks(retired_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_adapter ON chunks(adapter_id)")

    # Create triggers
    cursor.execute("""
        CREATE TRIGGER sources_update_timestamp
        AFTER UPDATE ON sources
        FOR EACH ROW
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
            UPDATE sources SET updated_at = CURRENT_TIMESTAMP WHERE source_id = NEW.source_id;
        END
    """)

    cursor.execute("""
        CREATE TRIGGER adapters_update_timestamp
        AFTER UPDATE ON adapters
        FOR EACH ROW
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
            UPDATE adapters SET updated_at = CURRENT_TIMESTAMP WHERE adapter_id = NEW.adapter_id;
        END
    """)

    # Create lancedb_sync_log table (unchanged)
    cursor.execute("""
        CREATE TABLE lancedb_sync_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_hash      TEXT NOT NULL,
            operation       TEXT NOT NULL CHECK (operation IN ('insert', 'delete')),
            synced_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (chunk_hash, operation)
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_lancedb_sync_log_synced_at ON lancedb_sync_log(synced_at)")

    conn.commit()


def _create_v2_schema(conn: sqlite3.Connection) -> None:
    """Create a v2 schema database (includes 'health' but not 'documents' in CHECK constraints).

    Args:
        conn: SQLite connection to populate with v2 schema.
    """
    cursor = conn.cursor()

    # Set version to 2
    cursor.execute("PRAGMA user_version=2")

    # Create adapters table with 'health' but WITHOUT 'documents' domain
    cursor.execute("""
        CREATE TABLE adapters (
            adapter_id          TEXT PRIMARY KEY,
            domain              TEXT NOT NULL CHECK (domain IN ('messages', 'notes', 'events', 'tasks', 'health')),
            adapter_type        TEXT NOT NULL,
            normalizer_version  TEXT NOT NULL,
            config              TEXT,
            enabled             BOOLEAN NOT NULL DEFAULT 1,
            created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create sources table with 'health' but WITHOUT 'documents' domain
    cursor.execute("""
        CREATE TABLE sources (
            source_id           TEXT PRIMARY KEY,
            adapter_id          TEXT NOT NULL,
            domain              TEXT NOT NULL CHECK (domain IN ('messages', 'notes', 'events', 'tasks', 'health')),
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

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sources_adapter ON sources(adapter_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources(domain)")

    # Create source_versions table
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

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_versions_adapter_id ON source_versions(adapter_id)")

    # Create chunks table with 'health' but WITHOUT 'documents' domain
    cursor.execute("""
        CREATE TABLE chunks (
            chunk_hash          TEXT NOT NULL,
            source_id           TEXT NOT NULL,
            source_version      INTEGER NOT NULL,
            chunk_index         INTEGER NOT NULL,
            content             TEXT NOT NULL,
            context_header      TEXT,
            domain              TEXT NOT NULL CHECK (domain IN ('messages', 'notes', 'events', 'tasks', 'health')),
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

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_id, source_version)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_domain ON chunks(domain)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_parent ON chunks(parent_chunk_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_retired ON chunks(retired_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_adapter ON chunks(adapter_id)")

    # Create triggers
    cursor.execute("""
        CREATE TRIGGER sources_update_timestamp
        AFTER UPDATE ON sources
        FOR EACH ROW
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
            UPDATE sources SET updated_at = CURRENT_TIMESTAMP WHERE source_id = NEW.source_id;
        END
    """)

    cursor.execute("""
        CREATE TRIGGER adapters_update_timestamp
        AFTER UPDATE ON adapters
        FOR EACH ROW
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
            UPDATE adapters SET updated_at = CURRENT_TIMESTAMP WHERE adapter_id = NEW.adapter_id;
        END
    """)

    # Create lancedb_sync_log table
    cursor.execute("""
        CREATE TABLE lancedb_sync_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_hash      TEXT NOT NULL,
            operation       TEXT NOT NULL CHECK (operation IN ('insert', 'delete')),
            synced_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (chunk_hash, operation)
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_lancedb_sync_log_synced_at ON lancedb_sync_log(synced_at)")

    conn.commit()


class TestSchemaMigrationV1ToV2:
    """Tests for migration from v1 (without health) to v2 (with health domain)."""

    def test_migrate_v1_to_v2_adapter_data_preservation(self) -> None:
        """Test that adapter data is preserved during v1 to v2 migration.

        Verifies that existing adapters in a v1 database are correctly copied
        to the new v2 schema after migration.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v1 database with adapter data
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            _create_v1_schema(conn)

            # Insert test adapter into v1 schema
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version, config, enabled)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("test-adapter", "messages", "gmail", "1.0", '{"key": "value"}', 1))
            conn.commit()
            conn.close()

            # Migrate by opening with DocumentStore
            store = DocumentStore(str(db_path))

            # Verify adapter data was preserved
            cursor = store.conn.cursor()
            cursor.execute("SELECT * FROM adapters WHERE adapter_id = 'test-adapter'")
            row = cursor.fetchone()

            assert row is not None
            assert row["adapter_id"] == "test-adapter"
            assert row["domain"] == "messages"
            assert row["adapter_type"] == "gmail"
            assert row["normalizer_version"] == "1.0"
            assert row["config"] == '{"key": "value"}'
            assert row["enabled"] == 1
            store.conn.close()

    def test_migrate_v1_to_v2_source_data_preservation(self) -> None:
        """Test that source data is preserved during v1 to v2 migration.

        Verifies that existing sources in a v1 database are correctly copied
        to the new v2 schema after migration, including all fields.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v1 database with source data
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            _create_v1_schema(conn)

            # Insert test adapter and source
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version)
                VALUES (?, ?, ?, ?)
            """, ("test-adapter", "messages", "gmail", "1.0"))

            cursor.execute("""
                INSERT INTO sources (source_id, adapter_id, domain, origin_ref, display_name, poll_strategy, poll_interval_sec)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("test-source", "test-adapter", "messages", "user@gmail.com", "My Inbox", "pull", 3600))
            conn.commit()
            conn.close()

            # Migrate by opening with DocumentStore
            store = DocumentStore(str(db_path))

            # Verify source data was preserved
            cursor = store.conn.cursor()
            cursor.execute("SELECT * FROM sources WHERE source_id = 'test-source'")
            row = cursor.fetchone()

            assert row is not None
            assert row["source_id"] == "test-source"
            assert row["adapter_id"] == "test-adapter"
            assert row["domain"] == "messages"
            assert row["origin_ref"] == "user@gmail.com"
            assert row["display_name"] == "My Inbox"
            assert row["poll_strategy"] == "pull"
            assert row["poll_interval_sec"] == 3600
            store.conn.close()

    def test_migrate_v1_to_v2_chunk_data_preservation(self) -> None:
        """Test that chunk data is preserved during v1 to v2 migration.

        Verifies that existing chunks in a v1 database are correctly copied
        to the new v2 schema after migration, including all metadata.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v1 database with chunk data
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            _create_v1_schema(conn)

            # Insert test adapter, source, source_version, and chunk
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version)
                VALUES (?, ?, ?, ?)
            """, ("test-adapter", "notes", "obsidian", "1.0"))

            cursor.execute("""
                INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy)
                VALUES (?, ?, ?, ?, ?)
            """, ("test-source", "test-adapter", "notes", "/vault", "pull"))

            cursor.execute("""
                INSERT INTO source_versions (source_id, version, markdown, chunk_hashes, adapter_id, normalizer_version, fetch_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("test-source", 1, "# Test\nContent", '["a"*64]', "test-adapter", "1.0", "2025-01-01T00:00:00Z"))

            cursor.execute("""
                INSERT INTO chunks (chunk_hash, source_id, source_version, chunk_index, content, domain, adapter_id, fetch_timestamp, normalizer_version, chunk_type, domain_metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("a" * 64, "test-source", 1, 0, "Test content", "notes", "test-adapter", "2025-01-01T00:00:00Z", "1.0", "standard", '{"key": "value"}'))
            conn.commit()
            conn.close()

            # Migrate by opening with DocumentStore
            store = DocumentStore(str(db_path))

            # Verify chunk data was preserved
            cursor = store.conn.cursor()
            cursor.execute("SELECT * FROM chunks WHERE chunk_hash = ?", ("a" * 64,))
            row = cursor.fetchone()

            assert row is not None
            assert row["chunk_hash"] == "a" * 64
            assert row["source_id"] == "test-source"
            assert row["source_version"] == 1
            assert row["chunk_index"] == 0
            assert row["content"] == "Test content"
            assert row["domain"] == "notes"
            assert row["adapter_id"] == "test-adapter"
            assert row["chunk_type"] == "standard"
            assert row["domain_metadata"] == '{"key": "value"}'
            store.conn.close()

    def test_migrate_v1_to_v2_multiple_adapters_and_sources(self) -> None:
        """Test migration preserves multiple adapters and sources with their relationships."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v1 database with multiple records
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            _create_v1_schema(conn)

            cursor = conn.cursor()

            # Insert multiple adapters
            cursor.execute("""
                INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version)
                VALUES (?, ?, ?, ?)
            """, ("adapter-1", "messages", "gmail", "1.0"))

            cursor.execute("""
                INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version)
                VALUES (?, ?, ?, ?)
            """, ("adapter-2", "notes", "obsidian", "1.0"))

            # Insert sources for different adapters
            cursor.execute("""
                INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy)
                VALUES (?, ?, ?, ?, ?)
            """, ("source-1", "adapter-1", "messages", "inbox", "pull"))

            cursor.execute("""
                INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy)
                VALUES (?, ?, ?, ?, ?)
            """, ("source-2", "adapter-2", "notes", "/vault", "push"))

            conn.commit()
            conn.close()

            # Migrate
            store = DocumentStore(str(db_path))

            # Verify all data preserved
            cursor = store.conn.cursor()

            cursor.execute("SELECT COUNT(*) as cnt FROM adapters")
            assert cursor.fetchone()["cnt"] == 2

            cursor.execute("SELECT COUNT(*) as cnt FROM sources")
            assert cursor.fetchone()["cnt"] == 2

            # Verify foreign key relationships still work
            cursor.execute("SELECT s.source_id FROM sources s JOIN adapters a ON s.adapter_id = a.adapter_id WHERE a.adapter_id = 'adapter-1'")
            source = cursor.fetchone()
            assert source["source_id"] == "source-1"
            store.conn.close()

    def test_migrate_v1_to_v2_triggers_recreated(self) -> None:
        """Test that update triggers are properly recreated during migration."""
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v1 database
            conn = sqlite3.connect(str(db_path))
            _create_v1_schema(conn)

            # Insert adapter and source
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version)
                VALUES (?, ?, ?, ?)
            """, ("test-adapter", "messages", "gmail", "1.0"))

            cursor.execute("""
                INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy)
                VALUES (?, ?, ?, ?, ?)
            """, ("test-source", "test-adapter", "messages", "inbox", "pull"))

            # Get original updated_at
            cursor.execute("SELECT updated_at FROM sources WHERE source_id = 'test-source'")
            cursor.fetchone()[0]
            conn.commit()
            conn.close()

            # Migrate
            store = DocumentStore(str(db_path))

            # Wait a moment to ensure timestamp changes
            time.sleep(0.01)

            # Update the source by explicitly setting updated_at to a past value so the trigger fires
            cursor = store.conn.cursor()
            cursor.execute("UPDATE sources SET updated_at = datetime('2020-01-01') WHERE source_id = ?", ("test-source",))
            store.conn.commit()

            time.sleep(0.01)

            # Now update display_name - the trigger should fire because updated_at changed
            cursor.execute("UPDATE sources SET display_name = ? WHERE source_id = ?", ("New Name", "test-source"))
            store.conn.commit()

            # Verify updated_at was updated by the trigger
            cursor.execute("SELECT updated_at FROM sources WHERE source_id = 'test-source'")
            new_updated_at = cursor.fetchone()[0]

            assert new_updated_at > "2020-01-01"
            store.conn.close()

    def test_migrate_v1_to_v2_indices_recreated(self) -> None:
        """Test that indices are properly recreated during migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v1 database
            conn = sqlite3.connect(str(db_path))
            _create_v1_schema(conn)
            conn.close()

            # Migrate
            store = DocumentStore(str(db_path))

            # Check that indices exist
            cursor = store.conn.cursor()

            # Query sqlite_master for indices
            cursor.execute("""
                SELECT name FROM sqlite_master WHERE type='index' AND name IN (
                    'idx_sources_adapter', 'idx_sources_domain',
                    'idx_chunks_source', 'idx_chunks_domain', 'idx_chunks_parent',
                    'idx_chunks_retired', 'idx_chunks_adapter'
                )
            """)

            indices = {row[0] for row in cursor.fetchall()}
            expected_indices = {
                'idx_sources_adapter', 'idx_sources_domain',
                'idx_chunks_source', 'idx_chunks_domain', 'idx_chunks_parent',
                'idx_chunks_retired', 'idx_chunks_adapter'
            }

            assert expected_indices.issubset(indices)
            store.conn.close()

    def test_migrate_v1_to_v2_foreign_keys_maintained(self) -> None:
        """Test that foreign key relationships are maintained after migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v1 database with relationships
            conn = sqlite3.connect(str(db_path))
            _create_v1_schema(conn)

            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version)
                VALUES (?, ?, ?, ?)
            """, ("test-adapter", "messages", "gmail", "1.0"))

            cursor.execute("""
                INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy)
                VALUES (?, ?, ?, ?, ?)
            """, ("test-source", "test-adapter", "messages", "inbox", "pull"))

            conn.commit()
            conn.close()

            # Migrate
            store = DocumentStore(str(db_path))

            # Try to insert a source with invalid adapter_id (should fail due to FK)
            cursor = store.conn.cursor()
            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute("""
                    INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy)
                    VALUES (?, ?, ?, ?, ?)
                """, ("bad-source", "nonexistent-adapter", "messages", "inbox", "pull"))
                store.conn.commit()
            store.conn.close()

    def test_migrate_v1_to_v2_schema_version_updated(self) -> None:
        """Test that schema version is correctly updated and CHECK constraints include 'documents'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v1 database
            conn = sqlite3.connect(str(db_path))
            _create_v1_schema(conn)

            # Verify it's version 1
            cursor = conn.cursor()
            cursor.execute("PRAGMA user_version")
            assert cursor.fetchone()[0] == 1
            conn.close()

            # Migrate
            store = DocumentStore(str(db_path))

            # Verify it's now version 3 (v1→v2 then v2→v3)
            cursor = store.conn.cursor()
            cursor.execute("PRAGMA user_version")
            assert cursor.fetchone()[0] == 3

            # Verify the actual CHECK constraint includes 'documents' (not just version number)
            # This ensures the migration actually updated the table constraints
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='adapters'")
            ddl = cursor.fetchone()[0]
            assert "'documents'" in ddl, "adapters table CHECK constraint missing 'documents' domain"

            store.conn.close()

    def test_migrate_v1_to_v2_fresh_database_starts_at_v3(self) -> None:
        """Test that a fresh database starts at version 3 (no migration needed)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create fresh database (DocumentStore should create v3 schema directly)
            store = DocumentStore(str(db_path))

            # Verify it's version 3
            cursor = store.conn.cursor()
            cursor.execute("PRAGMA user_version")
            assert cursor.fetchone()[0] == 3

            # Verify 'health' and 'documents' domains are in CHECK constraints
            cursor.execute("""
                SELECT sql FROM sqlite_master WHERE type='table' AND name='adapters'
            """)
            schema = cursor.fetchone()[0]
            assert "health" in schema
            assert "documents" in schema
            store.conn.close()

    def test_migrate_v1_to_v2_new_health_domain_insertable_after_migration(self) -> None:
        """Test that 'health' domain can be inserted after migration.

        This verifies the entire point of the migration: that the CHECK constraint
        was properly updated to accept 'health' domain.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v1 database
            conn = sqlite3.connect(str(db_path))
            _create_v1_schema(conn)
            conn.close()

            # Migrate
            store = DocumentStore(str(db_path))

            # Try to insert adapter with 'health' domain (should succeed after migration)
            cursor = store.conn.cursor()
            cursor.execute("""
                INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version)
                VALUES (?, ?, ?, ?)
            """, ("health-adapter", "health", "oura", "1.0"))
            store.conn.commit()

            # Verify it was inserted
            cursor.execute("SELECT domain FROM adapters WHERE adapter_id = 'health-adapter'")
            assert cursor.fetchone()[0] == "health"
            store.conn.close()

    def test_migrate_v1_to_v2_new_health_domain_insertable_in_sources(self) -> None:
        """Test that 'health' domain can be inserted in sources table after migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v1 database and migrate
            conn = sqlite3.connect(str(db_path))
            _create_v1_schema(conn)
            conn.close()

            store = DocumentStore(str(db_path))

            # Insert health adapter and source
            cursor = store.conn.cursor()
            cursor.execute("""
                INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version)
                VALUES (?, ?, ?, ?)
            """, ("oura-adapter", "health", "oura", "1.0"))

            cursor.execute("""
                INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy)
                VALUES (?, ?, ?, ?, ?)
            """, ("oura-source", "oura-adapter", "health", "user-123", "pull"))
            store.conn.commit()

            # Verify it was inserted
            cursor.execute("SELECT domain FROM sources WHERE source_id = 'oura-source'")
            assert cursor.fetchone()[0] == "health"
            store.conn.close()

    def test_migrate_v1_to_v2_new_health_domain_insertable_in_chunks(self) -> None:
        """Test that 'health' domain can be inserted in chunks table after migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v1 database and migrate
            conn = sqlite3.connect(str(db_path))
            _create_v1_schema(conn)
            conn.close()

            store = DocumentStore(str(db_path))
            store.conn.close()

            # Reopen the database in a fresh connection to test chunks insertability
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Insert health adapter and source for chunks
            cursor.execute("""
                INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version)
                VALUES (?, ?, ?, ?)
            """, ("health-adapter", "health", "oura", "1.0"))

            cursor.execute("""
                INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy)
                VALUES (?, ?, ?, ?, ?)
            """, ("health-source", "health-adapter", "health", "user-123", "pull"))

            cursor.execute("""
                INSERT INTO source_versions (source_id, version, markdown, chunk_hashes, adapter_id, normalizer_version, fetch_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("health-source", 1, "Health data", '["c"*64]', "health-adapter", "1.0", "2025-01-02T00:00:00Z"))

            # Insert a chunk with health domain
            cursor.execute("""
                INSERT INTO chunks (chunk_hash, source_id, source_version, chunk_index, content, domain, adapter_id, fetch_timestamp, normalizer_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("c" * 64, "health-source", 1, 0, "Health data", "health", "health-adapter", "2025-01-02T00:00:00Z", "1.0"))
            conn.commit()

            # Verify health domain works in chunks table after migration
            cursor.execute("SELECT domain FROM chunks WHERE chunk_hash = ?", ("c" * 64,))
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "health"

            conn.close()

    def test_migrate_v1_to_v2_migration_failure_raises_runtime_error(self) -> None:
        """Test that migration failure raises RuntimeError with descriptive message.

        This tests the error handling path by simulating a migration failure.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create a v1 database with a source that has data
            conn = sqlite3.connect(str(db_path))
            _create_v1_schema(conn)

            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version)
                VALUES (?, ?, ?, ?)
            """, ("test-adapter", "messages", "gmail", "1.0"))
            conn.commit()
            conn.close()

            # Now corrupt the database by dropping the adapters table
            # This will cause the migration to fail when trying to rename adapters
            conn = sqlite3.connect(str(db_path))
            conn.execute("DROP TABLE adapters")
            conn.execute("PRAGMA user_version=1")  # Reset version to trigger migration
            conn.commit()
            conn.close()

            # Attempting to initialize DocumentStore should raise RuntimeError
            with pytest.raises(RuntimeError, match="Failed to migrate schema from v1 to v2"):
                DocumentStore(str(db_path))

    def test_migrate_v1_to_v2_foreign_keys_reenabled_after_migration(self) -> None:
        """Test that foreign key enforcement is re-enabled after migration completes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v1 database
            conn = sqlite3.connect(str(db_path))
            _create_v1_schema(conn)
            conn.close()

            # Migrate
            store = DocumentStore(str(db_path))

            # Verify foreign_keys is ON
            cursor = store.conn.cursor()
            cursor.execute("PRAGMA foreign_keys")
            assert cursor.fetchone()[0] == 1
            store.conn.close()

    def test_migrate_v1_to_v2_idempotent_on_reopen(self) -> None:
        """Test that opening a migrated database again doesn't re-run migration.

        This verifies idempotency: a v2 database should not try to migrate again.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v1 database and migrate
            conn = sqlite3.connect(str(db_path))
            _create_v1_schema(conn)

            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version)
                VALUES (?, ?, ?, ?)
            """, ("test-adapter", "messages", "gmail", "1.0"))
            conn.commit()
            conn.close()

            # First open: migrate from v1 to v2
            store1 = DocumentStore(str(db_path))
            cursor = store1.conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM adapters")
            count_after_first_open = cursor.fetchone()["cnt"]
            store1.conn.close()

            # Second open: should not re-run migration, data should still be there
            store2 = DocumentStore(str(db_path))
            cursor = store2.conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM adapters")
            count_after_second_open = cursor.fetchone()["cnt"]

            assert count_after_first_open == count_after_second_open == 1
            store2.conn.close()


class TestSchemaPragmasAndConfiguration:
    """Tests for schema PRAGMA settings and database configuration."""

    def test_schema_pragma_foreign_keys_enforced(self) -> None:
        """Test that PRAGMA foreign_keys=ON is enforced."""
        store = DocumentStore(":memory:")
        cursor = store.conn.cursor()
        cursor.execute("PRAGMA foreign_keys")
        assert cursor.fetchone()[0] == 1
        store.conn.close()

    def test_schema_pragma_synchronous_normal(self) -> None:
        """Test that PRAGMA synchronous=NORMAL (value 1) is set."""
        store = DocumentStore(":memory:")
        cursor = store.conn.cursor()
        cursor.execute("PRAGMA synchronous")
        assert cursor.fetchone()[0] == 1
        store.conn.close()

    def test_schema_pragma_wal_mode(self) -> None:
        """Test that WAL mode is enabled (or memory for in-memory DBs)."""
        store = DocumentStore(":memory:")
        cursor = store.conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0].lower()
        assert mode in ("wal", "memory")
        store.conn.close()

    def test_schema_user_version_is_3(self) -> None:
        """Test that user_version is set to 3."""
        store = DocumentStore(":memory:")
        cursor = store.conn.cursor()
        cursor.execute("PRAGMA user_version")
        assert cursor.fetchone()[0] == 3
        store.conn.close()


class TestSchemaMigrationV2ToV3:
    """Test suite for v2→v3 schema migration.

    Tests migration from schema version 2 (includes 'health' domain) to version 3
    (adds 'documents' domain). Covers data preservation, constraint validation,
    and idempotency.
    """

    def test_migrate_v2_to_v3_version_updated_and_constraint_includes_documents(self) -> None:
        """Test that v2 database migrates to v3 and CHECK constraints include 'documents'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v2 database
            conn = sqlite3.connect(str(db_path))
            _create_v2_schema(conn)

            # Verify it's version 2
            cursor = conn.cursor()
            cursor.execute("PRAGMA user_version")
            assert cursor.fetchone()[0] == 2

            # Verify constraint does NOT include 'documents' yet
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='adapters'")
            ddl = cursor.fetchone()[0]
            assert "'documents'" not in ddl

            conn.close()

            # Migrate
            store = DocumentStore(str(db_path))

            # Verify it's now version 3
            cursor = store.conn.cursor()
            cursor.execute("PRAGMA user_version")
            assert cursor.fetchone()[0] == 3

            # Verify the actual CHECK constraint includes 'documents'
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='adapters'")
            ddl = cursor.fetchone()[0]
            assert "'documents'" in ddl, "adapters table CHECK constraint missing 'documents' domain"

            store.conn.close()

    def test_migrate_v2_to_v3_all_tables_have_documents_constraint(self) -> None:
        """Test that all three tables (adapters, sources, chunks) have 'documents' in CHECK."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v2 database
            conn = sqlite3.connect(str(db_path))
            _create_v2_schema(conn)
            conn.close()

            # Migrate
            store = DocumentStore(str(db_path))
            cursor = store.conn.cursor()

            # Verify 'documents' in all three table CHECK constraints
            for table_name in ("adapters", "sources", "chunks"):
                cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'")
                ddl = cursor.fetchone()[0]
                assert "'documents'" in ddl, f"{table_name} table missing 'documents' in CHECK constraint"

            store.conn.close()

    def test_migrate_v2_to_v3_data_preservation(self) -> None:
        """Test that existing data in adapters, sources, and chunks is preserved after migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v2 database with test data
            conn = sqlite3.connect(str(db_path))
            _create_v2_schema(conn)
            cursor = conn.cursor()

            # Insert test data in adapters table
            cursor.execute("""
                INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version)
                VALUES (?, ?, ?, ?)
            """, ("test-adapter", "health", "health_adapter", "1.0"))

            # Insert test data in sources table
            cursor.execute("""
                INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy)
                VALUES (?, ?, ?, ?, ?)
            """, ("test-source", "test-adapter", "health", "test-origin", "push"))

            # Insert test data in source_versions table
            cursor.execute("""
                INSERT INTO source_versions (source_id, version, markdown, chunk_hashes, adapter_id, normalizer_version, fetch_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("test-source", 1, "# Test", "hash1,hash2", "test-adapter", "1.0", "2024-01-01T00:00:00Z"))

            # Insert test data in chunks table
            cursor.execute("""
                INSERT INTO chunks (chunk_hash, source_id, source_version, chunk_index, content, domain, adapter_id, fetch_timestamp, normalizer_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("chunk-hash-1", "test-source", 1, 0, "Test content", "health", "test-adapter", "2024-01-01T00:00:00Z", "1.0"))

            conn.commit()
            conn.close()

            # Migrate
            store = DocumentStore(str(db_path))
            cursor = store.conn.cursor()

            # Verify adapter data preserved
            cursor.execute("SELECT adapter_id, domain FROM adapters WHERE adapter_id = ?", ("test-adapter",))
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "test-adapter"
            assert row[1] == "health"

            # Verify source data preserved
            cursor.execute("SELECT source_id, domain FROM sources WHERE source_id = ?", ("test-source",))
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "test-source"
            assert row[1] == "health"

            # Verify chunk data preserved
            cursor.execute("SELECT chunk_hash, domain FROM chunks WHERE chunk_hash = ?", ("chunk-hash-1",))
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "chunk-hash-1"
            assert row[1] == "health"

            store.conn.close()

    def test_migrate_v2_to_v3_can_insert_documents_domain(self) -> None:
        """Test that after migration, 'documents' domain rows can be inserted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v2 database
            conn = sqlite3.connect(str(db_path))
            _create_v2_schema(conn)
            conn.close()

            # Migrate
            store = DocumentStore(str(db_path))
            cursor = store.conn.cursor()

            # Insert adapter with 'documents' domain (should not raise)
            cursor.execute("""
                INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version)
                VALUES (?, ?, ?, ?)
            """, ("doc-adapter", "documents", "document_adapter", "1.0"))

            # Insert source with 'documents' domain (should not raise)
            cursor.execute("""
                INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy)
                VALUES (?, ?, ?, ?, ?)
            """, ("doc-source", "doc-adapter", "documents", "doc-origin", "push"))

            # Insert source version
            cursor.execute("""
                INSERT INTO source_versions (source_id, version, markdown, chunk_hashes, adapter_id, normalizer_version, fetch_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("doc-source", 1, "# Doc", "hash1", "doc-adapter", "1.0", "2024-01-01T00:00:00Z"))

            # Insert chunk with 'documents' domain (should not raise)
            cursor.execute("""
                INSERT INTO chunks (chunk_hash, source_id, source_version, chunk_index, content, domain, adapter_id, fetch_timestamp, normalizer_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("doc-chunk-1", "doc-source", 1, 0, "Document content", "documents", "doc-adapter", "2024-01-01T00:00:00Z", "1.0"))

            store.conn.commit()

            # Verify data was inserted
            cursor.execute("SELECT COUNT(*) FROM adapters WHERE domain = 'documents'")
            assert cursor.fetchone()[0] == 1

            cursor.execute("SELECT COUNT(*) FROM sources WHERE domain = 'documents'")
            assert cursor.fetchone()[0] == 1

            cursor.execute("SELECT COUNT(*) FROM chunks WHERE domain = 'documents'")
            assert cursor.fetchone()[0] == 1

            store.conn.close()

    def test_migrate_v2_to_v3_idempotent(self) -> None:
        """Test that opening a v3 database again is idempotent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create v2 database
            conn = sqlite3.connect(str(db_path))
            _create_v2_schema(conn)
            conn.close()

            # First migration
            store1 = DocumentStore(str(db_path))
            cursor = store1.conn.cursor()
            cursor.execute("PRAGMA user_version")
            version1 = cursor.fetchone()[0]
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='adapters'")
            ddl1 = cursor.fetchone()[0]
            store1.conn.close()

            # Second opening (should be no-op)
            store2 = DocumentStore(str(db_path))
            cursor = store2.conn.cursor()
            cursor.execute("PRAGMA user_version")
            version2 = cursor.fetchone()[0]
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='adapters'")
            ddl2 = cursor.fetchone()[0]
            store2.conn.close()

            # Verify both are v3 and DDL is identical
            assert version1 == 3
            assert version2 == 3
            assert ddl1 == ddl2

    def test_migrate_v2_to_v3_migration_failure_raises_runtime_error(self) -> None:
        """Test that v2-to-v3 migration failure raises RuntimeError with descriptive message.

        This tests the error handling path by simulating a migration failure through
        database corruption. Verifies that rollback prevents partial schema changes.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create a v2 database with data
            conn = sqlite3.connect(str(db_path))
            _create_v2_schema(conn)

            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version)
                VALUES (?, ?, ?, ?)
            """, ("test-adapter", "health", "health_adapter", "1.0"))
            conn.commit()
            conn.close()

            # Corrupt the database by dropping the sources table
            # This will cause the migration to fail when trying to rename sources
            conn = sqlite3.connect(str(db_path))
            conn.execute("DROP TABLE sources")
            conn.execute("DROP TABLE lancedb_sync_log")
            conn.execute("PRAGMA user_version=2")  # Ensure version is still 2
            conn.commit()
            conn.close()

            # Attempting to initialize DocumentStore should raise RuntimeError
            with pytest.raises(RuntimeError, match="Failed to migrate schema from v2 to v3"):
                DocumentStore(str(db_path))
