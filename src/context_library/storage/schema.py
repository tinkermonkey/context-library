"""SQLite schema initialization with PRAGMA validation.

Provides utilities to apply the schema and validate PRAGMA configuration
to ensure correct database behavior.
"""

import sqlite3
from pathlib import Path


def apply_schema_and_validate_pragmas(conn: sqlite3.Connection) -> None:
    """Apply schema and validate PRAGMA configuration.

    Reads schema.sql and applies all PRAGMAs and table definitions.
    The schema file contains PRAGMAs that are applied via executescript().

    Args:
        conn: SQLite database connection

    Raises:
        sqlite3.DatabaseError: If schema cannot be applied
    """
    schema_path = Path(__file__).parent / "schema.sql"
    with open(schema_path, "r") as f:
        schema_content = f.read()

    cursor = conn.cursor()

    # Apply schema which includes all PRAGMA statements
    cursor.executescript(schema_content)
    conn.commit()


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
        ValueError: If any PRAGMA has an unexpected value
    """
    cursor = conn.cursor()

    # Verify foreign_keys is ON
    cursor.execute("PRAGMA foreign_keys")
    if cursor.fetchone()[0] != 1:
        raise ValueError("PRAGMA foreign_keys must be ON (1)")

    # Verify synchronous is NORMAL (1)
    cursor.execute("PRAGMA synchronous")
    if cursor.fetchone()[0] != 1:
        raise ValueError("PRAGMA synchronous must be NORMAL (1)")

    # Verify user_version is set
    cursor.execute("PRAGMA user_version")
    if cursor.fetchone()[0] < 1:
        raise ValueError("PRAGMA user_version must be >= 1")

    # Verify journal_mode is WAL or memory (memory for in-memory databases)
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    if mode not in ("wal", "memory"):
        raise ValueError(f"PRAGMA journal_mode must be 'wal' or 'memory', got {mode!r}")
