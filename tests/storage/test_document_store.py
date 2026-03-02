"""Tests for the document store.

Tests include schema validation for the SQLite DDL.
Implementation of document store operations will be covered when the module is implemented.
"""

import sqlite3
from pathlib import Path

import pytest


class TestSchemaInitialization:
    """Tests for document store schema initialization via schema.sql."""

    SCHEMA_PATH = Path(__file__).parent.parent.parent / "src" / "context_library" / "storage" / "schema.sql"

    def test_schema_file_exists(self) -> None:
        """Schema file exists at expected location."""
        assert self.SCHEMA_PATH.exists(), f"Schema file not found at {self.SCHEMA_PATH}"

    def test_schema_file_is_readable(self) -> None:
        """Schema file can be read without errors."""
        with open(self.SCHEMA_PATH, "r") as f:
            content = f.read()
        assert len(content) > 0, "Schema file is empty"
        assert "CREATE TABLE" in content, "Schema file does not contain table definitions"

    def test_schema_applies_without_syntax_error(self) -> None:
        """Schema can be applied to an in-memory SQLite database without syntax errors."""
        with open(self.SCHEMA_PATH, "r") as f:
            schema_content = f.read()

        # Use in-memory database for testing
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        try:
            # Execute schema; should not raise
            cursor.executescript(schema_content)
            conn.commit()
        finally:
            conn.close()

    def test_schema_creates_required_tables(self) -> None:
        """Schema creates all expected tables."""
        with open(self.SCHEMA_PATH, "r") as f:
            schema_content = f.read()

        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        try:
            cursor.executescript(schema_content)
            conn.commit()

            # Query sqlite_master to verify table creation
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row[0] for row in cursor.fetchall()}

            expected_tables = {
                "adapters",
                "sources",
                "source_versions",
                "chunks",
                "lancedb_sync_log"
            }
            assert expected_tables.issubset(tables), (
                f"Missing tables: {expected_tables - tables}"
            )
        finally:
            conn.close()

    def test_schema_enforces_foreign_keys(self) -> None:
        """Schema enables foreign key constraints."""
        with open(self.SCHEMA_PATH, "r") as f:
            schema_content = f.read()

        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        try:
            cursor.executescript(schema_content)

            # Check that PRAGMA foreign_keys is on (enforced)
            cursor.execute("PRAGMA foreign_keys")
            result = cursor.fetchone()
            # Result should be (1,) when ON
            assert result[0] == 1, "Foreign keys not enforced by schema"
        finally:
            conn.close()

    def test_schema_rejects_invalid_foreign_keys(self) -> None:
        """Schema enforces foreign key constraints by rejecting invalid INSERTs."""
        with open(self.SCHEMA_PATH, "r") as f:
            schema_content = f.read()

        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        try:
            cursor.executescript(schema_content)
            conn.commit()

            # Attempt to insert a source with a non-existent adapter_id
            # This should raise an IntegrityError due to FK constraint
            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute(
                    "INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy) "
                    "VALUES ('test_source_1', 'nonexistent_adapter', 'messages', 'ref1', 'pull')"
                )
        finally:
            conn.close()
