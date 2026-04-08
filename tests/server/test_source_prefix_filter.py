"""Tests for source_id_prefix filtering on GET /sources endpoint."""

from fastapi.testclient import TestClient
import pytest
import tempfile
import os
from context_library.server.app import create_app
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import (
    AdapterConfig,
    Chunk,
    ChunkType,
    Domain,
    LineageRecord,
    PollStrategy,
    compute_chunk_hash,
)
from unittest.mock import MagicMock
from contextlib import asynccontextmanager
from typing import Generator, AsyncGenerator, Any


def _create_app_with_store(ds: DocumentStore) -> Generator[TestClient, None, None]:
    """Helper to create a FastAPI TestClient with document store."""
    mock_embedder = MagicMock()
    mock_embedder.model_id = "all-MiniLM-L6-v2"
    mock_embedder.dimension = 384
    mock_embedder.embed_query.return_value = [0.1] * 384

    mock_vector_store = MagicMock()
    mock_vector_store.count.return_value = 0
    mock_vector_store.search.return_value = []

    @asynccontextmanager
    async def noop_lifespan(app: Any) -> AsyncGenerator[None, None]:
        mock_config = MagicMock()
        mock_config.webhook_secret = None
        app.state.document_store = ds
        app.state.embedder = mock_embedder
        app.state.vector_store = mock_vector_store
        app.state.pipeline = MagicMock()
        app.state.reranker = None
        app.state.config = mock_config
        app.state.helper_adapters = []
        app.state.helper_health_cache = None
        yield

    app = create_app()
    app.router.lifespan_context = noop_lifespan

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture()
def ds_with_hierarchical_sources() -> Generator[DocumentStore, None, None]:
    """DocumentStore with hierarchical source_ids for prefix filtering tests."""
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_path = temp_file.name
    temp_file.close()

    store = DocumentStore(temp_path, check_same_thread=False)

    # Register filesystem adapter
    config = AdapterConfig(
        adapter_id="filesystem:default",
        adapter_type="filesystem",
        domain=Domain.DOCUMENTS,
        normalizer_version="1.0.0",
    )
    store.register_adapter(config)

    # Create sources with hierarchical paths
    test_sources = [
        "projects/alpha/doc1.md",
        "projects/alpha/doc2.md",
        "projects/alpha/subfolder/doc3.md",
        "projects/beta/doc4.md",
        "projects/beta/subfolder/doc5.md",
        "notes/personal/doc6.md",
        "notes/work/doc7.md",
    ]

    for source_id in test_sources:
        store.register_source(
            source_id=source_id,
            adapter_id="filesystem:default",
            domain=Domain.DOCUMENTS,
            origin_ref=f"/fs/{source_id}",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )

        # Create version 1 with a chunk
        content = f"Content for {source_id}"
        chunk_hash = compute_chunk_hash(content)
        chunk = Chunk(
            chunk_hash=chunk_hash,
            content=content,
            context_header=f"# {source_id}",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
        )

        store.create_source_version(
            source_id=source_id,
            version=1,
            markdown=f"# {source_id}\n{content}",
            chunk_hashes=[chunk_hash],
            adapter_id="filesystem:default",
            normalizer_version="1.0.0",
            fetch_timestamp="2024-01-01T00:00:00+00:00",
        )
        lineage = LineageRecord(
            chunk_hash=chunk_hash,
            source_id=source_id,
            source_version_id=1,
            adapter_id="filesystem:default",
            domain=Domain.DOCUMENTS,
            normalizer_version="1.0.0",
            embedding_model_id="all-MiniLM-L6-v2",
        )
        store.write_chunks(
            chunks=[chunk],
            lineage_records=[lineage],
        )

    yield store

    # Cleanup
    store.close()
    try:
        os.unlink(temp_path)
    except OSError:
        pass


@pytest.fixture()
def client_with_hierarchical_sources(
    ds_with_hierarchical_sources: DocumentStore,
) -> Generator[TestClient, None, None]:
    """TestClient with hierarchical sources fixture."""
    yield from _create_app_with_store(ds_with_hierarchical_sources)


class TestSourceIdPrefixFilter:
    """Test source_id_prefix filtering functionality."""

    def test_prefix_filter_returns_matching_sources(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that prefix filter returns only sources starting with prefix."""
        resp = client_with_hierarchical_sources.get("/sources?source_id_prefix=projects/alpha/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        source_ids = [s["source_id"] for s in data["sources"]]
        assert "projects/alpha/doc1.md" in source_ids
        assert "projects/alpha/doc2.md" in source_ids
        assert "projects/alpha/subfolder/doc3.md" in source_ids
        # Should not include other projects
        assert "projects/beta/doc4.md" not in source_ids

    def test_prefix_filter_with_beta_project(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test prefix filter for a different project."""
        resp = client_with_hierarchical_sources.get("/sources?source_id_prefix=projects/beta/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        source_ids = [s["source_id"] for s in data["sources"]]
        assert "projects/beta/doc4.md" in source_ids
        assert "projects/beta/subfolder/doc5.md" in source_ids

    def test_prefix_filter_for_notes(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test prefix filter for notes folder."""
        resp = client_with_hierarchical_sources.get("/sources?source_id_prefix=notes/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        source_ids = [s["source_id"] for s in data["sources"]]
        assert "notes/personal/doc6.md" in source_ids
        assert "notes/work/doc7.md" in source_ids

    def test_nonexistent_prefix_returns_empty_list(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that nonexistent prefix returns empty list with HTTP 200."""
        resp = client_with_hierarchical_sources.get("/sources?source_id_prefix=nonexistent/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["sources"] == []

    def test_no_prefix_param_returns_all(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that omitting prefix param returns all sources."""
        resp = client_with_hierarchical_sources.get("/sources")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 7
        assert len(data["sources"]) == 7

    def test_prefix_filter_with_domain_filter(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that prefix filter composes with domain filter."""
        resp = client_with_hierarchical_sources.get(
            "/sources?source_id_prefix=projects/alpha/&domain=documents"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        source_ids = [s["source_id"] for s in data["sources"]]
        assert "projects/alpha/doc1.md" in source_ids

    def test_prefix_filter_with_adapter_filter(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that prefix filter composes with adapter_id filter."""
        resp = client_with_hierarchical_sources.get(
            "/sources?source_id_prefix=projects/&adapter_id=filesystem:default"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        # All projects sources
        source_ids = [s["source_id"] for s in data["sources"]]
        assert all(s.startswith("projects/") for s in source_ids)

    def test_prefix_filter_with_both_domain_and_adapter_filters(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that all three filters compose conjunctively."""
        resp = client_with_hierarchical_sources.get(
            "/sources?source_id_prefix=projects/beta/&domain=documents&adapter_id=filesystem:default"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        source_ids = [s["source_id"] for s in data["sources"]]
        assert "projects/beta/doc4.md" in source_ids
        assert "projects/beta/subfolder/doc5.md" in source_ids

    def test_prefix_filter_respects_pagination(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that prefix filter respects pagination parameters."""
        resp = client_with_hierarchical_sources.get(
            "/sources?source_id_prefix=projects/&limit=2&offset=0"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5  # Total matching count
        assert len(data["sources"]) == 2  # Page size
        assert data["limit"] == 2
        assert data["offset"] == 0

    def test_prefix_filter_pagination_offset(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test pagination offset with prefix filter."""
        resp = client_with_hierarchical_sources.get(
            "/sources?source_id_prefix=projects/&limit=2&offset=2"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["sources"]) == 2
        assert data["offset"] == 2

    def test_empty_prefix_string_matches_all(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that empty prefix string matches all sources."""
        resp = client_with_hierarchical_sources.get("/sources?source_id_prefix=")
        assert resp.status_code == 200
        data = resp.json()
        # Empty string matches everything (all sources start with empty string)
        assert data["total"] == 7

    def test_prefix_case_insensitive(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that prefix matching is case-insensitive (SQLite LIKE behavior)."""
        resp = client_with_hierarchical_sources.get("/sources?source_id_prefix=Projects/")
        assert resp.status_code == 200
        data = resp.json()
        # SQLite LIKE is case-insensitive by default
        assert data["total"] == 5
        source_ids = [s["source_id"] for s in data["sources"]]
        assert all(s.lower().startswith("projects/") for s in source_ids)

    def test_partial_path_prefix(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test prefix matching on partial folder names."""
        resp = client_with_hierarchical_sources.get("/sources?source_id_prefix=projects/alpha/sub")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["sources"][0]["source_id"] == "projects/alpha/subfolder/doc3.md"

    def test_result_ordering(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that results are ordered by source_id."""
        resp = client_with_hierarchical_sources.get("/sources?source_id_prefix=projects/")
        assert resp.status_code == 200
        data = resp.json()
        source_ids = [s["source_id"] for s in data["sources"]]
        # Verify ordering
        assert source_ids == sorted(source_ids)
