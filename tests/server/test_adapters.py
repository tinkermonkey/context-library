"""Tests for GET /adapters and GET /adapters/{adapter_id}."""

from fastapi.testclient import TestClient


class TestListAdapters:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/adapters")
        assert resp.status_code == 200

    def test_contains_registered_adapter(self, client: TestClient) -> None:
        data = client.get("/adapters").json()
        assert data["total"] == 1
        assert len(data["adapters"]) == 1
        adapter = data["adapters"][0]
        assert adapter["adapter_id"] == "test-adapter"
        assert adapter["adapter_type"] == "filesystem"
        assert adapter["domain"] == "notes"

    def test_links_present(self, client: TestClient) -> None:
        adapter = client.get("/adapters").json()["adapters"][0]
        links = adapter["_links"]
        assert links["self"] == "/adapters/test-adapter"
        assert "adapter_id=test-adapter" in links["sources"]

    def test_empty_when_no_adapters(self, client: TestClient, ds) -> None:
        # Remove in FK order: chunks → source_versions → sources → adapters
        ds.conn.execute("DELETE FROM chunks")
        ds.conn.execute("DELETE FROM source_versions")
        ds.conn.execute("DELETE FROM sources")
        ds.conn.execute("DELETE FROM adapters")
        ds.conn.commit()
        data = client.get("/adapters").json()
        assert data["total"] == 0
        assert data["adapters"] == []


class TestGetAdapter:
    def test_returns_adapter(self, client: TestClient) -> None:
        resp = client.get("/adapters/test-adapter")
        assert resp.status_code == 200
        data = resp.json()
        assert data["adapter_id"] == "test-adapter"
        assert data["normalizer_version"] == "1.0.0"

    def test_404_for_missing_adapter(self, client: TestClient) -> None:
        resp = client.get("/adapters/nonexistent")
        assert resp.status_code == 404

    def test_links_present(self, client: TestClient) -> None:
        data = client.get("/adapters/test-adapter").json()
        assert "_links" in data
        assert data["_links"]["self"] == "/adapters/test-adapter"
