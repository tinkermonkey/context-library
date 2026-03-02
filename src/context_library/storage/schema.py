"""SQLite schema initialization and PRAGMA configuration.

This module handles SQLite schema bootstrap and PRAGMA configuration validation.

Session-level PRAGMAs (journal_mode, synchronous) are applied at connection time
via configure_connection(). Persistent PRAGMAs (foreign_keys, user_version) are
set via executescript() reading schema.sql. All PRAGMAs are validated to ensure
correct application.

SchemaConfigError is raised if schema file cannot be read, DDL fails, or
PRAGMA validation fails. This module is independent of LanceDB and is
suitable for all SQLite concerns.
"""

import sqlite3
from pathlib import Path


class SchemaConfigError(Exception):
    """Raised when PRAGMA configuration is invalid or schema cannot be applied."""

    pass


def configure_connection(conn: sqlite3.Connection) -> None:
    """Configure session-level PRAGMAs on the connection.

    Sets PRAGMAs that must be applied at connection initialization time:
    - journal_mode=WAL: Write-ahead logging for better concurrency
    - synchronous=NORMAL: Balanced durability and performance

    These PRAGMAs are session-level and cannot be set via executescript().
    Must be called immediately after creating a connection, before other operations.

    Args:
        conn: SQLite database connection

    Raises:
        SchemaConfigError: If PRAGMA configuration fails
    """
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.OperationalError as e:
        raise SchemaConfigError(f"Failed to configure connection PRAGMAs: {e}") from e


def apply_schema_and_validate_pragmas(conn: sqlite3.Connection) -> None:
    """Apply schema and validate PRAGMA configuration.

    Configures session-level PRAGMAs at connection time, reads schema.sql,
    applies table definitions and persistent PRAGMAs via executescript(),
    then validates all PRAGMA settings.

    Args:
        conn: SQLite database connection

    Raises:
        SchemaConfigError: If schema file cannot be read, DDL fails, or PRAGMA
                          validation fails
    """
    # Configure connection-time PRAGMAs (journal_mode, synchronous)
    configure_connection(conn)

    schema_path = Path(__file__).parent / "schema.sql"

    # Read schema file with proper error handling
    try:
        with open(schema_path, "r") as f:
            schema_content = f.read()
    except OSError as e:
        raise SchemaConfigError(
            f"Failed to read schema file at {schema_path}: {e}"
        ) from e

    cursor = conn.cursor()

    # Apply the schema (persistent PRAGMAs, table definitions, and triggers)
    try:
        cursor.executescript(schema_content)
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        raise SchemaConfigError(
            f"Failed to apply schema: {e}"
        ) from e

    # Validate all pragmas are in effect
    validate_pragmas(conn)


def validate_pragmas(conn: sqlite3.Connection) -> None:
    """Validate that PRAGMAs are applied correctly.

    Checks that the critical PRAGMAs are in effect:
    - foreign_keys: ON (persistent, set in schema.sql)
    - synchronous: NORMAL (session-level, set at connection time)
    - user_version: >= 1 (persistent, set in schema.sql)
    - journal_mode: wal or memory (session-level, set at connection time)

    Args:
        conn: SQLite database connection

    Raises:
        SchemaConfigError: If any PRAGMA has an unexpected value or cannot be
                          queried
    """
    cursor = conn.cursor()

    # Verify foreign_keys is ON
    try:
        cursor.execute("PRAGMA foreign_keys")
        result = cursor.fetchone()
    except sqlite3.OperationalError as e:
        raise SchemaConfigError(f"Failed to query PRAGMA foreign_keys: {e}") from e
    if result is None or result[0] != 1:
        raise SchemaConfigError("PRAGMA foreign_keys must be ON (1)")

    # Verify synchronous is NORMAL (1)
    try:
        cursor.execute("PRAGMA synchronous")
        result = cursor.fetchone()
    except sqlite3.OperationalError as e:
        raise SchemaConfigError(f"Failed to query PRAGMA synchronous: {e}") from e
    if result is None or result[0] != 1:
        raise SchemaConfigError("PRAGMA synchronous must be NORMAL (1)")

    # Verify user_version is set
    try:
        cursor.execute("PRAGMA user_version")
        result = cursor.fetchone()
    except sqlite3.OperationalError as e:
        raise SchemaConfigError(f"Failed to query PRAGMA user_version: {e}") from e
    if result is None or result[0] < 1:
        raise SchemaConfigError("PRAGMA user_version must be >= 1")

    # Verify journal_mode is WAL or memory (memory for in-memory databases)
    try:
        cursor.execute("PRAGMA journal_mode")
        result = cursor.fetchone()
    except sqlite3.OperationalError as e:
        raise SchemaConfigError(f"Failed to query PRAGMA journal_mode: {e}") from e
    if result is None or result[0] not in ("wal", "memory"):
        mode = result[0] if result else None
        raise SchemaConfigError(f"PRAGMA journal_mode must be 'wal' or 'memory', got {mode!r}")
