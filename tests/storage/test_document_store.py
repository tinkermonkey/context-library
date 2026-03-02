"""Tests for the document store.

Tests include schema validation for the SQLite DDL.
Implementation of document store operations will be covered when the module is implemented.
"""

import re
import sqlite3
import time
from pathlib import Path

import pytest

from src.context_library.storage.models import Domain
from src.context_library.storage.schema import (
    SchemaConfigError,
    apply_schema_and_validate_pragmas,
    validate_pragmas,
)


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

    def test_schema_uses_pragma_user_version(self) -> None:
        """Schema uses PRAGMA user_version for schema versioning (not a schema_version table)."""
        with open(self.SCHEMA_PATH, "r") as f:
            schema_content = f.read()

        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        try:
            cursor.executescript(schema_content)
            conn.commit()

            # Verify PRAGMA user_version is set
            cursor.execute("PRAGMA user_version")
            version = cursor.fetchone()[0]
            assert version >= 1, f"Expected user_version >= 1, got {version}"

            # Verify there is no separate schema_version table
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
            )
            result = cursor.fetchone()
            assert result is None, "Schema should not have a separate schema_version table; PRAGMA user_version is used instead"
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

    def test_schema_applies_pragmas_correctly(self) -> None:
        """Schema PRAGMA settings are applied and validated individually."""
        with open(self.SCHEMA_PATH, "r") as f:
            schema_content = f.read()

        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        try:
            cursor.executescript(schema_content)
            conn.commit()

            # Verify foreign_keys is ON
            cursor.execute("PRAGMA foreign_keys")
            assert cursor.fetchone()[0] == 1, "foreign_keys should be ON (1)"

            # Verify synchronous is NORMAL (1)
            cursor.execute("PRAGMA synchronous")
            assert cursor.fetchone()[0] == 1, "synchronous should be NORMAL (1)"

            # Verify user_version is set
            cursor.execute("PRAGMA user_version")
            assert cursor.fetchone()[0] >= 1, "user_version should be >= 1"

            # Verify journal_mode (should be 'memory' for in-memory DB)
            cursor.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            assert mode in ("wal", "memory"), f"journal_mode should be 'wal' or 'memory', got {mode}"
        finally:
            conn.close()

    def test_schema_init_helper_applies_schema(self) -> None:
        """apply_schema_and_validate_pragmas helper correctly initializes schema."""
        conn = sqlite3.connect(":memory:")

        try:
            apply_schema_and_validate_pragmas(conn)

            # Verify tables were created
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
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

            # Verify PRAGMAs are set
            validate_pragmas(conn)
        finally:
            conn.close()

    def test_pragma_validation_helper(self) -> None:
        """validate_pragmas helper detects correct PRAGMA configuration."""
        with open(self.SCHEMA_PATH, "r") as f:
            schema_content = f.read()

        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        try:
            cursor.executescript(schema_content)
            conn.commit()

            # This should not raise - all PRAGMAs are correct
            validate_pragmas(conn)
        finally:
            conn.close()

    def test_domain_enum_matches_schema_constraints(self) -> None:
        """Domain enum values match all CHECK constraints in schema."""
        with open(self.SCHEMA_PATH, "r") as f:
            schema_content = f.read()

        # Get Domain enum values
        enum_values = {domain.value for domain in Domain}

        # Extract all CHECK constraints for domain columns from schema
        # Pattern: CHECK (domain IN ('...', '...', ...))
        pattern = r"CHECK\s*\(\s*domain\s+IN\s*\((.*?)\)\s*\)"
        matches = re.findall(pattern, schema_content)

        assert len(matches) >= 3, "Expected at least 3 domain CHECK constraints in schema"

        for match in matches:
            # Extract quoted values from the constraint
            constraint_values = set(re.findall(r"'([^']+)'", match))
            assert (
                enum_values == constraint_values
            ), f"Domain enum {enum_values} doesn't match constraint {constraint_values}"

    def test_adapters_domain_constraint(self) -> None:
        """adapters.domain CHECK constraint rejects invalid values."""
        with open(self.SCHEMA_PATH, "r") as f:
            schema_content = f.read()

        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        try:
            cursor.executescript(schema_content)
            conn.commit()

            # Try to insert adapter with invalid domain
            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute(
                    "INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version) "
                    "VALUES ('test_adapter', 'invalid_domain', 'type1', '1.0')"
                )
        finally:
            conn.close()

    def test_sources_domain_constraint(self) -> None:
        """sources.domain CHECK constraint rejects invalid values."""
        with open(self.SCHEMA_PATH, "r") as f:
            schema_content = f.read()

        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        try:
            cursor.executescript(schema_content)
            conn.commit()

            # Insert valid adapter first
            cursor.execute(
                "INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version) "
                "VALUES ('adapter1', 'messages', 'type1', '1.0')"
            )

            # Try to insert source with invalid domain
            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute(
                    "INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy) "
                    "VALUES ('src1', 'adapter1', 'invalid_domain', 'ref1', 'pull')"
                )
        finally:
            conn.close()

    def test_chunks_domain_constraint(self) -> None:
        """chunks.domain CHECK constraint rejects invalid values."""
        with open(self.SCHEMA_PATH, "r") as f:
            schema_content = f.read()

        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        try:
            cursor.executescript(schema_content)
            conn.commit()

            # Set up prerequisites
            cursor.execute(
                "INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version) "
                "VALUES ('adapter1', 'messages', 'type1', '1.0')"
            )
            cursor.execute(
                "INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy) "
                "VALUES ('src1', 'adapter1', 'messages', 'ref1', 'pull')"
            )
            cursor.execute(
                "INSERT INTO source_versions (source_id, version, markdown, chunk_hashes, adapter_id, normalizer_version, fetch_timestamp) "
                "VALUES ('src1', 1, 'md', '[]', 'adapter1', '1.0', datetime('now'))"
            )

            # Try to insert chunk with invalid domain
            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute(
                    "INSERT INTO chunks (chunk_hash, source_id, source_version, chunk_index, content, domain, adapter_id, fetch_timestamp, normalizer_version) "
                    "VALUES ('hash1', 'src1', 1, 0, 'content', 'invalid_domain', 'adapter1', datetime('now'), '1.0')"
                )
        finally:
            conn.close()

    def test_sources_poll_strategy_constraint(self) -> None:
        """sources.poll_strategy CHECK constraint rejects invalid values."""
        with open(self.SCHEMA_PATH, "r") as f:
            schema_content = f.read()

        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        try:
            cursor.executescript(schema_content)
            conn.commit()

            # Insert valid adapter first
            cursor.execute(
                "INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version) "
                "VALUES ('adapter1', 'messages', 'type1', '1.0')"
            )

            # Try to insert source with invalid poll_strategy
            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute(
                    "INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy) "
                    "VALUES ('src1', 'adapter1', 'messages', 'ref1', 'invalid_strategy')"
                )
        finally:
            conn.close()

    def test_chunks_chunk_type_constraint(self) -> None:
        """chunks.chunk_type CHECK constraint rejects invalid values."""
        with open(self.SCHEMA_PATH, "r") as f:
            schema_content = f.read()

        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        try:
            cursor.executescript(schema_content)
            conn.commit()

            # Set up prerequisites
            cursor.execute(
                "INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version) "
                "VALUES ('adapter1', 'messages', 'type1', '1.0')"
            )
            cursor.execute(
                "INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy) "
                "VALUES ('src1', 'adapter1', 'messages', 'ref1', 'pull')"
            )
            cursor.execute(
                "INSERT INTO source_versions (source_id, version, markdown, chunk_hashes, adapter_id, normalizer_version, fetch_timestamp) "
                "VALUES ('src1', 1, 'md', '[]', 'adapter1', '1.0', datetime('now'))"
            )

            # Try to insert chunk with invalid chunk_type
            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute(
                    "INSERT INTO chunks (chunk_hash, source_id, source_version, chunk_index, content, domain, adapter_id, fetch_timestamp, normalizer_version, chunk_type) "
                    "VALUES ('hash1', 'src1', 1, 0, 'content', 'messages', 'adapter1', datetime('now'), '1.0', 'invalid_type')"
                )
        finally:
            conn.close()

    def test_sources_update_timestamp_trigger(self) -> None:
        """sources_update_timestamp trigger updates updated_at on row modification."""
        with open(self.SCHEMA_PATH, "r") as f:
            schema_content = f.read()

        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        try:
            cursor.executescript(schema_content)
            conn.commit()

            # Insert adapter and source with known timestamp
            old_time = "2020-01-01 00:00:00"
            cursor.execute(
                "INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version, updated_at) "
                "VALUES ('adapter1', 'messages', 'type1', '1.0', ?)",
                (old_time,),
            )
            cursor.execute(
                "INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy, updated_at) "
                "VALUES ('src1', 'adapter1', 'messages', 'ref1', 'pull', ?)",
                (old_time,),
            )
            conn.commit()

            # Get original timestamp
            cursor.execute("SELECT updated_at FROM sources WHERE source_id = 'src1'")
            original_ts = cursor.fetchone()[0]
            assert original_ts == old_time

            # Wait a bit and update a non-timestamp column
            time.sleep(0.01)
            cursor.execute("UPDATE sources SET origin_ref = 'ref2' WHERE source_id = 'src1'")
            conn.commit()

            # Verify updated_at has changed
            cursor.execute("SELECT updated_at FROM sources WHERE source_id = 'src1'")
            new_ts = cursor.fetchone()[0]
            assert new_ts != old_time, "Trigger should have updated the timestamp"
        finally:
            conn.close()

    def test_adapters_update_timestamp_trigger(self) -> None:
        """adapters_update_timestamp trigger updates updated_at on row modification."""
        with open(self.SCHEMA_PATH, "r") as f:
            schema_content = f.read()

        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        try:
            cursor.executescript(schema_content)
            conn.commit()

            # Insert adapter with known timestamp
            old_time = "2020-01-01 00:00:00"
            cursor.execute(
                "INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version, updated_at) "
                "VALUES ('adapter1', 'messages', 'type1', '1.0', ?)",
                (old_time,),
            )
            conn.commit()

            # Get original timestamp
            cursor.execute("SELECT updated_at FROM adapters WHERE adapter_id = 'adapter1'")
            original_ts = cursor.fetchone()[0]
            assert original_ts == old_time

            # Wait a bit and update a non-timestamp column
            time.sleep(0.01)
            cursor.execute("UPDATE adapters SET adapter_type = 'type2' WHERE adapter_id = 'adapter1'")
            conn.commit()

            # Verify updated_at has changed
            cursor.execute("SELECT updated_at FROM adapters WHERE adapter_id = 'adapter1'")
            new_ts = cursor.fetchone()[0]
            assert new_ts != old_time, "Trigger should have updated the timestamp"
        finally:
            conn.close()

    def test_triggers_prevent_recursion(self) -> None:
        """Trigger WHEN guard prevents infinite recursion when updating updated_at.

        The trigger fires when NEW.updated_at = OLD.updated_at and updates to CURRENT_TIMESTAMP.
        When we directly set updated_at to a different value, NEW.updated_at != OLD.updated_at,
        so the WHEN clause is FALSE and the trigger does not fire.
        """
        with open(self.SCHEMA_PATH, "r") as f:
            schema_content = f.read()

        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        try:
            cursor.executescript(schema_content)
            conn.commit()

            # Insert adapter
            cursor.execute(
                "INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version) "
                "VALUES ('adapter1', 'messages', 'type1', '1.0')"
            )
            conn.commit()

            # Get the inserted timestamp
            cursor.execute("SELECT updated_at FROM adapters WHERE adapter_id = 'adapter1'")
            first_ts = cursor.fetchone()[0]

            # Directly set updated_at to a different value
            # Since NEW.updated_at != OLD.updated_at, the WHEN clause is FALSE and trigger does not fire
            different_ts = "2099-01-01 00:00:00"
            cursor.execute("UPDATE adapters SET updated_at = ? WHERE adapter_id = 'adapter1'", (different_ts,))
            conn.commit()

            # Verify updated_at is still the different value (trigger didn't fire)
            cursor.execute("SELECT updated_at FROM adapters WHERE adapter_id = 'adapter1'")
            final_ts = cursor.fetchone()[0]
            assert final_ts == different_ts, "WHEN guard should prevent trigger from updating when NEW.updated_at != OLD.updated_at"
        finally:
            conn.close()

    def test_chunks_default_chunk_type(self) -> None:
        """chunks.chunk_type defaults to 'standard' when not provided."""
        with open(self.SCHEMA_PATH, "r") as f:
            schema_content = f.read()

        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        try:
            cursor.executescript(schema_content)
            conn.commit()

            # Set up prerequisites
            cursor.execute(
                "INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version) "
                "VALUES ('adapter1', 'messages', 'type1', '1.0')"
            )
            cursor.execute(
                "INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy) "
                "VALUES ('src1', 'adapter1', 'messages', 'ref1', 'pull')"
            )
            cursor.execute(
                "INSERT INTO source_versions (source_id, version, markdown, chunk_hashes, adapter_id, normalizer_version, fetch_timestamp) "
                "VALUES ('src1', 1, 'md', '[]', 'adapter1', '1.0', datetime('now'))"
            )

            # Insert chunk without specifying chunk_type
            cursor.execute(
                "INSERT INTO chunks (chunk_hash, source_id, source_version, chunk_index, content, domain, adapter_id, fetch_timestamp, normalizer_version) "
                "VALUES ('hash1', 'src1', 1, 0, 'content', 'messages', 'adapter1', datetime('now'), '1.0')"
            )
            conn.commit()

            # Verify chunk_type defaults to 'standard'
            cursor.execute("SELECT chunk_type FROM chunks WHERE chunk_hash = 'hash1'")
            chunk_type = cursor.fetchone()[0]
            assert chunk_type == "standard", f"chunk_type should default to 'standard', got {chunk_type}"
        finally:
            conn.close()

    def test_adapters_default_enabled(self) -> None:
        """adapters.enabled defaults to 1 (true) when not provided."""
        with open(self.SCHEMA_PATH, "r") as f:
            schema_content = f.read()

        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        try:
            cursor.executescript(schema_content)
            conn.commit()

            # Insert adapter without specifying enabled
            cursor.execute(
                "INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version) "
                "VALUES ('adapter1', 'messages', 'type1', '1.0')"
            )
            conn.commit()

            # Verify enabled defaults to 1
            cursor.execute("SELECT enabled FROM adapters WHERE adapter_id = 'adapter1'")
            enabled = cursor.fetchone()[0]
            assert enabled == 1, f"enabled should default to 1, got {enabled}"
        finally:
            conn.close()

    def test_source_versions_unique_constraint(self) -> None:
        """source_versions has unique constraint on (source_id, version)."""
        with open(self.SCHEMA_PATH, "r") as f:
            schema_content = f.read()

        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        try:
            cursor.executescript(schema_content)
            conn.commit()

            # Set up prerequisites
            cursor.execute(
                "INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version) "
                "VALUES ('adapter1', 'messages', 'type1', '1.0')"
            )
            cursor.execute(
                "INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy) "
                "VALUES ('src1', 'adapter1', 'messages', 'ref1', 'pull')"
            )

            # Insert first version
            cursor.execute(
                "INSERT INTO source_versions (source_id, version, markdown, chunk_hashes, adapter_id, normalizer_version, fetch_timestamp) "
                "VALUES ('src1', 1, 'md1', '[]', 'adapter1', '1.0', datetime('now'))"
            )
            conn.commit()

            # Try to insert duplicate (source_id, version)
            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute(
                    "INSERT INTO source_versions (source_id, version, markdown, chunk_hashes, adapter_id, normalizer_version, fetch_timestamp) "
                    "VALUES ('src1', 1, 'md2', '[]', 'adapter1', '1.0', datetime('now'))"
                )
        finally:
            conn.close()
