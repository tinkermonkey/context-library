"""LanceDB-backed vector index; derived and fully rebuildable from the document store."""

import sqlite3
from pathlib import Path

from lancedb.pydantic import (  # type: ignore[import-untyped]
    LanceModel,
    Vector,
)
from pydantic import field_validator

from context_library.storage.models import Domain
from context_library.storage.validators import EMBEDDING_DIM, validate_iso8601_timestamp

VECTOR_DIR = Path.home() / ".context-library" / "vectors"


class SchemaConfigError(Exception):
    """Raised when PRAGMA configuration is invalid or schema cannot be applied."""

    pass


def apply_schema_and_validate_pragmas(conn: sqlite3.Connection) -> None:
    """Apply schema and validate PRAGMA configuration.

    Reads schema.sql, applies table definitions and PRAGMAs via executescript(),
    then validates PRAGMA settings.

    Args:
        conn: SQLite database connection

    Raises:
        SchemaConfigError: If schema file cannot be read, DDL fails, or PRAGMA
                          validation fails
    """
    schema_path = Path(__file__).parent / "schema.sql"

    # Read schema file with proper error handling
    try:
        with open(schema_path, "r") as f:
            schema_content = f.read()
    except FileNotFoundError as e:
        raise SchemaConfigError(
            f"Schema file not found at {schema_path}"
        ) from e

    cursor = conn.cursor()

    # Apply the full schema (PRAGMAs, table definitions, and triggers)
    # PRAGMAs are defined in schema.sql lines 1-4 and applied here
    try:
        cursor.executescript(schema_content)
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        raise SchemaConfigError(
            f"Failed to apply schema: {e}"
        ) from e

    # Validate pragmas are in effect
    validate_pragmas(conn)


def validate_pragmas(conn: sqlite3.Connection) -> None:
    """Validate that PRAGMAs are applied correctly.

    Checks that the critical PRAGMAs defined in schema.sql (lines 1-4) are in effect:
    - foreign_keys: ON (enforces foreign key constraints)
    - synchronous: NORMAL (balanced durability/performance)
    - user_version: >= 1 (schema versioning)
    - journal_mode: wal or memory (WAL mode or in-memory)

    Args:
        conn: SQLite database connection

    Raises:
        SchemaConfigError: If any PRAGMA has an unexpected value or cannot be
                          queried
    """
    cursor = conn.cursor()

    # Verify foreign_keys is ON
    cursor.execute("PRAGMA foreign_keys")
    result = cursor.fetchone()
    if result is None or result[0] != 1:
        raise SchemaConfigError("PRAGMA foreign_keys must be ON (1)")

    # Verify synchronous is NORMAL (1)
    cursor.execute("PRAGMA synchronous")
    result = cursor.fetchone()
    if result is None or result[0] != 1:
        raise SchemaConfigError("PRAGMA synchronous must be NORMAL (1)")

    # Verify user_version is set
    cursor.execute("PRAGMA user_version")
    result = cursor.fetchone()
    if result is None or result[0] < 1:
        raise SchemaConfigError("PRAGMA user_version must be >= 1")

    # Verify journal_mode is WAL or memory (memory for in-memory databases)
    cursor.execute("PRAGMA journal_mode")
    result = cursor.fetchone()
    if result is None or result[0] not in ("wal", "memory"):
        mode = result[0] if result else None
        raise SchemaConfigError(f"PRAGMA journal_mode must be 'wal' or 'memory', got {mode!r}")


class ChunkVector(LanceModel):
    """Schema for the LanceDB chunk_vectors table.

    chunk_hash is the join key to the SQLite chunks table.
    LanceDB is derived and disposable; it can be fully rebuilt from SQLite.
    """

    chunk_hash: str              # join key to SQLite chunks table
    content: str                 # denormalized for reranker access without SQLite lookup
    vector: Vector(EMBEDDING_DIM)  # type: ignore[valid-type]  # fixed-size embedding vector (float32 optimized storage)
    domain: Domain               # supports filtered vector search by domain
    source_id: str               # supports filtered vector search by source
    source_version: int          # supports filtered vector search by version
    created_at: str              # ISO 8601 timestamp

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: str) -> str:
        """Validate that created_at is a valid ISO 8601 timestamp."""
        validate_iso8601_timestamp(value)
        return value
