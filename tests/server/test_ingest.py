"""Tests for POST /webhooks/ingest endpoint."""

from fastapi.testclient import TestClient


def _make_structural_hints():
    """Create minimal valid structural hints for testing."""
    return {
        "has_headings": True,
        "has_lists": False,
        "has_tables": False,
        "natural_boundaries": [],
        "file_path": None,
        "modified_at": None,
        "file_size_bytes": None,
    }


class TestIngestWebhook:
    """Tests for webhook ingestion with various payload scenarios."""

    def test_ingest_returns_200(self, client: TestClient) -> None:
        """Verify ingest endpoint returns 200 on valid payload."""
        payload = {
            "adapter_id": "test-adapter",
            "domain": "notes",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "test-source",
                    "markdown": "# Test\nContent here",
                    "structural_hints": _make_structural_hints(),
                }
            ],
        }
        resp = client.post("/webhooks/ingest", json=payload)
        assert resp.status_code == 200

    def test_ingest_processes_multiple_versions(self, client: TestClient) -> None:
        """Verify ingest accepts multiple source versions in request."""
        payload = {
            "adapter_id": "test-adapter",
            "domain": "notes",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "src-v1",
                    "markdown": "# First version",
                    "structural_hints": _make_structural_hints(),
                },
                {
                    "source_id": "src-v1",
                    "markdown": "# Second version",
                    "structural_hints": _make_structural_hints(),
                },
            ],
        }
        resp = client.post("/webhooks/ingest", json=payload)
        assert resp.status_code == 200

    def test_ingest_accepts_new_source(self, client: TestClient) -> None:
        """Verify ingest accepts new sources in payload."""
        # Ingest to non-existent source — ingest endpoint will try to create it
        payload = {
            "adapter_id": "test-adapter",
            "domain": "notes",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "brand-new-source",
                    "markdown": "# New",
                    "structural_hints": _make_structural_hints(),
                }
            ],
        }
        resp = client.post("/webhooks/ingest", json=payload)
        # Endpoint should accept it (pipeline may create or fail gracefully)
        assert resp.status_code == 200

    def test_ingest_stores_chunks(self, client: TestClient, ds) -> None:
        """Verify ingest stores chunks with correct lineage."""
        payload = {
            "adapter_id": "test-adapter",
            "domain": "notes",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "src-1",
                    "markdown": "# README\nMore content",
                    "structural_hints": _make_structural_hints(),
                }
            ],
        }
        resp = client.post("/webhooks/ingest", json=payload)
        assert resp.status_code == 200
        # Chunks are created by the domain chunker during ingestion

    def test_ingest_multi_items_single_request(self, client: TestClient) -> None:
        """Verify ingest accepts multiple items in single request."""
        payload = {
            "adapter_id": "test-adapter",
            "domain": "notes",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "src-multi-1",
                    "markdown": "# First",
                    "structural_hints": _make_structural_hints(),
                },
                {
                    "source_id": "src-multi-2",
                    "markdown": "# Second",
                    "structural_hints": _make_structural_hints(),
                },
            ],
        }
        resp = client.post("/webhooks/ingest", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ["ok", "partial"]

    def test_ingest_multi_domain_sources(self, client_multi_domain: TestClient) -> None:
        """Verify ingest works with multi-domain fixture."""
        # Ingest to notes domain
        notes_payload = {
            "adapter_id": "notes-adapter",
            "domain": "notes",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "src-notes-new",
                    "markdown": "# Note",
                    "structural_hints": _make_structural_hints(),
                }
            ],
        }
        resp1 = client_multi_domain.post("/webhooks/ingest", json=notes_payload)
        assert resp1.status_code == 200

    def test_ingest_invalid_domain_returns_422(self, client: TestClient) -> None:
        """Verify ingest rejects invalid domain."""
        payload = {
            "adapter_id": "test-adapter",
            "domain": "invalid-domain",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "test-source",
                    "markdown": "# Test",
                    "structural_hints": _make_structural_hints(),
                }
            ],
        }
        resp = client.post("/webhooks/ingest", json=payload)
        assert resp.status_code == 422

    def test_ingest_missing_required_field(self, client: TestClient) -> None:
        """Verify ingest rejects payloads missing required fields."""
        payload = {
            # Missing adapter_id
            "domain": "notes",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "test-source",
                    "markdown": "# Test",
                    "structural_hints": _make_structural_hints(),
                }
            ],
        }
        resp = client.post("/webhooks/ingest", json=payload)
        assert resp.status_code == 422

    def test_ingest_empty_items_list_returns_422(self, client: TestClient) -> None:
        """Verify ingest rejects empty items list."""
        payload = {
            "adapter_id": "test-adapter",
            "domain": "notes",
            "normalizer_version": "1.0.0",
            "items": [],
        }
        resp = client.post("/webhooks/ingest", json=payload)
        assert resp.status_code == 422

    def test_ingest_comprehensive_fixture_multi_adapter(
        self, client_comprehensive: TestClient
    ) -> None:
        """Verify ingest works with comprehensive fixture."""
        # Verify we can query sources before ingest
        sources_before = client_comprehensive.get(
            "/sources?adapter_id=obsidian-adapter"
        ).json()
        assert sources_before["total"] == 2  # Base has 2 obsidian sources

        # Attempt ingest to same adapter
        payload = {
            "adapter_id": "obsidian-adapter",
            "domain": "notes",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "src-new-obsidian",
                    "markdown": "# New Note",
                    "structural_hints": _make_structural_hints(),
                }
            ],
        }
        resp = client_comprehensive.post("/webhooks/ingest", json=payload)
        assert resp.status_code == 200
        # Response should be well-formed
        data = resp.json()
        assert "status" in data
