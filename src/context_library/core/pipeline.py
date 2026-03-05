"""Orchestrates the full ingestion pipeline: fetch → normalize → diff → chunk → embed → store.

DESIGN NOTE: This implementation does NOT provide atomic writes across SQLite and LanceDB.
SQLite is the source of truth; LanceDB is derived and fully rebuildable from SQLite.
See failure modes below for recovery procedures.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PartialFailureReport:
    """Tracks success/failure state for individual store operations.

    This report allows the caller to understand exactly what failed and recover appropriately.
    Since LanceDB is derived from SQLite, a SQLite failure is critical, but an LanceDB failure
    can be recovered by rebuilding the vector index from the SQLite source of truth.
    """

    sqlite_success_count: int = 0
    lancedb_success_count: int = 0
    sqlite_exception: Optional[Exception] = None
    lancedb_exception: Optional[Exception] = None

    @property
    def is_complete_success(self) -> bool:
        """Return True only if both stores succeeded."""
        return self.sqlite_exception is None and self.lancedb_exception is None

    @property
    def is_recoverable(self) -> bool:
        """Return True if data is safe in SQLite (source of truth)."""
        return self.sqlite_exception is None


class Pipeline:
    """Orchestrates multi-stage data flow with explicit error handling.

    FAILURE MODES (in order of severity):

    1. SQLite write fails → Data loss (CRITICAL)
       - Ingest attempt halted
       - LanceDB not updated (stays in sync with last successful SQLite state)
       - Recovery: Investigate SQLite error and retry

    2. SQLite succeeds, LanceDB fails → Data inconsistency (RECOVERABLE)
       - Data safely stored in SQLite
       - LanceDB becomes stale (missing new chunks)
       - Recovery: Rebuild vector index from SQLite using rebuild_vector_index()
       - This is expected behavior; LanceDB is disposable

    3. Partial success within a store → Caller sees it
       - For example, if SQLite wrote 10 of 12 chunks then failed
       - PartialFailureReport.sqlite_success_count tells you how many succeeded
       - Caller must decide: retry (may duplicate) or manual cleanup
    """

    def ingest(self, chunks: list) -> PartialFailureReport:
        """Ingest chunks into both SQLite and LanceDB with explicit error handling.

        Args:
            chunks: List of chunk objects to ingest

        Returns:
            PartialFailureReport detailing success/failure for each store

        PATTERN: Always try SQLite first (source of truth), then LanceDB (derived).
        """
        report = PartialFailureReport()

        # === STAGE 1: SQLite (Source of Truth) ===
        try:
            for chunk in chunks:
                # Simulated write operation
                self._write_to_sqlite(chunk)
                report.sqlite_success_count += 1
        except Exception as e:
            # SQLite failure = critical; don't proceed to LanceDB
            report.sqlite_exception = e
            return report  # Early exit: LanceDB stays in sync with last good state

        # === STAGE 2: LanceDB (Derived, Rebuildable) ===
        # Only reached if SQLite succeeded; data is safe
        try:
            for chunk in chunks:
                # Simulated vector store write
                self._write_to_lancedb(chunk)
                report.lancedb_success_count += 1
        except Exception as e:
            # LanceDB failure = degraded but not critical
            # Data is safe in SQLite; vector index can be rebuilt later
            report.lancedb_exception = e

        return report

    def delete_chunks_safely(self, chunk_hashes: list[str]) -> None:
        """Delete chunks from vector store using safe parameterized approach.

        SECURITY: Prevents SQL injection by validating input before constructing queries.
        Hashes are never interpolated directly into SQL strings via f-strings.

        Args:
            chunk_hashes: List of hex hash strings to delete

        Raises:
            ValueError: If any hash contains non-hex characters
        """
        # Validate each hash contains only hex characters (0-9, a-f, A-F)
        for hash_value in chunk_hashes:
            if not isinstance(hash_value, str):
                raise ValueError(f"Hash must be string, got {type(hash_value)}")
            if not all(c in "0123456789abcdefABCDEF" for c in hash_value):
                raise ValueError(f"Hash contains non-hex characters: {hash_value}")

        # Pass validated hashes to vector store as parameter list
        # The vector store implementation must use parameterized queries internally
        self._delete_from_lancedb(chunk_hashes)

    # === Private implementation methods (to be connected to actual stores) ===

    def _write_to_sqlite(self, chunk) -> None:
        """Write chunk to SQLite (source of truth).

        IMPLEMENTATION STUB: Replace with actual document store calls.
        Should include transaction wrapping for single-store atomicity.
        """
        pass

    def _write_to_lancedb(self, chunk) -> None:
        """Write chunk vector to LanceDB (derived index).

        IMPLEMENTATION STUB: Replace with actual vector store calls.
        Non-atomic by design; individual write failures don't rollback SQLite.
        """
        pass

    def _delete_from_lancedb(self, chunk_hashes: list[str]) -> None:
        """Delete chunks from vector store using parameterized approach.

        IMPLEMENTATION STUB: Replace with actual vector store calls.
        The vector_store.delete_chunks() method must accept the hash list as a parameter
        and construct SQL queries safely (not via string interpolation).
        """
        pass

    def rebuild_vector_index(self) -> None:
        """Rebuild LanceDB from SQLite source of truth.

        IMPLEMENTATION STUB: Use when LanceDB falls out of sync.
        Reads all chunks from SQLite, re-embeds, and rebuilds LanceDB.
        """
        pass
