"""Tests for GET /stats/activity and GET /admin/pipelines endpoints."""

from unittest.mock import MagicMock
from fastapi.testclient import TestClient


class TestGetActivity:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/stats/activity")
        assert resp.status_code == 200

    def test_response_structure(self, client: TestClient) -> None:
        data = client.get("/stats/activity").json()
        assert "events" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

    def test_returns_ingestion_events(self, client: TestClient) -> None:
        data = client.get("/stats/activity").json()
        assert data["total"] == 1
        event = data["events"][0]
        assert event["event_type"] == "ingested"
        assert event["identifier"] == "src-1"
        assert isinstance(event["tags"], list)
        assert "notes" in event["tags"]
        assert "filesystem" in event["tags"]

    def test_entity_name_falls_back_to_source_id(self, client: TestClient) -> None:
        data = client.get("/stats/activity").json()
        event = data["events"][0]
        # Source has no display_name set, so entity_name should be the source_id
        assert event["entity_name"] == "src-1"

    def test_pagination_params(self, client: TestClient) -> None:
        resp = client.get("/stats/activity?limit=10&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 10
        assert data["offset"] == 0

    def test_empty_when_no_versions(self, client: TestClient, ds) -> None:
        ds.conn.execute("DELETE FROM entity_links")
        ds.conn.execute("DELETE FROM chunks")
        ds.conn.execute("DELETE FROM source_versions")
        ds.conn.commit()
        data = client.get("/stats/activity").json()
        assert data["total"] == 0
        assert data["events"] == []

    def test_multi_source_returns_multiple_events(self, client_multi_source: TestClient) -> None:
        data = client_multi_source.get("/stats/activity").json()
        assert data["total"] == 3

    def test_timestamp_present(self, client: TestClient) -> None:
        data = client.get("/stats/activity").json()
        event = data["events"][0]
        assert "timestamp" in event
        assert event["timestamp"] is not None

    def test_auth_required_when_secret_set(self, ds) -> None:
        """Verify 401 is returned when webhook secret is set and auth header is missing."""
        mock_config = MagicMock()
        mock_config.webhook_secret = "test-secret"

        # Build a client with a secret configured
        from contextlib import asynccontextmanager
        from typing import AsyncGenerator, Any
        from context_library.server.app import create_app

        @asynccontextmanager
        async def lifespan_with_secret(app: Any) -> AsyncGenerator[None, None]:
            app.state.document_store = ds
            app.state.embedder = MagicMock()
            app.state.vector_store = MagicMock()
            app.state.pipeline = MagicMock()
            app.state.reranker = None
            app.state.config = mock_config
            app.state.helper_adapters = []
            app.state.helper_health_cache = None
            app.state.poller = MagicMock()
            yield

        app = create_app()
        app.router.lifespan_context = lifespan_with_secret
        with TestClient(app, raise_server_exceptions=True) as c:
            resp = c.get("/stats/activity")
            assert resp.status_code == 401

    def test_auth_succeeds_with_correct_token(self, ds) -> None:
        from contextlib import asynccontextmanager
        from typing import AsyncGenerator, Any
        from context_library.server.app import create_app

        mock_config = MagicMock()
        mock_config.webhook_secret = "my-secret"

        @asynccontextmanager
        async def lifespan_with_secret(app: Any) -> AsyncGenerator[None, None]:
            app.state.document_store = ds
            app.state.embedder = MagicMock()
            app.state.vector_store = MagicMock()
            app.state.pipeline = MagicMock()
            app.state.reranker = None
            app.state.config = mock_config
            app.state.helper_adapters = []
            app.state.helper_health_cache = None
            app.state.poller = MagicMock()
            yield

        app = create_app()
        app.router.lifespan_context = lifespan_with_secret
        with TestClient(app, raise_server_exceptions=True) as c:
            resp = c.get("/stats/activity", headers={"Authorization": "Bearer my-secret"})
            assert resp.status_code == 200


class TestGetPipelines:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/admin/pipelines")
        assert resp.status_code == 200

    def test_empty_when_no_runs(self, client: TestClient) -> None:
        data = client.get("/admin/pipelines").json()
        assert data["runs"] == []
        assert data["total"] == 0

    def test_response_structure(self, client: TestClient) -> None:
        data = client.get("/admin/pipelines").json()
        assert "runs" in data
        assert "total" in data

    def test_returns_active_runs(self, client: TestClient) -> None:
        """Inject a fake active run and verify the endpoint returns it."""
        from datetime import datetime, timedelta, timezone
        from context_library.core.pipeline import _PipelineRun

        pipeline = client.app.state.pipeline

        # Use a started_at that is guaranteed to be in the past
        started = datetime.now(timezone.utc) - timedelta(seconds=30)
        fake_run = _PipelineRun(
            run_id="test-run-id",
            adapter_id="test-adapter",
            started_at=started,
            current_step="processing",
            sources_ingested=5,
            chunks_created=10,
            chunks_updated=3,
            errors=1,
        )
        pipeline.get_active_runs = lambda: [fake_run]

        data = client.get("/admin/pipelines").json()
        assert data["total"] == 1
        run = data["runs"][0]
        assert run["run_id"] == "test-run-id"
        assert run["adapter_id"] == "test-adapter"
        assert run["current_step"] == "processing"
        assert run["ingested"] == 5
        assert run["created"] == 10
        assert run["updated"] == 3
        assert run["errors"] == 1
        assert run["duration_sec"] >= 0

    def test_auth_required_when_secret_set(self, ds) -> None:
        from contextlib import asynccontextmanager
        from typing import AsyncGenerator, Any
        from context_library.server.app import create_app

        mock_config = MagicMock()
        mock_config.webhook_secret = "secret"

        @asynccontextmanager
        async def lifespan(app: Any) -> AsyncGenerator[None, None]:
            app.state.document_store = ds
            app.state.embedder = MagicMock()
            app.state.vector_store = MagicMock()
            mock_pipeline = MagicMock()
            mock_pipeline.get_active_runs.return_value = []
            app.state.pipeline = mock_pipeline
            app.state.reranker = None
            app.state.config = mock_config
            app.state.helper_adapters = []
            app.state.helper_health_cache = None
            app.state.poller = MagicMock()
            yield

        app = create_app()
        app.router.lifespan_context = lifespan
        with TestClient(app, raise_server_exceptions=True) as c:
            resp = c.get("/admin/pipelines")
            assert resp.status_code == 401
