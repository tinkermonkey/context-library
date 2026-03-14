"""Tests for /chunks endpoints."""

from fastapi.testclient import TestClient


class TestGetChunk:
    def test_returns_chunk(self, client: TestClient, chunk_hash: str) -> None:
        resp = client.get(f"/chunks/{chunk_hash}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["chunk_hash"] == chunk_hash
        assert data["content"] == "Hello world"
        assert "lineage" in data

    def test_with_source_id_filter(self, client: TestClient, chunk_hash: str) -> None:
        resp = client.get(f"/chunks/{chunk_hash}?source_id=src-1")
        assert resp.status_code == 200
        assert resp.json()["chunk_hash"] == chunk_hash

    def test_404_for_missing_hash(self, client: TestClient) -> None:
        resp = client.get(f"/chunks/{'a' * 64}")
        assert resp.status_code == 404

    def test_422_for_invalid_hash_format(self, client: TestClient) -> None:
        resp = client.get("/chunks/not-a-hash")
        assert resp.status_code == 422

    def test_links_present(self, client: TestClient, chunk_hash: str) -> None:
        data = client.get(f"/chunks/{chunk_hash}").json()
        links = data["_links"]
        assert "self" in links
        assert "provenance" in links
        assert "version_chain" in links


class TestGetChunkProvenance:
    def test_returns_provenance(self, client: TestClient, chunk_hash: str) -> None:
        resp = client.get(f"/chunks/{chunk_hash}/provenance?source_id=src-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_origin_ref"] == "/docs/readme.md"
        assert data["adapter_type"] == "filesystem"
        assert len(data["version_chain"]) >= 1

    def test_404_for_missing_chunk(self, client: TestClient) -> None:
        resp = client.get(f"/chunks/{'b' * 64}/provenance?source_id=src-1")
        assert resp.status_code == 404

    def test_422_for_invalid_hash(self, client: TestClient) -> None:
        resp = client.get("/chunks/badhash/provenance")
        assert resp.status_code == 422


class TestGetChunkVersionChain:
    def test_returns_chain(self, client: TestClient, chunk_hash: str) -> None:
        resp = client.get(f"/chunks/{chunk_hash}/version-chain?source_id=src-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["chunk_hash"] == chunk_hash
        assert data["source_id"] == "src-1"
        assert len(data["chain"]) == 1

    def test_404_for_missing_chunk_in_source(self, client: TestClient) -> None:
        resp = client.get(f"/chunks/{'c' * 64}/version-chain?source_id=src-1")
        assert resp.status_code == 404

    def test_422_requires_source_id(self, client: TestClient, chunk_hash: str) -> None:
        resp = client.get(f"/chunks/{chunk_hash}/version-chain")
        assert resp.status_code == 422
