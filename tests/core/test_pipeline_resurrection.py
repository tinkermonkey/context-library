"""Regression: adapter reset + unchanged content must resurrect, not skip.

Production failure: reset_adapter() retires all chunks but preserves version
history; on re-ingest the differ saw identical hashes → the unchanged
short-circuit skipped the source → its chunks stayed retired forever."""

import os
import tempfile

import pytest

from context_library.adapters.base import BaseAdapter
from context_library.core.differ import Differ
from context_library.core.embedder import Embedder
from context_library.core.pipeline import IngestionPipeline
from context_library.domains.notes import NotesDomain
from context_library.storage.chromadb_store import ChromaDBVectorStore
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import (
    Domain,
    NormalizedContent,
    PollStrategy,
    StructuralHints,
)


class _StaticAdapter(BaseAdapter):
    """Yields one fixed markdown document every fetch."""

    def __init__(self):
        self.acked = 0

    @property
    def adapter_id(self):
        return "static:test"

    @property
    def domain(self):
        return Domain.NOTES

    @property
    def poll_strategy(self):
        return PollStrategy.PULL

    @property
    def normalizer_version(self):
        return "1.0"

    def fetch(self, source_ref: str):
        yield NormalizedContent(
            markdown="# Stable\n\nThis content never changes.",
            source_id="static/doc.md",
            structural_hints=StructuralHints(
                has_headings=True, has_lists=False, has_tables=False,
                natural_boundaries=[], file_path=None,
            ),
            normalizer_version="1.0",
        )


@pytest.fixture
def pipeline_env():
    dbf = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    dbf.close()
    ds = DocumentStore(dbf.name)
    with tempfile.TemporaryDirectory() as vdir:
        vs = ChromaDBVectorStore(vdir)
        pipe = IngestionPipeline(
            document_store=ds,
            embedder=Embedder(model_name="all-MiniLM-L6-v2"),
            differ=Differ(),
            vector_store=vs,
        )
        yield pipe, ds, vs
    ds.close()
    os.unlink(dbf.name)


class TestResetResurrection:
    def test_unchanged_source_with_retired_chunks_is_rewritten(self, pipeline_env):
        pipe, ds, vs = pipeline_env
        adapter = _StaticAdapter()
        chunker = NotesDomain()

        r1 = pipe.ingest(adapter, chunker, source_ref="")
        assert r1["sources_processed"] == 1
        assert ds.has_active_chunks("static/doc.md")
        vectors_before = vs.count()
        assert vectors_before > 0

        # Adapter reset: retires all chunks, preserves version history
        reset = ds.reset_adapter("static:test")
        assert reset["chunks_retired"] > 0
        assert not ds.has_active_chunks("static/doc.md")

        # Re-ingest identical content: must resurrect, not skip
        r2 = pipe.ingest(adapter, chunker, source_ref="")
        assert r2["sources_failed"] == 0
        assert ds.has_active_chunks("static/doc.md")
        assert vs.count() >= vectors_before  # vectors re-added

    def test_unchanged_source_with_active_chunks_still_skips(self, pipeline_env):
        pipe, ds, _ = pipeline_env
        adapter = _StaticAdapter()
        chunker = NotesDomain()

        pipe.ingest(adapter, chunker, source_ref="")
        v1 = ds.get_latest_version("static/doc.md")
        r2 = pipe.ingest(adapter, chunker, source_ref="")
        assert r2["chunks_added"] == 0
        assert ds.get_latest_version("static/doc.md") == v1  # no new version
