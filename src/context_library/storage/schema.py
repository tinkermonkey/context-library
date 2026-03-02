"""SQLite schema initialization and PRAGMA validation.

This module handles SQLite schema bootstrap and configuration validation.
PRAGMAs are applied via executescript() reading schema.sql, and the
configuration is validated to ensure correct application.

SchemaConfigError is raised if schema file cannot be read, DDL fails, or
PRAGMA validation fails. This module is independent of LanceDB and is
suitable for all SQLite concerns.
"""

import sqlite3
from pathlib import Path


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
