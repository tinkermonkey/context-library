"""Integration test: FilesystemHelperAdapter tombstone retires chunks AND vectors.

Proves the deletion approach (adapter yields empty-markdown NormalizedContent for a
deleted source) drives the pipeline's existing Case-2 removal path to retire every
chunk in SQLite and delete every vector from the vector store.
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from context_library.adapters.filesystem_helper import FilesystemHelperAdapter
from context_library.core.differ import Differ
from context_library.core.embedder import Embedder
from context_library.core.pipeline import IngestionPipeline
from context_library.domains.documents import DocumentsDomain
from context_library.storage.chromadb_store import ChromaDBVectorStore
from context_library.storage.document_store import DocumentStore


# ---------------------------------------------------------------------------
# Wire-shape helpers (mirror the helper's NDJSON contract)
# ---------------------------------------------------------------------------

def _content_line(source_id: str, markdown: str) -> str:
    return json.dumps({
        "markdown": markdown,
        "source_id": source_id,
        "structural_hints": {
            "has_headings": True,
            "has_lists": False,
            "has_tables": False,
            "natural_boundaries": [],
            "file_path": source_id,
            "modified_at": "2026-03-15T10:00:00+00:00",
            "file_size_bytes": len(markdown.encode()),
            "extra_metadata": None,
        },
        "normalizer_version": "1.0.0",
    })


def _tombstone_line(source_id: str) -> str:
    return json.dumps({"op": "delete", "source_id": source_id, "modified_at": None})


def _meta_line(has_more: bool = False, next_cursor: str | None = None) -> str:
    return json.dumps({"has_more": has_more, "next_cursor": next_cursor})


@contextmanager
def _stream(lines: list[str]):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def iter_lines(self):
            yield from lines

    yield FakeResponse()


class _Recorder:
    def __init__(self, pages):
        self._pages = list(pages)

    def __call__(self, method, url, params=None, json=None, headers=None):
        lines = self._pages.pop(0) if self._pages else [_meta_line()]
        return _stream(lines)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def document_store():
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    path = tf.name
    tf.close()
    store = DocumentStore(path)
    yield store
    store.close()
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def pipeline(document_store):
    with tempfile.TemporaryDirectory() as tmpdir:
        vector_store = ChromaDBVectorStore(tmpdir)
        yield IngestionPipeline(
            document_store=document_store,
            embedder=Embedder(model_name="all-MiniLM-L6-v2"),
            differ=Differ(),
            vector_store=vector_store,
        )


@pytest.fixture
def chunker():
    return DocumentsDomain()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _count_active_chunks_all_versions(document_store, source_id: str) -> int:
    cur = document_store.conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM chunks WHERE source_id = ? AND retired_at IS NULL",
        (source_id,),
    )
    return cur.fetchone()[0]


class TestFilesystemTombstoneRetirement:
    def test_tombstone_retires_chunks_and_vectors(self, pipeline, chunker):
        adapter = FilesystemHelperAdapter(api_url="http://host:8000", api_key="k")

        # 1. Ingest a real file.
        ingest_pages = [[
            _content_line("doomed.md", "# Doomed\n\nThis content will be deleted later.\n"),
            _meta_line(has_more=False, next_cursor="1"),
        ]]
        with patch.object(adapter._client, "stream", side_effect=_Recorder(ingest_pages)):
            result = pipeline.ingest(adapter, chunker)

        assert result["sources_processed"] == 1
        assert result["chunks_added"] >= 1
        assert _count_active_chunks_all_versions(pipeline.document_store, "doomed.md") >= 1
        assert pipeline.vector_store.count() >= 1

        # 2. Helper streams a tombstone for the deleted file.
        delete_pages = [[
            _tombstone_line("doomed.md"),
            _meta_line(has_more=False, next_cursor="2"),
        ]]
        with patch.object(adapter._client, "stream", side_effect=_Recorder(delete_pages)):
            del_result = pipeline.ingest(adapter, chunker)

        # 3. SQLite: no active chunks remain for the source (all retired).
        assert _count_active_chunks_all_versions(pipeline.document_store, "doomed.md") == 0
        assert del_result["chunks_removed"] >= 1

        # 4. Vector store: every embedding for the source is gone.
        assert pipeline.vector_store.count() == 0

    def test_tombstone_only_retires_target_source(self, pipeline, chunker):
        """Deleting one file leaves another file's chunks + vectors intact."""
        adapter = FilesystemHelperAdapter(api_url="http://host:8000", api_key="k")

        ingest_pages = [[
            _content_line("keep.md", "# Keep\n\nThis content survives.\n"),
            _content_line("gone.md", "# Gone\n\nThis content is removed.\n"),
            _meta_line(has_more=False, next_cursor="1"),
        ]]
        with patch.object(adapter._client, "stream", side_effect=_Recorder(ingest_pages)):
            pipeline.ingest(adapter, chunker)

        keep_before = _count_active_chunks_all_versions(pipeline.document_store, "keep.md")
        total_before = pipeline.vector_store.count()
        assert keep_before >= 1
        assert total_before >= 2

        delete_pages = [[_tombstone_line("gone.md"), _meta_line(has_more=False, next_cursor="2")]]
        with patch.object(adapter._client, "stream", side_effect=_Recorder(delete_pages)):
            pipeline.ingest(adapter, chunker)

        # keep.md is untouched; gone.md is fully retired.
        assert _count_active_chunks_all_versions(pipeline.document_store, "keep.md") == keep_before
        assert _count_active_chunks_all_versions(pipeline.document_store, "gone.md") == 0
        # Only gone.md's vectors were removed.
        assert pipeline.vector_store.count() == keep_before
