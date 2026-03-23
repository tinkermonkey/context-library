"""Root pytest configuration and fixtures."""

import gc
import hashlib
import sqlite3
import time
import pytest

from context_library.storage.document_store import DocumentStore
from context_library.storage.models import AdapterConfig, Domain, LineageRecord


def make_sha256_hash(text: str) -> str:
    """Create a valid SHA-256 hash from text."""
    return hashlib.sha256(text.encode()).hexdigest()


def setup_chunk_in_store(
    store: DocumentStore,
    chunk_or_chunks,  # Chunk or list of Chunks
    adapter_id: str,
    adapter_type: str,
    source_id: str,
    domain: Domain,
    version: int = 1,
) -> None:
    """Helper to set up chunks in the store with all required metadata.

    Note: Chunks passed in a list must have distinct chunk_index values due to
    the UNIQUE constraint on (source_id, source_version, chunk_index).
    """
    # Normalize input to list
    chunks = chunk_or_chunks if isinstance(chunk_or_chunks, list) else [chunk_or_chunks]

    # Register adapter if not already registered
    try:
        config = AdapterConfig(
            adapter_id=adapter_id,
            adapter_type=adapter_type,
            domain=domain,
            normalizer_version="1.0.0",
        )
        store.register_adapter(config)
    except sqlite3.IntegrityError:
        # Already registered
        pass

    # Register source if not already registered
    try:
        store.register_source(source_id, adapter_id, domain, "")
    except sqlite3.IntegrityError:
        # Already registered
        pass

    # Create source version
    chunk_hashes = [ch.chunk_hash for ch in chunks]
    store.create_source_version(
        source_id,
        version,
        "markdown content",
        chunk_hashes,
        adapter_id,
        "1.0.0",
        "2024-01-01T00:00:00Z",
    )

    # Create lineage records
    lineages = [
        LineageRecord(
            chunk_hash=chunk.chunk_hash,
            source_id=source_id,
            source_version_id=version,
            adapter_id=adapter_id,
            domain=domain,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )
        for chunk in chunks
    ]

    # Write chunks with lineage
    store.write_chunks(chunks, lineages)


@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Ensure proper cleanup after each test to prevent resource leaks.

    Particularly important for:
    - FileSystemWatcher instances that hold inotify watches
    - Temporary directories that may hold open file handles
    """
    yield
    # Force garbage collection to ensure file handles and inotify watches are released
    # This helps prevent "inotify watch limit reached" errors in test_watching.py
    gc.collect()

    # Give the system time to release inotify resources
    time.sleep(0.02)
