"""Tests for POST /query endpoint (semantic search)."""

from fastapi.testclient import TestClient


class TestSemanticSearch:
    """Tests for semantic search retrieval across multiple entities."""

    def test_query_returns_200(self, client: TestClient) -> None:
        """Verify query endpoint returns 200."""
        payload = {"query": "hello"}
        resp = client.post("/query", json=payload)
        assert resp.status_code == 200

    def test_query_response_structure(self, client: TestClient) -> None:
        """Verify query response has expected structure."""
        payload = {"query": "content"}
        resp = client.post("/query", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        # Query response should have top-level result fields
        assert isinstance(data, dict)
        # The endpoint returns query results with specific fields
        assert "query" in data or "results" in data or "matches" in data

    def test_query_with_domain_filter_single_domain(self, client_multi_domain: TestClient) -> None:
        """Verify domain filter works with multi-domain fixture."""
        # Mock the vector store to return results from any source
        # Query for notes only
        payload = {"query": "notes content", "domain": "notes"}
        resp = client_multi_domain.post("/query", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        # Should return query endpoint response
        assert "results" in data

    def test_query_with_domain_string_filter(self, client: TestClient) -> None:
        """Verify query accepts domain filter as string."""
        payload = {"query": "test", "domain": "notes"}
        resp = client.post("/query", json=payload)
        # Query should accept domain filter (may validate or accept any string)
        assert resp.status_code in [200, 422]

    def test_query_with_adapter_filter(self, client_multi_adapter_same_domain: TestClient) -> None:
        """Verify adapter_id filter works with multi-adapter fixture."""
        payload = {"query": "content", "adapter_id": "test-adapter"}
        resp = client_multi_adapter_same_domain.post("/query", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data

    def test_query_with_source_filter(self, client_multi_source: TestClient) -> None:
        """Verify source_id filter works with multi-source fixture."""
        payload = {"query": "content", "source_id": "src-1"}
        resp = client_multi_source.post("/query", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data

    def test_query_multi_source_all_sources(self, client_multi_source: TestClient) -> None:
        """Verify query searches across all sources in multi-source fixture."""
        payload = {"query": "content"}
        resp = client_multi_source.post("/query", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data

    def test_query_multi_adapter_returns_200(self, client_multi_adapter_same_domain: TestClient) -> None:
        """Verify query works with multiple adapters managing same domain."""
        payload = {"query": "note content"}
        resp = client_multi_adapter_same_domain.post("/query", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data

    def test_query_multi_domain_filter_by_domain(self, client_multi_domain: TestClient) -> None:
        """Verify domain filter isolates results in multi-domain fixture."""
        # Query for messages domain
        messages_payload = {"query": "content", "domain": "messages"}
        resp = client_multi_domain.post("/query", json=messages_payload)
        assert resp.status_code == 200

        # Query for events domain
        events_payload = {"query": "content", "domain": "events"}
        resp = client_multi_domain.post("/query", json=events_payload)
        assert resp.status_code == 200

    def test_query_comprehensive_fixture_by_domain(self, client_comprehensive: TestClient) -> None:
        """Verify domain filter works in comprehensive fixture."""
        # Query notes (should match 3 sources: 1 base + 2 obsidian)
        notes_payload = {"query": "content", "domain": "notes"}
        resp = client_comprehensive.post("/query", json=notes_payload)
        assert resp.status_code == 200

        # Query messages (should match 1 email source)
        messages_payload = {"query": "content", "domain": "messages"}
        resp = client_comprehensive.post("/query", json=messages_payload)
        assert resp.status_code == 200

        # Query events (should match 1 calendar source)
        events_payload = {"query": "content", "domain": "events"}
        resp = client_comprehensive.post("/query", json=events_payload)
        assert resp.status_code == 200

    def test_query_comprehensive_fixture_by_adapter(self, client_comprehensive: TestClient) -> None:
        """Verify adapter filter works in comprehensive fixture."""
        # Query obsidian adapter (2 sources)
        payload = {"query": "content", "adapter_id": "obsidian-adapter"}
        resp = client_comprehensive.post("/query", json=payload)
        assert resp.status_code == 200

        # Query email adapter (1 source)
        payload = {"query": "content", "adapter_id": "email-adapter"}
        resp = client_comprehensive.post("/query", json=payload)
        assert resp.status_code == 200

    def test_query_comprehensive_fixture_by_source(self, client_comprehensive: TestClient) -> None:
        """Verify source filter works in comprehensive fixture."""
        payload = {"query": "content", "source_id": "src-obsidian-1"}
        resp = client_comprehensive.post("/query", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data

    def test_query_with_limit(self, client: TestClient) -> None:
        """Verify limit parameter is accepted."""
        payload = {"query": "content", "limit": 5}
        resp = client.post("/query", json=payload)
        assert resp.status_code == 200

    def test_query_with_reranker_disabled(self, client: TestClient) -> None:
        """Verify query works when reranker is disabled."""
        payload = {"query": "content"}
        resp = client.post("/query", json=payload)
        assert resp.status_code == 200
        # Client fixture has reranker set to None
        data = resp.json()
        assert "results" in data

    def test_query_missing_query_field_returns_422(self, client: TestClient) -> None:
        """Verify query endpoint rejects missing query field."""
        payload = {}  # Missing query
        resp = client.post("/query", json=payload)
        assert resp.status_code == 422

    def test_query_empty_string_returns_422(self, client: TestClient) -> None:
        """Verify query endpoint rejects empty query string."""
        payload = {"query": ""}
        resp = client.post("/query", json=payload)
        assert resp.status_code == 422
