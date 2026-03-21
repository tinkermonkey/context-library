"""Shared fixtures for server tests."""

import pytest
import tempfile
import os
from typing import Generator, AsyncGenerator, Any
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from contextlib import asynccontextmanager

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


def _create_app_with_store(
    ds: DocumentStore,
    mock_embedder: Any = None,
    mock_vector_store: Any = None,
    mock_reranker: Any = None,
) -> Generator[TestClient, None, None]:
    """Helper to create a FastAPI TestClient with mocked lifespan state."""
    if mock_embedder is None:
        mock_embedder = MagicMock()
        mock_embedder.model_id = "all-MiniLM-L6-v2"
        mock_embedder.dimension = 384
        # Mock embed_query to return valid embeddings
        mock_embedder.embed_query.return_value = [0.1] * 384
    if mock_vector_store is None:
        mock_vector_store = MagicMock()
        mock_vector_store.count.return_value = 0
        # Mock search to return empty results
        mock_vector_store.search.return_value = []

    @asynccontextmanager
    async def noop_lifespan(app: Any) -> AsyncGenerator[None, None]:
        mock_config = MagicMock()
        mock_config.webhook_secret = None
        app.state.document_store = ds
        app.state.embedder = mock_embedder
        app.state.vector_store = mock_vector_store
        app.state.pipeline = MagicMock()
        app.state.reranker = mock_reranker or None
        app.state.config = mock_config
        app.state.helper_adapters = []
        yield

    app = create_app()
    app.router.lifespan_context = noop_lifespan

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture()
def ds() -> Generator[DocumentStore, None, None]:
    """In-memory DocumentStore pre-populated with test data."""
    # Use a temporary file instead of :memory: to support multi-threaded access.
    # SQLite :memory: databases are per-connection, so each thread gets its own
    # isolated empty database. File-based databases work correctly across threads.
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_path = temp_file.name
    temp_file.close()

    store = DocumentStore(temp_path, check_same_thread=False)

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

    yield store

    # Cleanup: close connections and delete temporary file
    store.close()
    try:
        os.unlink(temp_path)
    except OSError:
        pass  # File might already be deleted


@pytest.fixture()
def client(ds: DocumentStore) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with mocked app state (lifespan bypassed)."""
    yield from _create_app_with_store(ds)


@pytest.fixture()
def chunk_hash(ds: DocumentStore) -> Generator[str, None, None]:
    """Return the hash of the test chunk."""
    yield compute_chunk_hash("Hello world")


@pytest.fixture()
def ds_with_metadata(ds: DocumentStore) -> Generator[DocumentStore, None, None]:
    """DocumentStore with a chunk containing domain_metadata and cross_refs."""
    # Create a chunk with domain_metadata and cross_refs
    content_with_meta = "Content with metadata"
    chunk_hash = compute_chunk_hash(content_with_meta)
    ref_hash = "b" * 64

    chunk = Chunk(
        chunk_hash=chunk_hash,
        content=content_with_meta,
        context_header="## Section",
        chunk_index=1,
        chunk_type=ChunkType.STANDARD,
        domain_metadata={"title": "Test Section", "_system_cross_refs": [ref_hash]},
        cross_refs=(ref_hash,),
    )

    # Create version 2 with the metadata chunk
    ds.create_source_version(
        source_id="src-1",
        version=2,
        markdown="## Section\nContent with metadata",
        chunk_hashes=[chunk_hash],
        adapter_id="test-adapter",
        normalizer_version="1.0.0",
        fetch_timestamp="2024-01-02T00:00:00+00:00",
    )
    lineage = LineageRecord(
        chunk_hash=chunk_hash,
        source_id="src-1",
        source_version_id=2,
        adapter_id="test-adapter",
        domain=Domain.NOTES,
        normalizer_version="1.0.0",
        embedding_model_id="all-MiniLM-L6-v2",
    )
    ds.write_chunks(
        chunks=[chunk],
        lineage_records=[lineage],
    )

    yield ds


@pytest.fixture()
def client_with_metadata(ds_with_metadata: DocumentStore) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with mocked app state using ds_with_metadata fixture."""
    yield from _create_app_with_store(ds_with_metadata)


# Multi-entity test fixtures


@pytest.fixture()
def ds_multi_source(ds: DocumentStore) -> Generator[DocumentStore, None, None]:
    """DocumentStore with multiple sources from a single adapter."""
    store = ds

    # Register two additional sources
    for src_num in range(2, 4):
        store.register_source(
            source_id=f"src-{src_num}",
            adapter_id="test-adapter",
            domain=Domain.NOTES,
            origin_ref=f"/docs/file{src_num}.md",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )

    # Create versions for each new source
    for src_num in range(2, 4):
        content = f"Content for source {src_num}"
        chunk_hash = compute_chunk_hash(content)
        chunk = Chunk(
            chunk_hash=chunk_hash,
            content=content,
            context_header=f"# File {src_num}",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
        )

        store.create_source_version(
            source_id=f"src-{src_num}",
            version=1,
            markdown=f"# File {src_num}\n{content}",
            chunk_hashes=[chunk_hash],
            adapter_id="test-adapter",
            normalizer_version="1.0.0",
            fetch_timestamp="2024-01-01T00:00:00+00:00",
        )
        lineage = LineageRecord(
            chunk_hash=chunk_hash,
            source_id=f"src-{src_num}",
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

    yield store


@pytest.fixture()
def ds_multi_adapter_same_domain(ds: DocumentStore) -> Generator[DocumentStore, None, None]:
    """DocumentStore with multiple adapters managing the same domain (NOTES)."""
    store = ds

    # Register a second filesystem adapter
    config2 = AdapterConfig(
        adapter_id="obsidian-adapter",
        adapter_type="obsidian",
        domain=Domain.NOTES,
        normalizer_version="1.0.0",
    )
    store.register_adapter(config2)

    # Register a source from the second adapter
    store.register_source(
        source_id="src-obsidian",
        adapter_id="obsidian-adapter",
        domain=Domain.NOTES,
        origin_ref="/vault/notes.md",
        poll_strategy=PollStrategy.PULL,
        poll_interval_sec=3600,
    )

    # Create version with chunks from second adapter
    content = "Obsidian note content"
    chunk_hash = compute_chunk_hash(content)
    chunk = Chunk(
        chunk_hash=chunk_hash,
        content=content,
        context_header="# Obsidian Note",
        chunk_index=0,
        chunk_type=ChunkType.STANDARD,
    )

    store.create_source_version(
        source_id="src-obsidian",
        version=1,
        markdown="# Obsidian Note\nObsidian note content",
        chunk_hashes=[chunk_hash],
        adapter_id="obsidian-adapter",
        normalizer_version="1.0.0",
        fetch_timestamp="2024-01-01T00:00:00+00:00",
    )
    lineage = LineageRecord(
        chunk_hash=chunk_hash,
        source_id="src-obsidian",
        source_version_id=1,
        adapter_id="obsidian-adapter",
        domain=Domain.NOTES,
        normalizer_version="1.0.0",
        embedding_model_id="all-MiniLM-L6-v2",
    )
    store.write_chunks(
        chunks=[chunk],
        lineage_records=[lineage],
    )

    yield store


@pytest.fixture()
def ds_multi_domain(ds: DocumentStore) -> Generator[DocumentStore, None, None]:
    """DocumentStore with multiple adapters across multiple domains."""
    store = ds

    # Register adapters for MESSAGES and EVENTS domains
    for domain, adapter_type in [
        (Domain.MESSAGES, "email"),
        (Domain.EVENTS, "calendar"),
    ]:
        config = AdapterConfig(
            adapter_id=f"{domain.value}-adapter",
            adapter_type=adapter_type,
            domain=domain,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)

        # Register source for this domain
        store.register_source(
            source_id=f"src-{domain.value}",
            adapter_id=f"{domain.value}-adapter",
            domain=domain,
            origin_ref=f"/{domain.value}/data",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )

        # Create version with chunks
        content = f"Sample {domain.value} content"
        chunk_hash = compute_chunk_hash(content)
        chunk = Chunk(
            chunk_hash=chunk_hash,
            content=content,
            context_header=f"{domain.value.upper()}",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
        )

        store.create_source_version(
            source_id=f"src-{domain.value}",
            version=1,
            markdown=f"{domain.value.upper()}\n{content}",
            chunk_hashes=[chunk_hash],
            adapter_id=f"{domain.value}-adapter",
            normalizer_version="1.0.0",
            fetch_timestamp="2024-01-01T00:00:00+00:00",
        )
        lineage = LineageRecord(
            chunk_hash=chunk_hash,
            source_id=f"src-{domain.value}",
            source_version_id=1,
            adapter_id=f"{domain.value}-adapter",
            domain=domain,
            normalizer_version="1.0.0",
            embedding_model_id="all-MiniLM-L6-v2",
        )
        store.write_chunks(
            chunks=[chunk],
            lineage_records=[lineage],
        )

    yield store


@pytest.fixture()
def ds_comprehensive(ds: DocumentStore) -> Generator[DocumentStore, None, None]:
    """DocumentStore with realistic multi-adapter × multi-domain scenario."""
    store = ds

    # Extend base fixture with additional adapters and sources
    # Adapter 2: Obsidian (NOTES)
    config_obsidian = AdapterConfig(
        adapter_id="obsidian-adapter",
        adapter_type="obsidian",
        domain=Domain.NOTES,
        normalizer_version="1.0.0",
    )
    store.register_adapter(config_obsidian)

    # Adapter 3: Email (MESSAGES)
    config_email = AdapterConfig(
        adapter_id="email-adapter",
        adapter_type="email",
        domain=Domain.MESSAGES,
        normalizer_version="1.0.0",
    )
    store.register_adapter(config_email)

    # Adapter 4: Calendar (EVENTS)
    config_calendar = AdapterConfig(
        adapter_id="calendar-adapter",
        adapter_type="calendar",
        domain=Domain.EVENTS,
        normalizer_version="1.0.0",
    )
    store.register_adapter(config_calendar)

    # Define test data: (source_id, adapter_id, domain, content, origin_ref)
    test_sources = [
        ("src-obsidian-1", "obsidian-adapter", Domain.NOTES, "Obsidian vault note 1", "/vault/note1.md"),
        ("src-obsidian-2", "obsidian-adapter", Domain.NOTES, "Obsidian vault note 2", "/vault/note2.md"),
        ("src-email-1", "email-adapter", Domain.MESSAGES, "Email message thread 1", "inbox/thread1"),
        ("src-calendar-1", "calendar-adapter", Domain.EVENTS, "Calendar event batch 1", "calendar/events"),
    ]

    for source_id, adapter_id, domain, content, origin_ref in test_sources:
        store.register_source(
            source_id=source_id,
            adapter_id=adapter_id,
            domain=domain,
            origin_ref=origin_ref,
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )

        # Create version 1
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
            adapter_id=adapter_id,
            normalizer_version="1.0.0",
            fetch_timestamp="2024-01-01T00:00:00+00:00",
        )
        lineage = LineageRecord(
            chunk_hash=chunk_hash,
            source_id=source_id,
            source_version_id=1,
            adapter_id=adapter_id,
            domain=domain,
            normalizer_version="1.0.0",
            embedding_model_id="all-MiniLM-L6-v2",
        )
        store.write_chunks(
            chunks=[chunk],
            lineage_records=[lineage],
        )

    yield store


# Client fixtures for multi-entity stores


@pytest.fixture()
def client_multi_source(ds_multi_source: DocumentStore) -> Generator[TestClient, None, None]:
    """TestClient with multi-source fixture."""
    yield from _create_app_with_store(ds_multi_source)


@pytest.fixture()
def client_multi_adapter_same_domain(ds_multi_adapter_same_domain: DocumentStore) -> Generator[TestClient, None, None]:
    """TestClient with multi-adapter same-domain fixture."""
    yield from _create_app_with_store(ds_multi_adapter_same_domain)


@pytest.fixture()
def client_multi_domain(ds_multi_domain: DocumentStore) -> Generator[TestClient, None, None]:
    """TestClient with multi-domain fixture."""
    yield from _create_app_with_store(ds_multi_domain)


@pytest.fixture()
def client_comprehensive(ds_comprehensive: DocumentStore) -> Generator[TestClient, None, None]:
    """TestClient with comprehensive multi-adapter × multi-domain fixture."""
    yield from _create_app_with_store(ds_comprehensive)
