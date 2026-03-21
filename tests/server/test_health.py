"""Tests for GET /health endpoint."""

from typing import Any, cast
from fastapi.testclient import TestClient
from unittest.mock import MagicMock


class TestGetHealth:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_response_structure(self, client: TestClient) -> None:
        data = client.get("/health").json()
        assert "status" in data
        assert "vector_count" in data
        assert "embedding_model" in data
        assert "embedding_dimension" in data
        assert "sqlite_ok" in data
        assert "chromadb_ok" in data

    def test_healthy_status(self, client: TestClient) -> None:
        data = client.get("/health").json()
        assert data["status"] == "healthy"
        assert data["sqlite_ok"] is True
        assert data["chromadb_ok"] is True

    def test_degraded_when_chromadb_unreachable(self, client: TestClient) -> None:
        # Replace the vector_store.count method with one that raises
        vector_store = cast(Any, client).app.state.vector_store
        original_count = vector_store.count
        vector_store.count = MagicMock(side_effect=Exception("ChromaDB unreachable"))
        try:
            data = client.get("/health").json()
            assert data["status"] == "degraded"
            assert data["sqlite_ok"] is True
            assert data["chromadb_ok"] is False
        finally:
            vector_store.count = original_count

    def test_vector_count_zero_when_error(self, client: TestClient) -> None:
        # When vector_store fails, vector_count should be 0
        vector_store = cast(Any, client).app.state.vector_store
        original_count = vector_store.count
        vector_store.count = MagicMock(side_effect=Exception("ChromaDB unreachable"))
        try:
            data = client.get("/health").json()
            assert data["vector_count"] == 0
        finally:
            vector_store.count = original_count

    def test_degraded_when_sqlite_unreachable(self, client: TestClient) -> None:
        # Mock the _make_connection method to return a broken connection
        document_store = cast(Any, client).app.state.document_store
        original_make_connection = document_store._make_connection

        def broken_make_connection():
            # Return a mock connection that fails on execute
            mock_conn = MagicMock()
            mock_conn.execute = MagicMock(side_effect=Exception("SQLite unreachable"))
            return mock_conn

        document_store._make_connection = broken_make_connection
        try:
            # Clear the thread-local connection so a new one is created
            if hasattr(document_store._local, "conn"):
                del document_store._local.conn

            data = client.get("/health").json()
            assert data["status"] == "degraded"
            assert data["sqlite_ok"] is False
            assert data["chromadb_ok"] is True
        finally:
            # Restore the original method
            document_store._make_connection = original_make_connection
            # Clear the thread-local connection so a new one is created on next use
            if hasattr(document_store._local, "conn"):
                del document_store._local.conn
