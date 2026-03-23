"""Tests for the EntityLinker post-pipeline linking pass."""

import hashlib

import pytest

from context_library.core.entity_linker import EntityLinker
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import AdapterConfig, Chunk, Domain, LineageRecord


def make_sha256_hash(text: str) -> str:
    """Create a valid SHA-256 hash from text."""
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def doc_store():
    """Fixture providing an in-memory SQLite DocumentStore."""
    store = DocumentStore(":memory:")
    yield store
    store.close()


def setup_chunk_in_store(
    store: DocumentStore,
    chunk_or_chunks,  # Chunk or list of Chunks
    adapter_id: str,
    adapter_type: str,
    source_id: str,
    domain: Domain,
    version: int = 1,
) -> None:
    """Helper to set up chunks in the store with all required metadata."""
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

    # Register source
    store.register_source(source_id, adapter_id, domain, "")

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


class TestEntityLinkerExtractIdentifiers:
    """Test identifier extraction from PeopleMetadata."""

    def test_extract_emails(self):
        """Extract emails from domain_metadata."""
        linker = EntityLinker(DocumentStore(":memory:"))
        metadata = {
            "contact_id": "contact_1",
            "display_name": "Alice",
            "emails": ["alice@example.com", "alice.work@company.com"],
            "phones": [],
        }
        identifiers = linker._extract_identifiers(metadata)
        assert set(identifiers) == {"alice@example.com", "alice.work@company.com"}

    def test_extract_phones(self):
        """Extract phones from domain_metadata."""
        linker = EntityLinker(DocumentStore(":memory:"))
        metadata = {
            "contact_id": "contact_1",
            "display_name": "Alice",
            "emails": [],
            "phones": ["+1-555-0101", "+1-555-0102"],
        }
        identifiers = linker._extract_identifiers(metadata)
        assert set(identifiers) == {"+1-555-0101", "+1-555-0102"}

    def test_extract_emails_and_phones(self):
        """Extract both emails and phones."""
        linker = EntityLinker(DocumentStore(":memory:"))
        metadata = {
            "contact_id": "contact_1",
            "display_name": "Alice",
            "emails": ["alice@example.com"],
            "phones": ["+1-555-0101"],
        }
        identifiers = linker._extract_identifiers(metadata)
        assert set(identifiers) == {"alice@example.com", "+1-555-0101"}

    def test_empty_identifiers(self):
        """Handle metadata with no emails or phones."""
        linker = EntityLinker(DocumentStore(":memory:"))
        metadata = {
            "contact_id": "contact_1",
            "display_name": "Alice",
            "emails": [],
            "phones": [],
        }
        identifiers = linker._extract_identifiers(metadata)
        assert identifiers == []

    def test_none_domain_metadata(self):
        """Handle None domain_metadata gracefully."""
        linker = EntityLinker(DocumentStore(":memory:"))
        identifiers = linker._extract_identifiers(None)
        assert identifiers == []

    def test_deduplication(self):
        """Deduplicate repeated identifiers."""
        linker = EntityLinker(DocumentStore(":memory:"))
        metadata = {
            "contact_id": "contact_1",
            "display_name": "Alice",
            "emails": ["alice@example.com", "alice@example.com"],
            "phones": ["+1-555-0101"],
        }
        identifiers = linker._extract_identifiers(metadata)
        assert identifiers == ["+1-555-0101", "alice@example.com"]  # Sorted, deduplicated


class TestEntityLinkerFindMatchingChunks:
    """Test finding chunks matching given identifiers."""

    def test_find_matching_chunks_by_sender(self, doc_store):
        """Find message chunks matching person identifier in sender field."""
        msg_hash = make_sha256_hash("message_from_alice_v1")
        msg_chunk = Chunk(
            chunk_hash=msg_hash,
            content="Message from Alice",
            context_header="Message",
            chunk_index=0,
            domain_metadata={"sender": "alice@example.com"},
        )

        setup_chunk_in_store(doc_store, msg_chunk, "msg_adapter", "test", "source_1", Domain.MESSAGES)

        linker = EntityLinker(doc_store)
        matching = linker._find_matching_chunks(["alice@example.com"])

        assert msg_chunk.chunk_hash in matching

    def test_find_matching_chunks_by_recipient(self, doc_store):
        """Find message chunks matching identifier in recipients array."""
        msg_hash = make_sha256_hash("message_to_alice_and_bob")
        msg_chunk = Chunk(
            chunk_hash=msg_hash,
            content="Message to Alice and Bob",
            context_header="Message",
            chunk_index=0,
            domain_metadata={"recipients": ["alice@example.com", "bob@example.com"]},
        )

        setup_chunk_in_store(doc_store, msg_chunk, "msg_adapter", "test", "source_1", Domain.MESSAGES)

        linker = EntityLinker(doc_store)
        matching = linker._find_matching_chunks(["alice@example.com"])

        assert msg_chunk.chunk_hash in matching

    def test_find_matching_chunks_no_match(self, doc_store):
        """No matches when identifier not found."""
        msg_hash = make_sha256_hash("message_from_someone_else")
        msg_chunk = Chunk(
            chunk_hash=msg_hash,
            content="Message from someone else",
            context_header="Message",
            chunk_index=0,
            domain_metadata={"sender": "other@example.com"},
        )

        setup_chunk_in_store(doc_store, msg_chunk, "msg_adapter", "test", "source_1", Domain.MESSAGES)

        linker = EntityLinker(doc_store)
        matching = linker._find_matching_chunks(["alice@example.com"])

        assert msg_chunk.chunk_hash not in matching

    def test_find_matching_chunks_excludes_people_domain(self, doc_store):
        """Exclude chunks from people domain (no self-links)."""
        people_hash = make_sha256_hash("contact_alice")
        people_chunk = Chunk(
            chunk_hash=people_hash,
            content="Contact Alice",
            context_header="Contact",
            chunk_index=0,
            domain_metadata={"sender": "alice@example.com"},
        )

        config = AdapterConfig(
            adapter_id="people_adapter",
            adapter_type="test",
            domain=Domain.PEOPLE,
            normalizer_version="1.0.0",
        )
        doc_store.register_adapter(config)
        doc_store.register_source("source_1", "people_adapter", Domain.PEOPLE, "")

        linker = EntityLinker(doc_store)
        matching = linker._find_matching_chunks(["alice@example.com"])

        assert people_chunk.chunk_hash not in matching

    def test_find_matching_chunks_excludes_retired_chunks(self, doc_store):
        """Exclude retired chunks from results."""
        msg_hash = make_sha256_hash("retired_message")
        msg_chunk = Chunk(
            chunk_hash=msg_hash,
            content="Retired message",
            context_header="Message",
            chunk_index=0,
            domain_metadata={"sender": "alice@example.com"},
        )

        setup_chunk_in_store(doc_store, msg_chunk, "msg_adapter", "test", "source_1", Domain.MESSAGES)

        # Retire the chunk
        doc_store.retire_chunks([msg_chunk.chunk_hash], "source_1", 1)

        linker = EntityLinker(doc_store)
        matching = linker._find_matching_chunks(["alice@example.com"])

        assert msg_chunk.chunk_hash not in matching

    def test_find_matching_chunks_multiple_fields(self, doc_store):
        """Match across multiple fields (sender, host, author, recipients, invitees, collaborators)."""
        chunk_sender_hash = make_sha256_hash("from_sender")
        chunk_host_hash = make_sha256_hash("host_alice")
        chunk_author_hash = make_sha256_hash("author_alice")

        chunk_sender = Chunk(
            chunk_hash=chunk_sender_hash,
            content="From sender",
            chunk_index=0,
            domain_metadata={"sender": "alice@example.com"},
        )
        chunk_host = Chunk(
            chunk_hash=chunk_host_hash,
            content="Host alice",
            chunk_index=1,
            domain_metadata={"host": "alice@example.com"},
        )
        chunk_author = Chunk(
            chunk_hash=chunk_author_hash,
            content="Author alice",
            chunk_index=2,
            domain_metadata={"author": "alice@example.com"},
        )

        setup_chunk_in_store(
            doc_store,
            [chunk_sender, chunk_host, chunk_author],
            "adapter",
            "test",
            "source_1",
            Domain.MESSAGES,
        )

        linker = EntityLinker(doc_store)
        matching = linker._find_matching_chunks(["alice@example.com"])

        assert len(matching) == 3
        assert chunk_sender.chunk_hash in matching
        assert chunk_host.chunk_hash in matching
        assert chunk_author.chunk_hash in matching


class TestEntityLinkerRun:
    """Test the full entity linking pass."""

    def test_run_creates_links_for_matching_identifiers(self, doc_store):
        """Full run creates entity_links for matching identifiers."""
        person_hash = make_sha256_hash("contact_alice_v1")
        msg_hash = make_sha256_hash("message_from_alice_v1")

        person_chunk = Chunk(
            chunk_hash=person_hash,
            content="Contact Alice",
            context_header="Contact",
            chunk_index=0,
            domain_metadata={
                "contact_id": "contact_1",
                "display_name": "Alice",
                "emails": ["alice@example.com"],
                "phones": [],
            },
        )

        msg_chunk = Chunk(
            chunk_hash=msg_hash,
            content="Message from Alice",
            chunk_index=0,
            domain_metadata={"sender": "alice@example.com"},
        )

        people_config = AdapterConfig(
            adapter_id="people_adapter",
            adapter_type="test",
            domain=Domain.PEOPLE,
            normalizer_version="1.0.0",
        )
        msg_config = AdapterConfig(
            adapter_id="msg_adapter",
            adapter_type="test",
            domain=Domain.MESSAGES,
            normalizer_version="1.0.0",
        )

        doc_store.register_adapter(people_config)
        doc_store.register_adapter(msg_config)

        people_source = doc_store.register_source("people_adapter", "people_source", Domain.PEOPLE, "")
        msg_source = doc_store.register_source("msg_adapter", "msg_source", Domain.MESSAGES, "")

        doc_store.create_source_version("people_source", 1, "people markdown", list({person_chunk.chunk_hash}), "people_adapter", "1.0.0", "2024-01-01T00:00:00Z")
        doc_store.create_source_version("msg_source", 1, "msg markdown", list({msg_chunk.chunk_hash}), "msg_adapter", "1.0.0", "2024-01-01T00:00:00Z")

        doc_store.write_chunks([person_chunk, msg_chunk], [])

        linker = EntityLinker(doc_store)
        new_links = linker.run()

        assert new_links == 1
        linked = doc_store.get_linked_chunks(person_chunk.chunk_hash, link_type="person_appearance")
        assert msg_chunk.chunk_hash in linked

    def test_run_idempotent(self, doc_store):
        """Running run() twice without data change does not increase count."""
        person_hash = make_sha256_hash("contact_bob")
        msg_hash = make_sha256_hash("message_from_bob")

        person_chunk = Chunk(
            chunk_hash=person_hash,
            content="Contact Bob",
            context_header="Contact",
            chunk_index=0,
            domain_metadata={
                "contact_id": "contact_2",
                "display_name": "Bob",
                "emails": ["bob@example.com"],
                "phones": [],
            },
        )

        msg_chunk = Chunk(
            chunk_hash=msg_hash,
            content="Message from Bob",
            chunk_index=0,
            domain_metadata={"sender": "bob@example.com"},
        )

        people_config = AdapterConfig(
            adapter_id="people_adapter",
            adapter_type="test",
            domain=Domain.PEOPLE,
            normalizer_version="1.0.0",
        )
        msg_config = AdapterConfig(
            adapter_id="msg_adapter",
            adapter_type="test",
            domain=Domain.MESSAGES,
            normalizer_version="1.0.0",
        )

        doc_store.register_adapter(people_config)
        doc_store.register_adapter(msg_config)

        people_source = doc_store.register_source("people_adapter", "people_source", Domain.PEOPLE, "")
        msg_source = doc_store.register_source("msg_adapter", "msg_source", Domain.MESSAGES, "")

        doc_store.create_source_version("people_source", 1, "people markdown", list({person_chunk.chunk_hash}), "people_adapter", "1.0.0", "2024-01-01T00:00:00Z")
        doc_store.create_source_version("msg_source", 1, "msg markdown", list({msg_chunk.chunk_hash}), "msg_adapter", "1.0.0", "2024-01-01T00:00:00Z")

        doc_store.write_chunks([person_chunk, msg_chunk], [])

        linker = EntityLinker(doc_store)
        first_run = linker.run()
        second_run = linker.run()

        assert first_run == 1
        assert second_run == 0

    def test_run_with_no_person_chunks(self, doc_store):
        """run() returns 0 when no person chunks exist."""
        linker = EntityLinker(doc_store)
        result = linker.run()
        assert result == 0

    def test_run_multi_identifier_contact(self, doc_store):
        """Person with multiple email/phone identifiers links to multiple messages."""
        person_hash = make_sha256_hash("contact_charlie")
        msg_work_hash = make_sha256_hash("work_email_from_charlie")
        msg_personal_hash = make_sha256_hash("personal_email_from_charlie")
        msg_phone_hash = make_sha256_hash("phone_call_from_charlie")

        person_chunk = Chunk(
            chunk_hash=person_hash,
            content="Contact Charlie",
            context_header="Contact",
            chunk_index=0,
            domain_metadata={
                "contact_id": "contact_3",
                "display_name": "Charlie",
                "emails": ["charlie.work@company.com", "charlie.personal@example.com"],
                "phones": ["+1-555-1234"],
            },
        )

        msg_chunk1 = Chunk(
            chunk_hash=msg_work_hash,
            content="Work email from Charlie",
            chunk_index=0,
            domain_metadata={"sender": "charlie.work@company.com"},
        )

        msg_chunk2 = Chunk(
            chunk_hash=msg_personal_hash,
            content="Personal email from Charlie",
            chunk_index=0,
            domain_metadata={"sender": "charlie.personal@example.com"},
        )

        msg_chunk3 = Chunk(
            chunk_hash=msg_phone_hash,
            content="Phone call from Charlie",
            chunk_index=0,
            domain_metadata={"sender": "+1-555-1234"},
        )

        people_config = AdapterConfig(
            adapter_id="people_adapter",
            adapter_type="test",
            domain=Domain.PEOPLE,
            normalizer_version="1.0.0",
        )
        msg_config = AdapterConfig(
            adapter_id="msg_adapter",
            adapter_type="test",
            domain=Domain.MESSAGES,
            normalizer_version="1.0.0",
        )

        doc_store.register_adapter(people_config)
        doc_store.register_adapter(msg_config)

        people_source = doc_store.register_source("people_adapter", "people_source", Domain.PEOPLE, "")
        msg_source = doc_store.register_source("msg_adapter", "msg_source", Domain.MESSAGES, "")

        doc_store.create_source_version(
            people_source,
            "people markdown",
            {person_chunk.chunk_hash},
            "people_adapter",
        )
        doc_store.create_source_version(
            msg_source,
            "msg markdown",
            {msg_chunk1.chunk_hash, msg_chunk2.chunk_hash, msg_chunk3.chunk_hash},
            "msg_adapter",
        )

        doc_store.write_chunks([person_chunk, msg_chunk1, msg_chunk2, msg_chunk3], [])

        linker = EntityLinker(doc_store)
        new_links = linker.run()

        assert new_links == 3
        linked = doc_store.get_linked_chunks(person_chunk.chunk_hash, link_type="person_appearance")
        assert msg_chunk1.chunk_hash in linked
        assert msg_chunk2.chunk_hash in linked
        assert msg_chunk3.chunk_hash in linked

    def test_run_link_type_and_confidence(self, doc_store):
        """Created links have correct link_type and confidence."""
        person_hash = make_sha256_hash("contact_dave")
        msg_hash = make_sha256_hash("message_from_dave")

        person_chunk = Chunk(
            chunk_hash=person_hash,
            content="Contact Dave",
            context_header="Contact",
            chunk_index=0,
            domain_metadata={
                "contact_id": "contact_4",
                "display_name": "Dave",
                "emails": ["dave@example.com"],
                "phones": [],
            },
        )

        msg_chunk = Chunk(
            chunk_hash=msg_hash,
            content="Message from Dave",
            chunk_index=0,
            domain_metadata={"sender": "dave@example.com"},
        )

        people_config = AdapterConfig(
            adapter_id="people_adapter",
            adapter_type="test",
            domain=Domain.PEOPLE,
            normalizer_version="1.0.0",
        )
        msg_config = AdapterConfig(
            adapter_id="msg_adapter",
            adapter_type="test",
            domain=Domain.MESSAGES,
            normalizer_version="1.0.0",
        )

        doc_store.register_adapter(people_config)
        doc_store.register_adapter(msg_config)

        people_source = doc_store.register_source("people_adapter", "people_source", Domain.PEOPLE, "")
        msg_source = doc_store.register_source("msg_adapter", "msg_source", Domain.MESSAGES, "")

        doc_store.create_source_version("people_source", 1, "people markdown", list({person_chunk.chunk_hash}), "people_adapter", "1.0.0", "2024-01-01T00:00:00Z")
        doc_store.create_source_version("msg_source", 1, "msg markdown", list({msg_chunk.chunk_hash}), "msg_adapter", "1.0.0", "2024-01-01T00:00:00Z")

        doc_store.write_chunks([person_chunk, msg_chunk], [])

        linker = EntityLinker(doc_store)
        linker.run()

        cursor = doc_store.conn.cursor()
        cursor.execute(
            """
            SELECT source_chunk_hash, target_chunk_hash, link_type, confidence
            FROM entity_links
            WHERE source_chunk_hash = ?
            """,
            (person_chunk.chunk_hash,),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == person_chunk.chunk_hash
        assert row[1] == msg_chunk.chunk_hash
        assert row[2] == "person_appearance"
        assert row[3] == 1.0

    def test_run_cleans_up_retired_person_links(self, doc_store):
        """Retiring a person chunk cleans up its entity_links."""
        person_hash = make_sha256_hash("contact_eve")
        msg_hash = make_sha256_hash("message_from_eve")

        person_chunk = Chunk(
            chunk_hash=person_hash,
            content="Contact Eve",
            context_header="Contact",
            chunk_index=0,
            domain_metadata={
                "contact_id": "contact_5",
                "display_name": "Eve",
                "emails": ["eve@example.com"],
                "phones": [],
            },
        )

        msg_chunk = Chunk(
            chunk_hash=msg_hash,
            content="Message from Eve",
            chunk_index=0,
            domain_metadata={"sender": "eve@example.com"},
        )

        people_config = AdapterConfig(
            adapter_id="people_adapter",
            adapter_type="test",
            domain=Domain.PEOPLE,
            normalizer_version="1.0.0",
        )
        msg_config = AdapterConfig(
            adapter_id="msg_adapter",
            adapter_type="test",
            domain=Domain.MESSAGES,
            normalizer_version="1.0.0",
        )

        doc_store.register_adapter(people_config)
        doc_store.register_adapter(msg_config)

        people_source = doc_store.register_source("people_adapter", "people_source", Domain.PEOPLE, "")
        msg_source = doc_store.register_source("msg_adapter", "msg_source", Domain.MESSAGES, "")

        doc_store.create_source_version("people_source", 1, "people markdown", list({person_chunk.chunk_hash}), "people_adapter", "1.0.0", "2024-01-01T00:00:00Z")
        doc_store.create_source_version("msg_source", 1, "msg markdown", list({msg_chunk.chunk_hash}), "msg_adapter", "1.0.0", "2024-01-01T00:00:00Z")

        doc_store.write_chunks([person_chunk, msg_chunk], [])

        linker = EntityLinker(doc_store)
        linker.run()

        linked = doc_store.get_linked_chunks(person_chunk.chunk_hash)
        assert msg_chunk.chunk_hash in linked

        doc_store.retire_chunks([person_chunk.chunk_hash], "people_source", 1)
        linker.run()

        linked = doc_store.get_linked_chunks(person_chunk.chunk_hash)
        assert len(linked) == 0

    def test_run_handles_multiple_people_chunks(self, doc_store):
        """run() links all person chunks to matching message chunks."""
        person_frank_hash = make_sha256_hash("contact_frank")
        person_grace_hash = make_sha256_hash("contact_grace")
        msg_frank_hash = make_sha256_hash("message_from_frank")
        msg_grace_hash = make_sha256_hash("message_from_grace")

        person_chunk1 = Chunk(
            chunk_hash=person_frank_hash,
            content="Contact Frank",
            context_header="Contact",
            chunk_index=0,
            domain_metadata={
                "contact_id": "contact_frank",
                "display_name": "Frank",
                "emails": ["frank@example.com"],
                "phones": [],
            },
        )

        person_chunk2 = Chunk(
            chunk_hash=person_grace_hash,
            content="Contact Grace",
            context_header="Contact",
            chunk_index=0,
            domain_metadata={
                "contact_id": "contact_grace",
                "display_name": "Grace",
                "emails": ["grace@example.com"],
                "phones": [],
            },
        )

        msg_chunk_frank = Chunk(
            chunk_hash=msg_frank_hash,
            content="Message from Frank",
            chunk_index=0,
            domain_metadata={"sender": "frank@example.com"},
        )

        msg_chunk_grace = Chunk(
            chunk_hash=msg_grace_hash,
            content="Message from Grace",
            chunk_index=0,
            domain_metadata={"sender": "grace@example.com"},
        )

        people_config = AdapterConfig(
            adapter_id="people_adapter",
            adapter_type="test",
            domain=Domain.PEOPLE,
            normalizer_version="1.0.0",
        )
        msg_config = AdapterConfig(
            adapter_id="msg_adapter",
            adapter_type="test",
            domain=Domain.MESSAGES,
            normalizer_version="1.0.0",
        )

        doc_store.register_adapter(people_config)
        doc_store.register_adapter(msg_config)

        people_source = doc_store.register_source("people_adapter", "people_source", Domain.PEOPLE, "")
        msg_source = doc_store.register_source("msg_adapter", "msg_source", Domain.MESSAGES, "")

        doc_store.create_source_version(
            people_source,
            "people markdown",
            {person_chunk1.chunk_hash, person_chunk2.chunk_hash},
            "people_adapter",
        )
        doc_store.create_source_version(
            msg_source,
            "msg markdown",
            {msg_chunk_frank.chunk_hash, msg_chunk_grace.chunk_hash},
            "msg_adapter",
        )

        doc_store.write_chunks([person_chunk1, person_chunk2, msg_chunk_frank, msg_chunk_grace], [])

        linker = EntityLinker(doc_store)
        new_links = linker.run()

        assert new_links == 2

        linked_frank = doc_store.get_linked_chunks(person_chunk1.chunk_hash, link_type="person_appearance")
        linked_grace = doc_store.get_linked_chunks(person_chunk2.chunk_hash, link_type="person_appearance")

        assert msg_chunk_frank.chunk_hash in linked_frank
        assert msg_chunk_grace.chunk_hash in linked_grace


class TestEntityLinkerIntegration:
    """Integration tests with multiple domains."""

    def test_integration_full_ingest_and_linking(self, doc_store):
        """Integration test: 2 people + 5 messages, 4 matches (3 for alice, 1 for bob)."""
        alice_hash = make_sha256_hash("alice_smith")
        bob_hash = make_sha256_hash("bob_jones")
        msg1_hash = make_sha256_hash("work_email_from_alice")
        msg2_hash = make_sha256_hash("home_email_from_alice")
        msg3_hash = make_sha256_hash("scheduled_call_with_alice")
        msg4_hash = make_sha256_hash("update_from_bob")
        msg5_hash = make_sha256_hash("unknown_message")

        alice = Chunk(
            chunk_hash=alice_hash,
            content="Alice contact",
            context_header="Contact",
            chunk_index=0,
            domain_metadata={
                "contact_id": "alice_id",
                "display_name": "Alice Smith",
                "emails": ["alice@work.com", "alice@home.com"],
                "phones": [],
            },
        )

        bob = Chunk(
            chunk_hash=bob_hash,
            content="Bob contact",
            context_header="Contact",
            chunk_index=0,
            domain_metadata={
                "contact_id": "bob_id",
                "display_name": "Bob Jones",
                "emails": ["bob@work.com"],
                "phones": ["+1-555-9876"],
            },
        )

        msg1 = Chunk(
            chunk_hash=msg1_hash,
            content="Hi from work",
            chunk_index=0,
            domain_metadata={"sender": "alice@work.com", "recipients": ["bob@work.com"]},
        )

        msg2 = Chunk(
            chunk_hash=msg2_hash,
            content="Hi from home",
            chunk_index=0,
            domain_metadata={"sender": "alice@home.com"},
        )

        msg3 = Chunk(
            chunk_hash=msg3_hash,
            content="Scheduled call",
            chunk_index=0,
            domain_metadata={"invitees": ["alice@home.com", "charlie@example.com"]},
        )

        msg4 = Chunk(
            chunk_hash=msg4_hash,
            content="Update from Bob",
            chunk_index=0,
            domain_metadata={"sender": "bob@work.com"},
        )

        msg5 = Chunk(
            chunk_hash=msg5_hash,
            content="From unknown person",
            chunk_index=0,
            domain_metadata={"sender": "unknown@example.com"},
        )

        people_config = AdapterConfig(
            adapter_id="people_adapter",
            adapter_type="test",
            domain=Domain.PEOPLE,
            normalizer_version="1.0.0",
        )
        msg_config = AdapterConfig(
            adapter_id="msg_adapter",
            adapter_type="test",
            domain=Domain.MESSAGES,
            normalizer_version="1.0.0",
        )

        doc_store.register_adapter(people_config)
        doc_store.register_adapter(msg_config)

        people_source = doc_store.register_source("people_adapter", "people_source", Domain.PEOPLE, "")
        msg_source = doc_store.register_source("msg_adapter", "msg_source", Domain.MESSAGES, "")

        doc_store.create_source_version(
            people_source,
            "people markdown",
            {alice.chunk_hash, bob.chunk_hash},
            "people_adapter",
        )
        doc_store.create_source_version(
            msg_source,
            "msg markdown",
            {msg1.chunk_hash, msg2.chunk_hash, msg3.chunk_hash, msg4.chunk_hash, msg5.chunk_hash},
            "msg_adapter",
        )

        all_chunks = [alice, bob, msg1, msg2, msg3, msg4, msg5]
        doc_store.write_chunks(all_chunks, [])

        linker = EntityLinker(doc_store)
        new_links = linker.run()

        assert new_links == 4

        alice_links = doc_store.get_linked_chunks(alice.chunk_hash, link_type="person_appearance")
        assert msg1.chunk_hash in alice_links
        assert msg2.chunk_hash in alice_links
        assert msg3.chunk_hash in alice_links
        assert msg4.chunk_hash not in alice_links

        bob_links = doc_store.get_linked_chunks(bob.chunk_hash, link_type="person_appearance")
        assert msg4.chunk_hash in bob_links
        assert msg1.chunk_hash not in bob_links
        assert msg2.chunk_hash not in bob_links
        assert msg3.chunk_hash not in bob_links

        msg5_links = doc_store.get_linked_chunks(msg5.chunk_hash)
        assert len(msg5_links) == 0
