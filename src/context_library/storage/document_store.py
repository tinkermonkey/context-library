"""SQLite-backed document store; source of truth for versions, chunks, and lineage."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import AdapterConfig, Chunk, Domain, LineageRecord, SourceVersion


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


    def __init__(self, db_path: str | Path) -> None:
        """Initialize the document store and set up the SQLite database.

        Connects to SQLite, enables WAL mode, enforces foreign keys,
        executes the schema, and verifies the user_version.

        Args:
            db_path: Path to SQLite database file. Use ':memory:' for in-memory DB.

        Raises:
            RuntimeError: If schema execution or verification fails.
        """
        # Convert to string path (handles both str and Path)
        db_path_str = str(db_path)

        # Connect to database
        self.conn = sqlite3.connect(db_path_str)

        # Enable WAL mode for better concurrency
        self.conn.execute("PRAGMA journal_mode=WAL")

        # Set synchronous mode to NORMAL for better performance
        self.conn.execute("PRAGMA synchronous=NORMAL")

        # Set row_factory to access columns by name
        self.conn.row_factory = sqlite3.Row

        # Load and execute schema
        schema_path = Path(__file__).parent / "schema.sql"
        schema_sql = schema_path.read_text()
        self.conn.executescript(schema_sql)

        # Re-enable foreign key constraints after executescript
        # (executescript can reset connection state)
        self.conn.execute("PRAGMA foreign_keys=ON")

        # Verify foreign keys are enforced
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA foreign_keys")
        foreign_keys_enabled = cursor.fetchone()[0]
        if foreign_keys_enabled != 1:
            raise RuntimeError(
                "Failed to enable foreign key constraints"
            )

        # Verify schema version
        cursor.execute("PRAGMA user_version")
        version = cursor.fetchone()[0]
        if version != 1:
            raise RuntimeError(
                f"Schema version mismatch: expected 1, got {version}"
            )

    def register_adapter(self, config: AdapterConfig) -> str:
        """Register an adapter configuration.

        Inserts the adapter config into the adapters table, or updates it if the
        adapter_id already exists with different normalizer_version or config.

        The adapter is identified by adapter_id. On first registration, a new row
        is created. On subsequent registrations, the row is updated with the new
        configuration. The trigger refreshes updated_at on any UPDATE.

        Args:
            config: AdapterConfig with adapter_id, type, domain, and config dict.

        Returns:
            The adapter_id.
        """
        config_json = json.dumps(config.config) if config.config else None

        with self.conn:
            # Use INSERT ... ON CONFLICT ... DO UPDATE for atomic upsert
            # This handles both insert (new adapter) and update (changed config)
            self.conn.execute(
                """
                INSERT INTO adapters
                (adapter_id, domain, adapter_type, normalizer_version, config)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(adapter_id)
                DO UPDATE SET
                    domain = excluded.domain,
                    adapter_type = excluded.adapter_type,
                    normalizer_version = excluded.normalizer_version,
                    config = excluded.config
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
    ) -> None:
        """Register a source.

        Inserts the source into the sources table. If the source_id already
        exists, does nothing (idempotent).

        Args:
            source_id: Unique identifier for the source.
            adapter_id: ID of the adapter handling this source.
            domain: Domain classification (messages, notes, events, tasks).
            origin_ref: URL, path, or reference to the original source.
        """
        with self.conn:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO sources
                (source_id, adapter_id, domain, origin_ref, poll_strategy)
                VALUES (?, ?, ?, ?, ?)
                """,
                (source_id, adapter_id, domain.value, origin_ref, "pull"),
            )

    def create_source_version(
        self,
        source_id: str,
        version: int,
        markdown: str,
        chunk_hashes: list[str],
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
            chunk_hashes: List of chunk hashes in this version.
            adapter_id: ID of the adapter that fetched this version.
            normalizer_version: Version of the normalizer used.
            fetch_timestamp: ISO 8601 timestamp when content was fetched.

        Returns:
            The SQLite rowid of the newly created source_version row.

        Raises:
            sqlite3.IntegrityError: If source_id or adapter_id don't exist.
        """
        chunk_hashes_json = json.dumps(chunk_hashes)

        with self.conn:
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
            assert source_version_id is not None

            # Update sources.current_version
            self.conn.execute(
                """
                UPDATE sources SET current_version = ? WHERE source_id = ?
                """,
                (version, source_id),
            )

            return source_version_id

    def write_chunks(
        self,
        chunks: list[Chunk],
        lineage_records: list[LineageRecord],
    ) -> None:
        """Write chunks and lineage records to storage.

        Inserts chunks into the database. Deduplicates by chunk_hash (content-addressed identity).
        If a chunk_hash already exists, it is skipped silently (content already stored).

        Chunks are linked to their sources and versions via lineage records.

        Args:
            chunks: List of Chunk objects to insert.
            lineage_records: List of LineageRecord objects with provenance info.

        Raises:
            ValueError: If a chunk has no matching lineage record.
            sqlite3.IntegrityError: If foreign key or UNIQUE constraint violations occur
                (other than chunk_hash PRIMARY KEY which is content deduplication).
        """
        # Create a map of chunk_hash to lineage for quick lookup
        lineage_map = {lr.chunk_hash: lr for lr in lineage_records}

        # Validate that all chunks have matching lineage
        for chunk in chunks:
            if chunk.chunk_hash not in lineage_map:
                raise ValueError(
                    f"No lineage record found for chunk_hash={chunk.chunk_hash}"
                )

        # Generate timestamp once for the entire batch
        batch_timestamp = datetime.now(timezone.utc).isoformat()

        with self.conn:
            for chunk in chunks:
                domain_metadata_json = (
                    json.dumps(chunk.domain_metadata)
                    if chunk.domain_metadata
                    else None
                )

                # Get lineage info for this chunk (guaranteed non-None due to validation above)
                lineage = lineage_map[chunk.chunk_hash]

                try:
                    self.conn.execute(
                        """
                        INSERT INTO chunks
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
                except sqlite3.IntegrityError as e:
                    # PRIMARY KEY collision (chunk_hash): content already stored (deduplication by hash)
                    # UNIQUE index collision (source_id, source_version, chunk_index): same chunk position in same version
                    # Both are expected and silent - the chunk is already in the database
                    error_msg = str(e)
                    if "UNIQUE constraint failed: chunks.chunk_hash" in error_msg or \
                       "UNIQUE constraint failed: chunks.source_id, chunks.source_version, chunks.chunk_index" in error_msg:
                        # Chunk already exists (either by hash or by position); skip silently
                        continue
                    # For any other constraint violation (foreign key, CHECK), re-raise
                    raise

    def retire_chunks(self, chunk_hashes: set[str]) -> None:
        """Mark chunks as retired.

        Updates the retired_at timestamp for matching chunks, indicating
        they are no longer active in the latest version.

        Args:
            chunk_hashes: Set of chunk hashes to retire.
        """
        now = datetime.now(timezone.utc).isoformat()

        with self.conn:
            self.conn.executemany(
                """
                UPDATE chunks SET retired_at = ? WHERE chunk_hash = ?
                """,
                [(now, h) for h in chunk_hashes],
            )

    def write_sync_log(self, chunk_hashes: list[str]) -> None:
        """Log chunk sync state (insert) to LanceDB.

        Inserts entries into lancedb_sync_log to track which chunks have been
        synced to the vector database. Uses INSERT OR REPLACE, so each operation
        creates a new timestamped record. The synced_at column reflects when the
        most recent insert operation was logged.

        Args:
            chunk_hashes: List of chunk hashes that were synced to the vector database.
        """
        with self.conn:
            self.conn.executemany(
                """
                INSERT OR REPLACE INTO lancedb_sync_log (chunk_hash, operation)
                VALUES (?, 'insert')
                """,
                [(h,) for h in chunk_hashes],
            )

    def delete_sync_log(self, chunk_hashes: list[str]) -> None:
        """Record delete operations for chunks in sync log.

        Updates lancedb_sync_log entries to record that chunks have been deleted
        from the vector database. Marks the operation as 'delete' for audit trail.
        Uses INSERT OR REPLACE, so each operation creates a new timestamped record.
        The synced_at column reflects when the delete operation was logged, not the
        original insert time.

        Args:
            chunk_hashes: List of chunk hashes that were deleted from LanceDB.
        """
        with self.conn:
            self.conn.executemany(
                """
                INSERT OR REPLACE INTO lancedb_sync_log (chunk_hash, operation)
                VALUES (?, 'delete')
                """,
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

    def get_chunks_by_source(
        self,
        source_id: str,
        version: Optional[int] = None,
    ) -> list[Chunk]:
        """Get active chunks for a source.

        Returns chunks for the specified version, or the latest version
        if no version is specified. Only returns non-retired chunks.

        Args:
            source_id: ID of the source.
            version: Specific version number, or None for latest.

        Returns:
            List of Chunk objects, or empty list if no chunks exist.
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
                return []
            version = row["current_version"]

        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT chunk_hash, chunk_index, content, context_header, chunk_type,
                   domain_metadata
            FROM chunks
            WHERE source_id = ? AND source_version = ? AND retired_at IS NULL
            ORDER BY chunk_index ASC
            """,
            (source_id, version),
        )
        rows = cursor.fetchall()

        chunks = []
        for row in rows:
            domain_metadata = (
                json.loads(row["domain_metadata"])
                if row["domain_metadata"]
                else None
            )
            chunks.append(
                Chunk(
                    chunk_hash=row["chunk_hash"],
                    content=row["content"],
                    context_header=row["context_header"],
                    chunk_index=row["chunk_index"],
                    chunk_type=row["chunk_type"],
                    domain_metadata=domain_metadata,
                )
            )

        return chunks

    def get_chunk_by_hash(self, chunk_hash: str) -> Optional[Chunk]:
        """Get a chunk by its hash.

        Args:
            chunk_hash: SHA-256 hash of the chunk.

        Returns:
            Chunk object, or None if not found.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT chunk_hash, chunk_index, content, context_header, chunk_type,
                   domain_metadata
            FROM chunks
            WHERE chunk_hash = ?
            LIMIT 1
            """,
            (chunk_hash,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        domain_metadata = (
            json.loads(row["domain_metadata"]) if row["domain_metadata"] else None
        )

        return Chunk(
            chunk_hash=row["chunk_hash"],
            content=row["content"],
            context_header=row["context_header"],
            chunk_index=row["chunk_index"],
            chunk_type=row["chunk_type"],
            domain_metadata=domain_metadata,
        )

    def get_lineage(self, chunk_hash: str) -> Optional[LineageRecord]:
        """Get the lineage record for a chunk.

        Retrieves the full provenance information for a chunk, including the
        embedding model ID that was used when the chunk was vectorized.

        Args:
            chunk_hash: SHA-256 hash of the chunk.

        Returns:
            LineageRecord with complete provenance information, or None if not found.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT chunk_hash, source_id, source_version, adapter_id, domain,
                   normalizer_version, embedding_model_id
            FROM chunks
            WHERE chunk_hash = ?
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
        """
        now = datetime.now(timezone.utc).isoformat()
        with self.conn:
            self.conn.execute(
                "UPDATE sources SET last_fetched_at = ? WHERE source_id = ?",
                (now, source_id),
            )

    def close(self) -> None:
        """Close the database connection.

        Should be called when the document store is no longer needed to ensure
        proper cleanup of the WAL mode checkpoint and file handles.
        """
        self.conn.close()

    def __enter__(self) -> "DocumentStore":
        """Enter context manager."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit context manager and close connection."""
        self.close()
