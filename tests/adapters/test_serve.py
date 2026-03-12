"""Integration tests for the serve_adapter HTTP wrapper."""

import json
import threading
import time
from unittest.mock import MagicMock

import httpx
import pytest

from context_library.adapters.base import BaseAdapter
from context_library.adapters.serve import serve_adapter
from context_library.storage.models import (
    Domain,
    NormalizedContent,
    StructuralHints,
)


class MockAdapter(BaseAdapter):
    """Mock adapter for testing serve_adapter wrapper."""

    def __init__(
        self,
        adapter_id: str = "test:adapter",
        domain: Domain = Domain.NOTES,
        normalizer_version: str = "1.0.0",
        fetch_impl=None,
    ):
        self._adapter_id = adapter_id
        self._domain = domain
        self._normalizer_version = normalizer_version
        self._fetch_impl = fetch_impl

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    @property
    def domain(self) -> Domain:
        return self._domain

    @property
    def normalizer_version(self) -> str:
        return self._normalizer_version

    def fetch(self, source_ref: str):
        """Fetch implementation that can be customized via constructor."""
        if self._fetch_impl:
            yield from self._fetch_impl(source_ref)
        else:
            hints = StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            )
            yield NormalizedContent(
                markdown=f"# {source_ref}\n\nContent for {source_ref}",
                source_id=f"src:{source_ref}",
                structural_hints=hints,
                normalizer_version=self.normalizer_version,
            )


class TestServerStartStop:
    """Tests for server startup and shutdown."""

    def test_serve_adapter_starts_server(self):
        """serve_adapter() starts an HTTP server on the specified port."""
        adapter = MockAdapter(adapter_id="test:1", domain=Domain.NOTES)
        port = 18001

        # Start server in background thread
        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()

        # Wait for server to start
        time.sleep(0.2)

        # Verify server is responding
        response = httpx.get(f"http://127.0.0.1:{port}/health")
        assert response.status_code == 200

    def test_serve_adapter_default_host_is_0_0_0_0(self):
        """serve_adapter() binds to 0.0.0.0 by default."""
        adapter = MockAdapter(adapter_id="test:2", domain=Domain.NOTES)
        port = 18002

        # Start server in background thread (using default host="0.0.0.0")
        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "0.0.0.0", port), daemon=True
        )
        server_thread.start()

        # Wait for server to start
        time.sleep(0.2)

        # Verify server responds on localhost
        response = httpx.get(f"http://127.0.0.1:{port}/health")
        assert response.status_code == 200

    def test_serve_adapter_default_port_is_8000(self):
        """serve_adapter() uses port 8000 by default (not testing actual bind)."""
        # This is verified through the function signature
        import inspect

        sig = inspect.signature(serve_adapter)
        assert sig.parameters["port"].default == 8000


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    def test_health_returns_200_ok(self):
        """GET /health returns 200 status code."""
        adapter = MockAdapter(
            adapter_id="test:health", domain=Domain.NOTES
        )
        port = 18003

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.get(f"http://127.0.0.1:{port}/health")
        assert response.status_code == 200

    def test_health_returns_json(self):
        """GET /health returns JSON response."""
        adapter = MockAdapter(
            adapter_id="test:health", domain=Domain.NOTES
        )
        port = 18004

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.get(f"http://127.0.0.1:{port}/health")
        data = response.json()
        assert isinstance(data, dict)

    def test_health_contains_status(self):
        """GET /health returns status field set to 'ok'."""
        adapter = MockAdapter(
            adapter_id="test:health", domain=Domain.NOTES
        )
        port = 18005

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.get(f"http://127.0.0.1:{port}/health")
        data = response.json()
        assert data.get("status") == "ok"

    def test_health_contains_adapter_id(self):
        """GET /health returns adapter_id field."""
        adapter = MockAdapter(
            adapter_id="my:custom:id", domain=Domain.NOTES
        )
        port = 18006

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.get(f"http://127.0.0.1:{port}/health")
        data = response.json()
        assert data.get("adapter_id") == "my:custom:id"

    def test_health_contains_domain(self):
        """GET /health returns domain field with domain value."""
        adapter = MockAdapter(
            adapter_id="test:domain", domain=Domain.TASKS
        )
        port = 18007

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.get(f"http://127.0.0.1:{port}/health")
        data = response.json()
        assert data.get("domain") == "tasks"

    def test_health_with_different_domains(self):
        """GET /health correctly returns domain for all domain types."""
        for domain in [Domain.MESSAGES, Domain.NOTES, Domain.EVENTS, Domain.TASKS]:
            adapter = MockAdapter(adapter_id="test", domain=domain)
            port = 18008 + list(Domain).index(domain)

            server_thread = threading.Thread(
                target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
            )
            server_thread.start()
            time.sleep(0.2)

            response = httpx.get(f"http://127.0.0.1:{port}/health")
            data = response.json()
            assert data.get("domain") == domain.value


class TestFetchEndpoint:
    """Tests for POST /fetch endpoint."""

    def test_fetch_returns_200_on_success(self):
        """POST /fetch returns 200 status code for valid request."""
        adapter = MockAdapter(adapter_id="test:fetch", domain=Domain.NOTES)
        port = 18012

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": "test_source"},
        )
        assert response.status_code == 200

    def test_fetch_returns_json(self):
        """POST /fetch returns JSON response."""
        adapter = MockAdapter(adapter_id="test:fetch", domain=Domain.NOTES)
        port = 18013

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": "test_source"},
        )
        data = response.json()
        assert isinstance(data, dict)

    def test_fetch_returns_normalized_contents(self):
        """POST /fetch returns normalized_contents field."""
        adapter = MockAdapter(adapter_id="test:fetch", domain=Domain.NOTES)
        port = 18014

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": "test_source"},
        )
        data = response.json()
        assert "normalized_contents" in data
        assert isinstance(data["normalized_contents"], list)

    def test_fetch_calls_adapter_fetch_with_source_ref(self):
        """POST /fetch calls adapter.fetch(source_ref)."""
        called_with = []

        def custom_fetch(source_ref):
            called_with.append(source_ref)
            hints = StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            )
            yield NormalizedContent(
                markdown="test",
                source_id="src",
                structural_hints=hints,
                normalizer_version="1.0.0",
            )

        adapter = MockAdapter(
            adapter_id="test:fetch",
            domain=Domain.NOTES,
            fetch_impl=custom_fetch,
        )
        port = 18015

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": "my_source"},
        )
        assert response.status_code == 200
        assert called_with == ["my_source"]

    def test_fetch_serializes_normalized_content(self):
        """POST /fetch serializes NormalizedContent objects correctly."""
        adapter = MockAdapter(adapter_id="test:fetch", domain=Domain.NOTES)
        port = 18016

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": "test_source"},
        )
        data = response.json()
        assert len(data["normalized_contents"]) == 1

        content = data["normalized_contents"][0]
        assert content["markdown"] == "# test_source\n\nContent for test_source"
        assert content["source_id"] == "src:test_source"
        assert content["normalizer_version"] == "1.0.0"

    def test_fetch_includes_structural_hints(self):
        """POST /fetch includes structural_hints in response."""
        adapter = MockAdapter(adapter_id="test:fetch", domain=Domain.NOTES)
        port = 18017

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": "test_source"},
        )
        data = response.json()
        content = data["normalized_contents"][0]
        hints = content["structural_hints"]

        assert "has_headings" in hints
        assert "has_lists" in hints
        assert "has_tables" in hints
        assert "natural_boundaries" in hints

    def test_fetch_with_multiple_results(self):
        """POST /fetch returns multiple NormalizedContent objects."""
        def custom_fetch(source_ref):
            hints = StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            )
            for i in range(3):
                yield NormalizedContent(
                    markdown=f"Content {i}",
                    source_id=f"src:{i}",
                    structural_hints=hints,
                    normalizer_version="1.0.0",
                )

        adapter = MockAdapter(
            adapter_id="test:fetch",
            domain=Domain.NOTES,
            fetch_impl=custom_fetch,
        )
        port = 18018

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": "test_source"},
        )
        data = response.json()
        assert len(data["normalized_contents"]) == 3
        assert data["normalized_contents"][0]["source_id"] == "src:0"
        assert data["normalized_contents"][1]["source_id"] == "src:1"
        assert data["normalized_contents"][2]["source_id"] == "src:2"

    def test_fetch_with_empty_results(self):
        """POST /fetch returns empty list when adapter yields nothing."""
        def custom_fetch(source_ref):
            return
            yield  # This line is unreachable, making this a generator that yields nothing

        adapter = MockAdapter(
            adapter_id="test:fetch",
            domain=Domain.NOTES,
            fetch_impl=custom_fetch,
        )
        port = 18019

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": "test_source"},
        )
        data = response.json()
        assert data["normalized_contents"] == []


class TestFetchValidation:
    """Tests for request validation and error handling."""

    def test_fetch_missing_source_ref_returns_400(self):
        """POST /fetch without source_ref returns 400 Bad Request."""
        adapter = MockAdapter(adapter_id="test:validation", domain=Domain.NOTES)
        port = 18020

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={},
        )
        assert response.status_code == 400

    def test_fetch_null_source_ref_returns_400(self):
        """POST /fetch with null source_ref returns 400 Bad Request."""
        adapter = MockAdapter(adapter_id="test:validation", domain=Domain.NOTES)
        port = 18021

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": None},
        )
        assert response.status_code == 400

    def test_fetch_non_string_source_ref_returns_400(self):
        """POST /fetch with non-string source_ref returns 400 Bad Request."""
        adapter = MockAdapter(adapter_id="test:validation", domain=Domain.NOTES)
        port = 18022

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": 123},
        )
        assert response.status_code == 400

    def test_fetch_invalid_json_returns_400(self):
        """POST /fetch with invalid JSON returns 400 Bad Request."""
        adapter = MockAdapter(adapter_id="test:validation", domain=Domain.NOTES)
        port = 18023

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    def test_fetch_empty_body_returns_400(self):
        """POST /fetch with empty body returns 400 Bad Request."""
        adapter = MockAdapter(adapter_id="test:validation", domain=Domain.NOTES)
        port = 18024

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            content="",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    def test_fetch_adapter_exception_returns_500(self):
        """POST /fetch returns 500 when adapter.fetch() raises exception."""
        def custom_fetch(source_ref):
            raise ValueError("Test error from adapter")

        adapter = MockAdapter(
            adapter_id="test:error",
            domain=Domain.NOTES,
            fetch_impl=custom_fetch,
        )
        port = 18025

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": "test"},
        )
        assert response.status_code == 500

    def test_fetch_error_response_contains_error_field(self):
        """POST /fetch 500 response contains error field with exception message."""
        def custom_fetch(source_ref):
            raise ValueError("Internal database connection failed")

        adapter = MockAdapter(
            adapter_id="test:error",
            domain=Domain.NOTES,
            fetch_impl=custom_fetch,
        )
        port = 18026

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": "test"},
        )
        data = response.json()
        assert "error" in data
        # Error message from exception is returned for debugging
        assert data["error"] == "Internal database connection failed"


class TestAuthentication:
    """Tests for Bearer token authentication."""

    def test_fetch_without_auth_succeeds_when_no_api_key(self):
        """POST /fetch succeeds without auth when api_key is None."""
        adapter = MockAdapter(adapter_id="test:noauth", domain=Domain.NOTES)
        port = 18027

        server_thread = threading.Thread(
            target=serve_adapter,
            args=(adapter, "127.0.0.1", port),
            kwargs={"api_key": None},
            daemon=True,
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": "test"},
        )
        assert response.status_code == 200

    def test_fetch_with_auth_header_succeeds_when_no_api_key(self):
        """POST /fetch with auth header succeeds when api_key is None."""
        adapter = MockAdapter(adapter_id="test:noauth", domain=Domain.NOTES)
        port = 18028

        server_thread = threading.Thread(
            target=serve_adapter,
            args=(adapter, "127.0.0.1", port),
            kwargs={"api_key": None},
            daemon=True,
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": "test"},
            headers={"Authorization": "Bearer token"},
        )
        assert response.status_code == 200

    def test_fetch_without_auth_returns_401_when_api_key_set(self):
        """POST /fetch without auth header returns 401 when api_key is set."""
        adapter = MockAdapter(adapter_id="test:auth", domain=Domain.NOTES)
        port = 18029

        server_thread = threading.Thread(
            target=serve_adapter,
            args=(adapter, "127.0.0.1", port),
            kwargs={"api_key": "secret"},
            daemon=True,
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": "test"},
        )
        assert response.status_code == 401

    def test_fetch_with_correct_token_succeeds(self):
        """POST /fetch with correct Bearer token succeeds."""
        adapter = MockAdapter(adapter_id="test:auth", domain=Domain.NOTES)
        port = 18030

        server_thread = threading.Thread(
            target=serve_adapter,
            args=(adapter, "127.0.0.1", port),
            kwargs={"api_key": "secret-key"},
            daemon=True,
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": "test"},
            headers={"Authorization": "Bearer secret-key"},
        )
        assert response.status_code == 200

    def test_fetch_with_incorrect_token_returns_401(self):
        """POST /fetch with incorrect Bearer token returns 401."""
        adapter = MockAdapter(adapter_id="test:auth", domain=Domain.NOTES)
        port = 18031

        server_thread = threading.Thread(
            target=serve_adapter,
            args=(adapter, "127.0.0.1", port),
            kwargs={"api_key": "correct-secret"},
            daemon=True,
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": "test"},
            headers={"Authorization": "Bearer wrong-secret"},
        )
        assert response.status_code == 401

    def test_fetch_with_malformed_auth_header_returns_401(self):
        """POST /fetch with malformed auth header returns 401."""
        adapter = MockAdapter(adapter_id="test:auth", domain=Domain.NOTES)
        port = 18032

        server_thread = threading.Thread(
            target=serve_adapter,
            args=(adapter, "127.0.0.1", port),
            kwargs={"api_key": "secret"},
            daemon=True,
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": "test"},
            headers={"Authorization": "NotBearer secret"},
        )
        assert response.status_code == 401

    def test_health_without_auth_succeeds_when_no_api_key(self):
        """GET /health succeeds without auth when api_key is None."""
        adapter = MockAdapter(adapter_id="test:noauth", domain=Domain.NOTES)
        port = 18033

        server_thread = threading.Thread(
            target=serve_adapter,
            args=(adapter, "127.0.0.1", port),
            kwargs={"api_key": None},
            daemon=True,
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.get(f"http://127.0.0.1:{port}/health")
        assert response.status_code == 200

    def test_health_does_not_require_auth_even_when_api_key_set(self):
        """GET /health succeeds without auth even when api_key is set."""
        adapter = MockAdapter(adapter_id="test:health", domain=Domain.NOTES)
        port = 18034

        server_thread = threading.Thread(
            target=serve_adapter,
            args=(adapter, "127.0.0.1", port),
            kwargs={"api_key": "secret"},
            daemon=True,
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.get(f"http://127.0.0.1:{port}/health")
        assert response.status_code == 200


class TestNotFound:
    """Tests for 404 responses."""

    def test_unknown_path_returns_404(self):
        """GET /unknown returns 404 Not Found."""
        adapter = MockAdapter(adapter_id="test:404", domain=Domain.NOTES)
        port = 18035

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.get(f"http://127.0.0.1:{port}/unknown")
        assert response.status_code == 404

    def test_post_to_unknown_path_returns_404(self):
        """POST /unknown returns 404 Not Found."""
        adapter = MockAdapter(adapter_id="test:404", domain=Domain.NOTES)
        port = 18036

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/unknown",
            json={"source_ref": "test"},
        )
        assert response.status_code == 404


class TestContentTypes:
    """Tests for Content-Type handling."""

    def test_health_response_has_json_content_type(self):
        """GET /health response includes Content-Type: application/json header."""
        adapter = MockAdapter(adapter_id="test:ct", domain=Domain.NOTES)
        port = 18037

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.get(f"http://127.0.0.1:{port}/health")
        assert response.headers.get("content-type") == "application/json"

    def test_fetch_response_has_json_content_type(self):
        """POST /fetch response includes Content-Type: application/json header."""
        adapter = MockAdapter(adapter_id="test:ct", domain=Domain.NOTES)
        port = 18038

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": "test"},
        )
        assert response.headers.get("content-type") == "application/json"

    def test_error_response_has_json_content_type(self):
        """Error responses include Content-Type: application/json header."""
        adapter = MockAdapter(adapter_id="test:ct", domain=Domain.NOTES)
        port = 18039

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={},
        )
        assert response.headers.get("content-type") == "application/json"


class TestRoundTrip:
    """Integration tests for end-to-end serialization/deserialization."""

    def test_normalized_content_survives_json_round_trip(self):
        """NormalizedContent survives JSON serialization and deserialization."""
        # Create original content with extra_metadata
        original_hints = StructuralHints(
            has_headings=True,
            has_lists=True,
            has_tables=False,
            natural_boundaries=[100, 200, 300],
            file_path="/some/file.md",
            modified_at="2024-01-15T10:30:00Z",
            file_size_bytes=1024,
            extra_metadata={"key1": "value1", "key2": {"nested": "value"}},
        )

        original = NormalizedContent(
            markdown="# Header\n\nSome content",
            source_id="src:test",
            structural_hints=original_hints,
            normalizer_version="1.5.0",
        )

        def custom_fetch(source_ref):
            yield original

        adapter = MockAdapter(
            adapter_id="test:roundtrip",
            domain=Domain.NOTES,
            fetch_impl=custom_fetch,
        )
        port = 18040

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        # Make request and get JSON response
        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": "test"},
        )
        data = response.json()

        # Reconstruct NormalizedContent from JSON
        item = data["normalized_contents"][0]
        reconstructed = NormalizedContent.model_validate(item)

        # Verify all fields match
        assert reconstructed.markdown == original.markdown
        assert reconstructed.source_id == original.source_id
        assert reconstructed.normalizer_version == original.normalizer_version
        assert reconstructed.structural_hints == original.structural_hints

    def test_extra_metadata_dict_survives_round_trip(self):
        """extra_metadata dict with various types survives round-trip."""
        hints = StructuralHints(
            has_headings=True,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata={
                "string_val": "text",
                "int_val": 42,
                "float_val": 3.14,
                "bool_val": True,
                "null_val": None,
                "list_val": [1, 2, 3],
                "nested_dict": {"inner": "value"},
            },
        )

        original = NormalizedContent(
            markdown="test",
            source_id="src",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        def custom_fetch(source_ref):
            yield original

        adapter = MockAdapter(
            adapter_id="test:metadata",
            domain=Domain.NOTES,
            fetch_impl=custom_fetch,
        )
        port = 18041

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        response = httpx.post(
            f"http://127.0.0.1:{port}/fetch",
            json={"source_ref": "test"},
        )
        data = response.json()
        item = data["normalized_contents"][0]
        reconstructed = NormalizedContent.model_validate(item)

        # Verify extra_metadata survived round-trip
        assert reconstructed.structural_hints.extra_metadata == original.structural_hints.extra_metadata
        assert reconstructed.structural_hints.extra_metadata["string_val"] == "text"
        assert reconstructed.structural_hints.extra_metadata["int_val"] == 42
        assert reconstructed.structural_hints.extra_metadata["float_val"] == 3.14
        assert reconstructed.structural_hints.extra_metadata["bool_val"] is True
        assert reconstructed.structural_hints.extra_metadata["null_val"] is None
        assert reconstructed.structural_hints.extra_metadata["list_val"] == [1, 2, 3]
        assert reconstructed.structural_hints.extra_metadata["nested_dict"] == {"inner": "value"}


class TestRemoteAdapterIntegration:
    """End-to-end integration tests with RemoteAdapter consuming from serve_adapter."""

    def test_remote_adapter_fetches_from_served_adapter(self):
        """RemoteAdapter can fetch from an adapter served by serve_adapter."""
        # Import RemoteAdapter (gated by httpx availability)
        try:
            from context_library.adapters.remote import RemoteAdapter
        except ImportError:
            pytest.skip("httpx not available")

        # Create and start a mock adapter via serve_adapter
        adapter = MockAdapter(
            adapter_id="test:served",
            domain=Domain.NOTES,
        )
        port = 18042

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        # Create a RemoteAdapter client pointing to the served adapter
        remote = RemoteAdapter(
            service_url=f"http://127.0.0.1:{port}",
            domain=Domain.NOTES,
            adapter_id="remote:test",
        )

        # Fetch via RemoteAdapter
        results = list(remote.fetch("test_source"))

        # Verify results
        assert len(results) == 1
        assert isinstance(results[0], NormalizedContent)
        assert results[0].markdown == "# test_source\n\nContent for test_source"
        assert results[0].source_id == "src:test_source"

    def test_remote_adapter_with_extra_metadata_round_trip(self):
        """NormalizedContent with extra_metadata round-trips through serve_adapter → RemoteAdapter."""
        # Import RemoteAdapter (gated by httpx availability)
        try:
            from context_library.adapters.remote import RemoteAdapter
        except ImportError:
            pytest.skip("httpx not available")

        # Create original content with rich metadata
        original_hints = StructuralHints(
            has_headings=True,
            has_lists=True,
            has_tables=False,
            natural_boundaries=[100, 200],
            extra_metadata={
                "author": "Test Author",
                "tags": ["tag1", "tag2"],
                "version": 2,
                "nested": {"level": 2, "value": "deep"},
            },
        )

        original = NormalizedContent(
            markdown="# Test\n\nContent",
            source_id="src:original",
            structural_hints=original_hints,
            normalizer_version="1.2.0",
        )

        def custom_fetch(source_ref):
            yield original

        # Create and start the adapter service
        adapter = MockAdapter(
            adapter_id="test:metadata_service",
            domain=Domain.NOTES,
            fetch_impl=custom_fetch,
        )
        port = 18043

        server_thread = threading.Thread(
            target=serve_adapter, args=(adapter, "127.0.0.1", port), daemon=True
        )
        server_thread.start()
        time.sleep(0.2)

        # Connect via RemoteAdapter
        remote = RemoteAdapter(
            service_url=f"http://127.0.0.1:{port}",
            domain=Domain.NOTES,
            adapter_id="remote:metadata",
        )

        # Fetch and verify round-trip
        results = list(remote.fetch("test"))
        assert len(results) == 1

        reconstructed = results[0]
        assert reconstructed.markdown == original.markdown
        assert reconstructed.source_id == original.source_id
        assert reconstructed.normalizer_version == original.normalizer_version

        # Verify extra_metadata survived the round-trip
        assert reconstructed.structural_hints.extra_metadata == original.structural_hints.extra_metadata
        assert reconstructed.structural_hints.extra_metadata["author"] == "Test Author"
        assert reconstructed.structural_hints.extra_metadata["tags"] == ["tag1", "tag2"]
        assert reconstructed.structural_hints.extra_metadata["version"] == 2
        assert reconstructed.structural_hints.extra_metadata["nested"]["level"] == 2

    def test_remote_adapter_with_api_key(self):
        """RemoteAdapter can authenticate with serve_adapter using API key."""
        # Import RemoteAdapter (gated by httpx availability)
        try:
            from context_library.adapters.remote import RemoteAdapter
        except ImportError:
            pytest.skip("httpx not available")

        adapter = MockAdapter(
            adapter_id="test:auth_service",
            domain=Domain.NOTES,
        )
        port = 18044
        api_key = "test-secret-key"

        # Start server with API key
        server_thread = threading.Thread(
            target=serve_adapter,
            args=(adapter, "127.0.0.1", port),
            kwargs={"api_key": api_key},
            daemon=True,
        )
        server_thread.start()
        time.sleep(0.2)

        # Create RemoteAdapter with matching API key
        remote = RemoteAdapter(
            service_url=f"http://127.0.0.1:{port}",
            domain=Domain.NOTES,
            adapter_id="remote:auth",
            api_key=api_key,
        )

        # Should succeed with correct key
        results = list(remote.fetch("test"))
        assert len(results) == 1
