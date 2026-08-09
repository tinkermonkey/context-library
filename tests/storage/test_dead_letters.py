"""Tests for the dead-letter store: durable record of skipped ingest failures."""

import os
import tempfile

import pytest

from context_library.storage.document_store import DocumentStore


@pytest.fixture
def store():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as temp_file:
        temp_path = temp_file.name
    ds = DocumentStore(temp_path)
    yield ds
    ds.close()
    try:
        os.unlink(temp_path)
    except OSError:
        pass


class TestRecordDeadLetter:
    def test_record_and_list(self, store):
        store.record_dead_letter("oura:default", "oura/sleep/2026-01-01", "ChunkingError", "boom")
        rows = store.list_dead_letters()
        assert len(rows) == 1
        row = rows[0]
        assert row["adapter_id"] == "oura:default"
        assert row["source_id"] == "oura/sleep/2026-01-01"
        assert row["error_type"] == "ChunkingError"
        assert row["message"] == "boom"
        assert row["retry_count"] == 0

    def test_repeat_failure_upserts_and_bumps_retry_count(self, store):
        store.record_dead_letter("a:1", "s1", "StorageError", "first")
        store.record_dead_letter("a:1", "s1", "StorageError", "second")
        rows = store.list_dead_letters()
        assert len(rows) == 1
        assert rows[0]["message"] == "second"
        assert rows[0]["retry_count"] == 1

    def test_distinct_error_types_are_separate_rows(self, store):
        store.record_dead_letter("a:1", "s1", "ChunkingError", "x")
        store.record_dead_letter("a:1", "s1", "EmbeddingError", "y")
        assert store.count_dead_letters() == 2

    def test_message_truncated(self, store):
        store.record_dead_letter("a:1", "s1", "E", "x" * 5000)
        assert len(store.list_dead_letters()[0]["message"]) == 2000


class TestListAndCount:
    def test_filter_by_adapter(self, store):
        store.record_dead_letter("a:1", "s1", "E", "m")
        store.record_dead_letter("b:1", "s2", "E", "m")
        assert store.count_dead_letters("a:1") == 1
        assert [r["adapter_id"] for r in store.list_dead_letters("a:1")] == ["a:1"]

    def test_limit(self, store):
        for i in range(5):
            store.record_dead_letter("a:1", f"s{i}", "E", "m")
        assert len(store.list_dead_letters(limit=3)) == 3
        assert store.count_dead_letters() == 5


class TestClear:
    def test_clear_by_source(self, store):
        store.record_dead_letter("a:1", "s1", "E", "m")
        store.record_dead_letter("a:1", "s2", "E", "m")
        deleted = store.clear_dead_letters(adapter_id="a:1", source_id="s1")
        assert deleted == 1
        assert store.count_dead_letters() == 1

    def test_clear_by_adapter(self, store):
        store.record_dead_letter("a:1", "s1", "E", "m")
        store.record_dead_letter("b:1", "s2", "E", "m")
        assert store.clear_dead_letters(adapter_id="a:1") == 1
        assert store.count_dead_letters() == 1

    def test_clear_all(self, store):
        store.record_dead_letter("a:1", "s1", "E", "m")
        store.record_dead_letter("b:1", "s2", "E", "m")
        assert store.clear_dead_letters() == 2
        assert store.count_dead_letters() == 0
