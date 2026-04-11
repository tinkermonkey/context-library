"""Tests for GET /adapters, GET /adapters/{adapter_id}, and POST /adapters/{adapter_id}/reset."""

from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from context_library.adapters.base import ResetResult


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
        # Remove in FK order: entity_links → chunks → source_versions → sources → adapters
        ds.conn.execute("DELETE FROM entity_links")
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


class TestResetAdapter:
    def test_returns_404_for_missing_adapter(self, client: TestClient) -> None:
        """Test that POST /adapters/unknown_id/reset returns 404."""
        resp = client.post("/adapters/unknown_id/reset")
        assert resp.status_code == 404

    def test_returns_401_without_auth_when_secret_configured(self, client: TestClient) -> None:
        """Test that missing auth returns 401 when webhook secret is configured."""
        # Configure webhook secret on the app
        client.app.state.config.webhook_secret = "test-secret"
        resp = client.post("/adapters/test-adapter/reset")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid webhook secret"

    def test_returns_401_with_invalid_auth(self, client: TestClient) -> None:
        """Test that invalid auth returns 401."""
        client.app.state.config.webhook_secret = "test-secret"
        resp = client.post(
            "/adapters/test-adapter/reset",
            headers={"Authorization": "Bearer wrong-secret"}
        )
        assert resp.status_code == 401

    def test_returns_502_when_helper_reset_fails(self, client: TestClient) -> None:
        """Test that helper reset failure returns 502 and document_store.reset_adapter is NOT called."""
        # Create a mock adapter that fails on reset
        mock_adapter = MagicMock()
        mock_adapter.adapter_id = "test-adapter"
        mock_adapter.reset.return_value = ResetResult(ok=False, cleared=[], errors=["Connection failed"])

        client.app.state.helper_adapters = [mock_adapter]

        resp = client.post("/adapters/test-adapter/reset")
        assert resp.status_code == 502
        assert "Helper reset failed" in resp.json()["detail"]

    def test_returns_500_when_library_reset_fails(self, client: TestClient) -> None:
        """Test that library reset failure returns 500 with warning about helper."""
        # Create a mock adapter that succeeds on reset
        mock_adapter = MagicMock()
        mock_adapter.adapter_id = "test-adapter"
        mock_adapter.reset.return_value = ResetResult(ok=True, cleared=[], errors=[])

        client.app.state.helper_adapters = [mock_adapter]

        # Mock document_store.reset_adapter to raise an error
        ds = client.app.state.document_store
        original_reset = ds.reset_adapter

        def failing_reset(adapter_id):
            raise RuntimeError("Database error")

        ds.reset_adapter = failing_reset

        resp = client.post("/adapters/test-adapter/reset")
        assert resp.status_code == 500
        assert "Library reset error" in resp.json()["detail"]
        assert "Note: helper was already reset" in resp.json()["detail"]

        # Restore original method
        ds.reset_adapter = original_reset

    def test_returns_207_when_poller_unavailable(self, client: TestClient) -> None:
        """Test that poller unavailability returns 207 with warning message."""
        # Create a mock adapter that succeeds
        mock_adapter = MagicMock()
        mock_adapter.adapter_id = "test-adapter"
        mock_adapter.reset.return_value = ResetResult(ok=True, cleared=[], errors=[])

        client.app.state.helper_adapters = [mock_adapter]

        # Mock poller to return False (unavailable)
        poller = MagicMock()
        poller.trigger_immediate_ingest.return_value = False
        client.app.state.poller = poller

        resp = client.post("/adapters/test-adapter/reset")
        # Endpoint returns 207 Partial Success if library reset succeeded but re-ingestion failed
        assert resp.status_code == 207
        data = resp.json()
        assert data["adapter_id"] == "test-adapter"
        assert data["helper_reset"] is True
        assert data["library_reset"] is True
        assert data["reingestion_triggered"] is False
        assert any("Poller unavailable" in err for err in data["errors"])

    def test_happy_path_returns_200(self, client: TestClient) -> None:
        """Test happy path: all steps succeed and returns 200."""
        # Create a mock adapter that succeeds
        mock_adapter = MagicMock()
        mock_adapter.adapter_id = "test-adapter"
        mock_adapter.reset.return_value = ResetResult(ok=True, cleared=["push_cursor"], errors=[])

        client.app.state.helper_adapters = [mock_adapter]

        # Mock poller to succeed
        poller = MagicMock()
        poller.trigger_immediate_ingest.return_value = True
        client.app.state.poller = poller

        resp = client.post("/adapters/test-adapter/reset")
        assert resp.status_code == 200

        data = resp.json()
        assert data["adapter_id"] == "test-adapter"
        assert data["helper_reset"] is True
        assert data["library_reset"] is True
        assert data["reingestion_triggered"] is True
        assert data["errors"] == []

        # Verify that helper reset was called
        mock_adapter.reset.assert_called_once()
        # Verify that poller was called
        poller.trigger_immediate_ingest.assert_called_once_with("test-adapter")

    def test_non_helper_adapter_skips_helper_reset(self, client: TestClient) -> None:
        """Test that adapters not in helper_adapters skip the helper reset step."""
        # helper_adapters is empty, so test-adapter won't be found
        client.app.state.helper_adapters = []

        # Mock poller to succeed
        poller = MagicMock()
        poller.trigger_immediate_ingest.return_value = True
        client.app.state.poller = poller

        resp = client.post("/adapters/test-adapter/reset")
        assert resp.status_code == 200

        data = resp.json()
        assert data["adapter_id"] == "test-adapter"
        assert data["helper_reset"] is False  # Not found, so False
        assert data["library_reset"] is True
        assert data["reingestion_triggered"] is True
        assert data["errors"] == []
