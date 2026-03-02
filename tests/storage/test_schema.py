"""Tests for SQLite schema initialization and PRAGMA validation."""

import sqlite3

import pytest

from context_library.storage.schema import (
    SchemaConfigError,
    apply_schema_and_validate_pragmas,
    validate_pragmas,
)


class TestApplySchemaAndValidatePragmas:
    """Tests for apply_schema_and_validate_pragmas()."""

    def test_successful_schema_application(self) -> None:
        """Successful schema application with PRAGMA validation."""
        # Create an in-memory database
        conn = sqlite3.connect(":memory:")
        # Apply schema and validate
        apply_schema_and_validate_pragmas(conn)

        # Verify tables were created
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='adapters'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_missing_schema_file_raises_schema_config_error(self, monkeypatch) -> None:
        """Missing schema.sql file raises SchemaConfigError, not FileNotFoundError."""

        def mock_open(*args, **kwargs):
            raise FileNotFoundError("No such file or directory")

        conn = sqlite3.connect(":memory:")
        monkeypatch.setattr("builtins.open", mock_open)

        with pytest.raises(SchemaConfigError) as exc_info:
            apply_schema_and_validate_pragmas(conn)

        assert "Failed to read schema file" in str(exc_info.value)
        conn.close()

    def test_permission_error_raises_schema_config_error(self, monkeypatch) -> None:
        """PermissionError (OSError subclass) raises SchemaConfigError."""

        def mock_open(*args, **kwargs):
            raise PermissionError("Permission denied")

        conn = sqlite3.connect(":memory:")
        monkeypatch.setattr("builtins.open", mock_open)

        with pytest.raises(SchemaConfigError) as exc_info:
            apply_schema_and_validate_pragmas(conn)

        assert "Failed to read schema file" in str(exc_info.value)
        conn.close()

    def test_invalid_sql_in_schema_raises_schema_config_error(self, monkeypatch) -> None:
        """Invalid SQL in schema.sql raises SchemaConfigError, not sqlite3.OperationalError."""
        conn = sqlite3.connect(":memory:")

        # Patch open to return invalid SQL
        import builtins
        original_open = builtins.open

        def mock_open(*args, **kwargs):
            from io import StringIO
            return StringIO("INVALID SQL SYNTAX HERE;")

        builtins.open = mock_open
        try:
            with pytest.raises(SchemaConfigError) as exc_info:
                apply_schema_and_validate_pragmas(conn)
            assert "Failed to apply schema" in str(exc_info.value)
        finally:
            builtins.open = original_open
            conn.close()


class TestValidatePragmas:
    """Tests for validate_pragmas() - focusing on valid configurations.

    Error path tests (foreign_keys, synchronous, user_version, journal_mode errors)
    are comprehensively covered in tests/storage/test_document_store.py:482-624
    (TestValidatePragmasErrorPaths) and are not duplicated here.
    """

    def test_valid_pragmas_pass(self) -> None:
        """Valid PRAGMA configuration passes without raising."""
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        # Set up correct PRAGMAs
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA user_version=1")
        cursor.execute("PRAGMA journal_mode=WAL")
        conn.commit()

        # Should not raise
        validate_pragmas(conn)
        conn.close()

    def test_journal_mode_memory_acceptable(self) -> None:
        """PRAGMA journal_mode=MEMORY is acceptable for in-memory databases."""
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        # Set up with journal_mode MEMORY
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA user_version=1")
        cursor.execute("PRAGMA journal_mode=MEMORY")
        conn.commit()

        # Should not raise
        validate_pragmas(conn)
        conn.close()

    def test_null_fetchone_result_raises_error(self) -> None:
        """Null fetchone() result from PRAGMA query raises SchemaConfigError."""

        # Create a wrapper that yields None for the first fetchone() to simulate
        # a PRAGMA query returning no results
        class NullResultConnection:
            def __init__(self):
                self._conn = sqlite3.connect(":memory:")

            def cursor(self):
                return NullResultCursor(self._conn.cursor())

            def __getattr__(self, name):
                return getattr(self._conn, name)

        class NullResultCursor:
            def __init__(self, real_cursor):
                self._cursor = real_cursor
                self._first_call = True

            def execute(self, query):
                return self._cursor.execute(query)

            def fetchone(self):
                if self._first_call:
                    self._first_call = False
                    return None  # Simulate null result
                return self._cursor.fetchone()

            def __getattr__(self, name):
                return getattr(self._cursor, name)

        conn_wrapper = NullResultConnection()
        try:
            with pytest.raises(SchemaConfigError) as exc_info:
                validate_pragmas(conn_wrapper)
            # Should fail on first PRAGMA (foreign_keys)
            assert "foreign_keys" in str(exc_info.value)
        finally:
            conn_wrapper._conn.close()
