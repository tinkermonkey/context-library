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
        mock_adapter.reset.return_value = ResetResult(cleared=[], errors=["Connection failed"])

        client.app.state.helper_adapters = [mock_adapter]

        # Mock document_store.reset_adapter to verify it's not called
        ds = client.app.state.document_store
        with patch.object(ds, "reset_adapter") as mock_reset_adapter:
            resp = client.post("/adapters/test-adapter/reset")
            assert resp.status_code == 502
            assert "Helper reset failed" in resp.json()["detail"]
            # Verify abort-on-failure: Step 3 (document_store.reset_adapter) should NOT be called
            mock_reset_adapter.assert_not_called()

    def test_returns_500_when_library_reset_fails(self, client: TestClient) -> None:
        """Test that library reset failure returns 500 with warning about helper."""
        # Create a mock adapter that succeeds on reset
        mock_adapter = MagicMock()
        mock_adapter.adapter_id = "test-adapter"
        mock_adapter.reset.return_value = ResetResult(cleared=[], errors=[])

        client.app.state.helper_adapters = [mock_adapter]

        # Mock document_store.reset_adapter to raise an error using context manager
        ds = client.app.state.document_store

        def failing_reset(adapter_id):
            raise RuntimeError("Database error")

        with patch.object(ds, "reset_adapter", side_effect=failing_reset):
            resp = client.post("/adapters/test-adapter/reset")
            assert resp.status_code == 500
            assert "Library reset error" in resp.json()["detail"]
            assert "Note: helper was already reset" in resp.json()["detail"]

    def test_returns_207_when_poller_unavailable(self, client: TestClient) -> None:
        """Test that poller unavailability returns 207 with warning message."""
        from context_library.scheduler.exceptions import PollerNotRunningError

        # Create a mock adapter that succeeds
        mock_adapter = MagicMock()
        mock_adapter.adapter_id = "test-adapter"
        mock_adapter.reset.return_value = ResetResult(cleared=[], errors=[])

        client.app.state.helper_adapters = [mock_adapter]

        # Mock poller to raise PollerNotRunningError (unavailable)
        poller = MagicMock()
        poller.trigger_immediate_ingest.side_effect = PollerNotRunningError("Poller is not running")
        client.app.state.poller = poller

        resp = client.post("/adapters/test-adapter/reset")
        # Endpoint returns 207 Partial Success if library reset succeeded but re-ingestion failed
        assert resp.status_code == 207
        data = resp.json()
        assert data["adapter_id"] == "test-adapter"
        assert data["helper_reset"]["ok"] is True
        assert data["library_reset"]["sources_reset"] is not None
        assert isinstance(data["library_reset"]["sources_reset"], int)
        assert data["reingestion_triggered"] is False
        assert any("Poller is not running" in err for err in data["errors"])
        # Verify response structure
        assert "sources_reset" in data["library_reset"]
        assert "chunks_retired" in data["library_reset"]
        assert isinstance(data["library_reset"]["chunks_retired"], int)
        assert data["helper_reset"]["cleared"] == []

    def test_happy_path_returns_200(self, client: TestClient) -> None:
        """Test happy path: all steps succeed and returns 200."""
        # Create a mock adapter that succeeds
        mock_adapter = MagicMock()
        mock_adapter.adapter_id = "test-adapter"
        mock_adapter.reset.return_value = ResetResult(cleared=["push_cursor"], errors=[])

        client.app.state.helper_adapters = [mock_adapter]

        # Mock poller to succeed
        poller = MagicMock()
        poller.trigger_immediate_ingest.return_value = True
        client.app.state.poller = poller

        resp = client.post("/adapters/test-adapter/reset")
        assert resp.status_code == 200

        data = resp.json()
        assert data["adapter_id"] == "test-adapter"
        assert data["helper_reset"]["ok"] is True
        assert data["library_reset"]["sources_reset"] is not None
        assert isinstance(data["library_reset"]["sources_reset"], int)
        assert data["reingestion_triggered"] is True
        assert data["errors"] == []
        # Verify response structure
        assert "sources_reset" in data["library_reset"]
        assert "chunks_retired" in data["library_reset"]
        assert isinstance(data["library_reset"]["chunks_retired"], int)
        assert data["helper_reset"]["cleared"] == ["push_cursor"]

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
        assert data["helper_reset"]["ok"] is None  # Not a helper adapter, so ok=None (not applicable)
        assert data["library_reset"]["sources_reset"] is not None
        assert data["reingestion_triggered"] is True
        assert data["errors"] == []

    def test_push_only_adapter_returns_200_when_poller_unavailable(self, client: TestClient, ds) -> None:
        """Test that push-only adapters return 200 even when poller unavailable.

        Push-only adapters don't need poller-driven re-ingestion, so unavailability
        should not result in 207 Partial Success — the reset fully succeeded.
        """
        from context_library.storage.models import PollStrategy
        from context_library.scheduler.exceptions import PollerNotRunningError

        # Update the existing source to use PUSH strategy instead of PULL
        cursor = ds.conn.cursor()
        cursor.execute(
            "UPDATE sources SET poll_strategy = ? WHERE adapter_id = ?",
            (PollStrategy.PUSH.value, "test-adapter"),
        )
        ds.conn.commit()

        # Create a mock adapter that succeeds
        mock_adapter = MagicMock()
        mock_adapter.adapter_id = "test-adapter"
        mock_adapter.reset.return_value = ResetResult(cleared=[], errors=[])

        client.app.state.helper_adapters = [mock_adapter]

        # Mock poller to raise PollerNotRunningError (unavailable)
        poller = MagicMock()
        poller.trigger_immediate_ingest.side_effect = PollerNotRunningError("Poller is not running")
        client.app.state.poller = poller

        resp = client.post("/adapters/test-adapter/reset")
        # Should return 200 (success) since push-only adapters don't need poller-driven re-ingestion
        assert resp.status_code == 200
        data = resp.json()
        assert data["adapter_id"] == "test-adapter"
        assert data["helper_reset"]["ok"] is True
        assert data["library_reset"]["sources_reset"] is not None
        assert data["reingestion_triggered"] is False
        # Should have error about poller, but still 200 because push-only
        assert any("Poller is not running" in err for err in data["errors"])

    def test_returns_500_when_adapter_reset_raises_programming_bug(self, client: TestClient) -> None:
        """Test that programming bugs from adapter.reset() return 500 and abort step 3.

        RuntimeError and other non-network exceptions are internal bugs, not legitimate
        502 (bad gateway) errors from the helper service. These should return 500.
        Step 3 (document_store.reset_adapter) should NOT be called due to abort-on-failure.
        """
        # Create a mock adapter that raises a programming bug during reset
        mock_adapter = MagicMock()
        mock_adapter.adapter_id = "test-adapter"
        mock_adapter.reset.side_effect = RuntimeError("Unexpected internal error")

        client.app.state.helper_adapters = [mock_adapter]

        # Mock document_store.reset_adapter to verify it's NOT called
        ds = client.app.state.document_store
        with patch.object(ds, "reset_adapter") as mock_reset_adapter:
            resp = client.post("/adapters/test-adapter/reset")
            assert resp.status_code == 500
            detail = resp.json()["detail"]
            assert "Helper reset error" in detail
            assert "RuntimeError" in detail
            # Verify abort-on-failure: Step 3 should NOT be called
            mock_reset_adapter.assert_not_called()

    def test_returns_502_when_adapter_reset_raises_network_error(self, client: TestClient) -> None:
        """Test that httpx network errors from adapter.reset() return 502 and abort step 3.

        httpx.HTTPStatusError and httpx.RequestError are legitimate network errors from
        the helper service, warranting a 502 (bad gateway) response.
        Step 3 (document_store.reset_adapter) should NOT be called due to abort-on-failure.
        """
        try:
            import httpx
        except ImportError:
            # Skip if httpx not available
            return

        # Create a mock adapter that raises httpx.RequestError during reset
        mock_adapter = MagicMock()
        mock_adapter.adapter_id = "test-adapter"
        mock_adapter.reset.side_effect = httpx.RequestError("Connection failed")

        client.app.state.helper_adapters = [mock_adapter]

        # Mock document_store.reset_adapter to verify it's NOT called
        ds = client.app.state.document_store
        with patch.object(ds, "reset_adapter") as mock_reset_adapter:
            resp = client.post("/adapters/test-adapter/reset")
            assert resp.status_code == 502
            detail = resp.json()["detail"]
            assert "Helper reset error" in detail
            assert "RequestError" in detail
            # Verify abort-on-failure: Step 3 should NOT be called
            mock_reset_adapter.assert_not_called()

    def test_poller_trigger_immediate_ingest_exception_is_handled(self, client: TestClient) -> None:
        """Test that exceptions from poller.trigger_immediate_ingest are handled gracefully.

        When trigger_immediate_ingest raises an unexpected exception (not a known poller
        exception), the error should be caught and added to the response's errors list.
        Since library reset has already succeeded, this returns 207 (partial success) with
        the error logged but not crashing the endpoint.
        """
        # Create a mock adapter that succeeds
        mock_adapter = MagicMock()
        mock_adapter.adapter_id = "test-adapter"
        mock_adapter.reset.return_value = ResetResult(cleared=[], errors=[])

        client.app.state.helper_adapters = [mock_adapter]

        # Mock poller.trigger_immediate_ingest to raise an unexpected exception
        poller = MagicMock()
        poller.trigger_immediate_ingest.side_effect = RuntimeError("Unexpected poller error")
        client.app.state.poller = poller

        # The exception should be caught and added to the errors list, returning 207
        # because library reset succeeded but re-ingestion failed
        resp = client.post("/adapters/test-adapter/reset")
        assert resp.status_code == 207
        data = resp.json()
        # Verify the error is captured
        assert len(data["errors"]) > 0
        assert any("Unexpected error while triggering re-ingestion" in error for error in data["errors"])
        # Verify response structure is correct even with errors
        assert data["helper_reset"]["ok"] is True
        assert data["library_reset"]["sources_reset"] is not None

    def test_sqlite_operational_error_from_trigger_ingest_returns_207(self, client: TestClient) -> None:
        """Test that sqlite3.OperationalError from trigger_immediate_ingest is handled gracefully.

        Transient DB errors (e.g., database locked, I/O error) during re-ingestion trigger
        should not crash the endpoint. Since library reset has already succeeded, this returns
        207 (partial success) with the error logged.
        """
        import sqlite3

        # Create a mock adapter that succeeds
        mock_adapter = MagicMock()
        mock_adapter.adapter_id = "test-adapter"
        mock_adapter.reset.return_value = ResetResult(cleared=[], errors=[])

        client.app.state.helper_adapters = [mock_adapter]

        # Mock poller.trigger_immediate_ingest to raise sqlite3.OperationalError
        poller = MagicMock()
        poller.trigger_immediate_ingest.side_effect = sqlite3.OperationalError("database is locked")
        client.app.state.poller = poller

        # The exception should be caught and added to the errors list, returning 207
        # because library reset succeeded but re-ingestion failed
        resp = client.post("/adapters/test-adapter/reset")
        assert resp.status_code == 207
        data = resp.json()
        # Verify library reset succeeded
        assert data["library_reset"]["sources_reset"] is not None
        # Verify the DB error is captured in errors
        assert len(data["errors"]) > 0
        assert any("Database error" in error for error in data["errors"])
        # Verify re-ingestion was not triggered
        assert data["reingestion_triggered"] is False

    def test_source_versions_survive_reset(self, client: TestClient, ds) -> None:
        """Test that reset_adapter preserves source_version history.

        The docstring explicitly states "Preserves all source rows, source_version history"
        but this was not being tested. Verify that after reset:
        - All source_versions for the adapter are preserved
        - Chunks are retired but versions remain
        """

        # Create a mock adapter that succeeds
        mock_adapter = MagicMock()
        mock_adapter.adapter_id = "test-adapter"
        mock_adapter.reset.return_value = ResetResult(cleared=[], errors=[])

        client.app.state.helper_adapters = [mock_adapter]

        # Mock poller to succeed
        poller = MagicMock()
        poller.trigger_immediate_ingest.return_value = True
        client.app.state.poller = poller

        # Verify initial state: version 1 exists
        cursor = ds.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) as count FROM source_versions WHERE adapter_id = ?",
            ("test-adapter",),
        )
        initial_version_count = cursor.fetchone()["count"]
        assert initial_version_count == 1  # fixture creates version 1

        # Call reset
        resp = client.post("/adapters/test-adapter/reset")
        assert resp.status_code == 200
        data = resp.json()
        # Verify response structure
        assert data["helper_reset"]["ok"] is True
        assert data["library_reset"]["sources_reset"] is not None
        assert data["library_reset"]["chunks_retired"] is not None

        # Verify source_versions are still there after reset
        cursor.execute(
            "SELECT COUNT(*) as count FROM source_versions WHERE adapter_id = ?",
            ("test-adapter",),
        )
        final_version_count = cursor.fetchone()["count"]
        assert final_version_count == initial_version_count, \
            "source_versions should be preserved after reset"

        # Verify the version record still has correct data
        cursor.execute(
            "SELECT source_id, version, markdown FROM source_versions WHERE adapter_id = ? ORDER BY version",
            ("test-adapter",),
        )
        versions = cursor.fetchall()
        assert len(versions) >= 1
        assert versions[0]["source_id"] == "src-1"
        assert versions[0]["version"] == 1
        assert "# README" in versions[0]["markdown"]

        # Verify chunks are retired (the reset side effect)
        cursor.execute(
            "SELECT COUNT(*) as count FROM chunks WHERE adapter_id = ? AND retired_at IS NULL",
            ("test-adapter",),
        )
        active_chunks = cursor.fetchone()["count"]
        assert active_chunks == 0, "All chunks should be retired after reset"

    def test_returns_207_when_adapter_not_registered(self, client: TestClient) -> None:
        """Test that AdapterNotRegisteredError returns 207 with warning message."""
        from context_library.scheduler.exceptions import AdapterNotRegisteredError

        # Create a mock adapter that succeeds
        mock_adapter = MagicMock()
        mock_adapter.adapter_id = "test-adapter"
        mock_adapter.reset.return_value = ResetResult(cleared=[], errors=[])

        client.app.state.helper_adapters = [mock_adapter]

        # Mock poller to raise AdapterNotRegisteredError
        poller = MagicMock()
        poller.trigger_immediate_ingest.side_effect = AdapterNotRegisteredError("Adapter not registered")
        client.app.state.poller = poller

        resp = client.post("/adapters/test-adapter/reset")
        # Endpoint returns 207 Partial Success if library reset succeeded but re-ingestion failed
        assert resp.status_code == 207
        data = resp.json()
        assert data["adapter_id"] == "test-adapter"
        assert data["helper_reset"]["ok"] is True
        assert data["library_reset"]["sources_reset"] is not None
        assert isinstance(data["library_reset"]["sources_reset"], int)
        assert data["reingestion_triggered"] is False
        assert any("Adapter is not registered" in err for err in data["errors"])

    def test_returns_207_when_no_sources_found(self, client: TestClient) -> None:
        """Test that NoSourcesError returns 207 with warning message."""
        from context_library.scheduler.exceptions import NoSourcesError

        # Create a mock adapter that succeeds
        mock_adapter = MagicMock()
        mock_adapter.adapter_id = "test-adapter"
        mock_adapter.reset.return_value = ResetResult(cleared=[], errors=[])

        client.app.state.helper_adapters = [mock_adapter]

        # Mock poller to raise NoSourcesError
        poller = MagicMock()
        poller.trigger_immediate_ingest.side_effect = NoSourcesError("No sources found")
        client.app.state.poller = poller

        resp = client.post("/adapters/test-adapter/reset")
        # Endpoint returns 207 Partial Success if library reset succeeded but re-ingestion failed
        assert resp.status_code == 207
        data = resp.json()
        assert data["adapter_id"] == "test-adapter"
        assert data["helper_reset"]["ok"] is True
        assert data["library_reset"]["sources_reset"] is not None
        assert isinstance(data["library_reset"]["sources_reset"], int)
        assert data["reingestion_triggered"] is False
        assert any("No sources found" in err for err in data["errors"])

    def test_returns_207_when_ingest_already_in_progress(self, client: TestClient) -> None:
        """Test that IngestAlreadyInProgressError returns 207 with warning message."""
        from context_library.scheduler.exceptions import IngestAlreadyInProgressError

        # Create a mock adapter that succeeds
        mock_adapter = MagicMock()
        mock_adapter.adapter_id = "test-adapter"
        mock_adapter.reset.return_value = ResetResult(cleared=[], errors=[])

        client.app.state.helper_adapters = [mock_adapter]

        # Mock poller to raise IngestAlreadyInProgressError
        poller = MagicMock()
        poller.trigger_immediate_ingest.side_effect = IngestAlreadyInProgressError("Ingest already in progress")
        client.app.state.poller = poller

        resp = client.post("/adapters/test-adapter/reset")
        # Endpoint returns 207 Partial Success if library reset succeeded but re-ingestion failed
        assert resp.status_code == 207
        data = resp.json()
        assert data["adapter_id"] == "test-adapter"
        assert data["helper_reset"]["ok"] is True
        assert data["library_reset"]["sources_reset"] is not None
        assert isinstance(data["library_reset"]["sources_reset"], int)
        assert data["reingestion_triggered"] is False
        assert any("Ingest is already in progress" in err for err in data["errors"])
