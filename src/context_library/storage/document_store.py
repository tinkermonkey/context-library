"""SQLite-backed document store; source of truth for versions, chunks, and lineage."""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import AdapterConfig, Chunk, Domain, LineageRecord, PollStrategy, Sha256Hash, SourceInfo, SourceVersion, VersionDiff, _validate_sha256_hex

logger = logging.getLogger(__name__)


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

        Connects to SQLite, executes the schema (which sets WAL mode, synchronous=NORMAL,
        and foreign_keys), and verifies the user_version.

        Args:
            db_path: Path to SQLite database file. Use ':memory:' for in-memory DB.

        Raises:
            RuntimeError: If schema execution or verification fails.
        """
        # Convert to string path (handles both str and Path)
        db_path_str = str(db_path)

        # Connect to database
        self.conn = sqlite3.connect(db_path_str)

        # Set row_factory to access columns by name
        self.conn.row_factory = sqlite3.Row

        # Load and execute schema (contains all required PRAGMAs)
        schema_path = Path(__file__).parent / "schema.sql"
        schema_sql = schema_path.read_text()
        self.conn.executescript(schema_sql)

        # Re-apply critical PRAGMAs after executescript
        # (executescript can reset connection state in some SQLite versions)
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

        # Verify foreign keys are enforced
        cursor = self.conn.cursor()
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

        # Verify schema version
        cursor.execute("PRAGMA user_version")
        version = cursor.fetchone()[0]
        if version != 1:
            raise RuntimeError(
                f"Schema version mismatch: expected 1, got {version}"
            )

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

        with self.conn:
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
    ) -> None:
        """Register a source.

        Inserts the source into the sources table if it doesn't exist, or updates
        all source configuration (adapter_id, domain, poll_strategy, poll_interval_sec)
        if the source is re-registered with different values.

        Args:
            source_id: Unique identifier for the source.
            adapter_id: ID of the adapter handling this source. Updated on re-registration.
            domain: Domain classification (messages, notes, events, tasks). Updated on re-registration.
            origin_ref: URL, path, or reference to the original source.
            poll_strategy: Strategy for polling this source (push, pull, or webhook).
                          Defaults to PollStrategy.PULL. Updated on re-registration.
            poll_interval_sec: Interval in seconds between polls for PULL strategy.
                              None if not applicable for this strategy. Updated on re-registration.
        """
        with self.conn:
            cursor = self.conn.cursor()
            # Check if source already exists
            cursor.execute(
                "SELECT source_id FROM sources WHERE source_id = ?",
                (source_id,),
            )
            existing = cursor.fetchone()

            if existing is None:
                # Insert new source
                self.conn.execute(
                    """
                    INSERT INTO sources
                    (source_id, adapter_id, domain, origin_ref, poll_strategy, poll_interval_sec)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (source_id, adapter_id, domain.value, origin_ref, poll_strategy.value, poll_interval_sec),
                )
            else:
                # Update all source configuration on re-registration
                self.conn.execute(
                    """
                    UPDATE sources
                    SET adapter_id = ?, domain = ?, poll_strategy = ?, poll_interval_sec = ?
                    WHERE source_id = ?
                    """,
                    (adapter_id, domain.value, poll_strategy.value, poll_interval_sec, source_id),
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

        with self.conn:
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

        with self.conn:
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

        with self.conn:
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
            chunk = self.get_chunk_by_hash(chunk_hash, source_id)
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
        """
        domain_metadata = (
            json.loads(row["domain_metadata"])
            if row["domain_metadata"]
            else None
        )
        # Extract cross_refs from domain_metadata using reserved "_system_cross_refs" key
        cross_refs = ()
        if domain_metadata and "_system_cross_refs" in domain_metadata:
            cross_refs = tuple(domain_metadata.pop("_system_cross_refs"))
            # Remove from domain_metadata if it's now empty
            if not domain_metadata:
                domain_metadata = None

        return Chunk(
            chunk_hash=row["chunk_hash"],
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
        return [self._build_chunk_from_row(row) for row in rows]

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
        with self.conn:
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
