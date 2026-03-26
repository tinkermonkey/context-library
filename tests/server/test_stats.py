"""Tests for GET /stats."""

from fastapi.testclient import TestClient


class TestGetStats:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/stats")
        assert resp.status_code == 200

    def test_structure(self, client: TestClient) -> None:
        data = client.get("/stats").json()
        assert "total_sources" in data
        assert "total_active_chunks" in data
        assert "retired_chunk_count" in data
        assert "sync_queue_pending_insert" in data
        assert "sync_queue_pending_delete" in data
        assert "by_domain" in data

    def test_counts_match_fixture(self, client: TestClient) -> None:
        data = client.get("/stats").json()
        assert data["total_sources"] == 1
        assert data["total_active_chunks"] == 1
        assert data["retired_chunk_count"] == 0

    def test_by_domain_entry(self, client: TestClient) -> None:
        data = client.get("/stats").json()
        assert len(data["by_domain"]) == 1
        domain_entry = data["by_domain"][0]
        assert domain_entry["domain"] == "notes"
        assert domain_entry["source_count"] == 1
        assert domain_entry["active_chunk_count"] == 1

    def test_zeros_when_empty(self, client: TestClient, ds) -> None:
        # Clear all data
        ds.conn.execute("DELETE FROM entity_links")
        ds.conn.execute("DELETE FROM chunks")
        ds.conn.execute("DELETE FROM source_versions")
        ds.conn.execute("DELETE FROM sources")
        ds.conn.execute("DELETE FROM adapters")
        ds.conn.commit()
        data = client.get("/stats").json()
        assert data["total_sources"] == 0
        assert data["total_active_chunks"] == 0
        assert data["by_domain"] == []


class TestGetAdapterStats:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/stats/adapters")
        assert resp.status_code == 200

    def test_response_structure(self, client: TestClient) -> None:
        data = client.get("/stats/adapters").json()
        assert "adapters" in data
        assert isinstance(data["adapters"], list)

    def test_returns_adapter_entry(self, client: TestClient) -> None:
        data = client.get("/stats/adapters").json()
        assert len(data["adapters"]) == 1
        adapter = data["adapters"][0]
        assert adapter["adapter_id"] == "test-adapter"
        assert adapter["adapter_type"] == "filesystem"
        assert adapter["domain"] == "notes"
        assert "source_count" in adapter
        assert "active_chunk_count" in adapter

    def test_counts_match_fixture(self, client: TestClient) -> None:
        data = client.get("/stats/adapters").json()
        adapter = data["adapters"][0]
        assert adapter["source_count"] == 1
        assert adapter["active_chunk_count"] == 1

    def test_empty_when_no_adapters(self, client: TestClient, ds) -> None:
        # Clear all data
        ds.conn.execute("DELETE FROM entity_links")
        ds.conn.execute("DELETE FROM chunks")
        ds.conn.execute("DELETE FROM source_versions")
        ds.conn.execute("DELETE FROM sources")
        ds.conn.execute("DELETE FROM adapters")
        ds.conn.commit()
        data = client.get("/stats/adapters").json()
        assert data["adapters"] == []

    def test_multi_source_same_adapter(self, client_multi_source: TestClient) -> None:
        """Verify adapter stats with multiple sources from single adapter."""
        data = client_multi_source.get("/stats/adapters").json()
        assert len(data["adapters"]) == 1
        adapter = data["adapters"][0]
        assert adapter["adapter_id"] == "test-adapter"
        assert adapter["source_count"] == 3  # src-1, src-2, src-3
        assert adapter["active_chunk_count"] == 3  # One chunk per source

    def test_multi_adapter_same_domain(self, client_multi_adapter_same_domain: TestClient) -> None:
        """Verify adapter stats with multiple adapters managing same domain."""
        data = client_multi_adapter_same_domain.get("/stats/adapters").json()
        assert len(data["adapters"]) == 2

        # Find adapters by ID
        adapters_by_id = {a["adapter_id"]: a for a in data["adapters"]}

        # Verify filesystem adapter
        assert adapters_by_id["test-adapter"]["domain"] == "notes"
        assert adapters_by_id["test-adapter"]["source_count"] == 1
        assert adapters_by_id["test-adapter"]["active_chunk_count"] == 1

        # Verify obsidian adapter
        assert adapters_by_id["obsidian-adapter"]["domain"] == "notes"
        assert adapters_by_id["obsidian-adapter"]["source_count"] == 1
        assert adapters_by_id["obsidian-adapter"]["active_chunk_count"] == 1

        # Total chunks should be 2 (one from each adapter)
        total_chunks = sum(a["active_chunk_count"] for a in data["adapters"])
        assert total_chunks == 2

    def test_multi_domain_adapters(self, client_multi_domain: TestClient) -> None:
        """Verify adapter stats with adapters across multiple domains."""
        data = client_multi_domain.get("/stats/adapters").json()
        assert len(data["adapters"]) == 3  # notes, messages, events

        # Verify domains are represented
        domains = {a["domain"] for a in data["adapters"]}
        assert domains == {"notes", "messages", "events"}

        # Each adapter should have exactly 1 source
        for adapter in data["adapters"]:
            assert adapter["source_count"] == 1
            assert adapter["active_chunk_count"] == 1

    def test_comprehensive_fixture(self, client_comprehensive: TestClient) -> None:
        """Verify adapter stats with comprehensive fixture (4 adapters, 3 domains)."""
        data = client_comprehensive.get("/stats/adapters").json()
        assert len(data["adapters"]) == 4

        # Verify specific adapters
        adapters_by_id = {a["adapter_id"]: a for a in data["adapters"]}

        # Filesystem adapter (base): 1 source, 1 chunk
        assert adapters_by_id["test-adapter"]["source_count"] == 1
        assert adapters_by_id["test-adapter"]["active_chunk_count"] == 1

        # Obsidian adapter: 2 sources, 2 chunks
        assert adapters_by_id["obsidian-adapter"]["source_count"] == 2
        assert adapters_by_id["obsidian-adapter"]["active_chunk_count"] == 2

        # Email adapter: 1 source, 1 chunk
        assert adapters_by_id["email-adapter"]["source_count"] == 1
        assert adapters_by_id["email-adapter"]["active_chunk_count"] == 1

        # Calendar adapter: 1 source, 1 chunk
        assert adapters_by_id["calendar-adapter"]["source_count"] == 1
        assert adapters_by_id["calendar-adapter"]["active_chunk_count"] == 1

        # Total chunks
        total_chunks = sum(a["active_chunk_count"] for a in data["adapters"])
        assert total_chunks == 5
