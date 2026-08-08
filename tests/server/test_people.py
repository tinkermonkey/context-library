"""Tests for GET /people/{contact_id}/context."""

from typing import Generator

import pytest
from fastapi.testclient import TestClient

from context_library.storage.document_store import DocumentStore
from context_library.storage.models import (
    AdapterConfig,
    Chunk,
    ChunkType,
    Domain,
    ENTITY_LINK_TYPE_PERSON_APPEARANCE,
    EntityLink,
    LineageRecord,
    PeopleMetadata,
    PollStrategy,
    compute_chunk_hash,
)

from .conftest import _create_app_with_store


CONTACT_ID = "apple-uuid-abc123"


@pytest.fixture()
def ds_with_contact(ds: DocumentStore) -> Generator[DocumentStore, None, None]:
    """DocumentStore with a PEOPLE chunk linked to a MESSAGES chunk via entity_links."""
    store = ds

    # PEOPLE adapter/source/chunk for the contact
    people_config = AdapterConfig(
        adapter_id="contacts-adapter",
        adapter_type="apple_contacts",
        domain=Domain.PEOPLE,
        normalizer_version="1.0.0",
    )
    store.register_adapter(people_config)
    store.register_source(
        source_id="src-people",
        adapter_id="contacts-adapter",
        domain=Domain.PEOPLE,
        origin_ref="contacts/alice",
        poll_strategy=PollStrategy.PULL,
        poll_interval_sec=3600,
    )

    person_meta = PeopleMetadata(
        contact_id=CONTACT_ID,
        display_name="Alice Example",
        emails=("alice@example.com",),
        source_type="apple_contacts",
    )
    person_content = "Alice Example"
    person_hash = compute_chunk_hash(person_content)
    person_chunk = Chunk(
        chunk_hash=person_hash,
        content=person_content,
        chunk_index=0,
        chunk_type=ChunkType.STANDARD,
        domain_metadata=person_meta.model_dump(),
    )
    store.create_source_version(
        source_id="src-people",
        version=1,
        markdown=person_content,
        chunk_hashes=[person_hash],
        adapter_id="contacts-adapter",
        normalizer_version="1.0.0",
        fetch_timestamp="2024-01-01T00:00:00+00:00",
    )
    store.write_chunks(
        chunks=[person_chunk],
        lineage_records=[
            LineageRecord(
                chunk_hash=person_hash,
                source_id="src-people",
                source_version_id=1,
                adapter_id="contacts-adapter",
                domain=Domain.PEOPLE,
                normalizer_version="1.0.0",
                embedding_model_id="all-MiniLM-L6-v2",
            )
        ],
    )

    # MESSAGES adapter/source/chunk that will be linked to the contact
    msg_config = AdapterConfig(
        adapter_id="imessage-adapter",
        adapter_type="apple_imessage",
        domain=Domain.MESSAGES,
        normalizer_version="1.0.0",
    )
    store.register_adapter(msg_config)
    store.register_source(
        source_id="src-messages",
        adapter_id="imessage-adapter",
        domain=Domain.MESSAGES,
        origin_ref="imessage/thread-1",
        poll_strategy=PollStrategy.PULL,
        poll_interval_sec=3600,
    )
    msg_content = "Hey, are we still on for lunch?"
    msg_hash = compute_chunk_hash(msg_content)
    msg_chunk = Chunk(
        chunk_hash=msg_hash,
        content=msg_content,
        chunk_index=0,
        chunk_type=ChunkType.STANDARD,
        domain_metadata={"sender": "alice@example.com"},
    )
    store.create_source_version(
        source_id="src-messages",
        version=1,
        markdown=msg_content,
        chunk_hashes=[msg_hash],
        adapter_id="imessage-adapter",
        normalizer_version="1.0.0",
        fetch_timestamp="2024-03-01T12:00:00+00:00",
    )
    store.write_chunks(
        chunks=[msg_chunk],
        lineage_records=[
            LineageRecord(
                chunk_hash=msg_hash,
                source_id="src-messages",
                source_version_id=1,
                adapter_id="imessage-adapter",
                domain=Domain.MESSAGES,
                normalizer_version="1.0.0",
                embedding_model_id="all-MiniLM-L6-v2",
            )
        ],
    )

    store.write_entity_links(
        [
            EntityLink(
                source_chunk_hash=person_hash,
                target_chunk_hash=msg_hash,
                link_type=ENTITY_LINK_TYPE_PERSON_APPEARANCE,
                confidence=1.0,
            )
        ]
    )

    yield store


@pytest.fixture()
def client_with_contact(ds_with_contact: DocumentStore) -> Generator[TestClient, None, None]:
    yield from _create_app_with_store(ds_with_contact)


class TestGetPersonContext:
    def test_returns_200_and_linked_chunk(self, client_with_contact: TestClient) -> None:
        resp = client_with_contact.get(f"/people/{CONTACT_ID}/context")
        assert resp.status_code == 200
        data = resp.json()
        assert data["contact_id"] == CONTACT_ID
        assert data["total"] == 1
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["content"] == "Hey, are we still on for lunch?"
        assert item["domain"] == "messages"
        assert item["lineage"]["source_id"] == "src-messages"

    def test_unknown_contact_returns_404(self, client_with_contact: TestClient) -> None:
        resp = client_with_contact.get("/people/no-such-contact/context")
        assert resp.status_code == 404

    def test_domain_filter_excludes_non_matching(self, client_with_contact: TestClient) -> None:
        resp = client_with_contact.get(f"/people/{CONTACT_ID}/context", params={"domains": "events,notes"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_domain_filter_includes_matching(self, client_with_contact: TestClient) -> None:
        resp = client_with_contact.get(f"/people/{CONTACT_ID}/context", params={"domains": "messages"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_since_filter_excludes_when_bound_is_in_future(self, client_with_contact: TestClient) -> None:
        # fetch_timestamp is stamped at write time, so a since-bound far in the
        # future must exclude a chunk written "now".
        resp = client_with_contact.get(
            f"/people/{CONTACT_ID}/context", params={"since": "2999-01-01T00:00:00+00:00"}
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_before_filter_excludes_when_bound_is_in_past(self, client_with_contact: TestClient) -> None:
        resp = client_with_contact.get(
            f"/people/{CONTACT_ID}/context", params={"before": "2000-01-01T00:00:00+00:00"}
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_since_and_before_include_when_bounds_span_now(self, client_with_contact: TestClient) -> None:
        resp = client_with_contact.get(
            f"/people/{CONTACT_ID}/context",
            params={"since": "2000-01-01T00:00:00+00:00", "before": "2999-01-01T00:00:00+00:00"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_limit_and_offset(self, client_with_contact: TestClient) -> None:
        resp = client_with_contact.get(f"/people/{CONTACT_ID}/context", params={"limit": 1, "offset": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"] == []
