"""SQLite-backed document store; source of truth for versions, chunks, and lineage."""

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, cast

from context_library.core.identifier_normalizer import normalize_email, normalize_phone
from .models import (
    AdapterConfig,
    Chunk,
    ChunkWithLineageContext,
    Domain,
    ENTITY_LINK_TYPE_PERSON_APPEARANCE,
    EntityLink,
    LineageRecord,
    PollStrategy,
    Sha256Hash,
    SourceInfo,
    SourceVersion,
    VersionDiff,
    _validate_sha256_hex,
)

logger = logging.getLogger(__name__)

# Characters that have special meaning in SQLite GLOB patterns
# and need to be escaped by wrapping in brackets
_GLOB_SPECIAL = frozenset('[]*?')


class DocumentStore:
    """SQLite document store for managing source versions, chunks, and lineage.

    This class serves as the system's source of truth for all ingested content,
    versions, chunks, and lineage records. It manages:
    - Adapter registration and configuration
    - Source registration and tracking
    - Version history (immutable snapshots of source content)
    - Chunk storage and deduplication
    - Lineage records for provenance tracing
    - Sync state with LanceDB vector store
    """


    def __init__(self, db_path: str | Path, check_same_thread: bool = True) -> None:
        """Initialize the document store and set up the SQLite database.

        Connects to SQLite, checks for schema version (running migration if needed),
        executes the schema (which sets WAL mode, synchronous=NORMAL, and foreign_keys),
        and verifies the result.

        Args:
            db_path: Path to SQLite database file. Use ':memory:' for in-memory DB.
            check_same_thread: Deprecated — ignored. Thread safety is now handled via
                per-thread connections (threading.local). Kept for API compatibility.

        Raises:
            RuntimeError: If schema execution or verification fails.
        """
        # Convert to string path (handles both str and Path)
        self._db_path = str(db_path)

        # Per-thread connection storage. SQLite connections must not be shared
        # across threads — even check_same_thread=False only disables the safety
        # check; the underlying C library is not thread-safe for concurrent access
        # on the same connection. Each thread gets its own connection via _local.
        self._local = threading.local()

        # Reentrant write lock. WAL mode serialises writers at the OS level, but
        # Python's `with conn:` transaction context manager is not thread-safe:
        # concurrent callers from different thread-local connections can still
        # interleave DML within the same WAL write slot. The write lock ensures
        # only one thread runs a write transaction at a time.
        self._write_lock = threading.RLock()

        # Initialise the connection for this (main) thread. Schema migration and
        # setup run here; subsequent threads get fresh connections via the property.
        self._local.conn = self._make_connection()

        # Check if this is an existing database that needs migration
        # This must be done BEFORE executing schema.sql which sets version to 4
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA user_version")
        version = cursor.fetchone()[0]

        if version == 1:
            # Migrate from v1 to v2 BEFORE executing new schema
            self._migrate_v1_to_v2()
            # Re-read version after migration to allow chaining to v2→v3
            cursor.execute("PRAGMA user_version")
            version = cursor.fetchone()[0]

        if version == 2:
            # Migrate from v2 to v3 BEFORE executing new schema
            self._migrate_v2_to_v3()
            # Re-read version after migration
            cursor.execute("PRAGMA user_version")
            version = cursor.fetchone()[0]

        if version == 3:
            # Migrate from v3 to v4 BEFORE executing new schema
            self._migrate_v3_to_v4()
            # Re-read version after migration
            cursor.execute("PRAGMA user_version")
            version = cursor.fetchone()[0]

        # Load and execute schema (contains all required PRAGMAs including PRAGMA user_version=4)
        schema_path = Path(__file__).parent / "schema.sql"
        schema_sql = schema_path.read_text()
        self.conn.executescript(schema_sql)

        # Re-apply critical PRAGMAs after executescript
        # (executescript can reset connection state in some SQLite versions)
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

        # Verify foreign keys are enforced
        cursor.execute("PRAGMA foreign_keys")
        foreign_keys_enabled = cursor.fetchone()[0]
        if foreign_keys_enabled != 1:
            raise RuntimeError(
                "Failed to enable foreign key constraints"
            )

        # Verify synchronous mode is NORMAL (value 1)
        cursor.execute("PRAGMA synchronous")
        synchronous_mode = cursor.fetchone()[0]
        if synchronous_mode != 1:
            raise RuntimeError(
                f"Failed to set synchronous=NORMAL (expected 1, got {synchronous_mode})"
            )

        # Verify final schema version
        cursor.execute("PRAGMA user_version")
        final_version = cursor.fetchone()[0]
        if final_version != 4:
            raise RuntimeError(
                f"Schema version mismatch: expected 4, got {final_version}"
            )

    def _make_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection with required pragmas applied."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        # Register custom SQLite functions for identifier normalization
        conn.create_function("normalize_email_sql", 1, self._normalize_email_sql)
        conn.create_function("normalize_phone_sql", 1, self._normalize_phone_sql)

        return conn

    @staticmethod
    def _normalize_email_sql(value: str | None) -> str | None:
        """SQLite custom function for email normalization."""
        if not value:
            return None
        return normalize_email(value)

    @staticmethod
    def _normalize_phone_sql(value: str | None) -> str | None:
        """SQLite custom function for phone normalization."""
        if not value:
            return None
        return normalize_phone(value)

    @property
    def conn(self) -> sqlite3.Connection:
        """Return the SQLite connection for the current thread, creating one if needed."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = self._make_connection()
        return cast(sqlite3.Connection, self._local.conn)

    def _migrate_v1_to_v2(self) -> None:
        """Migrate schema from v1 to v2: add 'health' to domain CHECK constraints.

        SQLite does not support ALTER TABLE ... MODIFY CONSTRAINT, so we must
        use the rename-recreate-copy pattern for each affected table (adapters,
        sources, chunks). All operations are wrapped in a transaction and foreign
        key enforcement is temporarily disabled.

        Raises:
            RuntimeError: If migration fails at any step.
        """
        logger.info("Migrating schema from v1 to v2 (adding health domain support)")

        cursor = self.conn.cursor()

        try:
            # Disable foreign key enforcement temporarily
            cursor.execute("PRAGMA foreign_keys=OFF")

            # Start transaction
            cursor.execute("BEGIN")

            # Migrate adapters table: rename old, create new with health domain, copy data
            cursor.execute("ALTER TABLE adapters RENAME TO _adapters_old")
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
            cursor.execute("INSERT INTO adapters SELECT * FROM _adapters_old")
            cursor.execute("DROP TABLE _adapters_old")

            # Migrate sources table: rename old, create new with health domain, copy data
            cursor.execute("ALTER TABLE sources RENAME TO _sources_old")
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
            cursor.execute("INSERT INTO sources SELECT * FROM _sources_old")
            cursor.execute("DROP TABLE _sources_old")

            # Recreate indices for sources
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sources_adapter ON sources(adapter_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources(domain)")

            # Recreate sources_update_timestamp trigger
            cursor.execute("DROP TRIGGER IF EXISTS sources_update_timestamp")
            cursor.execute("""
                CREATE TRIGGER sources_update_timestamp
                AFTER UPDATE ON sources
                FOR EACH ROW
                WHEN NEW.updated_at = OLD.updated_at
                BEGIN
                    UPDATE sources SET updated_at = CURRENT_TIMESTAMP WHERE source_id = NEW.source_id;
                END
            """)

            # Migrate chunks table: rename old, create new with health domain, copy data
            cursor.execute("ALTER TABLE chunks RENAME TO _chunks_old")
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
            cursor.execute("INSERT INTO chunks SELECT * FROM _chunks_old")
            cursor.execute("DROP TABLE _chunks_old")

            # Recreate indices for chunks
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks(chunk_hash)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_id, source_version)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_domain ON chunks(domain)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_parent ON chunks(parent_chunk_hash)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_retired ON chunks(retired_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_adapter ON chunks(adapter_id)")

            # Recreate adapters_update_timestamp trigger
            cursor.execute("DROP TRIGGER IF EXISTS adapters_update_timestamp")
            cursor.execute("""
                CREATE TRIGGER adapters_update_timestamp
                AFTER UPDATE ON adapters
                FOR EACH ROW
                WHEN NEW.updated_at = OLD.updated_at
                BEGIN
                    UPDATE adapters SET updated_at = CURRENT_TIMESTAMP WHERE adapter_id = NEW.adapter_id;
                END
            """)

            # Update schema version to 2
            cursor.execute("PRAGMA user_version=2")

            # Commit transaction
            self.conn.commit()

            # Re-enable foreign key enforcement
            cursor.execute("PRAGMA foreign_keys=ON")

            logger.info("Successfully migrated schema from v1 to v2")

        except Exception as e:
            try:
                self.conn.rollback()
            except Exception as rollback_error:
                logger.error(f"Failed to rollback migration: {rollback_error}")
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            except Exception as pragma_error:
                logger.error(f"Failed to re-enable foreign keys after migration error: {pragma_error}")
            raise RuntimeError(
                f"Failed to migrate schema from v1 to v2: {e}"
            ) from e

    def _migrate_v2_to_v3(self) -> None:
        """Migrate schema from v2 to v3: add 'documents' to domain CHECK constraints.

        SQLite does not support ALTER TABLE ... MODIFY CONSTRAINT, so we must
        use the rename-recreate-copy pattern for each affected table (adapters,
        sources, chunks). All operations are wrapped in a transaction and foreign
        key enforcement is temporarily disabled.

        Raises:
            RuntimeError: If migration fails at any step.
        """
        logger.info("Migrating schema from v2 to v3 (adding documents domain support)")

        cursor = self.conn.cursor()

        try:
            # Disable foreign key enforcement temporarily
            cursor.execute("PRAGMA foreign_keys=OFF")

            # Start transaction
            cursor.execute("BEGIN")

            # Migrate adapters table: rename old, create new with documents domain, copy data
            cursor.execute("ALTER TABLE adapters RENAME TO _adapters_old")
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
            cursor.execute("INSERT INTO adapters SELECT * FROM _adapters_old")
            cursor.execute("DROP TABLE _adapters_old")

            # Migrate sources table: rename old, create new with documents domain, copy data
            cursor.execute("ALTER TABLE sources RENAME TO _sources_old")
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
            cursor.execute("INSERT INTO sources SELECT * FROM _sources_old")
            cursor.execute("DROP TABLE _sources_old")

            # Recreate indices for sources
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sources_adapter ON sources(adapter_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources(domain)")

            # Recreate sources_update_timestamp trigger
            cursor.execute("DROP TRIGGER IF EXISTS sources_update_timestamp")
            cursor.execute("""
                CREATE TRIGGER sources_update_timestamp
                AFTER UPDATE ON sources
                FOR EACH ROW
                WHEN NEW.updated_at = OLD.updated_at
                BEGIN
                    UPDATE sources SET updated_at = CURRENT_TIMESTAMP WHERE source_id = NEW.source_id;
                END
            """)

            # Migrate source_versions table: rename old, create new with correct foreign keys, copy data
            # This is necessary because the old source_versions has foreign keys pointing to _sources_old and _adapters_old
            cursor.execute("ALTER TABLE source_versions RENAME TO _source_versions_old")
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
            cursor.execute("INSERT INTO source_versions SELECT * FROM _source_versions_old")
            cursor.execute("DROP TABLE _source_versions_old")

            # Create index for source_versions
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_versions_adapter_id ON source_versions(adapter_id)")

            # Migrate chunks table: rename old, create new with documents domain, copy data
            cursor.execute("ALTER TABLE chunks RENAME TO _chunks_old")
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
            cursor.execute("INSERT INTO chunks SELECT * FROM _chunks_old")
            cursor.execute("DROP TABLE _chunks_old")

            # Recreate indices for chunks
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks(chunk_hash)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_id, source_version)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_domain ON chunks(domain)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_parent ON chunks(parent_chunk_hash)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_retired ON chunks(retired_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_adapter ON chunks(adapter_id)")

            # Recreate adapters_update_timestamp trigger
            cursor.execute("DROP TRIGGER IF EXISTS adapters_update_timestamp")
            cursor.execute("""
                CREATE TRIGGER adapters_update_timestamp
                AFTER UPDATE ON adapters
                FOR EACH ROW
                WHEN NEW.updated_at = OLD.updated_at
                BEGIN
                    UPDATE adapters SET updated_at = CURRENT_TIMESTAMP WHERE adapter_id = NEW.adapter_id;
                END
            """)

            # Update schema version to 3
            cursor.execute("PRAGMA user_version=3")

            # Commit transaction using connection object
            self.conn.commit()

            # Re-enable foreign key enforcement
            cursor.execute("PRAGMA foreign_keys=ON")

            logger.info("Successfully migrated schema from v2 to v3")

        except Exception as e:
            # Rollback transaction using connection object, catching any rollback errors
            try:
                self.conn.rollback()
            except Exception as rollback_error:
                logger.error(f"Failed to rollback migration: {rollback_error}")
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            except Exception as pragma_error:
                logger.error(f"Failed to re-enable foreign keys after migration error: {pragma_error}")
            raise RuntimeError(
                f"Failed to migrate schema from v2 to v3: {e}"
            ) from e

    def _migrate_v3_to_v4(self) -> None:
        """Migrate schema from v3 to v4: add 'people' to domain CHECK constraints and create entity_links table.

        SQLite does not support ALTER TABLE ... MODIFY CONSTRAINT, so we must
        use the rename-recreate-copy pattern for each affected table (adapters,
        sources, chunks). All operations are wrapped in a transaction and foreign
        key enforcement is temporarily disabled.

        Raises:
            RuntimeError: If migration fails at any step.
        """
        logger.info("Migrating schema from v3 to v4 (adding people domain support and entity_links table)")

        cursor = self.conn.cursor()

        try:
            # Disable foreign key enforcement temporarily
            cursor.execute("PRAGMA foreign_keys=OFF")

            # Start transaction
            cursor.execute("BEGIN")

            # Migrate adapters table: rename old, create new with people domain, copy data
            cursor.execute("ALTER TABLE adapters RENAME TO _adapters_old")
            cursor.execute("""
                CREATE TABLE adapters (
                    adapter_id          TEXT PRIMARY KEY,
                    domain              TEXT NOT NULL CHECK (domain IN ('messages', 'notes', 'events', 'tasks', 'health', 'documents', 'people')),
                    adapter_type        TEXT NOT NULL,
                    normalizer_version  TEXT NOT NULL,
                    config              TEXT,
                    enabled             BOOLEAN NOT NULL DEFAULT 1,
                    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("INSERT INTO adapters SELECT * FROM _adapters_old")
            cursor.execute("DROP TABLE _adapters_old")

            # Migrate sources table: rename old, create new with people domain, copy data
            cursor.execute("ALTER TABLE sources RENAME TO _sources_old")
            cursor.execute("""
                CREATE TABLE sources (
                    source_id           TEXT PRIMARY KEY,
                    adapter_id          TEXT NOT NULL,
                    domain              TEXT NOT NULL CHECK (domain IN ('messages', 'notes', 'events', 'tasks', 'health', 'documents', 'people')),
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
            cursor.execute("INSERT INTO sources SELECT * FROM _sources_old")
            cursor.execute("DROP TABLE _sources_old")

            # Recreate indices for sources
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sources_adapter ON sources(adapter_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources(domain)")

            # Recreate sources_update_timestamp trigger
            cursor.execute("DROP TRIGGER IF EXISTS sources_update_timestamp")
            cursor.execute("""
                CREATE TRIGGER sources_update_timestamp
                AFTER UPDATE ON sources
                FOR EACH ROW
                WHEN NEW.updated_at = OLD.updated_at
                BEGIN
                    UPDATE sources SET updated_at = CURRENT_TIMESTAMP WHERE source_id = NEW.source_id;
                END
            """)

            # Migrate source_versions table: rename old, create new with correct foreign keys, copy data
            # This is necessary because the old source_versions has foreign keys pointing to _sources_old and _adapters_old
            cursor.execute("ALTER TABLE source_versions RENAME TO _source_versions_old")
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
            cursor.execute("INSERT INTO source_versions SELECT * FROM _source_versions_old")
            cursor.execute("DROP TABLE _source_versions_old")

            # Create index for source_versions
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_versions_adapter_id ON source_versions(adapter_id)")

            # Migrate chunks table: rename old, create new with people domain, copy data
            cursor.execute("ALTER TABLE chunks RENAME TO _chunks_old")
            cursor.execute("""
                CREATE TABLE chunks (
                    chunk_hash          TEXT NOT NULL,
                    source_id           TEXT NOT NULL,
                    source_version      INTEGER NOT NULL,
                    chunk_index         INTEGER NOT NULL,
                    content             TEXT NOT NULL,
                    context_header      TEXT,
                    domain              TEXT NOT NULL CHECK (domain IN ('messages', 'notes', 'events', 'tasks', 'health', 'documents', 'people')),
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
            cursor.execute("INSERT INTO chunks SELECT * FROM _chunks_old")
            cursor.execute("DROP TABLE _chunks_old")

            # Recreate indices for chunks
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks(chunk_hash)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_id, source_version)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_domain ON chunks(domain)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_parent ON chunks(parent_chunk_hash)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_retired ON chunks(retired_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_adapter ON chunks(adapter_id)")

            # Recreate adapters_update_timestamp trigger
            cursor.execute("DROP TRIGGER IF EXISTS adapters_update_timestamp")
            cursor.execute("""
                CREATE TRIGGER adapters_update_timestamp
                AFTER UPDATE ON adapters
                FOR EACH ROW
                WHEN NEW.updated_at = OLD.updated_at
                BEGIN
                    UPDATE adapters SET updated_at = CURRENT_TIMESTAMP WHERE adapter_id = NEW.adapter_id;
                END
            """)

            # Create entity_links table (without FK constraints since chunk_hash can appear in multiple sources/versions)
            cursor.execute("""
                CREATE TABLE entity_links (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_chunk_hash   TEXT NOT NULL,
                    target_chunk_hash   TEXT NOT NULL,
                    link_type           TEXT NOT NULL,
                    confidence          REAL NOT NULL DEFAULT 1.0,
                    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(source_chunk_hash, target_chunk_hash, link_type)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entity_links_source ON entity_links(source_chunk_hash)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entity_links_target ON entity_links(target_chunk_hash)")

            # Update schema version to 4
            cursor.execute("PRAGMA user_version=4")

            # Commit transaction using connection object
            self.conn.commit()

            # Re-enable foreign key enforcement
            cursor.execute("PRAGMA foreign_keys=ON")

            logger.info("Successfully migrated schema from v3 to v4")

        except Exception as e:
            # Rollback transaction using connection object, catching any rollback errors
            try:
                self.conn.rollback()
            except Exception as rollback_error:
                logger.error(f"Failed to rollback migration: {rollback_error}")
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            except Exception as pragma_error:
                logger.error(f"Failed to re-enable foreign keys after migration error: {pragma_error}")
            raise RuntimeError(
                f"Failed to migrate schema from v3 to v4: {e}"
            ) from e

    def register_adapter(self, config: AdapterConfig) -> str:
        """Register an adapter configuration.

        Inserts the adapter config into the adapters table. If the adapter_id
        already exists, returns the existing adapter_id without modifying any
        configuration (idempotent operation as per ADR-003).

        The adapter is identified by adapter_id. On first registration, a new row
        is created with the provided configuration. On subsequent registrations
        with the same adapter_id, the existing row is returned unchanged, preserving
        the original domain, adapter_type, normalizer_version, and config.

        Args:
            config: AdapterConfig with adapter_id, type, domain, and config dict.

        Returns:
            The adapter_id.
        """
        config_json = json.dumps(config.config) if config.config else None

        with self._write_lock, self.conn:
            cursor = self.conn.cursor()
            # Check if adapter already exists
            cursor.execute(
                "SELECT adapter_id FROM adapters WHERE adapter_id = ?",
                (config.adapter_id,),
            )
            existing = cursor.fetchone()

            if existing is None:
                # Insert new adapter
                self.conn.execute(
                    """
                    INSERT INTO adapters
                    (adapter_id, domain, adapter_type, normalizer_version, config)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        config.adapter_id,
                        config.domain.value,
                        config.adapter_type,
                        config.normalizer_version,
                        config_json,
                    ),
                )

        return config.adapter_id

    def register_source(
        self,
        source_id: str,
        adapter_id: str,
        domain: Domain,
        origin_ref: str,
        poll_strategy: PollStrategy = PollStrategy.PULL,
        poll_interval_sec: int | None = None,
        display_name: str | None = None,
    ) -> None:
        """Register a source.

        Inserts the source into the sources table if it doesn't exist, or updates
        all source configuration (adapter_id, domain, poll_strategy, poll_interval_sec)
        if the source is re-registered with different values.

        When a source is re-registered with a different domain, all existing chunks
        for that source are updated to the new domain in SQLite, and sync log entries
        are recorded for all affected chunks so the vector store is updated during
        reconciliation.

        Args:
            source_id: Unique identifier for the source.
            adapter_id: ID of the adapter handling this source. Updated on re-registration.
            domain: Domain classification (messages, notes, events, tasks, health). Updated on re-registration.
            origin_ref: URL, path, or reference to the original source.
            poll_strategy: Strategy for polling this source (push, pull, or webhook).
                          Defaults to PollStrategy.PULL. Updated on re-registration.
            poll_interval_sec: Interval in seconds between polls for PULL strategy.
                              None if not applicable for this strategy. Updated on re-registration.
        """
        with self._write_lock, self.conn:
            cursor = self.conn.cursor()
            # Check if source already exists and get its current domain
            cursor.execute(
                "SELECT source_id, domain FROM sources WHERE source_id = ?",
                (source_id,),
            )
            existing = cursor.fetchone()

            if existing is None:
                # Insert new source
                self.conn.execute(
                    """
                    INSERT INTO sources
                    (source_id, adapter_id, domain, origin_ref, display_name, poll_strategy, poll_interval_sec)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (source_id, adapter_id, domain.value, origin_ref, display_name, poll_strategy.value, poll_interval_sec),
                )
            else:
                # Check if domain is changing
                old_domain = existing["domain"]
                if old_domain != domain.value:
                    # Get all chunk hashes affected by the domain change
                    cursor.execute(
                        "SELECT DISTINCT chunk_hash FROM chunks WHERE source_id = ?",
                        (source_id,),
                    )
                    affected_hashes = [row["chunk_hash"] for row in cursor.fetchall()]

                    # Update all chunks for this source to the new domain
                    self.conn.execute(
                        "UPDATE chunks SET domain = ? WHERE source_id = ?",
                        (domain.value, source_id),
                    )

                    # Record sync log entries to trigger vector store reconciliation
                    if affected_hashes:
                        self.conn.executemany(
                            """
                            INSERT OR REPLACE INTO lancedb_sync_log (chunk_hash, operation)
                            VALUES (?, 'insert')
                            """,
                            [(h,) for h in affected_hashes],
                        )

                # Update all source configuration on re-registration
                self.conn.execute(
                    """
                    UPDATE sources
                    SET adapter_id = ?, domain = ?, poll_strategy = ?, poll_interval_sec = ?
                    WHERE source_id = ?
                    """,
                    (adapter_id, domain.value, poll_strategy.value, poll_interval_sec, source_id),
                )

    def update_display_name(self, source_id: str, display_name: str) -> None:
        """Update the display_name for a source if it differs from the stored value."""
        with self._write_lock, self.conn:
            self.conn.execute(
                "UPDATE sources SET display_name = ? WHERE source_id = ? AND (display_name IS NULL OR display_name != ?)",
                (display_name, source_id, display_name),
            )

    def create_source_version(
        self,
        source_id: str,
        version: int,
        markdown: str,
        chunk_hashes: list[Sha256Hash],
        adapter_id: str,
        normalizer_version: str,
        fetch_timestamp: str,
    ) -> int:
        """Create a new source version.

        Inserts a source_version record and updates the source's current_version.

        Args:
            source_id: ID of the source.
            version: Version number (monotonically increasing per source).
            markdown: Full normalized content as markdown.
            chunk_hashes: List of validated SHA-256 chunk hashes in this version.
            adapter_id: ID of the adapter that fetched this version.
            normalizer_version: Version of the normalizer used.
            fetch_timestamp: ISO 8601 timestamp when content was fetched.

        Returns:
            The SQLite rowid of the newly created source_version row.

        Raises:
            ValueError: If any chunk_hash is not a valid SHA-256 hex string.
            sqlite3.IntegrityError: If source_id or adapter_id don't exist.
        """
        # Validate all hashes at write time to prevent malformed data in database
        for chunk_hash in chunk_hashes:
            _validate_sha256_hex(chunk_hash)

        chunk_hashes_json = json.dumps(chunk_hashes)

        with self._write_lock, self.conn:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO source_versions
                (source_id, version, markdown, chunk_hashes, adapter_id,
                 normalizer_version, fetch_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    version,
                    markdown,
                    chunk_hashes_json,
                    adapter_id,
                    normalizer_version,
                    fetch_timestamp,
                ),
            )

            # Capture the rowid of the inserted row
            source_version_id = cursor.lastrowid
            if source_version_id is None:
                raise RuntimeError(
                    "Failed to insert source_version: cursor.lastrowid is None"
                )

            # Update sources.current_version
            self.conn.execute(
                """
                UPDATE sources SET current_version = ? WHERE source_id = ?
                """,
                (version, source_id),
            )

            return source_version_id

    def create_next_source_version(
        self,
        source_id: str,
        markdown: str,
        chunk_hashes: list[Sha256Hash],
        adapter_id: str,
        normalizer_version: str,
        fetch_timestamp: str,
    ) -> tuple[int, int]:
        """Create a new source version with atomically assigned version number.

        Unlike create_source_version, the version number is computed inside the
        write lock as MAX(version) + 1 for this source. This prevents UNIQUE
        constraint violations when concurrent requests race to create the next
        version for the same source.

        Args:
            source_id: ID of the source.
            markdown: Full normalized content as markdown.
            chunk_hashes: List of validated SHA-256 chunk hashes in this version.
            adapter_id: ID of the adapter that fetched this version.
            normalizer_version: Version of the normalizer used.
            fetch_timestamp: ISO 8601 timestamp when content was fetched.

        Returns:
            Tuple of (rowid, version) for the newly created source_version row.

        Raises:
            ValueError: If any chunk_hash is not a valid SHA-256 hex string.
            sqlite3.IntegrityError: If source_id or adapter_id don't exist.
        """
        for chunk_hash in chunk_hashes:
            _validate_sha256_hex(chunk_hash)

        chunk_hashes_json = json.dumps(chunk_hashes)

        with self._write_lock, self.conn:
            cursor = self.conn.cursor()

            # Compute the next version atomically inside the lock
            cursor.execute(
                "SELECT COALESCE(MAX(version), 0) FROM source_versions WHERE source_id = ?",
                (source_id,),
            )
            version = cursor.fetchone()[0] + 1

            cursor.execute(
                """
                INSERT INTO source_versions
                (source_id, version, markdown, chunk_hashes, adapter_id,
                 normalizer_version, fetch_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    version,
                    markdown,
                    chunk_hashes_json,
                    adapter_id,
                    normalizer_version,
                    fetch_timestamp,
                ),
            )

            source_version_id = cursor.lastrowid
            if source_version_id is None:
                raise RuntimeError(
                    "Failed to insert source_version: cursor.lastrowid is None"
                )

            self.conn.execute(
                "UPDATE sources SET current_version = ? WHERE source_id = ?",
                (version, source_id),
            )

            return source_version_id, version

    def write_chunks(
        self,
        chunks: list[Chunk],
        lineage_records: list[LineageRecord],
    ) -> None:
        """Write chunks and lineage records to storage.

        Inserts chunks into the database. Each chunk is stored once per (source_id, source_version)
        combination to support:
        - Unchanged chunks appearing in multiple versions of the same source
        - The same content (identical chunk_hash) appearing in different sources

        Chunks are linked to their sources and versions via lineage records.

        Cross-references are persisted in domain_metadata JSON under the reserved "_system_cross_refs" key.
        This key is reserved to prevent collisions with domain-provided metadata. Domain implementations
        must not use "_system_cross_refs" in their own domain_metadata dictionaries.

        Idempotent behavior: Uses INSERT OR IGNORE with UNIQUE (source_id, source_version, chunk_index)
        constraint to atomically skip duplicates. If a chunk at a given position already exists,
        the insertion is silently ignored without raising an error. This provides thread-safe
        duplicate detection without TOCTOU race conditions and allows calling write_chunks
        multiple times with the same data without errors.

        Args:
            chunks: List of Chunk objects to insert.
            lineage_records: List of LineageRecord objects with provenance info.

        Raises:
            ValueError: If a chunk has no matching lineage record, or if cross-source
                        dedup is detected without proper matching context.
            sqlite3.IntegrityError: If foreign key or CHECK constraint violations occur.
        """
        # Create a map of chunk_hash to list of lineage records.
        # Preserves all records to detect cross-source chunks and prevent silent overwrites.
        lineage_map: dict[str, list[LineageRecord]] = {}
        for lr in lineage_records:
            if lr.chunk_hash not in lineage_map:
                lineage_map[lr.chunk_hash] = []
            lineage_map[lr.chunk_hash].append(lr)

        # Validate that all chunks have matching lineage
        for chunk in chunks:
            if chunk.chunk_hash not in lineage_map:
                raise ValueError(
                    f"No lineage record found for chunk_hash={chunk.chunk_hash}"
                )

        # Generate timestamp once for the entire batch
        batch_timestamp = datetime.now(timezone.utc).isoformat()

        with self._write_lock, self.conn:
            for chunk in chunks:
                # Merge domain_metadata with cross_refs
                # cross_refs are stored in domain_metadata JSON under the reserved "_system_cross_refs" key
                # (reserved to prevent collisions with domain-provided metadata)
                merged_metadata = dict(chunk.domain_metadata) if chunk.domain_metadata else {}
                if chunk.cross_refs:
                    merged_metadata["_system_cross_refs"] = list(chunk.cross_refs)

                domain_metadata_json = (
                    json.dumps(merged_metadata)
                    if merged_metadata
                    else None
                )

                # Get lineage records for this chunk hash
                lineage_records_for_chunk = lineage_map[chunk.chunk_hash]

                # If multiple lineage records exist for this chunk hash, all should have
                # the same source_id and source_version_id (enforced by lineage generation).
                # Validate this assumption and use the first record.
                if len(lineage_records_for_chunk) > 1:
                    first_lr = lineage_records_for_chunk[0]
                    for lr in lineage_records_for_chunk[1:]:
                        if (lr.source_id != first_lr.source_id or
                            lr.source_version_id != first_lr.source_version_id):
                            raise ValueError(
                                f"Cross-source dedup detected for chunk_hash={chunk.chunk_hash}: "
                                f"multiple lineage records with different source contexts. "
                                f"Expected all records for a chunk in a single write_chunks call to be from "
                                f"the same source ({first_lr.source_id}/{first_lr.source_version_id}), "
                                f"but found ({lr.source_id}/{lr.source_version_id}). "
                                f"Cannot safely select lineage without explicit source context."
                            )

                lineage = lineage_records_for_chunk[0]

                # Use INSERT OR IGNORE to atomically skip duplicates without TOCTOU race.
                # Duplicate detection is based on UNIQUE constraint on (source_id, source_version, chunk_index).
                # This avoids the race condition between SELECT check and INSERT.
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO chunks
                    (chunk_hash, source_id, source_version, chunk_index, content,
                     context_header, domain, adapter_id, fetch_timestamp,
                     normalizer_version, embedding_model_id, domain_metadata, chunk_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.chunk_hash,
                        lineage.source_id,
                        lineage.source_version_id,
                        chunk.chunk_index,
                        chunk.content,
                        chunk.context_header,
                        lineage.domain.value,
                        lineage.adapter_id,
                        batch_timestamp,
                        lineage.normalizer_version,
                        lineage.embedding_model_id,
                        domain_metadata_json,
                        chunk.chunk_type,
                    ),
                )

    def retire_chunks(self, chunk_hashes: set[Sha256Hash], source_id: str, source_version: int) -> None:
        """Mark chunks as retired for a specific source and version.

        Updates the retired_at timestamp for matching chunks, indicating
        they are no longer active in the specified version.

        With composite PK (chunk_hash, source_id, source_version), the same chunk_hash
        can exist across multiple sources/versions. This method only retires the copy
        for the specified source and version, preventing accidental over-retirement of
        identical content in other sources.

        Args:
            chunk_hashes: Set of validated SHA-256 chunk hashes to retire.
            source_id: Source ID to scope retirement to (prevents cross-source retirement).
            source_version: Source version to scope retirement to.

        Raises:
            ValueError: If any chunk_hash is not a valid SHA-256 hex string.
            RuntimeError: If any chunk hash does not exist for the given source/version.
        """
        # Validate all hashes at write time to prevent malformed data in database
        for chunk_hash in chunk_hashes:
            _validate_sha256_hex(chunk_hash)

        now = datetime.now(timezone.utc).isoformat()

        with self._write_lock, self.conn:
            cursor = self.conn.cursor()
            for chunk_hash in chunk_hashes:
                cursor.execute(
                    "UPDATE chunks SET retired_at = ? WHERE chunk_hash = ? AND source_id = ? AND source_version = ?",
                    (now, chunk_hash, source_id, source_version),
                )
                if cursor.rowcount == 0:
                    raise RuntimeError(
                        f"Chunk '{chunk_hash}' does not exist for source '{source_id}' version {source_version}"
                    )

    def write_sync_log(self, chunk_hashes: list[Sha256Hash]) -> None:
        """Record insert operations for chunks in the sync log.

        Inserts entries into lancedb_sync_log before LanceDB write attempts. The sync log
        tracks sync operations and provides a recovery trail: if a LanceDB write fails,
        the sync log can be queried to identify which chunks need to be retried.

        Uses INSERT OR REPLACE with UNIQUE (chunk_hash, operation), so multiple inserts
        of the same chunk_hash overwrite the previous entry (last-write-wins). The synced_at
        timestamp reflects when the operation was last recorded.

        Args:
            chunk_hashes: List of validated SHA-256 chunk hashes marked for vector database insertion.

        Raises:
            ValueError: If any chunk_hash is not a valid SHA-256 hex string.
        """
        # Validate all hashes at write time to prevent malformed data in database
        for chunk_hash in chunk_hashes:
            _validate_sha256_hex(chunk_hash)

        with self._write_lock, self.conn:
            self.conn.executemany(
                """
                INSERT OR REPLACE INTO lancedb_sync_log (chunk_hash, operation)
                VALUES (?, 'insert')
                """,
                [(h,) for h in chunk_hashes],
            )

    def delete_sync_log(self, chunk_hashes: list[Sha256Hash]) -> None:
        """Record delete operations for chunks in the sync log.

        Inserts entries into lancedb_sync_log before LanceDB delete attempts. The sync log
        tracks sync operations and provides a recovery trail: if a LanceDB delete fails,
        the sync log can be queried to identify which chunks still need to be removed.

        Uses INSERT OR REPLACE with UNIQUE (chunk_hash, operation), so multiple deletes
        of the same chunk_hash overwrite the previous entry (last-write-wins). The synced_at
        timestamp reflects when the operation was last logged.

        Args:
            chunk_hashes: List of validated SHA-256 chunk hashes marked for deletion from LanceDB.

        Raises:
            ValueError: If any chunk_hash is not a valid SHA-256 hex string.
        """
        # Validate all hashes at write time to prevent malformed data in database
        for chunk_hash in chunk_hashes:
            _validate_sha256_hex(chunk_hash)

        with self._write_lock, self.conn:
            self.conn.executemany(
                """
                INSERT OR REPLACE INTO lancedb_sync_log (chunk_hash, operation)
                VALUES (?, 'delete')
                """,
                [(h,) for h in chunk_hashes],
            )


    def clear_sync_log(self, chunk_hashes: list[Sha256Hash]) -> None:
        """Remove entries from the sync log after successful vector store operations.

        Called after vectors have been successfully written to or deleted from the
        vector store, so the sync log only retains entries for operations that have
        not yet been applied (i.e. need recovery on next startup).
        """
        with self._write_lock, self.conn:
            self.conn.executemany(
                "DELETE FROM lancedb_sync_log WHERE chunk_hash = ?",
                [(h,) for h in chunk_hashes],
            )

    def get_latest_version(self, source_id: str) -> Optional[SourceVersion]:
        """Get the latest version of a source.

        Args:
            source_id: ID of the source.

        Returns:
            SourceVersion object for the latest version, or None if source has
            no versions.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT source_id, version, markdown, chunk_hashes, adapter_id,
                   normalizer_version, fetch_timestamp
            FROM source_versions
            WHERE source_id = ?
            ORDER BY version DESC
            LIMIT 1
            """,
            (source_id,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        chunk_hashes = json.loads(row["chunk_hashes"])

        return SourceVersion(
            source_id=row["source_id"],
            version=row["version"],
            markdown=row["markdown"],
            chunk_hashes=chunk_hashes,
            adapter_id=row["adapter_id"],
            normalizer_version=row["normalizer_version"],
            fetch_timestamp=row["fetch_timestamp"],
        )

    def get_version_history(self, source_id: str) -> list[SourceVersion]:
        """Get all versions of a source, ordered by version ascending.

        Args:
            source_id: ID of the source.

        Returns:
            List of SourceVersion objects, ordered by version ascending.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT source_id, version, markdown, chunk_hashes, adapter_id,
                   normalizer_version, fetch_timestamp
            FROM source_versions
            WHERE source_id = ?
            ORDER BY version ASC
            """,
            (source_id,),
        )
        rows = cursor.fetchall()

        versions = []
        for row in rows:
            chunk_hashes = json.loads(row["chunk_hashes"])
            versions.append(
                SourceVersion(
                    source_id=row["source_id"],
                    version=row["version"],
                    markdown=row["markdown"],
                    chunk_hashes=chunk_hashes,
                    adapter_id=row["adapter_id"],
                    normalizer_version=row["normalizer_version"],
                    fetch_timestamp=row["fetch_timestamp"],
                )
            )

        return versions

    def get_version_diff(
        self,
        source_id: str,
        from_version: int,
        to_version: int,
    ) -> VersionDiff:
        """Get the difference between two source versions based on chunk hashes.

        Computes set-based diff of chunk hashes between two versions, returning
        added, removed, and unchanged hashes. Enables efficient re-embedding by
        identifying only new/modified chunks.

        Args:
            source_id: ID of the source.
            from_version: Starting version number.
            to_version: Ending version number.

        Returns:
            VersionDiff with added_hashes, removed_hashes, and unchanged_hashes
            as frozensets.

        Raises:
            ValueError: If source_id does not exist, either version does not exist,
                or from_version and to_version are the same.
        """
        if from_version == to_version:
            raise ValueError(
                f"from_version and to_version must be different, got both as {from_version}"
            )

        cursor = self.conn.cursor()
        # First check if source exists
        cursor.execute(
            "SELECT source_id FROM sources WHERE source_id = ?",
            (source_id,),
        )
        if cursor.fetchone() is None:
            raise ValueError(f"Source '{source_id}' does not exist")

        # Then fetch both versions
        cursor.execute(
            """
            SELECT version, chunk_hashes
            FROM source_versions
            WHERE source_id = ? AND version IN (?, ?)
            """,
            (source_id, from_version, to_version),
        )
        rows = cursor.fetchall()

        if len(rows) < 2:
            # Determine which versions are missing
            found_versions = {row["version"] for row in rows}
            missing_versions = []
            if from_version not in found_versions:
                missing_versions.append(from_version)
            if to_version not in found_versions:
                missing_versions.append(to_version)

            missing_str = ", ".join(str(v) for v in missing_versions)
            raise ValueError(
                f"Source '{source_id}' does not have version(s): {missing_str}"
            )

        # Parse the two versions
        version_map = {}
        for row in rows:
            version_map[row["version"]] = json.loads(row["chunk_hashes"])

        from_hashes = version_map[from_version]
        to_hashes = version_map[to_version]

        # Compute set operations
        from_set = set(from_hashes)
        to_set = set(to_hashes)

        added = frozenset(to_set - from_set)
        removed = frozenset(from_set - to_set)
        unchanged = frozenset(from_set & to_set)

        # Fetch actual chunk objects for added and removed hashes
        # Log warnings for missing chunks (possible data integrity issues)
        # Pass source_id to correctly scope lookups in cross-source dedup scenarios
        added_chunks_list = []
        missing_added_hashes = []
        for chunk_hash in added:
            chunk = self.get_chunk_by_hash(chunk_hash, source_id)
            if chunk is not None:
                added_chunks_list.append(chunk)
            else:
                missing_added_hashes.append(chunk_hash)

        if missing_added_hashes:
            logger.warning(
                f"Source '{source_id}': get_version_diff could not retrieve {len(missing_added_hashes)} "
                f"added chunk(s) by hash (possible data integrity issue): {missing_added_hashes}"
            )
        added_chunks = tuple(added_chunks_list)

        removed_chunks_list = []
        missing_removed_hashes = []
        for chunk_hash in removed:
            # For removed chunks, query including retired chunks since they're typically
            # retired by retire_chunks() when removed from a version
            chunk = self._get_chunk_by_hash_including_retired(chunk_hash, source_id)
            if chunk is not None:
                removed_chunks_list.append(chunk)
            else:
                missing_removed_hashes.append(chunk_hash)

        if missing_removed_hashes:
            logger.warning(
                f"Source '{source_id}': get_version_diff could not retrieve {len(missing_removed_hashes)} "
                f"removed chunk(s) by hash (possible data integrity issue): {missing_removed_hashes}"
            )
        removed_chunks = tuple(removed_chunks_list)

        return VersionDiff(
            source_id=source_id,
            from_version=from_version,
            to_version=to_version,
            added_hashes=added,
            removed_hashes=removed,
            unchanged_hashes=unchanged,
            added_chunks=added_chunks,
            removed_chunks=removed_chunks,
        )

    def _build_chunk_from_row(self, row: sqlite3.Row) -> Chunk:
        """Build a Chunk object from a database row, extracting cross_refs from domain_metadata.

        Deserializes domain_metadata JSON, extracts and removes the reserved "_system_cross_refs"
        key (cross-reference hashes), and reconstructs the Chunk with both metadata and cross_refs.
        If domain_metadata becomes empty after cross_refs extraction, it is set to None.

        Args:
            row: Database row with chunk_hash, content, context_header, chunk_index, chunk_type,
                 and domain_metadata columns.

        Returns:
            Chunk object with cross_refs tuple and cleaned domain_metadata dict.

        Raises:
            ValueError: If domain_metadata JSON is malformed or _system_cross_refs is not iterable.
        """
        chunk_hash = row["chunk_hash"]
        domain_metadata = None

        if row["domain_metadata"]:
            try:
                domain_metadata = json.loads(row["domain_metadata"])
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Chunk '{chunk_hash}': domain_metadata contains malformed JSON: {e}"
                ) from e

        # Extract cross_refs from domain_metadata using reserved "_system_cross_refs" key
        cross_refs = ()
        if domain_metadata and "_system_cross_refs" in domain_metadata:
            cross_refs_value = domain_metadata.pop("_system_cross_refs")
            try:
                cross_refs = tuple(cross_refs_value)
            except TypeError as e:
                raise ValueError(
                    f"Chunk '{chunk_hash}': _system_cross_refs must be iterable, got {type(cross_refs_value).__name__}"
                ) from e
            # Remove from domain_metadata if it's now empty
            if not domain_metadata:
                domain_metadata = None

        return Chunk(
            chunk_hash=chunk_hash,
            content=row["content"],
            context_header=row["context_header"],
            chunk_index=row["chunk_index"],
            chunk_type=row["chunk_type"],
            domain_metadata=domain_metadata,
            cross_refs=cross_refs,
        )

    def get_chunk_version_chain(self, chunk_hash: str, source_id: str) -> list[Chunk]:
        """Get the recursive ancestry chain of a chunk via parent_chunk_hash.

        Walks backward through chunk history using parent_chunk_hash references,
        returning all ancestors of the chunk (including the chunk itself), ordered
        by created_at ascending (oldest ancestor first).

        Uses a recursive CTE for efficient ancestry traversal. An empty list is
        returned if the chunk does not exist. A single-element list is returned
        if the chunk has no parent (is the oldest version).

        The traversal includes an explicit depth limit (1000) for safety. This prevents
        infinite traversal in the presence of circular parent_chunk_hash references. Uses
        UNION to deduplicate chunks, ensuring each chunk appears only once even if
        circular references exist.

        Only non-retired chunks (retired_at IS NULL) are included in the chain.
        The CTE is scoped by source_id to correctly handle cross-source chunks
        with identical hashes.

        Args:
            chunk_hash: SHA-256 hash of the chunk to trace.
            source_id: ID of the source to scope the ancestry chain.

        Returns:
            List of Chunk objects ordered by created_at ascending (oldest first).
            Empty list if chunk_hash does not exist in the specified source.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            WITH RECURSIVE chain AS (
                SELECT chunk_hash, source_id, content, context_header, chunk_index, chunk_type,
                       domain_metadata, created_at, parent_chunk_hash, 1 AS depth
                FROM chunks
                WHERE chunk_hash = ? AND source_id = ? AND retired_at IS NULL
                UNION
                SELECT c.chunk_hash, c.source_id, c.content, c.context_header, c.chunk_index, c.chunk_type,
                       c.domain_metadata, c.created_at, c.parent_chunk_hash, ch.depth + 1
                FROM chunks c
                JOIN chain ch ON c.chunk_hash = ch.parent_chunk_hash AND c.source_id = ch.source_id
                WHERE ch.depth < 1000 AND c.retired_at IS NULL
            )
            SELECT chunk_hash, content, context_header, chunk_index, chunk_type,
                   domain_metadata
            FROM chain
            ORDER BY created_at ASC
            """,
            (chunk_hash, source_id),
        )
        rows = cursor.fetchall()
        return [self._build_chunk_from_row(row) for row in rows]

    def get_chunks_by_source(
        self,
        source_id: str,
        version: Optional[int] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> tuple[list[Chunk], int]:
        """Get active chunks for a source with optional pagination.

        Returns chunks for the specified version, or the latest version
        if no version is specified. Only returns non-retired chunks.

        Args:
            source_id: ID of the source.
            version: Specific version number, or None for latest.
            limit: Maximum number of chunks to return, or None for all.
            offset: Number of chunks to skip (default 0).

        Returns:
            Tuple of (list of Chunk objects, total count of matching chunks)
        """
        if version is None:
            # Get latest version
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT current_version FROM sources WHERE source_id = ?",
                (source_id,),
            )
            row = cursor.fetchone()
            if not row:
                return [], 0
            version = row["current_version"]

        cursor = self.conn.cursor()
        # Get total count
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM chunks
            WHERE source_id = ? AND source_version = ? AND retired_at IS NULL
            """,
            (source_id, version),
        )
        total = cursor.fetchone()["count"]

        # Get paginated results
        query = """
            SELECT chunk_hash, chunk_index, content, context_header, chunk_type,
                   domain_metadata
            FROM chunks
            WHERE source_id = ? AND source_version = ? AND retired_at IS NULL
            ORDER BY chunk_index ASC
        """
        params: list = [source_id, version]

        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [self._build_chunk_from_row(row) for row in rows], total

    def get_chunk_by_hash(self, chunk_hash: str, source_id: Optional[str] = None) -> Optional[Chunk]:
        """Get a chunk by its hash.

        Only returns non-retired chunks. Retired chunks are not returned.

        When source_id is not provided and the same chunk_hash exists across multiple sources,
        returns the earliest-created instance (deterministic behavior). Callers should pass
        source_id when they need a specific source's version of the chunk.

        Args:
            chunk_hash: SHA-256 hash of the chunk.
            source_id: Optional source ID to scope the lookup. If provided, returns the chunk
                       from this specific source. If None and the chunk appears in multiple sources,
                       returns the earliest-created instance.

        Returns:
            Chunk object, or None if not found or if the chunk is retired.
        """
        cursor = self.conn.cursor()
        if source_id is not None:
            cursor.execute(
                """
                SELECT chunk_hash, chunk_index, content, context_header, chunk_type,
                       domain_metadata
                FROM chunks
                WHERE chunk_hash = ? AND source_id = ? AND retired_at IS NULL
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (chunk_hash, source_id),
            )
        else:
            cursor.execute(
                """
                SELECT chunk_hash, chunk_index, content, context_header, chunk_type,
                       domain_metadata
                FROM chunks
                WHERE chunk_hash = ? AND retired_at IS NULL
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (chunk_hash,),
            )
        row = cursor.fetchone()
        return self._build_chunk_from_row(row) if row else None

    def _get_chunk_by_hash_including_retired(self, chunk_hash: str, source_id: str) -> Optional[Chunk]:
        """Get a chunk by its hash, including retired chunks.

        Internal helper for get_version_diff to retrieve removed chunks that may have been
        retired between versions. Unlike get_chunk_by_hash, this method does NOT filter out
        retired chunks, since removed chunks are typically retired by retire_chunks().

        Args:
            chunk_hash: SHA-256 hash of the chunk.
            source_id: Source ID to scope the lookup.

        Returns:
            Chunk object (including retired chunks), or None if not found.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT chunk_hash, chunk_index, content, context_header, chunk_type,
                   domain_metadata
            FROM chunks
            WHERE chunk_hash = ? AND source_id = ?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (chunk_hash, source_id),
        )
        row = cursor.fetchone()
        return self._build_chunk_from_row(row) if row else None

    def is_chunk_retired(self, chunk_hash: str) -> bool:
        """Check if a chunk is retired (exists but marked as retired).

        Distinguishes between a truly missing chunk (never existed) and a retired chunk
        (existed but was removed from a source version). This is important for diagnosing
        desynchronization between SQLite and LanceDB: a chunk existing in LanceDB but
        retired in SQLite is normal pipeline behavior (lazy cleanup), not an inconsistency.

        Args:
            chunk_hash: SHA-256 hash of the chunk.

        Returns:
            True if the chunk exists but is marked as retired (retired_at IS NOT NULL).
            False if the chunk doesn't exist or is not retired.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT retired_at
            FROM chunks
            WHERE chunk_hash = ?
            LIMIT 1
            """,
            (chunk_hash,),
        )
        row = cursor.fetchone()

        if not row:
            return False

        return row["retired_at"] is not None

    def get_lineage(self, chunk_hash: str, source_id: Optional[str] = None) -> Optional[LineageRecord]:
        """Get the lineage record for a chunk.

        Retrieves the full provenance information for a chunk, including the
        embedding model ID that was used when the chunk was vectorized.

        When source_id is not provided and the same chunk_hash exists across multiple sources,
        returns the earliest-created instance (deterministic behavior). Callers should pass
        source_id when they need the lineage from a specific source.

        Args:
            chunk_hash: SHA-256 hash of the chunk.
            source_id: Optional source ID to scope the lookup. If provided, returns the lineage
                       for this specific source. Important for cross-source dedup where the same
                       hash can appear in multiple sources—callers should pass source_id to get
                       the correct record. If None and the chunk appears in multiple sources,
                       returns the earliest-created instance.

        Returns:
            LineageRecord with complete provenance information, or None if not found.
        """
        cursor = self.conn.cursor()
        if source_id is not None:
            cursor.execute(
                """
                SELECT chunk_hash, source_id, source_version, adapter_id, domain,
                       normalizer_version, embedding_model_id
                FROM chunks
                WHERE chunk_hash = ? AND source_id = ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (chunk_hash, source_id),
            )
        else:
            cursor.execute(
                """
                SELECT chunk_hash, source_id, source_version, adapter_id, domain,
                       normalizer_version, embedding_model_id
                FROM chunks
                WHERE chunk_hash = ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (chunk_hash,),
            )
        row = cursor.fetchone()

        if not row:
            return None

        return LineageRecord(
            chunk_hash=row["chunk_hash"],
            source_id=row["source_id"],
            source_version_id=row["source_version"],
            adapter_id=row["adapter_id"],
            domain=Domain(row["domain"]),
            normalizer_version=row["normalizer_version"],
            embedding_model_id=row["embedding_model_id"],
        )

    def get_adapter(self, adapter_id: str) -> Optional[AdapterConfig]:
        """Get an adapter configuration by ID.

        Args:
            adapter_id: ID of the adapter.

        Returns:
            AdapterConfig object, or None if not found.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT adapter_id, adapter_type, domain, normalizer_version, config
            FROM adapters
            WHERE adapter_id = ?
            """,
            (adapter_id,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        config_dict = json.loads(row["config"]) if row["config"] else None

        return AdapterConfig(
            adapter_id=row["adapter_id"],
            adapter_type=row["adapter_type"],
            domain=Domain(row["domain"]),
            normalizer_version=row["normalizer_version"],
            config=config_dict,
        )

    def update_last_fetched_at(self, source_id: str) -> None:
        """Update the last_fetched_at timestamp for a source.

        Called when a source is re-fetched but has not changed, to track
        that we have verified its current state.

        Args:
            source_id: The source to update.

        Raises:
            RuntimeError: If the source_id does not exist.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._write_lock, self.conn:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE sources SET last_fetched_at = ? WHERE source_id = ?",
                (now, source_id),
            )
            if cursor.rowcount == 0:
                raise RuntimeError(
                    f"Source '{source_id}' does not exist"
                )

    def get_sources_due_for_poll(self) -> list[dict]:
        """Get all sources due for polling.

        Queries sources where poll_strategy = 'pull' and either:
        - last_fetched_at IS NULL (never fetched), or
        - last_fetched_at + poll_interval_sec < now (interval has passed)

        Sources with poll_interval_sec IS NULL are excluded (no interval configured).

        Returns:
            List of dicts with keys: source_id, adapter_id, origin_ref, poll_interval_sec,
                                     last_fetched_at
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT source_id, adapter_id, origin_ref, poll_interval_sec, last_fetched_at
            FROM sources
            WHERE poll_strategy = 'pull'
              AND poll_interval_sec IS NOT NULL
              AND (
                last_fetched_at IS NULL
                OR datetime(last_fetched_at, '+' || poll_interval_sec || ' seconds') < datetime('now')
              )
            """
        )
        rows = cursor.fetchall()

        result = []
        for row in rows:
            result.append({
                "source_id": row["source_id"],
                "adapter_id": row["adapter_id"],
                "origin_ref": row["origin_ref"],
                "poll_interval_sec": row["poll_interval_sec"],
                "last_fetched_at": row["last_fetched_at"],
            })

        return result

    def get_chunks_pending_sync(self) -> list[dict]:
        """Get all chunks with 'insert' operations in the sync log.

        Queries the sync log for all chunks with 'insert' operations recorded. The sync log
        uses INSERT OR REPLACE with a UNIQUE (chunk_hash, operation) constraint, so repeated
        inserts of the same chunk overwrite the previous insert entry (last-write-wins within
        each operation type). A chunk_hash may have both an 'insert' and 'delete' row
        simultaneously. Use this method to rebuild LanceDB from SQLite if an insert operation
        failed.

        With composite PK (chunk_hash, source_id, source_version), the same chunk_hash can
        exist in multiple rows (different sources/versions). This query GROUPs BY chunk_hash
        to consolidate and prevent duplicate sync attempts for identical content across
        different sources.

        Returns:
            List of dicts with keys: chunk_hash, content, domain, source_id,
                                     source_version, created_at
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT c.chunk_hash, c.content, c.domain, c.source_id,
                   c.source_version, c.fetch_timestamp as created_at
            FROM chunks c
            INNER JOIN lancedb_sync_log l ON c.chunk_hash = l.chunk_hash
            WHERE l.operation = 'insert'
            GROUP BY c.chunk_hash
            ORDER BY l.synced_at ASC
            """
        )
        rows = cursor.fetchall()

        result = []
        for row in rows:
            result.append({
                "chunk_hash": row["chunk_hash"],
                "content": row["content"],
                "domain": row["domain"],
                "source_id": row["source_id"],
                "source_version": row["source_version"],
                "created_at": row["created_at"],
            })

        return result

    def get_chunks_pending_deletion(self) -> list[str]:
        """Get all chunk hashes with 'delete' operations in the sync log.

        Queries the sync log for all chunks with 'delete' operations recorded. The sync log
        uses INSERT OR REPLACE with a UNIQUE (chunk_hash, operation) constraint, so repeated
        deletes of the same chunk overwrite the previous delete entry (last-write-wins within
        each operation type). A chunk_hash may have both an 'insert' and 'delete' row
        simultaneously. Use this method to complete LanceDB deletion if a delete operation
        failed.

        Returns:
            List of chunk hashes to delete from LanceDB
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT chunk_hash
            FROM lancedb_sync_log
            WHERE operation = 'delete'
            ORDER BY synced_at ASC
            """
        )
        rows = cursor.fetchall()
        return [row["chunk_hash"] for row in rows]

    def get_source_info(self, source_id: str) -> Optional[SourceInfo]:
        """Fetch origin_ref and adapter_type for a source.

        Joins sources and adapters tables to retrieve both pieces of metadata
        needed for chunk provenance tracing.

        Args:
            source_id: The source to retrieve info for.

        Returns:
            SourceInfo with origin_ref and adapter_type if source exists, None otherwise.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT s.origin_ref, a.adapter_type
            FROM sources s
            JOIN adapters a ON s.adapter_id = a.adapter_id
            WHERE s.source_id = ?
            """,
            (source_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return SourceInfo(origin_ref=row[0], adapter_type=row[1])

    def list_adapters(self) -> list[AdapterConfig]:
        """List all registered adapters, ordered by adapter_id.

        Returns:
            List of AdapterConfig objects.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT adapter_id, adapter_type, domain, normalizer_version, config
            FROM adapters ORDER BY adapter_id ASC
            """
        )
        rows = cursor.fetchall()
        result = []
        for row in rows:
            config_dict = json.loads(row["config"]) if row["config"] else None
            result.append(
                AdapterConfig(
                    adapter_id=row["adapter_id"],
                    adapter_type=row["adapter_type"],
                    domain=Domain(row["domain"]),
                    normalizer_version=row["normalizer_version"],
                    config=config_dict,
                )
            )
        return result

    def list_sources(
        self,
        domain: Optional[str] = None,
        adapter_id: Optional[str] = None,
        source_id_prefix: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """List sources with optional filtering and pagination.

        Args:
            domain: Optional domain filter.
            adapter_id: Optional adapter_id filter.
            source_id_prefix: Optional prefix filter on source_id.
            limit: Maximum number of results to return.
            offset: Number of results to skip.

        Returns:
            Tuple of (page rows, total_matching_count). Each row dict includes
            chunk_count for the current version.
        """
        cursor = self.conn.cursor()
        filter_params: list[object] = []
        where_clauses = ["1=1"]
        if domain is not None:
            where_clauses.append("s.domain = ?")
            filter_params.append(domain)
        if adapter_id is not None:
            where_clauses.append("s.adapter_id = ?")
            filter_params.append(adapter_id)
        if source_id_prefix is not None:
            # Use GLOB for case-sensitive matching (Unix filesystem semantics).
            # GLOB uses * and ? as wildcards (not % and _), and special chars need escaping:
            # - * (any sequence) → [*]
            # - ? (any single char) → [?]
            # - [ (char class start) → [[]
            # - ] (char class end) → []]
            # Use single-pass escaping to avoid re-escaping characters introduced by earlier replacements.
            escaped_prefix = ''.join(f'[{c}]' if c in _GLOB_SPECIAL else c for c in source_id_prefix)
            where_clauses.append("s.source_id GLOB ? || '*'")
            filter_params.append(escaped_prefix)
        where_sql = " AND ".join(where_clauses)

        # Total count of matching sources (without LIMIT/OFFSET)
        cursor.execute(
            f"SELECT COUNT(*) FROM sources s WHERE {where_sql}",
            filter_params,
        )
        total: int = cursor.fetchone()[0]

        # Paginated rows with chunk_count
        page_params = list(filter_params) + [limit, offset]
        cursor.execute(
            f"""
            SELECT s.source_id, s.adapter_id, a.adapter_type, s.domain, s.origin_ref,
                   s.display_name, s.current_version, s.last_fetched_at, s.poll_strategy,
                   s.poll_interval_sec, s.created_at, s.updated_at,
                   COUNT(c.chunk_hash) AS chunk_count
            FROM sources s
            JOIN adapters a ON s.adapter_id = a.adapter_id
            LEFT JOIN chunks c
              ON c.source_id = s.source_id
             AND c.source_version = s.current_version
             AND c.retired_at IS NULL
            WHERE {where_sql}
            GROUP BY s.source_id
            ORDER BY s.source_id ASC
            LIMIT ? OFFSET ?
            """,
            page_params,
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows], total

    def get_source_detail(self, source_id: str) -> Optional[dict]:
        """Get detailed information about a single source, including adapter metadata.

        Args:
            source_id: ID of the source.

        Returns:
            Dict with all source fields plus adapter_type and normalizer_version,
            or None if the source does not exist.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT s.source_id, s.adapter_id, s.domain, s.origin_ref, s.display_name,
                   s.current_version, s.last_fetched_at, s.poll_strategy,
                   s.poll_interval_sec, s.created_at, s.updated_at,
                   a.adapter_type, a.normalizer_version,
                   COUNT(c.chunk_hash) AS chunk_count
            FROM sources s
            JOIN adapters a ON s.adapter_id = a.adapter_id
            LEFT JOIN chunks c
              ON c.source_id = s.source_id
             AND c.source_version = s.current_version
             AND c.retired_at IS NULL
            WHERE s.source_id = ?
            GROUP BY s.source_id
            """,
            (source_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_source_version(self, source_id: str, version: int) -> Optional[SourceVersion]:
        """Get a specific version of a source.

        Args:
            source_id: ID of the source.
            version: Version number.

        Returns:
            SourceVersion if found, None otherwise.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT source_id, version, markdown, chunk_hashes, adapter_id,
                   normalizer_version, fetch_timestamp
            FROM source_versions
            WHERE source_id = ? AND version = ?
            """,
            (source_id, version),
        )
        row = cursor.fetchone()
        if not row:
            return None
        chunk_hashes = json.loads(row["chunk_hashes"])
        return SourceVersion(
            source_id=row["source_id"],
            version=row["version"],
            markdown=row["markdown"],
            chunk_hashes=chunk_hashes,
            adapter_id=row["adapter_id"],
            normalizer_version=row["normalizer_version"],
            fetch_timestamp=row["fetch_timestamp"],
        )

    def get_dataset_stats(self) -> dict:
        """Get dataset-level statistics.

        Returns:
            Dict with by_domain list, total_sources, total_active_chunks,
            retired_chunk_count, sync_queue_pending_insert, sync_queue_pending_delete.
        """
        cursor = self.conn.cursor()

        # Per-domain source and active chunk counts
        cursor.execute(
            """
            SELECT s.domain,
                   COUNT(DISTINCT s.source_id) AS source_count,
                   COUNT(c.chunk_hash) AS active_chunk_count
            FROM sources s
            LEFT JOIN chunks c
              ON c.source_id = s.source_id
             AND c.source_version = s.current_version
             AND c.retired_at IS NULL
            GROUP BY s.domain
            ORDER BY s.domain ASC
            """
        )
        by_domain = [
            {
                "domain": row["domain"],
                "source_count": row["source_count"],
                "active_chunk_count": row["active_chunk_count"],
            }
            for row in cursor.fetchall()
        ]

        total_sources = sum(d["source_count"] for d in by_domain)
        total_active_chunks = sum(d["active_chunk_count"] for d in by_domain)

        # Retired chunk count
        cursor.execute("SELECT COUNT(*) AS cnt FROM chunks WHERE retired_at IS NOT NULL")
        retired_chunk_count = cursor.fetchone()["cnt"]

        # Sync queue breakdown
        cursor.execute(
            "SELECT operation, COUNT(*) AS cnt FROM lancedb_sync_log GROUP BY operation"
        )
        sync_counts: dict[str, int] = {"insert": 0, "delete": 0}
        for row in cursor.fetchall():
            sync_counts[row["operation"]] = row["cnt"]

        return {
            "by_domain": by_domain,
            "total_sources": total_sources,
            "total_active_chunks": total_active_chunks,
            "retired_chunk_count": retired_chunk_count,
            "sync_queue_pending_insert": sync_counts["insert"],
            "sync_queue_pending_delete": sync_counts["delete"],
        }

    def list_chunks(
        self,
        domain: Optional[str] = None,
        adapter_id: Optional[str] = None,
        source_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        metadata_filter: Optional[dict[str, str]] = None,
    ) -> tuple[list[ChunkWithLineageContext], int]:
        """List active chunks with optional filtering and pagination.

        Returns paginated chunks from the current (latest) version of each source,
        filtered by domain, adapter_id, source_id, and/or domain_metadata if specified.
        Only returns non-retired chunks. Deduplicates by constraining to current_version.

        Corrupt chunks (with malformed domain_metadata JSON) are skipped with warnings
        logged, but do not cause the entire list operation to fail. This ensures one
        corrupt chunk does not make all valid chunks invisible.

        Args:
            domain: Optional domain filter (e.g., "notes", "messages").
            adapter_id: Optional adapter_id filter.
            source_id: Optional source_id filter (returns only chunks from this source).
            limit: Maximum number of results to return.
            offset: Number of results to skip.
            metadata_filter: Optional dict of domain_metadata key-value pairs to filter by.
                For example: {"health_type": "workout_session"} returns only chunks where
                domain_metadata["health_type"] == "workout_session".

        Returns:
            Tuple of (page chunks, total_count). Each chunk is a ChunkWithLineageContext
            with the chunk object and associated metadata. Total count is the full count
            of matching, returnable (non-corrupt) chunks across all pages.
        """
        cursor = self.conn.cursor()
        filter_params: list[object] = []
        where_clauses = ["c.retired_at IS NULL", "c.source_version = s.current_version"]

        if domain is not None:
            where_clauses.append("s.domain = ?")
            filter_params.append(domain)
        if adapter_id is not None:
            where_clauses.append("s.adapter_id = ?")
            filter_params.append(adapter_id)
        if source_id is not None:
            where_clauses.append("c.source_id = ?")
            filter_params.append(source_id)

        # Add metadata filters to WHERE clause (server-side filtering via SQL)
        if metadata_filter:
            for key, value in metadata_filter.items():
                where_clauses.append("json_extract(c.domain_metadata, ?) = ?")
                filter_params.append(f"$.{key}")
                filter_params.append(value)

        where_sql = " AND ".join(where_clauses)

        # Get total count of matching items (after metadata filters)
        cursor.execute(
            f"""
            SELECT COUNT(*) as count
            FROM chunks c
            JOIN sources s ON c.source_id = s.source_id
            WHERE {where_sql}
            """,
            filter_params,
        )
        total = cursor.fetchone()["count"]

        # Fetch paginated results
        query = f"""
            SELECT c.chunk_hash, c.source_id, c.source_version, c.chunk_index,
                   c.content, c.context_header, c.chunk_type, c.domain_metadata,
                   c.normalizer_version, c.embedding_model_id, c.created_at,
                   s.adapter_id, s.domain, s.current_version as source_version_id
            FROM chunks c
            JOIN sources s ON c.source_id = s.source_id
            WHERE {where_sql}
            ORDER BY c.created_at DESC
            LIMIT ? OFFSET ?
            """
        all_params = filter_params + [limit, offset]
        cursor.execute(query, all_params)
        all_rows = cursor.fetchall()

        # Build chunks, skipping corrupt ones with logged warnings
        paginated_results = []
        for row in all_rows:
            try:
                chunk = self._build_chunk_from_row(row)
                paginated_results.append(ChunkWithLineageContext(
                    chunk=chunk,
                    source_id=row["source_id"],
                    source_version_id=row["source_version_id"],
                    adapter_id=row["adapter_id"],
                    domain=row["domain"],
                    normalizer_version=row["normalizer_version"],
                    embedding_model_id=row["embedding_model_id"],
                ))
            except ValueError as e:
                logger.warning("Skipping corrupt chunk during list: %s", e)
                # Note: Corrupt chunks reduce the actual returned count below total.
                # This is acceptable as corrupt chunks are not returnable.
                continue

        return paginated_results, total

    def get_adapter_stats(self) -> list[dict]:
        """Get per-adapter source and active chunk counts.

        Returns a list of one dict per adapter, with source and chunk counts.
        Adapters with no sources are not included.

        Returns:
            List of dicts with keys: adapter_id, adapter_type, domain,
            source_count, active_chunk_count. Ordered by adapter_id.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT s.adapter_id, a.adapter_type, s.domain,
                   COUNT(DISTINCT s.source_id) AS source_count,
                   COUNT(DISTINCT c.chunk_hash) AS active_chunk_count
            FROM sources s
            LEFT JOIN adapters a ON s.adapter_id = a.adapter_id
            LEFT JOIN chunks c
              ON c.source_id = s.source_id
             AND c.source_version = s.current_version
             AND c.retired_at IS NULL
            GROUP BY s.adapter_id, a.adapter_type, s.domain
            ORDER BY s.adapter_id ASC
            """
        )
        rows = cursor.fetchall()
        return [
            {
                "adapter_id": row["adapter_id"],
                "adapter_type": row["adapter_type"],
                "domain": row["domain"],
                "source_count": row["source_count"],
                "active_chunk_count": row["active_chunk_count"],
            }
            for row in rows
        ]

    def write_entity_links(
        self,
        links: list[EntityLink],
    ) -> int:
        """Write entity links to the entity_links table.

        Inserts rows into entity_links with idempotency enforced by the UNIQUE constraint
        (source_chunk_hash, target_chunk_hash, link_type). Duplicate inserts are silently
        ignored via INSERT OR IGNORE.

        Args:
            links: List of EntityLink objects representing directed links between chunks.

        Returns:
            The number of new rows inserted (duplicates are not counted).
        """
        if not links:
            return 0

        try:
            with self._write_lock, self.conn:
                cursor = self.conn.cursor()
                inserted_count = 0
                for link in links:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO entity_links
                        (source_chunk_hash, target_chunk_hash, link_type, confidence)
                        VALUES (?, ?, ?, ?)
                        """,
                        (link.source_chunk_hash, link.target_chunk_hash, link.link_type, link.confidence),
                    )
                    # Check if row was actually inserted (not ignored)
                    if cursor.rowcount > 0:
                        inserted_count += 1

                return inserted_count
        except Exception as e:
            logger.error(f"Failed to write entity links: {e}")
            raise

    def query_chunks_by_identifiers(
        self,
        identifiers: list[str],
        scalar_fields: list[str],
        array_fields: list[str],
        exclude_domain: Optional[str] = None,
    ) -> list[str]:
        """Query chunks where domain_metadata contains any of the given identifiers.

        Uses normalized SQL-based matching with custom SQLite functions for:
        - Emails: case-insensitive matching via LOWER()
        - Phones: format-insensitive matching via custom normalize_phone_sql() function

        This approach keeps filtering in SQL (where it's efficient) rather than loading
        all chunks into memory. Identifiers are normalized on both sides of the comparison.

        Args:
            identifiers: List of email/phone strings to search for.
            scalar_fields: List of scalar field names to search (e.g., ['sender', 'host', 'author']).
            array_fields: List of array field names to search (e.g., ['recipients', 'invitees', 'collaborators']).
            exclude_domain: Optional domain to exclude from results (e.g., 'people').

        Returns:
            List of chunk_hashes from chunks where a match was found.

        Raises:
            ValueError: If both scalar_fields and array_fields are empty, or if any field name
                        contains invalid characters (not alphanumeric or underscore).
        """
        if not identifiers:
            return []

        # Validate that at least one field type is provided
        if not scalar_fields and not array_fields:
            raise ValueError("At least one of scalar_fields or array_fields must be provided")

        # Validate field names: allow only alphanumeric characters and underscores
        for field in scalar_fields + array_fields:
            if not field or not all(c.isalnum() or c == "_" for c in field):
                raise ValueError(
                    f"Invalid field name '{field}': field names must be alphanumeric or underscore only"
                )

        cursor = self.conn.cursor()

        # Normalize all query identifiers once, building as a list
        normalized_query_identifiers: list[str] = []
        seen = set()
        for identifier in identifiers:
            # Simple heuristic: if it contains '@', treat as email; otherwise as phone
            if "@" in identifier:
                normalized = normalize_email(identifier)
            else:
                normalized = normalize_phone(identifier)
            if normalized and normalized not in seen:
                normalized_query_identifiers.append(normalized)
                seen.add(normalized)

        if not normalized_query_identifiers:
            return []

        # Build SQL conditions and parameters incrementally
        params: list = []
        scalar_conditions = []
        for field in scalar_fields:
            # Use custom functions for emails and phones
            scalar_conditions.append(f"""
                (normalize_email_sql(json_extract(c.domain_metadata, '$.{field}')) IN ({','.join('?' * len(normalized_query_identifiers))})
                 OR
                 normalize_phone_sql(json_extract(c.domain_metadata, '$.{field}')) IN ({','.join('?' * len(normalized_query_identifiers))}))
            """)
            # Add parameters for email matching: normalized_query_identifiers twice (once for email, once for phone)
            params.extend(normalized_query_identifiers)
            params.extend(normalized_query_identifiers)

        # Build SQL conditions for array fields (e.g., recipients, invitees, collaborators)
        array_conditions = []
        for field in array_fields:
            array_conditions.append(f"""
                EXISTS (
                    SELECT 1 FROM json_each(c.domain_metadata, '$.{field}')
                    WHERE normalize_email_sql(json_each.value) IN ({','.join('?' * len(normalized_query_identifiers))})
                       OR normalize_phone_sql(json_each.value) IN ({','.join('?' * len(normalized_query_identifiers))})
                )
            """)
            # Add parameters for array matching: normalized_query_identifiers twice (once for email, once for phone)
            params.extend(normalized_query_identifiers)
            params.extend(normalized_query_identifiers)

        # Combine all conditions
        where_conditions = []
        if scalar_conditions:
            where_conditions.append(f"({' OR '.join(scalar_conditions)})")
        if array_conditions:
            where_conditions.append(f"({' OR '.join(array_conditions)})")

        where_clause = " OR ".join(where_conditions)

        query = f"""
            SELECT DISTINCT c.chunk_hash
            FROM chunks c
            JOIN sources s ON c.source_id = s.source_id
            WHERE c.retired_at IS NULL
            AND c.source_version = s.current_version
            AND ({where_clause})
        """

        if exclude_domain:
            query += " AND s.domain != ?"
            params.append(exclude_domain)

        cursor.execute(query, params)

        rows = cursor.fetchall()
        found_hashes = {row[0] for row in rows}

        return sorted(list(found_hashes))

    def get_linked_chunks(
        self,
        chunk_hash: str,
        link_type: str | None = None,
    ) -> list[str]:
        """Query all chunks linked to a given chunk.

        Bidirectional traversal: returns chunks where the given chunk is the source OR the target.
        Optionally filters by link_type.

        Args:
            chunk_hash: The chunk hash to find links for.
            link_type: Optional link type to filter by (e.g., 'person_appearance').

        Returns:
            A list of linked chunk hashes (deduplicated).
        """
        cursor = self.conn.cursor()

        if link_type:
            # Query where chunk_hash is source or target, with link_type filter
            cursor.execute(
                """
                SELECT DISTINCT target_chunk_hash FROM entity_links
                WHERE source_chunk_hash = ? AND link_type = ?
                UNION
                SELECT DISTINCT source_chunk_hash FROM entity_links
                WHERE target_chunk_hash = ? AND link_type = ?
                """,
                (chunk_hash, link_type, chunk_hash, link_type),
            )
        else:
            # Query where chunk_hash is source or target, no filter
            cursor.execute(
                """
                SELECT DISTINCT target_chunk_hash FROM entity_links
                WHERE source_chunk_hash = ?
                UNION
                SELECT DISTINCT source_chunk_hash FROM entity_links
                WHERE target_chunk_hash = ?
                """,
                (chunk_hash, chunk_hash),
            )

        rows = cursor.fetchall()
        return [row[0] for row in rows]

    def delete_retired_person_links_atomic(self) -> int:
        """Atomically delete entity_links for all retired person chunks.

        Deletes all entity_links where source_chunk_hash is no longer active
        in the people domain. Uses a single DELETE ... WHERE NOT EXISTS query
        to ensure atomicity and eliminate TOCTOU race conditions.

        Returns:
            The number of rows deleted.

        Raises:
            Exception: If the database operation fails.
        """
        try:
            with self._write_lock, self.conn:
                cursor = self.conn.cursor()
                cursor.execute(
                    """
                    DELETE FROM entity_links
                    WHERE link_type = ?
                    AND NOT EXISTS (
                        SELECT 1
                        FROM chunks c
                        JOIN sources s ON c.source_id = s.source_id
                        WHERE c.chunk_hash = entity_links.source_chunk_hash
                        AND s.domain = ?
                        AND c.retired_at IS NULL
                        AND c.source_version = s.current_version
                    )
                    AND EXISTS (
                        SELECT 1
                        FROM chunks c2
                        JOIN sources s2 ON c2.source_id = s2.source_id
                        WHERE c2.chunk_hash = entity_links.source_chunk_hash
                        AND s2.domain = ?
                    )
                    """,
                    (ENTITY_LINK_TYPE_PERSON_APPEARANCE, Domain.PEOPLE, Domain.PEOPLE),
                )
                return cursor.rowcount
        except Exception as e:
            logger.error(f"Failed to delete retired person links atomically: {e}")
            raise

    def delete_retired_target_links_atomic(self) -> int:
        """Atomically delete entity_links for all retired target chunks.

        Deletes all entity_links where target_chunk_hash is retired (not active
        in the current version). Uses a single DELETE ... WHERE NOT EXISTS query
        to ensure atomicity and eliminate TOCTOU race conditions.

        Returns:
            The number of rows deleted.

        Raises:
            Exception: If the database operation fails.
        """
        try:
            with self._write_lock, self.conn:
                cursor = self.conn.cursor()
                cursor.execute(
                    """
                    DELETE FROM entity_links
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM chunks c
                        JOIN sources s ON c.source_id = s.source_id
                        WHERE c.chunk_hash = entity_links.target_chunk_hash
                        AND c.retired_at IS NULL
                        AND c.source_version = s.current_version
                    )
                    AND EXISTS (
                        SELECT 1
                        FROM chunks c2
                        WHERE c2.chunk_hash = entity_links.target_chunk_hash
                    )
                    """
                )
                return cursor.rowcount
        except Exception as e:
            logger.error(f"Failed to delete retired target links atomically: {e}")
            raise

    def close(self) -> None:
        """Close the current thread's database connection.

        Should be called from the thread that owns the main connection (i.e. the
        server lifespan coroutine) when the document store is no longer needed,
        to flush the WAL checkpoint and release file handles.
        """
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

    def __enter__(self) -> "DocumentStore":
        """Enter context manager."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit context manager and close connection."""
        self.close()
