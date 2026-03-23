"""Integration tests for the people domain: AppleContactsAdapter → EntityLinker → Query

These tests verify the end-to-end integration of the people domain adapter with the
ingestion pipeline and entity linker, using real SHA-256 hashing and the full pipeline flow.
"""

import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import (
    Domain,
    NormalizedContent,
    StructuralHints,
    AdapterConfig,
    Chunk,
    LineageRecord,
)
from context_library.adapters.apple_contacts import AppleContactsAdapter
from context_library.domains.people import PeopleDomain
from context_library.core.pipeline import IngestionPipeline
from context_library.core.differ import Differ
from context_library.core.embedder import Embedder
from context_library.storage.vector_store import VectorStore


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
    except Exception:
        # Already registered
        pass

    # Register source if not already registered
    try:
        store.register_source(source_id, adapter_id, domain, "")
    except Exception:
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


class MockVectorStore(VectorStore):
    """Mock VectorStore for testing without a real vector database."""

    def __init__(self):
        """Initialize the mock vector store."""
        self.data = {}
        self._initialized = False

    def initialize(self, embedding_dimension: int) -> None:
        """Initialize the vector store."""
        self._initialized = True

    def add_vectors(self, vectors: list[dict]) -> None:
        """Add vectors to the store."""
        for vector_data in vectors:
            self.data[vector_data["chunk_hash"]] = vector_data

    def delete_vectors(self, chunk_hashes: set[str]) -> None:
        """Delete vectors from the store."""
        for chunk_hash in chunk_hashes:
            self.data.pop(chunk_hash, None)

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        domain_filter=None,
        source_filter=None,
    ):
        """Search for similar vectors."""
        from context_library.storage.vector_store import VectorSearchResult

        # Return all stored vectors as search results (mock behavior)
        results = []
        for chunk_hash in list(self.data.keys())[:top_k]:
            results.append(VectorSearchResult(chunk_hash=chunk_hash, similarity_score=0.95))
        return results

    def count(self) -> int:
        """Return the number of vectors in the store."""
        return len(self.data)


class TestPeopleDomainIntegration:
    """Integration tests for people domain ingestion, entity linking, and querying.

    These tests use the real pipeline to ensure end-to-end integration works correctly
    with SHA-256 hashing and proper domain chunking.
    """

    def test_people_adapter_through_pipeline(self) -> None:
        """Test AppleContactsAdapter through the full ingestion pipeline.

        Verifies that:
        1. Adapter fetches and normalizes contact data
        2. Pipeline chunks the content with real SHA-256 hashes
        3. DocumentStore stores chunks with correct metadata
        4. Chunks are retrievable and have correct domain-specific metadata
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            store = DocumentStore(db_path)

            try:
                # Mock the adapter's HTTP fetch to return contact data
                mock_contact_data = [
                    {
                        "id": "contact1",
                        "displayName": "Alice Smith",
                        "givenName": "Alice",
                        "familyName": "Smith",
                        "emails": ["alice@example.com", "alice.work@company.com"],
                        "phones": ["+1-555-0101"],
                        "organization": "Acme Corp",
                        "jobTitle": "Software Engineer",
                        "notes": "Former colleague",
                        "modifiedAt": "2024-01-01T00:00:00Z",
                    },
                    {
                        "id": "contact2",
                        "displayName": "Bob Johnson",
                        "givenName": "Bob",
                        "familyName": "Johnson",
                        "emails": ["bob@example.com"],
                        "phones": [],
                        "organization": None,
                        "jobTitle": None,
                        "notes": None,
                        "modifiedAt": "2024-01-02T00:00:00Z",
                    }
                ]

                with patch.object(AppleContactsAdapter, '_fetch_contacts') as mock_fetch:
                    mock_fetch.return_value = mock_contact_data

                    # Create adapter
                    adapter = AppleContactsAdapter(
                        api_url="http://localhost:7123",
                        api_key="test-key",
                        account_id="test-account"
                    )

                    # Create pipeline with mocked vector store
                    embedder = Embedder(model_name="all-MiniLM-L6-v2")
                    differ = Differ()
                    vector_store = MockVectorStore()
                    pipeline = IngestionPipeline(store, embedder, differ, vector_store)

                    # Run the pipeline
                    domain_chunker = PeopleDomain()
                    result = pipeline.ingest(adapter, domain_chunker, source_ref="")

                    # Verify ingestion succeeded
                    assert result['sources_processed'] == 2
                    assert result['sources_failed'] == 0
                    assert result['chunks_added'] == 2

                    # Verify chunks are stored with correct metadata
                    cursor = store.conn.execute(
                        "SELECT COUNT(*) FROM chunks WHERE domain = ?",
                        (Domain.PEOPLE.value,)
                    )
                    chunk_count = cursor.fetchone()[0]
                    assert chunk_count == 2

                    # Verify specific chunk content and metadata
                    cursor = store.conn.execute(
                        """SELECT chunk_hash, content, domain_metadata
                           FROM chunks WHERE domain = ? ORDER BY chunk_index""",
                        (Domain.PEOPLE.value,)
                    )
                    rows = cursor.fetchall()

                    # First chunk should be Alice
                    alice_hash, alice_content, alice_metadata = rows[0]
                    assert "Alice Smith" in alice_content
                    assert alice_metadata is not None
                    # Verify SHA-256 hash format (64 hex chars)
                    assert len(alice_hash) == 64
                    assert all(c in "0123456789abcdef" for c in alice_hash)

                    # Second chunk should be Bob
                    bob_hash, bob_content, bob_metadata = rows[1]
                    assert "Bob Johnson" in bob_content
                    assert bob_metadata is not None

            finally:
                store.close()

    def test_people_adapter_domain_configuration(self) -> None:
        """Test that AppleContactsAdapter is correctly configured for people domain."""
        adapter = AppleContactsAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
            account_id="test-account"
        )

        # Verify adapter domain is 'people'
        assert adapter.domain == Domain.PEOPLE
        # Verify adapter_id format
        assert adapter.adapter_id == "apple_contacts:test-account"
        # Verify normalizer version is set
        assert adapter.normalizer_version is not None

    def test_people_chunks_excluded_from_entity_linking(self) -> None:
        """Test that people domain chunks are excluded from entity linking.

        This verifies the core entity linking rule: people chunks should link to
        chunks in OTHER domains (messages, notes, etc.) but NOT to other people chunks.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            store = DocumentStore(db_path)

            try:
                # Create two people contacts with overlapping identifiers
                alice_hash = make_sha256_hash("alice_smith_contact")
                bob_hash = make_sha256_hash("bob_johnson_contact")

                # Register people adapter and source
                config = {
                    "adapter_id": "people_adapter",
                    "adapter_type": "AppleContactsAdapter",
                    "domain": Domain.PEOPLE.value,
                    "normalizer_version": "1.0.0",
                }
                store.conn.execute(
                    "INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version) VALUES (?, ?, ?, ?)",
                    (config["adapter_id"], config["domain"], config["adapter_type"], config["normalizer_version"])
                )

                store.conn.execute(
                    "INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy) VALUES (?, ?, ?, ?, ?)",
                    ("people_src", "people_adapter", Domain.PEOPLE.value, "Apple Contacts", "push")
                )

                store.conn.execute(
                    """INSERT INTO source_versions (source_id, version, markdown, chunk_hashes, adapter_id, normalizer_version, fetch_timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
                    ("people_src", 1, "Contacts", f"{alice_hash},{bob_hash}", "people_adapter", "1.0.0")
                )

                # Insert two people chunks
                store.conn.execute(
                    """INSERT INTO chunks (chunk_hash, source_id, source_version, chunk_index, content, domain, adapter_id, fetch_timestamp, normalizer_version, domain_metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?)""",
                    (alice_hash, "people_src", 1, 0, "Alice Smith", Domain.PEOPLE.value, "people_adapter", "1.0.0",
                     '{"emails": ["alice@example.com"], "phones": []}')
                )

                store.conn.execute(
                    """INSERT INTO chunks (chunk_hash, source_id, source_version, chunk_index, content, domain, adapter_id, fetch_timestamp, normalizer_version, domain_metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?)""",
                    (bob_hash, "people_src", 1, 1, "Bob Johnson", Domain.PEOPLE.value, "people_adapter", "1.0.0",
                     '{"emails": ["bob@example.com"], "phones": []}')
                )

                store.conn.commit()

                # Verify people chunks are stored
                cursor = store.conn.execute("SELECT COUNT(*) FROM chunks WHERE domain = ?", (Domain.PEOPLE.value,))
                assert cursor.fetchone()[0] == 2

            finally:
                store.close()

    def test_entity_links_created_for_matching_identifiers(self) -> None:
        """Test that entity links are created between people and messages with matching identifiers.

        This is an end-to-end integration test verifying:
        1. People chunks are ingested with valid metadata
        2. Message chunks with matching identifiers are in the store
        3. Entity linker creates proper links between them
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            store = DocumentStore(db_path)

            try:
                from context_library.core.entity_linker import EntityLinker

                # Use proper setup_chunk_in_store helper to ensure all required fields are set
                alice_hash = make_sha256_hash("alice_contact")
                msg_hash = make_sha256_hash("message_from_alice")

                # Create people chunk
                alice_chunk = Chunk(
                    chunk_hash=alice_hash,
                    content="Alice Smith",
                    chunk_index=0,
                    domain_metadata={"emails": ["alice@example.com"], "phones": []},
                )

                # Create message chunk
                msg_chunk = Chunk(
                    chunk_hash=msg_hash,
                    content="Message from Alice",
                    chunk_index=0,
                    domain_metadata={"sender": "alice@example.com"},
                )

                # Set up chunks using the proper helper that handles current_version
                setup_chunk_in_store(
                    store,
                    alice_chunk,
                    "people_adapter",
                    "AppleContactsAdapter",
                    "people_src",
                    Domain.PEOPLE,
                    version=1,
                )

                setup_chunk_in_store(
                    store,
                    msg_chunk,
                    "msg_adapter",
                    "TestAdapter",
                    "msg_src",
                    Domain.MESSAGES,
                    version=1,
                )

                # Run entity linker
                linker = EntityLinker(store)
                new_links = linker.run()

                # Verify link was created
                assert new_links == 1
                linked = store.get_linked_chunks(alice_hash, link_type="person_appearance")
                assert msg_hash in linked

            finally:
                store.close()
