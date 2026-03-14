"""Tests for /sources endpoints."""

from fastapi.testclient import TestClient


class TestListSources:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/sources")
        assert resp.status_code == 200

    def test_contains_registered_source(self, client: TestClient) -> None:
        data = client.get("/sources").json()
        assert data["total"] == 1
        src = data["sources"][0]
        assert src["source_id"] == "src-1"
        assert src["domain"] == "notes"
        assert src["adapter_id"] == "test-adapter"

    def test_chunk_count_included(self, client: TestClient) -> None:
        src = client.get("/sources").json()["sources"][0]
        assert src["chunk_count"] == 1

    def test_links_present(self, client: TestClient) -> None:
        src = client.get("/sources").json()["sources"][0]
        links = src["_links"]
        assert links["self"] == "/sources/src-1"
        assert links["versions"] == "/sources/src-1/versions"
        assert links["chunks"] == "/sources/src-1/chunks"

    def test_filter_by_domain(self, client: TestClient) -> None:
        data = client.get("/sources?domain=notes").json()
        assert data["total"] == 1
        data2 = client.get("/sources?domain=messages").json()
        assert data2["total"] == 0

    def test_filter_by_adapter_id(self, client: TestClient) -> None:
        data = client.get("/sources?adapter_id=test-adapter").json()
        assert data["total"] == 1
        data2 = client.get("/sources?adapter_id=other").json()
        assert data2["total"] == 0

    def test_pagination(self, client: TestClient) -> None:
        data = client.get("/sources?limit=10&offset=0").json()
        assert data["limit"] == 10
        assert data["offset"] == 0


class TestGetSource:
    def test_returns_source(self, client: TestClient) -> None:
        resp = client.get("/sources/src-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_id"] == "src-1"
        assert data["adapter_type"] == "filesystem"
        assert data["normalizer_version"] == "1.0.0"
        assert "created_at" in data
        assert "updated_at" in data

    def test_404_for_missing_source(self, client: TestClient) -> None:
        assert client.get("/sources/no-such-source").status_code == 404


class TestGetVersionHistory:
    def test_returns_versions(self, client: TestClient) -> None:
        resp = client.get("/sources/src-1/versions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_id"] == "src-1"
        assert len(data["versions"]) == 1
        v = data["versions"][0]
        assert v["version"] == 1
        assert v["chunk_hash_count"] == 1

    def test_404_for_missing_source(self, client: TestClient) -> None:
        assert client.get("/sources/no-such/versions").status_code == 404

    def test_links_present(self, client: TestClient) -> None:
        v = client.get("/sources/src-1/versions").json()["versions"][0]
        assert "_links" in v
        assert "self" in v["_links"]

    def test_no_diff_link_for_version_1(self, client: TestClient) -> None:
        v = client.get("/sources/src-1/versions").json()["versions"][0]
        assert "diff_from_prev" not in v["_links"]


class TestGetSourceVersion:
    def test_returns_version_detail(self, client: TestClient) -> None:
        resp = client.get("/sources/src-1/versions/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 1
        assert len(data["chunk_hashes"]) == 1
        assert "markdown" in data

    def test_404_for_missing_version(self, client: TestClient) -> None:
        assert client.get("/sources/src-1/versions/99").status_code == 404


class TestGetSourceChunks:
    def test_returns_chunks(self, client: TestClient) -> None:
        resp = client.get("/sources/src-1/chunks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_id"] == "src-1"
        assert len(data["chunks"]) == 1
        chunk = data["chunks"][0]
        assert chunk["content"] == "Hello world"
        assert "lineage" in chunk

    def test_chunks_with_version_filter(self, client: TestClient) -> None:
        resp = client.get("/sources/src-1/chunks?version=1")
        assert resp.status_code == 200
        assert len(resp.json()["chunks"]) == 1

    def test_empty_for_wrong_version(self, client: TestClient) -> None:
        resp = client.get("/sources/src-1/chunks?version=99")
        assert resp.status_code == 200
        assert resp.json()["chunks"] == []


class TestVersionDiff:
    def test_400_when_same_version(self, client: TestClient) -> None:
        resp = client.get("/sources/src-1/diff?from_version=1&to_version=1")
        assert resp.status_code == 400

    def test_404_when_version_missing(self, client: TestClient) -> None:
        resp = client.get("/sources/src-1/diff?from_version=1&to_version=99")
        assert resp.status_code == 404

    def test_404_for_missing_source(self, client: TestClient) -> None:
        resp = client.get("/sources/no-such/diff?from_version=1&to_version=2")
        assert resp.status_code == 404
