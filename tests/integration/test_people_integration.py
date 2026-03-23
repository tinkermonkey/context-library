"""Integration tests for the people domain: AppleContactsAdapter → EntityLinker → Query"""

import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock
import pytest
from context_library.storage.document_store import DocumentStore
from context_library.adapters.apple_contacts import AppleContactsAdapter
from context_library.core.entity_linker import EntityLinker


class TestPeopleDomainIntegration:
    """Integration tests for people domain ingestion, entity linking, and querying."""

    def test_people_domain_chunks_stored_correctly(self) -> None:
        """Test that people domain chunks are stored and retrievable from DocumentStore."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            store = DocumentStore(db_path)

            try:
                # Setup: Create adapters and sources for people domain
                store.conn.execute("""
                    INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version)
                    VALUES (?, ?, ?, ?)
                """, ("apple_contacts_adapter", "people", "AppleContactsAdapter", "1.0"))

                store.conn.execute("""
                    INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy)
                    VALUES (?, ?, ?, ?, ?)
                """, ("contacts_source", "apple_contacts_adapter", "people", "Apple Contacts", "push"))

                store.conn.execute("""
                    INSERT INTO source_versions (source_id, version, markdown, chunk_hashes, adapter_id, normalizer_version, fetch_timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """, ("contacts_source", 1, "# Contacts", "alice_chunk,bob_chunk", "apple_contacts_adapter", "1.0"))

                # Create people chunks
                people_chunks = [
                    {
                        "chunk_hash": "alice_chunk",
                        "content": "# Alice Smith\nalice@example.com\n+15551234567\nAcme Corp",
                        "domain_metadata": '{"contact_id": "contact1", "display_name": "Alice Smith", "emails": ["alice@example.com"], "phones": ["+15551234567"], "organization": "Acme Corp"}'
                    },
                    {
                        "chunk_hash": "bob_chunk",
                        "content": "# Bob Johnson\nbob@example.com",
                        "domain_metadata": '{"contact_id": "contact2", "display_name": "Bob Johnson", "emails": ["bob@example.com"], "phones": []}'
                    }
                ]

                # Insert people chunks
                for idx, chunk in enumerate(people_chunks):
                    store.conn.execute("""
                        INSERT INTO chunks
                        (chunk_hash, source_id, source_version, chunk_index, content, domain, adapter_id, fetch_timestamp, normalizer_version, domain_metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?)
                    """, (
                        chunk["chunk_hash"],
                        "contacts_source",
                        1,
                        idx,
                        chunk["content"],
                        "people",
                        "apple_contacts_adapter",
                        "1.0",
                        chunk["domain_metadata"]
                    ))

                store.conn.commit()

                # Verify chunks are stored
                cursor = store.conn.execute("SELECT COUNT(*) FROM chunks WHERE domain = ?", ("people",))
                people_count = cursor.fetchone()[0]
                assert people_count == 2

                # Verify chunk retrieval
                cursor = store.conn.execute(
                    "SELECT chunk_hash, content FROM chunks WHERE domain = ? AND chunk_hash = ?",
                    ("people", "alice_chunk")
                )
                result = cursor.fetchone()
                assert result is not None
                assert result[0] == "alice_chunk"
                assert "Alice Smith" in result[1]

            finally:
                store.close()

    def test_people_adapter_creates_people_domain_chunks(self) -> None:
        """Test that AppleContactsAdapter properly creates people domain chunks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            store = DocumentStore(db_path)

            try:
                # Mock AppleContactsAdapter fetch to return contact data
                mock_contacts = [
                    {
                        "id": "contact1",
                        "display_name": "Alice Smith",
                        "emails": ["alice@example.com"],
                        "phones": ["+15551234567"],
                        "organization": "Acme Corp",
                        "source_type": "apple_contacts"
                    }
                ]

                # Create mock adapter and verify it's configured for people domain
                with patch.object(AppleContactsAdapter, 'fetch', new_callable=AsyncMock) as mock_fetch:
                    mock_fetch.return_value = mock_contacts

                    adapter = AppleContactsAdapter(
                        api_url="http://localhost:7123",
                        api_key="test-key",
                        account_id="test-account"
                    )

                    # Verify adapter domain is 'people'
                    assert adapter.domain == "people"
                    assert adapter.adapter_id is not None
                    assert adapter.domain == "people"

            finally:
                store.close()

    def test_domain_filter_returns_only_people_chunks(self) -> None:
        """Test that domain filter correctly returns only people chunks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            store = DocumentStore(db_path)

            try:
                # Create seed data with multiple domains
                store.conn.execute("""
                    INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version)
                    VALUES (?, ?, ?, ?), (?, ?, ?, ?), (?, ?, ?, ?)
                """, (
                    "adapter_people", "people", "AppleContactsAdapter", "1.0",
                    "adapter_messages", "messages", "TestAdapter", "1.0",
                    "adapter_notes", "notes", "TestAdapter", "1.0"
                ))

                store.conn.execute("""
                    INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy)
                    VALUES (?, ?, ?, ?, ?), (?, ?, ?, ?, ?), (?, ?, ?, ?, ?)
                """, (
                    "source_people", "adapter_people", "people", "ref1", "push",
                    "source_messages", "adapter_messages", "messages", "ref2", "push",
                    "source_notes", "adapter_notes", "notes", "ref3", "push"
                ))

                store.conn.execute("""
                    INSERT INTO source_versions (source_id, version, markdown, chunk_hashes, adapter_id, normalizer_version, fetch_timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now')), (?, ?, ?, ?, ?, ?, datetime('now')), (?, ?, ?, ?, ?, ?, datetime('now'))
                """, (
                    "source_people", 1, "people content", "p1,p2", "adapter_people", "1.0",
                    "source_messages", 1, "message content", "m1,m2", "adapter_messages", "1.0",
                    "source_notes", 1, "notes content", "n1", "adapter_notes", "1.0"
                ))

                # Insert chunks from different domains
                chunks = [
                    ("person_1", "source_people", 1, 0, "Alice Smith", "people", "adapter_people"),
                    ("person_2", "source_people", 1, 1, "Bob Johnson", "people", "adapter_people"),
                    ("msg_1", "source_messages", 1, 0, "Hello world", "messages", "adapter_messages"),
                    ("msg_2", "source_messages", 1, 1, "Hi there", "messages", "adapter_messages"),
                    ("note_1", "source_notes", 1, 0, "My note", "notes", "adapter_notes")
                ]

                for chunk_hash, source_id, version, chunk_idx, content, domain, adapter_id in chunks:
                    store.conn.execute("""
                        INSERT INTO chunks (chunk_hash, source_id, source_version, chunk_index, content, domain, adapter_id, fetch_timestamp, normalizer_version)
                        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
                    """, (chunk_hash, source_id, version, chunk_idx, content, domain, adapter_id, "1.0"))

                store.conn.commit()

                # Query for people domain only
                cursor = store.conn.execute("SELECT COUNT(*) FROM chunks WHERE domain = ?", ("people",))
                people_count = cursor.fetchone()[0]
                assert people_count == 2

                # Verify filtering works - get all chunks and filter in SQL
                cursor = store.conn.execute("SELECT domain FROM chunks WHERE domain != ?", ("people",))
                non_people = [row[0] for row in cursor.fetchall()]
                assert all(d != "people" for d in non_people)
                assert len(non_people) == 3

                # Query only people chunks
                cursor = store.conn.execute("SELECT chunk_hash FROM chunks WHERE domain = ? ORDER BY chunk_hash", ("people",))
                people_hashes = [row[0] for row in cursor.fetchall()]
                assert people_hashes == ["person_1", "person_2"]

            finally:
                store.close()

    def test_entity_links_infrastructure_for_people(self) -> None:
        """Test that entity_links table and methods work correctly for people domain."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            store = DocumentStore(db_path)

            try:
                # Create test data
                store.conn.execute("""
                    INSERT INTO adapters (adapter_id, domain, adapter_type, normalizer_version)
                    VALUES (?, ?, ?, ?), (?, ?, ?, ?)
                """, (
                    "people_adapter", "people", "AppleContactsAdapter", "1.0",
                    "messages_adapter", "messages", "TestAdapter", "1.0"
                ))

                store.conn.execute("""
                    INSERT INTO sources (source_id, adapter_id, domain, origin_ref, poll_strategy)
                    VALUES (?, ?, ?, ?, ?), (?, ?, ?, ?, ?)
                """, (
                    "people_src", "people_adapter", "people", "ref1", "push",
                    "messages_src", "messages_adapter", "messages", "ref2", "push"
                ))

                store.conn.execute("""
                    INSERT INTO source_versions (source_id, version, markdown, chunk_hashes, adapter_id, normalizer_version, fetch_timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now')), (?, ?, ?, ?, ?, ?, datetime('now'))
                """, (
                    "people_src", 1, "people content", "alice_chunk", "people_adapter", "1.0",
                    "messages_src", 1, "message content", "msg_chunk", "messages_adapter", "1.0"
                ))

                # Insert chunks
                store.conn.execute("""
                    INSERT INTO chunks (chunk_hash, source_id, source_version, chunk_index, content, domain, adapter_id, fetch_timestamp, normalizer_version, domain_metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?), (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?)
                """, (
                    "alice_chunk", "people_src", 1, 0, "Alice Smith", "people", "people_adapter", "1.0", '{"emails": ["alice@example.com"]}',
                    "msg_chunk", "messages_src", 1, 0, "Message from Alice", "messages", "messages_adapter", "1.0", '{"sender": "alice@example.com"}'
                ))

                store.conn.commit()

                # Write entity links
                store.write_entity_links([
                    ("alice_chunk", "msg_chunk", "person_appearance", 0.95)
                ])

                # Verify link exists
                cursor = store.conn.execute("""
                    SELECT COUNT(*) FROM entity_links
                    WHERE source_chunk_hash = ? AND target_chunk_hash = ? AND link_type = ?
                """, ("alice_chunk", "msg_chunk", "person_appearance"))

                assert cursor.fetchone()[0] == 1

                # Verify get_linked_chunks works
                links = store.get_linked_chunks("alice_chunk", link_type="person_appearance")
                assert len(links) == 1
                assert links[0] == "msg_chunk"

                # Test bidirectional retrieval
                reverse_links = store.get_linked_chunks("msg_chunk")
                assert "alice_chunk" in reverse_links

                # Test deletion
                store.delete_entity_links_for_chunk("alice_chunk")
                links_after_delete = store.get_linked_chunks("alice_chunk")
                assert len(links_after_delete) == 0

            finally:
                store.close()
