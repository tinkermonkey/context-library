"""Tests for the FastAPI server lifespan management."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestLifespanInitialization:
    """Tests for lifespan initialization and state setup."""

    @pytest.mark.asyncio
    async def test_lifespan_initializes_required_components(self):
        """Lifespan initializes document_store, embedder, vector_store, and pipeline."""
        from context_library.server.app import lifespan
        from fastapi import FastAPI

        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock environment variables for this test
            with patch.dict(
                os.environ,
                {
                    "CTX_SQLITE_DB_PATH": str(Path(tmpdir) / "test.db"),
                    "CTX_CHROMADB_PATH": str(Path(tmpdir) / "chroma"),
                    "CTX_EMBEDDING_MODEL": "all-MiniLM-L6-v2",
                },
            ):
                app = FastAPI()

                async with lifespan(app):
                    # Verify all required components are initialized
                    assert hasattr(app.state, "document_store")
                    assert hasattr(app.state, "embedder")
                    assert hasattr(app.state, "vector_store")
                    assert hasattr(app.state, "pipeline")
                    assert hasattr(app.state, "helper_adapters")

                    # Verify they're not None
                    assert app.state.document_store is not None
                    assert app.state.embedder is not None
                    assert app.state.vector_store is not None
                    assert app.state.pipeline is not None
                    assert isinstance(app.state.helper_adapters, list)

    @pytest.mark.asyncio
    async def test_lifespan_sets_config_on_app_state(self):
        """Lifespan sets config on app.state for route access."""
        from context_library.server.app import lifespan
        from fastapi import FastAPI

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CTX_SQLITE_DB_PATH": str(Path(tmpdir) / "test.db"),
                    "CTX_CHROMADB_PATH": str(Path(tmpdir) / "chroma"),
                    "CTX_EMBEDDING_MODEL": "all-MiniLM-L6-v2",
                },
            ):
                app = FastAPI()

                async with lifespan(app):
                    assert hasattr(app.state, "config")
                    assert app.state.config is not None

    @pytest.mark.asyncio
    async def test_lifespan_creates_sqlite_parent_directory(self):
        """Lifespan creates parent directory for SQLite database if it doesn't exist."""
        from context_library.server.app import lifespan
        from fastapi import FastAPI

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "subdir" / "nested" / "test.db"

            with patch.dict(
                os.environ,
                {
                    "CTX_SQLITE_DB_PATH": str(db_path),
                    "CTX_CHROMADB_PATH": str(Path(tmpdir) / "chroma"),
                    "CTX_EMBEDDING_MODEL": "all-MiniLM-L6-v2",
                },
            ):
                app = FastAPI()

                async with lifespan(app):
                    # Parent directory should have been created
                    assert db_path.parent.exists()
                    assert db_path.parent.is_dir()

    @pytest.mark.asyncio
    async def test_lifespan_reranker_disabled_by_default(self):
        """Lifespan initializes reranker as None when CTX_ENABLE_RERANKER is false."""
        from context_library.server.app import lifespan
        from fastapi import FastAPI

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CTX_SQLITE_DB_PATH": str(Path(tmpdir) / "test.db"),
                    "CTX_CHROMADB_PATH": str(Path(tmpdir) / "chroma"),
                    "CTX_EMBEDDING_MODEL": "all-MiniLM-L6-v2",
                    "CTX_ENABLE_RERANKER": "false",
                },
            ):
                app = FastAPI()

                async with lifespan(app):
                    assert app.state.reranker is None

    @pytest.mark.asyncio
    async def test_lifespan_no_helper_adapters_when_url_not_configured(self):
        """Lifespan initializes empty helper_adapters list when helper_url is not set."""
        from context_library.server.app import lifespan
        from fastapi import FastAPI

        with tempfile.TemporaryDirectory() as tmpdir:
            # Set CTX_HELPER_URL="" explicitly — env vars take priority over .env file in
            # pydantic-settings, so an empty string here overrides any value in .env.
            with patch.dict(
                os.environ,
                {
                    "CTX_SQLITE_DB_PATH": str(Path(tmpdir) / "test.db"),
                    "CTX_CHROMADB_PATH": str(Path(tmpdir) / "chroma"),
                    "CTX_EMBEDDING_MODEL": "all-MiniLM-L6-v2",
                    "CTX_HELPER_URL": "",
                    "CTX_HELPER_API_KEY": "",
                    "CTX_YOUTUBE_ENABLED": "false",
                },
            ):
                app = FastAPI()

                async with lifespan(app):
                    assert app.state.helper_adapters == []


class TestOuraAdapterInitialization:
    """Tests for OuraAdapter conditional initialization in lifespan."""

    @pytest.mark.asyncio
    async def test_oura_adapter_initialized_when_enabled_with_valid_config(self):
        """OuraAdapter is initialized when CTX_HELPER_OURA_ENABLED=true and credentials are set."""
        from context_library.server.app import lifespan
        from context_library.adapters.oura import OuraAdapter
        from fastapi import FastAPI

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CTX_SQLITE_DB_PATH": str(Path(tmpdir) / "test.db"),
                    "CTX_CHROMADB_PATH": str(Path(tmpdir) / "chroma"),
                    "CTX_EMBEDDING_MODEL": "all-MiniLM-L6-v2",
                    "CTX_HELPER_URL": "http://localhost:7123",
                    "CTX_HELPER_API_KEY": "test-key",
                    "CTX_HELPER_OURA_ENABLED": "true",
                },
            ):
                app = FastAPI()

                async with lifespan(app):
                    # OuraAdapter should be in helper_adapters
                    oura_adapters = [a for a in app.state.helper_adapters if isinstance(a, OuraAdapter)]
                    assert len(oura_adapters) == 1
                    assert oura_adapters[0]._api_url == "http://localhost:7123"

    @pytest.mark.asyncio
    async def test_oura_adapter_not_initialized_when_disabled(self):
        """OuraAdapter is not initialized when CTX_HELPER_OURA_ENABLED=false."""
        from context_library.server.app import lifespan
        from context_library.adapters.oura import OuraAdapter
        from fastapi import FastAPI

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CTX_SQLITE_DB_PATH": str(Path(tmpdir) / "test.db"),
                    "CTX_CHROMADB_PATH": str(Path(tmpdir) / "chroma"),
                    "CTX_EMBEDDING_MODEL": "all-MiniLM-L6-v2",
                    "CTX_HELPER_URL": "http://localhost:7123",
                    "CTX_HELPER_API_KEY": "test-key",
                    "CTX_HELPER_OURA_ENABLED": "false",
                },
            ):
                app = FastAPI()

                async with lifespan(app):
                    # OuraAdapter should NOT be in helper_adapters
                    oura_adapters = [a for a in app.state.helper_adapters if isinstance(a, OuraAdapter)]
                    assert len(oura_adapters) == 0

    @pytest.mark.asyncio
    async def test_oura_adapter_initialization_failure_gracefully_handled(self):
        """OuraAdapter initialization failure is caught and does not crash lifespan."""
        from context_library.server.app import lifespan
        from fastapi import FastAPI

        with tempfile.TemporaryDirectory() as tmpdir:
            # Set CTX_HELPER_API_KEY="" explicitly — env vars take priority over .env file in
            # pydantic-settings, so an empty string here overrides any value in .env.
            with patch.dict(
                os.environ,
                {
                    "CTX_SQLITE_DB_PATH": str(Path(tmpdir) / "test.db"),
                    "CTX_CHROMADB_PATH": str(Path(tmpdir) / "chroma"),
                    "CTX_EMBEDDING_MODEL": "all-MiniLM-L6-v2",
                    "CTX_HELPER_URL": "http://localhost:7123",
                    "CTX_HELPER_API_KEY": "",  # empty → OuraAdapter raises ValueError
                    "CTX_HELPER_OURA_ENABLED": "true",
                },
            ):
                app = FastAPI()

                # lifespan should complete successfully despite OuraAdapter failing
                async with lifespan(app):
                    # Verify core components are still initialized
                    assert app.state.document_store is not None
                    assert app.state.embedder is not None
                    # OuraAdapter should not be in helper_adapters due to ValueError
                    from context_library.adapters.oura import OuraAdapter
                    oura_adapters = [a for a in app.state.helper_adapters if isinstance(a, OuraAdapter)]
                    assert len(oura_adapters) == 0

    @pytest.mark.asyncio
    async def test_oura_adapter_receives_correct_config_parameters(self):
        """OuraAdapter is initialized with api_url and api_key from config."""
        from context_library.server.app import lifespan
        from context_library.adapters.oura import OuraAdapter
        from fastapi import FastAPI

        with tempfile.TemporaryDirectory() as tmpdir:
            api_url = "http://custom-oura-host:9000"
            api_key = "custom-oura-key-12345"

            with patch.dict(
                os.environ,
                {
                    "CTX_SQLITE_DB_PATH": str(Path(tmpdir) / "test.db"),
                    "CTX_CHROMADB_PATH": str(Path(tmpdir) / "chroma"),
                    "CTX_EMBEDDING_MODEL": "all-MiniLM-L6-v2",
                    "CTX_HELPER_URL": api_url,
                    "CTX_HELPER_API_KEY": api_key,
                    "CTX_HELPER_OURA_ENABLED": "true",
                },
            ):
                app = FastAPI()

                async with lifespan(app):
                    oura_adapters = [a for a in app.state.helper_adapters if isinstance(a, OuraAdapter)]
                    assert len(oura_adapters) == 1

                    # Verify OuraAdapter was initialized with correct parameters
                    adapter = oura_adapters[0]
                    assert adapter._api_url == api_url
                    assert adapter._api_key == api_key

    @pytest.mark.asyncio
    async def test_oura_adapter_in_helper_adapters_list(self):
        """OuraAdapter instance is added to helper_adapters list when enabled."""
        from context_library.server.app import lifespan
        from context_library.adapters.oura import OuraAdapter
        from fastapi import FastAPI

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CTX_SQLITE_DB_PATH": str(Path(tmpdir) / "test.db"),
                    "CTX_CHROMADB_PATH": str(Path(tmpdir) / "chroma"),
                    "CTX_EMBEDDING_MODEL": "all-MiniLM-L6-v2",
                    "CTX_HELPER_URL": "http://localhost:7123",
                    "CTX_HELPER_API_KEY": "test-key",
                    "CTX_HELPER_OURA_ENABLED": "true",
                },
            ):
                app = FastAPI()

                async with lifespan(app):
                    # helper_adapters should be a list
                    assert isinstance(app.state.helper_adapters, list)

                    # Should contain at least the OuraAdapter
                    assert any(isinstance(a, OuraAdapter) for a in app.state.helper_adapters)

    @pytest.mark.asyncio
    async def test_lifespan_with_multiple_helper_adapters_including_oura(self):
        """Lifespan initializes multiple helper adapters including OuraAdapter when all enabled."""
        from context_library.server.app import lifespan
        from context_library.adapters.oura import OuraAdapter
        from fastapi import FastAPI

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CTX_SQLITE_DB_PATH": str(Path(tmpdir) / "test.db"),
                    "CTX_CHROMADB_PATH": str(Path(tmpdir) / "chroma"),
                    "CTX_EMBEDDING_MODEL": "all-MiniLM-L6-v2",
                    "CTX_HELPER_URL": "http://localhost:7123",
                    "CTX_HELPER_API_KEY": "test-key",
                    "CTX_HELPER_OURA_ENABLED": "true",
                },
            ):
                app = FastAPI()

                async with lifespan(app):
                    # Should have at least one adapter (OuraAdapter)
                    assert len(app.state.helper_adapters) >= 1

                    # At least one should be OuraAdapter
                    assert any(isinstance(a, OuraAdapter) for a in app.state.helper_adapters)
