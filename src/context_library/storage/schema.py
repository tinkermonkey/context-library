"""SQLite schema initialization with PRAGMA validation.

Provides utilities to apply the schema and validate PRAGMA configuration
to ensure correct database behavior.
"""

import sqlite3
from pathlib import Path


class SchemaConfigError(Exception):
    """Raised when PRAGMA configuration is invalid or schema cannot be applied."""

    pass


def apply_schema_and_validate_pragmas(conn: sqlite3.Connection) -> None:
    """Apply schema and validate PRAGMA configuration.

    Reads schema.sql, applies PRAGMAs via individual execute() calls with
    verification, and applies table definitions via executescript().

    Args:
        conn: SQLite database connection

    Raises:
        SchemaConfigError: If PRAGMA application or validation fails
    """
    schema_path = Path(__file__).parent / "schema.sql"
    with open(schema_path, "r") as f:
        schema_content = f.read()

    cursor = conn.cursor()

    # Apply critical PRAGMAs individually with verification
    _apply_pragmas(cursor)

    # Apply the full schema (table definitions and triggers)
    cursor.executescript(schema_content)
    conn.commit()

    # Validate pragmas are in effect
    validate_pragmas(conn)


def _apply_pragmas(cursor: sqlite3.Cursor) -> None:
    """Apply critical PRAGMAs via individual execute() calls with verification.

    Raises:
        SchemaConfigError: If PRAGMA application or verification fails
    """
    # Apply and verify foreign_keys=ON
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA foreign_keys")
    if cursor.fetchone()[0] != 1:
        raise SchemaConfigError("Failed to enable PRAGMA foreign_keys")

    # Apply and verify synchronous=NORMAL
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA synchronous")
    if cursor.fetchone()[0] != 1:
        raise SchemaConfigError("Failed to set PRAGMA synchronous=NORMAL")

    # Apply and verify user_version=1
    cursor.execute("PRAGMA user_version=1")
    cursor.execute("PRAGMA user_version")
    if cursor.fetchone()[0] < 1:
        raise SchemaConfigError("Failed to set PRAGMA user_version>=1")

    # Apply and verify journal_mode (WAL or memory for in-memory databases)
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    if mode not in ("wal", "memory"):
        raise SchemaConfigError(f"Failed to set journal_mode to WAL; got {mode!r}")


def validate_pragmas(conn: sqlite3.Connection) -> None:
    """Validate that PRAGMAs are applied correctly.

    Checks that the critical PRAGMAs set by schema.sql are in effect:
    - foreign_keys: ON (enforces foreign key constraints)
    - synchronous: NORMAL (balanced durability/performance)
    - user_version: >= 1 (schema versioning)
    - journal_mode: wal or memory (WAL mode or in-memory)

    Args:
        conn: SQLite database connection

    Raises:
        SchemaConfigError: If any PRAGMA has an unexpected value
    """
    cursor = conn.cursor()

    # Verify foreign_keys is ON
    cursor.execute("PRAGMA foreign_keys")
    if cursor.fetchone()[0] != 1:
        raise SchemaConfigError("PRAGMA foreign_keys must be ON (1)")

    # Verify synchronous is NORMAL (1)
    cursor.execute("PRAGMA synchronous")
    if cursor.fetchone()[0] != 1:
        raise SchemaConfigError("PRAGMA synchronous must be NORMAL (1)")

    # Verify user_version is set
    cursor.execute("PRAGMA user_version")
    if cursor.fetchone()[0] < 1:
        raise SchemaConfigError("PRAGMA user_version must be >= 1")

    # Verify journal_mode is WAL or memory (memory for in-memory databases)
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    if mode not in ("wal", "memory"):
        raise SchemaConfigError(f"PRAGMA journal_mode must be 'wal' or 'memory', got {mode!r}")
