"""Shared fixtures for server tests."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

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


def _make_hash(char: str) -> str:
    return char * 64


@pytest.fixture()
def ds() -> DocumentStore:
    """In-memory DocumentStore pre-populated with test data."""
    store = DocumentStore(":memory:", check_same_thread=False)

    # Register adapter
    config = AdapterConfig(
        adapter_id="test-adapter",
        adapter_type="filesystem",
        domain=Domain.NOTES,
        normalizer_version="1.0.0",
    )
    store.register_adapter(config)

    # Register source
    store.register_source(
        source_id="src-1",
        adapter_id="test-adapter",
        domain=Domain.NOTES,
        origin_ref="/docs/readme.md",
        poll_strategy=PollStrategy.PULL,
        poll_interval_sec=3600,
    )

    # Create a chunk
    content = "Hello world"
    chunk_hash = compute_chunk_hash(content)
    chunk = Chunk(
        chunk_hash=chunk_hash,
        content=content,
        context_header="# README",
        chunk_index=0,
        chunk_type=ChunkType.STANDARD,
    )

    # Create version 1
    store.create_source_version(
        source_id="src-1",
        version=1,
        markdown="# README\nHello world",
        chunk_hashes=[chunk_hash],
        adapter_id="test-adapter",
        normalizer_version="1.0.0",
        fetch_timestamp="2024-01-01T00:00:00+00:00",
    )
    lineage = LineageRecord(
        chunk_hash=chunk_hash,
        source_id="src-1",
        source_version_id=1,
        adapter_id="test-adapter",
        domain=Domain.NOTES,
        normalizer_version="1.0.0",
        embedding_model_id="all-MiniLM-L6-v2",
    )
    store.write_chunks(
        chunks=[chunk],
        lineage_records=[lineage],
    )

    return store


@pytest.fixture()
def client(ds: DocumentStore) -> TestClient:
    """FastAPI TestClient with mocked app state (lifespan bypassed)."""
    from contextlib import asynccontextmanager

    mock_embedder = MagicMock()
    mock_embedder.model_id = "all-MiniLM-L6-v2"
    mock_embedder.dimension = 384
    mock_vector_store = MagicMock()
    mock_vector_store.count.return_value = 0

    @asynccontextmanager
    async def noop_lifespan(app):
        app.state.document_store = ds
        app.state.embedder = mock_embedder
        app.state.vector_store = mock_vector_store
        app.state.pipeline = MagicMock()
        app.state.reranker = None
        yield

    app = create_app()
    # Replace the lifespan with a no-op that injects state
    app.router.lifespan_context = noop_lifespan

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture()
def chunk_hash(ds: DocumentStore) -> str:
    """Return the hash of the test chunk."""
    return compute_chunk_hash("Hello world")
