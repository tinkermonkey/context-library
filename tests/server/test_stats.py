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
        ds.conn.execute("DELETE FROM chunks")
        ds.conn.execute("DELETE FROM source_versions")
        ds.conn.execute("DELETE FROM sources")
        ds.conn.execute("DELETE FROM adapters")
        ds.conn.commit()
        data = client.get("/stats").json()
        assert data["total_sources"] == 0
        assert data["total_active_chunks"] == 0
        assert data["by_domain"] == []
