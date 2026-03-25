"""Tests for the EntityLinker post-pipeline linking pass."""

import pytest
import sys
from pathlib import Path

from context_library.core.entity_linker import EntityLinker
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import Chunk, Domain

# Add parent directory to sys.path to allow importing helpers module
sys.path.insert(0, str(Path(__file__).parent.parent))
from helpers import make_sha256_hash, setup_chunk_in_store


@pytest.fixture
def doc_store():
    """Fixture providing an in-memory SQLite DocumentStore."""
    store = DocumentStore(":memory:")
    yield store
    store.close()


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
        """Exclude chunks from people domain (no self-links).

        Verifies that when searching for matching chunks, the entity linker
        properly excludes chunks from the people domain even if they contain
        matching identifiers. This prevents people chunks from linking to each
        other, which would create spurious "person of person" links.
        """
        people_hash = make_sha256_hash("contact_alice")
        people_chunk = Chunk(
            chunk_hash=people_hash,
            content="Contact Alice",
            context_header="Contact",
            chunk_index=0,
            domain_metadata={"emails": ["alice@example.com"], "phones": []},
        )

        # CRITICAL: Actually set up the chunk in the store with proper lineage
        setup_chunk_in_store(
            doc_store,
            people_chunk,
            "people_adapter",
            "AppleContactsAdapter",
            "people_source",
            Domain.PEOPLE,
        )

        linker = EntityLinker(doc_store)
        matching = linker._find_matching_chunks(["alice@example.com"])

        # The key assertion: people domain chunks should NOT be in matching results
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
            chunk_index=0,  # Distinct index required for UNIQUE constraint
            domain_metadata={"sender": "alice@example.com"},
        )
        chunk_host = Chunk(
            chunk_hash=chunk_host_hash,
            content="Host alice",
            chunk_index=1,  # Distinct index required for UNIQUE constraint
            domain_metadata={"host": "alice@example.com"},
        )
        chunk_author = Chunk(
            chunk_hash=chunk_author_hash,
            content="Author alice",
            chunk_index=2,  # Distinct index required for UNIQUE constraint
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

    def test_find_matching_chunks_with_missing_array_fields(self, doc_store):
        """Match scalar fields even when array fields are missing or NULL.

        This tests the fix for json_each() SQL errors when chunks lack array
        fields like recipients, invitees, or collaborators. Previously, a single
        missing array field would cause the entire query to fail via exception,
        silently discarding all valid scalar field matches.
        """
        # Chunk with only scalar fields, no array fields
        msg_hash = make_sha256_hash("message_minimal_fields")
        msg_chunk = Chunk(
            chunk_hash=msg_hash,
            content="Minimal message",
            chunk_index=0,
            domain_metadata={"sender": "alice@example.com"},
            # Note: no recipients, invitees, collaborators fields
        )

        setup_chunk_in_store(doc_store, msg_chunk, "msg_adapter", "test", "source_1", Domain.MESSAGES)

        linker = EntityLinker(doc_store)
        matching = linker._find_matching_chunks(["alice@example.com"])

        # Should find the chunk via scalar field match despite missing array fields
        assert msg_chunk.chunk_hash in matching

    def test_find_matching_chunks_with_null_domain_metadata(self, doc_store):
        """Match chunks with NULL domain_metadata in scalar field comparisons.

        When a chunk has domain_metadata=NULL, json_extract() for scalar fields
        returns NULL, which does not match. Array field checks should also not
        error (thanks to COALESCE default to '[]'). This ensures the query doesn't
        crash on NULL metadata.
        """
        # Chunk with NULL domain_metadata (edge case but possible)
        msg_hash = make_sha256_hash("message_null_metadata")
        msg_chunk = Chunk(
            chunk_hash=msg_hash,
            content="Message with null metadata",
            chunk_index=0,
            domain_metadata=None,  # NULL metadata
        )

        setup_chunk_in_store(doc_store, msg_chunk, "msg_adapter", "test", "source_1", Domain.MESSAGES)

        linker = EntityLinker(doc_store)
        # Should not crash; NULL metadata won't match any identifier
        matching = linker._find_matching_chunks(["alice@example.com"])
        assert msg_chunk.chunk_hash not in matching

    def test_find_matching_chunks_filters_by_current_version(self, doc_store):
        """Only match chunks from the current version of a source.

        When a source has multiple versions, only chunks belonging to
        source_version = current_version should be returned. This prevents
        entity links pointing to stale/superseded chunks.
        """
        # Create a source with v1 chunks
        msg_hash_v1 = make_sha256_hash("message_v1_old_version")
        msg_chunk_v1 = Chunk(
            chunk_hash=msg_hash_v1,
            content="Old message v1",
            chunk_index=0,
            domain_metadata={"sender": "alice@example.com"},
        )

        setup_chunk_in_store(
            doc_store, msg_chunk_v1, "msg_adapter", "test", "msg_source", Domain.MESSAGES, version=1
        )

        # Create v2 of the same source with different content
        msg_hash_v2 = make_sha256_hash("message_v2_new_version")
        msg_chunk_v2 = Chunk(
            chunk_hash=msg_hash_v2,
            content="New message v2",
            chunk_index=0,
            domain_metadata={"sender": "alice@example.com"},
        )

        setup_chunk_in_store(
            doc_store, msg_chunk_v2, "msg_adapter", "test", "msg_source", Domain.MESSAGES, version=2
        )

        linker = EntityLinker(doc_store)
        matching = linker._find_matching_chunks(["alice@example.com"])

        # Should only match v2 (current version), not v1 (superseded)
        assert msg_chunk_v2.chunk_hash in matching
        assert msg_chunk_v1.chunk_hash not in matching


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

        setup_chunk_in_store(doc_store, person_chunk, "people_adapter", "test", "people_source", Domain.PEOPLE)
        setup_chunk_in_store(doc_store, msg_chunk, "msg_adapter", "test", "msg_source", Domain.MESSAGES)

        linker = EntityLinker(doc_store)
        new_links, failures = linker.run()

        assert new_links == 1
        assert failures == 0
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

        setup_chunk_in_store(doc_store, person_chunk, "people_adapter", "test", "people_source", Domain.PEOPLE)
        setup_chunk_in_store(doc_store, msg_chunk, "msg_adapter", "test", "msg_source", Domain.MESSAGES)

        linker = EntityLinker(doc_store)
        first_links, first_failures = linker.run()
        second_links, second_failures = linker.run()

        assert first_links == 1
        assert first_failures == 0
        assert second_links == 0
        assert second_failures == 0

    def test_run_with_no_person_chunks(self, doc_store):
        """run() returns (0, 0) when no person chunks exist."""
        linker = EntityLinker(doc_store)
        links, failures = linker.run()
        assert links == 0
        assert failures == 0

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
            chunk_index=0,  # Distinct index required for UNIQUE constraint
            domain_metadata={"sender": "charlie.work@company.com"},
        )

        msg_chunk2 = Chunk(
            chunk_hash=msg_personal_hash,
            content="Personal email from Charlie",
            chunk_index=1,  # Distinct index required for UNIQUE constraint
            domain_metadata={"sender": "charlie.personal@example.com"},
        )

        msg_chunk3 = Chunk(
            chunk_hash=msg_phone_hash,
            content="Phone call from Charlie",
            chunk_index=2,  # Distinct index required for UNIQUE constraint
            domain_metadata={"sender": "+1-555-1234"},
        )

        setup_chunk_in_store(doc_store, person_chunk, "people_adapter", "test", "people_source", Domain.PEOPLE)
        setup_chunk_in_store(
            doc_store,
            [msg_chunk1, msg_chunk2, msg_chunk3],
            "msg_adapter",
            "test",
            "msg_source",
            Domain.MESSAGES,
        )

        linker = EntityLinker(doc_store)
        new_links, failures = linker.run()

        assert new_links == 3
        assert failures == 0
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

        setup_chunk_in_store(doc_store, person_chunk, "people_adapter", "test", "people_source", Domain.PEOPLE)
        setup_chunk_in_store(doc_store, msg_chunk, "msg_adapter", "test", "msg_source", Domain.MESSAGES)

        linker = EntityLinker(doc_store)
        new_links, failures = linker.run()
        assert new_links == 1
        assert failures == 0

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

        setup_chunk_in_store(doc_store, person_chunk, "people_adapter", "test", "people_source", Domain.PEOPLE)
        setup_chunk_in_store(doc_store, msg_chunk, "msg_adapter", "test", "msg_source", Domain.MESSAGES)

        linker = EntityLinker(doc_store)
        new_links, failures = linker.run()
        assert new_links == 1
        assert failures == 0

        linked = doc_store.get_linked_chunks(person_chunk.chunk_hash)
        assert msg_chunk.chunk_hash in linked

        doc_store.retire_chunks({person_chunk.chunk_hash}, "people_source", 1)
        new_links, failures = linker.run()

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
            chunk_index=0,  # Distinct index required for UNIQUE constraint
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
            chunk_index=1,  # Distinct index required for UNIQUE constraint
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
            chunk_index=0,  # Distinct index required for UNIQUE constraint
            domain_metadata={"sender": "frank@example.com"},
        )

        msg_chunk_grace = Chunk(
            chunk_hash=msg_grace_hash,
            content="Message from Grace",
            chunk_index=1,  # Distinct index required for UNIQUE constraint
            domain_metadata={"sender": "grace@example.com"},
        )

        setup_chunk_in_store(
            doc_store,
            [person_chunk1, person_chunk2],
            "people_adapter",
            "test",
            "people_source",
            Domain.PEOPLE,
        )
        setup_chunk_in_store(
            doc_store,
            [msg_chunk_frank, msg_chunk_grace],
            "msg_adapter",
            "test",
            "msg_source",
            Domain.MESSAGES,
        )

        linker = EntityLinker(doc_store)
        new_links, failures = linker.run()

        assert new_links == 2
        assert failures == 0

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
            chunk_index=0,  # Distinct index required for UNIQUE constraint
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
            chunk_index=1,  # Distinct index required for UNIQUE constraint
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
            chunk_index=0,  # Distinct index required for UNIQUE constraint
            domain_metadata={"sender": "alice@work.com", "recipients": ["bob@work.com"]},  # Matches alice (sender) and bob (recipients)
        )

        msg2 = Chunk(
            chunk_hash=msg2_hash,
            content="Hi from home",
            chunk_index=1,  # Distinct index required for UNIQUE constraint
            domain_metadata={"sender": "alice@home.com"},
        )

        msg3 = Chunk(
            chunk_hash=msg3_hash,
            content="Scheduled call",
            chunk_index=2,  # Distinct index required for UNIQUE constraint
            domain_metadata={"invitees": ["alice@home.com", "charlie@example.com"]},
        )

        msg4 = Chunk(
            chunk_hash=msg4_hash,
            content="Update from Bob",
            chunk_index=3,  # Distinct index required for UNIQUE constraint
            domain_metadata={"sender": "bob@work.com"},
        )

        msg5 = Chunk(
            chunk_hash=msg5_hash,
            content="From unknown person",
            chunk_index=4,  # Distinct index required for UNIQUE constraint
            domain_metadata={"sender": "unknown@example.com"},
        )

        setup_chunk_in_store(
            doc_store,
            [alice, bob],
            "people_adapter",
            "test",
            "people_source",
            Domain.PEOPLE,
        )
        setup_chunk_in_store(
            doc_store,
            [msg1, msg2, msg3, msg4, msg5],
            "msg_adapter",
            "test",
            "msg_source",
            Domain.MESSAGES,
        )

        linker = EntityLinker(doc_store)
        new_links, failures = linker.run()

        # msg1 matches alice (sender) and bob (recipients) = 2 links
        # msg2 matches alice (sender) = 1 link
        # msg3 matches alice (invitees) = 1 link
        # msg4 matches bob (sender) = 1 link
        # Total = 5 links
        assert new_links == 5
        assert failures == 0

        alice_links = doc_store.get_linked_chunks(alice.chunk_hash, link_type="person_appearance")
        assert msg1.chunk_hash in alice_links
        assert msg2.chunk_hash in alice_links
        assert msg3.chunk_hash in alice_links
        assert msg4.chunk_hash not in alice_links

        bob_links = doc_store.get_linked_chunks(bob.chunk_hash, link_type="person_appearance")
        assert msg4.chunk_hash in bob_links
        assert msg1.chunk_hash in bob_links  # msg1 has bob in recipients
        assert msg2.chunk_hash not in bob_links
        assert msg3.chunk_hash not in bob_links

        msg5_links = doc_store.get_linked_chunks(msg5.chunk_hash)
        assert len(msg5_links) == 0
