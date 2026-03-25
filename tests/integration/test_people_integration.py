"""Integration tests for the people domain: AppleContactsAdapter → EntityLinker → Query

These tests verify the end-to-end integration of the people domain adapter with the
ingestion pipeline and entity linker, using real SHA-256 hashing and the full pipeline flow.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
import sys

from context_library.storage.document_store import DocumentStore
from context_library.storage.models import Domain, Chunk, ENTITY_LINK_TYPE_PERSON_APPEARANCE
from context_library.adapters.apple_contacts import AppleContactsAdapter
from context_library.domains.people import PeopleDomain

# Add parent directory to sys.path to allow importing helpers module
sys.path.insert(0, str(Path(__file__).parent.parent))
from helpers import make_sha256_hash, setup_chunk_in_store

# Guard heavy imports that pull in sentence_transformers (ML stack)
pytest.importorskip("sentence_transformers")
from context_library.core.pipeline import IngestionPipeline
from context_library.core.differ import Differ
from context_library.core.embedder import Embedder
from context_library.storage.vector_store import VectorStore


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

        This verifies the core entity linking rule: people chunks should NOT link to
        other people chunks, only to chunks in other domains (messages, notes, etc.).
        The entity linker should return no matches when searching for identifiers
        that only exist in people domain chunks.
        """
        from context_library.core.entity_linker import EntityLinker

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            store = DocumentStore(db_path)

            try:
                # Create a people chunk with Alice's email
                alice_hash = make_sha256_hash("alice_smith_contact")
                alice_chunk = Chunk(
                    chunk_hash=alice_hash,
                    content="Alice Smith",
                    chunk_index=0,
                    domain_metadata={"emails": ["alice@example.com"], "phones": []},
                )

                # Set up the chunk with proper metadata and lineage
                setup_chunk_in_store(
                    store,
                    alice_chunk,
                    "people_adapter",
                    "AppleContactsAdapter",
                    "people_src",
                    Domain.PEOPLE,
                    version=1,
                )

                # Create entity linker and search for chunks matching alice@example.com
                linker = EntityLinker(store)
                matching = linker._find_matching_chunks(["alice@example.com"])

                # Key assertion: people domain chunks should NOT be in matching results
                # (i.e., people chunks do not link to other people chunks)
                assert alice_chunk.chunk_hash not in matching

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
                new_links, failures = linker.run()

                # Verify link was created
                assert new_links == 1
                assert failures == 0
                linked = store.get_linked_chunks(alice_hash, link_type=ENTITY_LINK_TYPE_PERSON_APPEARANCE)
                assert msg_hash in linked

            finally:
                store.close()
