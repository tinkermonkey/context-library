"""Tests for the RemoteAdapter."""

import pytest

import httpx

from context_library.adapters.remote import RemoteAdapter
from context_library.storage.models import Domain, NormalizedContent
from tests.adapters.conftest import MockResponse


class TestRemoteAdapterServiceUrlValidation:
    """Tests for RemoteAdapter service_url validation."""

    def test_init_rejects_empty_service_url(self):
        """__init__ raises ValueError when service_url is empty string."""
        with pytest.raises(ValueError, match="service_url must not be empty"):
            RemoteAdapter(
                service_url="",
                domain=Domain.NOTES,
                adapter_id="test",
            )

    def test_init_rejects_service_url_without_scheme(self):
        """__init__ raises ValueError when service_url lacks valid http(s) scheme."""
        # "/path" has empty scheme, so should be caught by scheme check
        with pytest.raises(ValueError, match="service_url must include a scheme"):
            RemoteAdapter(
                service_url="/path/to/resource",
                domain=Domain.NOTES,
                adapter_id="test",
            )

    def test_init_rejects_service_url_without_netloc(self):
        """__init__ raises ValueError when service_url lacks host/netloc."""
        with pytest.raises(ValueError, match="service_url must include a host"):
            RemoteAdapter(
                service_url="http://",
                domain=Domain.NOTES,
                adapter_id="test",
            )

    def test_init_rejects_bare_localhost_without_scheme(self):
        """__init__ rejects bare 'localhost:8000' (common user mistake)."""
        # This is the key case from requirements - localhost:8000 parsed
        # as scheme='localhost', netloc='', path='8000', should be rejected
        with pytest.raises(ValueError, match="service_url must include a host"):
            RemoteAdapter(
                service_url="localhost:8000",
                domain=Domain.NOTES,
                adapter_id="test",
            )

    def test_init_accepts_http_scheme(self):
        """__init__ accepts http:// scheme."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test",
        )
        assert adapter._service_url == "http://localhost:8000"

    def test_init_accepts_https_scheme(self):
        """__init__ accepts https:// scheme."""
        adapter = RemoteAdapter(
            service_url="https://example.com",
            domain=Domain.NOTES,
            adapter_id="test",
        )
        assert adapter._service_url == "https://example.com"

    def test_init_accepts_hostname_with_port(self):
        """__init__ accepts hostnames with explicit port numbers."""
        adapter = RemoteAdapter(
            service_url="http://localhost:9000",
            domain=Domain.NOTES,
            adapter_id="test",
        )
        assert adapter._service_url == "http://localhost:9000"

    def test_init_accepts_full_domain_name(self):
        """__init__ accepts fully qualified domain names."""
        adapter = RemoteAdapter(
            service_url="https://api.example.com",
            domain=Domain.NOTES,
            adapter_id="test",
        )
        assert adapter._service_url == "https://api.example.com"


class TestRemoteAdapterAPIKeyValidation:
    """Tests for RemoteAdapter API key validation."""

    def test_init_rejects_empty_api_key(self):
        """__init__ raises ValueError when api_key is empty string."""
        with pytest.raises(ValueError, match="must not be an empty string"):
            RemoteAdapter(
                service_url="http://localhost:8000",
                domain=Domain.NOTES,
                adapter_id="test",
                api_key="",
            )

    def test_init_accepts_none_api_key(self):
        """__init__ accepts None as api_key (disables auth)."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test",
            api_key=None,
        )
        assert adapter._api_key is None

    def test_init_accepts_non_empty_api_key(self):
        """__init__ accepts non-empty api_key."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test",
            api_key="valid-secret-key",
        )
        assert adapter._api_key == "valid-secret-key"


class TestRemoteAdapterInitialization:
    """Tests for RemoteAdapter initialization."""

    def test_init_required_parameters(self):
        """__init__ accepts required parameters and stores them."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test_adapter",
        )
        assert adapter._service_url == "http://localhost:8000"
        assert adapter._domain == Domain.NOTES
        assert adapter._adapter_id == "test_adapter"
        assert adapter._normalizer_version == "1.0.0"
        assert adapter._api_key is None

    def test_init_custom_parameters(self):
        """__init__ accepts and stores custom parameters."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.TASKS,
            adapter_id="my_adapter",
            normalizer_version="2.0.0",
            api_key="secret_key",
            timeout=60.0,
        )
        assert adapter._service_url == "http://localhost:8000"
        assert adapter._domain == Domain.TASKS
        assert adapter._adapter_id == "my_adapter"
        assert adapter._normalizer_version == "2.0.0"
        assert adapter._api_key == "secret_key"

    def test_init_strips_trailing_slash_from_url(self):
        """__init__ strips trailing slash from service_url."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000/",
            domain=Domain.NOTES,
            adapter_id="test",
        )
        assert adapter._service_url == "http://localhost:8000"

    def test_init_no_trailing_slash(self):
        """__init__ leaves service_url unchanged if no trailing slash."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test",
        )
        assert adapter._service_url == "http://localhost:8000"

    def test_init_multiple_trailing_slashes(self):
        """__init__ strips all trailing slashes from service_url."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000///",
            domain=Domain.NOTES,
            adapter_id="test",
        )
        assert adapter._service_url == "http://localhost:8000"


class TestRemoteAdapterProperties:
    """Tests for RemoteAdapter properties."""

    def test_adapter_id_property(self):
        """adapter_id property returns constructor-supplied value."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="my_unique_id",
        )
        assert adapter.adapter_id == "my_unique_id"

    def test_domain_property(self):
        """domain property returns constructor-supplied domain."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.EVENTS,
            adapter_id="test",
        )
        assert adapter.domain == Domain.EVENTS

    def test_normalizer_version_property_default(self):
        """normalizer_version property returns default when not provided."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test",
        )
        assert adapter.normalizer_version == "1.0.0"

    def test_normalizer_version_property_custom(self):
        """normalizer_version property returns constructor-supplied version."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test",
            normalizer_version="3.5.1",
        )
        assert adapter.normalizer_version == "3.5.1"

    def test_properties_deterministic(self):
        """Properties are deterministic for the same configuration."""
        adapter1 = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="adapter1",
            normalizer_version="1.5.0",
        )
        adapter2 = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="adapter1",
            normalizer_version="1.5.0",
        )
        assert adapter1.adapter_id == adapter2.adapter_id
        assert adapter1.domain == adapter2.domain
        assert adapter1.normalizer_version == adapter2.normalizer_version


class TestRemoteAdapterFetch:
    """Tests for RemoteAdapter.fetch() method."""

    def test_fetch_single_item(self, mock_httpx_client):
        """fetch() yields NormalizedContent for a single item."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test_adapter",
        )

        # Mock response with single normalized content
        fetch_url = "http://localhost:8000/fetch"
        mock_httpx_client.set_response(
            fetch_url,
            {
                "normalized_contents": [
                    {
                        "markdown": "# Test Note\n\nThis is test content.",
                        "source_id": "note_1",
                        "structural_hints": {
                            "has_headings": True,
                            "has_lists": False,
                            "has_tables": False,
                            "natural_boundaries": (10, 20),
                        },
                        "normalizer_version": "1.0.0",
                    }
                ]
            },
        )

        # Fetch and collect results
        results = list(adapter.fetch("note_1"))

        # Verify results
        assert len(results) == 1
        assert isinstance(results[0], NormalizedContent)
        assert results[0].markdown == "# Test Note\n\nThis is test content."
        assert results[0].source_id == "note_1"
        assert results[0].normalizer_version == "1.0.0"

    def test_fetch_multiple_items(self, mock_httpx_client):
        """fetch() yields multiple NormalizedContent objects."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test_adapter",
        )

        fetch_url = "http://localhost:8000/fetch"
        mock_httpx_client.set_response(
            fetch_url,
            {
                "normalized_contents": [
                    {
                        "markdown": "# Note 1",
                        "source_id": "note_1",
                        "structural_hints": {
                            "has_headings": True,
                            "has_lists": False,
                            "has_tables": False,
                            "natural_boundaries": (),
                        },
                        "normalizer_version": "1.0.0",
                    },
                    {
                        "markdown": "# Note 2",
                        "source_id": "note_2",
                        "structural_hints": {
                            "has_headings": True,
                            "has_lists": False,
                            "has_tables": False,
                            "natural_boundaries": (),
                        },
                        "normalizer_version": "1.0.0",
                    },
                ]
            },
        )

        results = list(adapter.fetch("source_ref"))
        assert len(results) == 2
        assert results[0].source_id == "note_1"
        assert results[1].source_id == "note_2"

    def test_fetch_empty_response(self, mock_httpx_client):
        """fetch() yields nothing for empty normalized_contents list."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test_adapter",
        )

        fetch_url = "http://localhost:8000/fetch"
        mock_httpx_client.set_response(fetch_url, {"normalized_contents": []})

        results = list(adapter.fetch("source_ref"))
        assert len(results) == 0

    def test_fetch_sends_post_request(self, mock_httpx_client):
        """fetch() sends POST request to /fetch endpoint."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test_adapter",
        )

        fetch_url = "http://localhost:8000/fetch"
        mock_httpx_client.set_response(fetch_url, {"normalized_contents": []})

        list(adapter.fetch("my_source_ref"))

        # Verify request was made
        assert len(mock_httpx_client.requests) == 1
        request = mock_httpx_client.requests[0]
        assert request["method"] == "POST"
        assert request["url"] == fetch_url

    def test_fetch_sends_correct_request_body(self, mock_httpx_client):
        """fetch() sends source_ref in JSON request body."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test_adapter",
        )

        fetch_url = "http://localhost:8000/fetch"
        mock_httpx_client.set_response(fetch_url, {"normalized_contents": []})

        list(adapter.fetch("specific_source_ref"))

        request = mock_httpx_client.requests[0]
        assert request["json"] == {"source_ref": "specific_source_ref"}

    def test_fetch_bearer_token_when_api_key_provided(self, mock_httpx_client):
        """fetch() sends Authorization: Bearer header when api_key is set."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test_adapter",
            api_key="secret_token_123",
        )

        fetch_url = "http://localhost:8000/fetch"
        mock_httpx_client.set_response(fetch_url, {"normalized_contents": []})

        list(adapter.fetch("source_ref"))

        request = mock_httpx_client.requests[0]
        assert request["headers"]["Authorization"] == "Bearer secret_token_123"

    def test_fetch_no_auth_header_when_api_key_none(self, mock_httpx_client):
        """fetch() omits Authorization header when api_key is None."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test_adapter",
            api_key=None,
        )

        fetch_url = "http://localhost:8000/fetch"
        mock_httpx_client.set_response(fetch_url, {"normalized_contents": []})

        list(adapter.fetch("source_ref"))

        request = mock_httpx_client.requests[0]
        assert "Authorization" not in request["headers"]

    def test_fetch_raises_on_http_4xx_error(self, mock_httpx_client):
        """fetch() raises httpx.HTTPStatusError on 4xx response."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test_adapter",
        )

        fetch_url = "http://localhost:8000/fetch"
        mock_httpx_client.set_response(fetch_url, {"error": "Not found"}, status_code=404)

        with pytest.raises(httpx.HTTPStatusError):
            list(adapter.fetch("source_ref"))

    def test_fetch_raises_on_http_5xx_error(self, mock_httpx_client):
        """fetch() raises httpx.HTTPStatusError on 5xx response."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test_adapter",
        )

        fetch_url = "http://localhost:8000/fetch"
        mock_httpx_client.set_response(fetch_url, {"error": "Server error"}, status_code=500)

        with pytest.raises(httpx.HTTPStatusError):
            list(adapter.fetch("source_ref"))

    def test_fetch_raises_on_missing_normalized_contents_key(self, mock_httpx_client):
        """fetch() raises KeyError when normalized_contents key is missing."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test_adapter",
        )

        fetch_url = "http://localhost:8000/fetch"
        mock_httpx_client.set_response(fetch_url, {"data": []})

        with pytest.raises(KeyError) as exc_info:
            list(adapter.fetch("source_ref"))
        assert "normalized_contents" in str(exc_info.value)

    def test_fetch_raises_on_non_list_normalized_contents(self, mock_httpx_client):
        """fetch() raises TypeError when normalized_contents is not a list."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test_adapter",
        )

        fetch_url = "http://localhost:8000/fetch"
        mock_httpx_client.set_response(fetch_url, {"normalized_contents": {"item": "dict"}})

        with pytest.raises(TypeError) as exc_info:
            list(adapter.fetch("source_ref"))
        assert "list" in str(exc_info.value).lower()

    def test_fetch_raises_on_invalid_normalized_content_item(self, mock_httpx_client):
        """fetch() raises ValidationError when item fails NormalizedContent validation."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test_adapter",
        )

        fetch_url = "http://localhost:8000/fetch"
        # Missing required 'markdown' field
        mock_httpx_client.set_response(
            fetch_url,
            {
                "normalized_contents": [
                    {
                        "source_id": "note_1",
                        "structural_hints": {
                            "has_headings": False,
                            "has_lists": False,
                            "has_tables": False,
                            "natural_boundaries": (),
                        },
                        "normalizer_version": "1.0.0",
                    }
                ]
            },
        )

        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            list(adapter.fetch("source_ref"))

    def test_fetch_non_validation_errors_propagate(self, mock_httpx_client):
        """fetch() allows non-ValidationError exceptions to propagate."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test_adapter",
        )

        fetch_url = "http://localhost:8000/fetch"
        # Mock the response to return data that will cause a non-ValidationError
        # when we force an exception during model_validate
        mock_httpx_client.set_response(
            fetch_url,
            {
                "normalized_contents": [
                    {
                        "markdown": "# Test",
                        "source_id": "note_1",
                        "structural_hints": {
                            "has_headings": False,
                            "has_lists": False,
                            "has_tables": False,
                            "natural_boundaries": (),
                        },
                        "normalizer_version": "1.0.0",
                    }
                ]
            },
        )

        from unittest.mock import patch

        # Patch NormalizedContent.model_validate to raise a non-ValidationError
        # This verifies that non-ValidationError exceptions are not caught
        with patch.object(NormalizedContent, 'model_validate') as mock_validate:
            mock_validate.side_effect = RuntimeError("Unexpected runtime error")

            # RuntimeError should propagate, not be caught as a validation failure
            with pytest.raises(RuntimeError, match="Unexpected runtime error"):
                list(adapter.fetch("source_ref"))


class TestRemoteAdapterContextManager:
    """Tests for RemoteAdapter context manager protocol."""

    def test_context_manager_enter(self):
        """__enter__ returns self."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test",
        )
        result = adapter.__enter__()
        assert result is adapter

    def test_context_manager_exit(self):
        """__exit__ closes the client."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test",
        )
        # Verify client is open
        assert hasattr(adapter, "_client")
        # Call __exit__
        result = adapter.__exit__(None, None, None)
        assert result is False

    def test_context_manager_with_statement(self, mock_httpx_client):
        """RemoteAdapter can be used in with statement."""
        with RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test",
        ) as adapter:
            assert adapter is not None
            assert isinstance(adapter, RemoteAdapter)

    def test_del_closes_client(self):
        """__del__ closes the client safely."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test",
        )
        # Verify client exists
        assert hasattr(adapter, "_client")
        # Call __del__
        adapter.__del__()
        # Should not raise


class TestRemoteAdapterRetry:
    """Tests for RemoteAdapter retry behavior with transient errors."""

    @pytest.mark.parametrize("status_code", [502, 503, 504])
    def test_fetch_retries_on_transient_errors(self, status_code, mock_httpx_client, monkeypatch):
        """fetch() retries on transient HTTP errors (502, 503, 504) and succeeds on retry."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test_adapter",
        )

        call_count = 0

        def tracking_post(url, json=None, headers=None, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call returns transient error
                return MockResponse({"error": "Transient error"}, status_code=status_code, url=url)
            else:
                # Second call succeeds
                return MockResponse(
                    {"normalized_contents": [
                        {
                            "markdown": "# Test",
                            "source_id": "test",
                            "structural_hints": {
                                "has_headings": True,
                                "has_lists": False,
                                "has_tables": False,
                                "natural_boundaries": (),
                            },
                            "normalizer_version": "1.0.0",
                        }
                    ]},
                    status_code=200,
                    url=url,
                )

        mock_httpx_client.post = tracking_post
        monkeypatch.setattr("context_library.adapters.remote.time.sleep", lambda x: None)

        results = list(adapter.fetch("source_ref"))
        assert len(results) == 1
        assert call_count == 2  # Should have retried once

    def test_fetch_raises_after_max_retries_exceeded(self, mock_httpx_client, monkeypatch):
        """fetch() raises HTTPStatusError after max retries exceeded for transient errors."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test_adapter",
        )

        def tracking_post(url, json=None, headers=None, timeout=None):
            # Always return 502
            return MockResponse({"error": "Bad Gateway"}, status_code=502, url=url)

        mock_httpx_client.post = tracking_post
        monkeypatch.setattr("context_library.adapters.remote.time.sleep", lambda x: None)

        with pytest.raises(httpx.HTTPStatusError):
            list(adapter.fetch("source_ref"))

    def test_fetch_does_not_retry_non_transient_errors(self, mock_httpx_client, monkeypatch):
        """fetch() does not retry on non-transient errors (4xx)."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test_adapter",
        )

        call_count = 0

        def tracking_post(url, json=None, headers=None, timeout=None):
            nonlocal call_count
            call_count += 1
            return MockResponse({"error": "Unauthorized"}, status_code=401, url=url)

        mock_httpx_client.post = tracking_post
        monkeypatch.setattr("context_library.adapters.remote.time.sleep", lambda x: None)

        with pytest.raises(httpx.HTTPStatusError):
            list(adapter.fetch("source_ref"))

        assert call_count == 1  # Should not retry


class TestRemoteAdapterIntegration:
    """Integration tests for RemoteAdapter."""

    def test_multiple_service_urls(self, mock_httpx_client):
        """RemoteAdapter works with different service URLs."""
        adapter1 = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="adapter1",
        )
        adapter2 = RemoteAdapter(
            service_url="http://localhost:9000",
            domain=Domain.NOTES,
            adapter_id="adapter2",
        )

        # Configure responses for both URLs
        mock_httpx_client.set_response(
            "http://localhost:8000/fetch",
            {"normalized_contents": [{"markdown": "A", "source_id": "a", "structural_hints": {"has_headings": False, "has_lists": False, "has_tables": False, "natural_boundaries": ()}, "normalizer_version": "1.0.0"}]},
        )
        mock_httpx_client.set_response(
            "http://localhost:9000/fetch",
            {"normalized_contents": [{"markdown": "B", "source_id": "b", "structural_hints": {"has_headings": False, "has_lists": False, "has_tables": False, "natural_boundaries": ()}, "normalizer_version": "1.0.0"}]},
        )

        results1 = list(adapter1.fetch("ref1"))
        results2 = list(adapter2.fetch("ref2"))

        assert len(results1) == 1
        assert len(results2) == 1
        assert results1[0].markdown == "A"
        assert results2[0].markdown == "B"

    def test_structural_hints_with_extra_metadata(self, mock_httpx_client):
        """fetch() preserves extra_metadata in StructuralHints."""
        adapter = RemoteAdapter(
            service_url="http://localhost:8000",
            domain=Domain.NOTES,
            adapter_id="test",
        )

        fetch_url = "http://localhost:8000/fetch"
        mock_httpx_client.set_response(
            fetch_url,
            {
                "normalized_contents": [
                    {
                        "markdown": "# Test",
                        "source_id": "test",
                        "structural_hints": {
                            "has_headings": True,
                            "has_lists": False,
                            "has_tables": False,
                            "natural_boundaries": (),
                            "file_path": "/path/to/file.md",
                            "modified_at": "2025-01-01T12:00:00Z",
                            "file_size_bytes": 1024,
                            "extra_metadata": {"custom_field": "custom_value"},
                        },
                        "normalizer_version": "1.0.0",
                    }
                ]
            },
        )

        results = list(adapter.fetch("source_ref"))
        assert len(results) == 1
        hints = results[0].structural_hints
        assert hints.file_path == "/path/to/file.md"
        assert hints.modified_at == "2025-01-01T12:00:00Z"
        assert hints.file_size_bytes == 1024
        assert hints.extra_metadata == {"custom_field": "custom_value"}


class TestRemoteAdapterImportError:
    """Tests for RemoteAdapter import error handling."""

    def test_init_import_error_includes_transitive_dependency_diagnostics(self, monkeypatch):
        """RemoteAdapter.__init__ includes diagnostic info when httpx import fails due to transitive dependency."""
        # Simulate transitive dependency failure by setting _IMPORT_ERROR
        import context_library.adapters.remote as remote_module

        original_has_httpx = remote_module.HAS_HTTPX
        original_import_error = remote_module._IMPORT_ERROR

        try:
            # Simulate httpx import failure with a transitive dependency error
            remote_module.HAS_HTTPX = False
            remote_module._IMPORT_ERROR = "No module named 'h11'"

            with pytest.raises(ImportError) as exc_info:
                RemoteAdapter(
                    service_url="http://localhost:8000",
                    domain=Domain.NOTES,
                    adapter_id="test",
                )

            error_msg = str(exc_info.value)
            # Verify diagnostic section is present
            assert "Diagnostics:" in error_msg
            assert "h11" in error_msg
            # Verify original installation instructions are still present
            assert "pip install" in error_msg
        finally:
            # Restore original values
            remote_module.HAS_HTTPX = original_has_httpx
            remote_module._IMPORT_ERROR = original_import_error

    def test_init_raises_import_error_when_httpx_not_available(self, monkeypatch):
        """RemoteAdapter.__init__ raises ImportError when httpx is not installed."""
        import context_library.adapters.remote as remote_module

        original_has_httpx = remote_module.HAS_HTTPX
        original_import_error = remote_module._IMPORT_ERROR

        try:
            # Simulate httpx not being installed
            remote_module.HAS_HTTPX = False
            remote_module._IMPORT_ERROR = None

            with pytest.raises(ImportError) as exc_info:
                RemoteAdapter(
                    service_url="http://localhost:8000",
                    domain=Domain.NOTES,
                    adapter_id="test",
                )

            error_msg = str(exc_info.value)
            # Verify installation instructions are present
            assert "pip install context-library[remote-adapter]" in error_msg
            # Verify error message indicates httpx is required
            assert "httpx is required" in error_msg
        finally:
            # Restore original values
            remote_module.HAS_HTTPX = original_has_httpx
            remote_module._IMPORT_ERROR = original_import_error
