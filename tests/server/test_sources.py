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

    def test_total_reflects_all_matches_not_page_size(self, client: TestClient) -> None:
        # With 1 source and limit=1, total should still be 1 (matching count, not page count)
        data = client.get("/sources?limit=1&offset=0").json()
        assert data["total"] == 1
        # Offset past results: total still reflects full match count
        data2 = client.get("/sources?limit=10&offset=100").json()
        assert data2["total"] == 1
        assert data2["sources"] == []

    def test_invalid_domain_returns_422(self, client: TestClient) -> None:
        resp = client.get("/sources?domain=invalid")
        assert resp.status_code == 422


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


class TestListSourcesMultiEntity:
    """Tests for listing sources with multi-source/multi-adapter/multi-domain scenarios."""

    def test_multi_source_list_all(self, client_multi_source: TestClient) -> None:
        """Verify all sources appear in multi-source fixture."""
        data = client_multi_source.get("/sources").json()
        assert data["total"] == 3
        source_ids = {s["source_id"] for s in data["sources"]}
        assert source_ids == {"src-1", "src-2", "src-3"}

    def test_multi_source_filter_by_adapter(self, client_multi_source: TestClient) -> None:
        """Verify filtering by adapter_id works with multiple sources."""
        data = client_multi_source.get("/sources?adapter_id=test-adapter").json()
        assert data["total"] == 3
        for src in data["sources"]:
            assert src["adapter_id"] == "test-adapter"

    def test_multi_source_filter_by_domain(self, client_multi_source: TestClient) -> None:
        """Verify filtering by domain works with multiple sources."""
        data = client_multi_source.get("/sources?domain=notes").json()
        assert data["total"] == 3
        for src in data["sources"]:
            assert src["domain"] == "notes"

    def test_multi_adapter_same_domain_all(self, client_multi_adapter_same_domain: TestClient) -> None:
        """Verify all sources appear with multiple adapters in same domain."""
        data = client_multi_adapter_same_domain.get("/sources").json()
        assert data["total"] == 2
        source_ids = {s["source_id"] for s in data["sources"]}
        assert source_ids == {"src-1", "src-obsidian"}

    def test_multi_adapter_same_domain_filter_by_adapter(
        self, client_multi_adapter_same_domain: TestClient
    ) -> None:
        """Verify filtering by adapter_id isolates sources to correct adapter."""
        fs_data = client_multi_adapter_same_domain.get("/sources?adapter_id=test-adapter").json()
        assert fs_data["total"] == 1
        assert fs_data["sources"][0]["source_id"] == "src-1"

        obs_data = client_multi_adapter_same_domain.get(
            "/sources?adapter_id=obsidian-adapter"
        ).json()
        assert obs_data["total"] == 1
        assert obs_data["sources"][0]["source_id"] == "src-obsidian"

    def test_multi_domain_list_all(self, client_multi_domain: TestClient) -> None:
        """Verify all sources appear with multiple domains."""
        data = client_multi_domain.get("/sources").json()
        assert data["total"] == 3  # notes, messages, events
        domains = {s["domain"] for s in data["sources"]}
        assert domains == {"notes", "messages", "events"}

    def test_multi_domain_filter_by_domain(self, client_multi_domain: TestClient) -> None:
        """Verify filtering by domain returns only matching sources."""
        notes_data = client_multi_domain.get("/sources?domain=notes").json()
        assert notes_data["total"] == 1
        assert notes_data["sources"][0]["domain"] == "notes"

        messages_data = client_multi_domain.get("/sources?domain=messages").json()
        assert messages_data["total"] == 1
        assert messages_data["sources"][0]["domain"] == "messages"

        events_data = client_multi_domain.get("/sources?domain=events").json()
        assert events_data["total"] == 1
        assert events_data["sources"][0]["domain"] == "events"

    def test_comprehensive_fixture_all_sources(self, client_comprehensive: TestClient) -> None:
        """Verify all sources appear in comprehensive fixture."""
        data = client_comprehensive.get("/sources").json()
        assert data["total"] == 5  # base + 2 obsidian + 1 email + 1 calendar
        source_ids = {s["source_id"] for s in data["sources"]}
        expected = {"src-1", "src-obsidian-1", "src-obsidian-2", "src-email-1", "src-calendar-1"}
        assert source_ids == expected

    def test_comprehensive_fixture_filter_by_adapter(self, client_comprehensive: TestClient) -> None:
        """Verify filtering by adapter_id in comprehensive fixture."""
        obsidian_data = client_comprehensive.get("/sources?adapter_id=obsidian-adapter").json()
        assert obsidian_data["total"] == 2
        for src in obsidian_data["sources"]:
            assert src["adapter_id"] == "obsidian-adapter"
            assert src["source_id"].startswith("src-obsidian")

    def test_comprehensive_fixture_filter_by_domain(self, client_comprehensive: TestClient) -> None:
        """Verify filtering by domain in comprehensive fixture."""
        # NOTES: base + 2 obsidian = 3
        notes_data = client_comprehensive.get("/sources?domain=notes").json()
        assert notes_data["total"] == 3

        # MESSAGES: 1 email
        messages_data = client_comprehensive.get("/sources?domain=messages").json()
        assert messages_data["total"] == 1

        # EVENTS: 1 calendar
        events_data = client_comprehensive.get("/sources?domain=events").json()
        assert events_data["total"] == 1
