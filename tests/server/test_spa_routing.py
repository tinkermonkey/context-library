"""Tests for SPA routing and static file serving."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from contextlib import asynccontextmanager

from context_library.server.app import create_app
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import AdapterConfig, Domain


@pytest.fixture()
def ds_for_spa() -> DocumentStore:
    """In-memory DocumentStore for SPA tests."""
    store = DocumentStore(":memory:", check_same_thread=False)
    config = AdapterConfig(
        adapter_id="test-adapter",
        adapter_type="filesystem",
        domain=Domain.NOTES,
        normalizer_version="1.0.0",
    )
    store.register_adapter(config)
    return store


@pytest.fixture()
def client_spa(ds_for_spa: DocumentStore) -> TestClient:
    """FastAPI TestClient for SPA routing tests."""
    mock_embedder = MagicMock()
    mock_embedder.model_id = "all-MiniLM-L6-v2"
    mock_embedder.dimension = 384
    mock_vector_store = MagicMock()
    mock_vector_store.count.return_value = 0

    @asynccontextmanager
    async def noop_lifespan(app):
        app.state.document_store = ds_for_spa
        app.state.embedder = mock_embedder
        app.state.vector_store = mock_vector_store
        app.state.pipeline = MagicMock()
        app.state.reranker = None
        yield

    app = create_app()
    app.router.lifespan_context = noop_lifespan

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


class TestAPIErrorHandling:
    """Test that unknown/mistyped paths return JSON 404, not HTML."""

    def test_unknown_path_returns_json_404(self, client_spa: TestClient):
        """
        Unknown paths (e.g., /chunkdata, /mistyped) should return JSON 404
        from the SPA fallback, not HTML. This prevents API clients from getting
        HTML when they make typos or call non-existent endpoints.
        """
        response = client_spa.get("/mistyped")
        assert response.status_code == 404
        # Should be JSON, not HTML
        assert response.headers["content-type"].startswith("application/json")
        data = response.json()
        assert "detail" in data

    def test_api_like_path_returns_json_404(self, client_spa: TestClient):
        """Paths that resemble API routes (but aren't registered) should return JSON 404."""
        # /chunks might match the actual router in some cases, so test with a variant
        response = client_spa.get("/chunkquery")
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")

    def test_api_typo_returns_json_404(self, client_spa: TestClient):
        """Typos of actual API routes should return JSON 404."""
        # /sources (note: /sources is the API route, but we're calling the router with /sources)
        # If it's not handled by the actual router, SPA fallback returns 404
        response = client_spa.get("/sourcedata")
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")

    def test_arbitrary_unknown_path_returns_json_404(self, client_spa: TestClient):
        """Any unregistered path (not in client routes whitelist) returns 404."""
        response = client_spa.get("/stats/unknown")
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")

    def test_correct_api_route_works(self, client_spa: TestClient):
        """Correct API routes should work normally."""
        response = client_spa.get("/health")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")

    def test_ingest_route_returns_json_404(self, client_spa: TestClient):
        """Ingest (webhook) routes that don't exist should return JSON 404."""
        response = client_spa.get("/ingest/nonexistent")
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")

    def test_real_world_mistyped_api_routes(self, client_spa: TestClient):
        """
        Real-world scenarios: mistyped or unknown API routes should return JSON 404
        instead of HTML from the SPA fallback. This is the core bug from the issue.
        """
        # These are paths users might try when calling the API
        mistyped_routes = [
            "/chunk",          # typo for /chunks
            "/source",         # typo for /sources
            "/stat",           # typo for /stats
            "/adapter",        # typo for /adapters
            "/quer",           # typo for /query
            "/healthcheck",    # common typo for /health
            "/ingestdata",     # typo attempt
        ]
        for route in mistyped_routes:
            response = client_spa.get(route)
            assert response.status_code == 404, f"Route {route} should return 404 (API error), not SPA fallback"
            assert response.headers["content-type"].startswith("application/json"), \
                f"Route {route} returned HTML instead of JSON"

    def test_registered_client_side_routes_return_spa_html(self, client_spa: TestClient):
        """
        Known client-side routes (in the whitelist) should return index.html for
        client-side router handling. Unknown routes return 404 to protect APIs.
        """
        # These are registered client-side routes (from ui/src/router.tsx)
        client_routes = [
            "",                     # root path (/)  -> returns as part of /
            "/browser",             # /browser route
            "/search",              # /search route
            "/browser/view",        # subpath of registered route
            "/search/results",      # subpath of registered route
        ]
        for route in client_routes:
            response = client_spa.get(route)
            assert response.status_code == 200, f"Route /{route} should return 200 for SPA fallback"
            content = response.text
            assert "<!doctype html>" in content.lower() or "<html" in content.lower(), \
                f"Route /{route} should return HTML (SPA), not 404"


class TestSPAFallback:
    """Test that known client-side routes fall back to index.html."""

    def test_browser_route_returns_spa_html(self, client_spa: TestClient):
        """Browser route should return index.html."""
        response = client_spa.get("/browser")
        assert response.status_code == 200
        # Should be HTML (or at least contain HTML elements)
        content = response.text
        assert "<!doctype html>" in content.lower() or "<html" in content.lower()

    def test_browser_route_with_subpath_returns_spa_html(self, client_spa: TestClient):
        """Browser route with subpaths should return index.html."""
        response = client_spa.get("/browser/sources")
        assert response.status_code == 200
        content = response.text
        assert "<!doctype html>" in content.lower() or "<html" in content.lower()

    def test_deeply_nested_client_route(self, client_spa: TestClient):
        """Deeply nested client-side routes should still return index.html."""
        response = client_spa.get("/search/results/filter/advanced")
        assert response.status_code == 200
        content = response.text
        assert "<!doctype html>" in content.lower() or "<html" in content.lower()


class TestFaviconServing:
    """Test that favicon.svg is served correctly."""

    def test_favicon_returns_svg(self, client_spa: TestClient):
        """
        Favicon request should return SVG file, not HTML.
        This test runs only if the favicon actually exists in the built assets.
        """
        response = client_spa.get("/favicon.svg")
        # If the app was built with favicon in dist/, we should get it
        if response.status_code == 200:
            # Should have SVG content type
            assert "svg" in response.headers.get("content-type", "").lower() or response.text.startswith("<svg")
        else:
            # If it doesn't exist, should be 404 JSON, not HTML
            assert response.status_code == 404
            assert response.headers["content-type"].startswith("application/json")


class TestStaticAssetServing:
    """Test that static assets are served correctly."""

    def test_js_bundle_request_not_spa_fallback(self, client_spa: TestClient):
        """
        Requests for assets that don't exist should be handled specially.
        Non-existent .js/.css requests should not return index.html.
        """
        response = client_spa.get("/assets/nonexistent.js")
        # Should be 404, not HTML from SPA fallback
        assert response.status_code == 404
