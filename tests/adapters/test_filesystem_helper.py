"""Tests for FilesystemHelperAdapter — streaming NDJSON fetch."""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from context_library.adapters.filesystem_helper import FilesystemHelperAdapter
from context_library.storage.models import Domain, NormalizedContent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_content_line(source_id: str = "note.md", markdown: str = "# Note\nBody") -> str:
    """Return a single NDJSON content line in NormalizedContent wire format."""
    obj = {
        "markdown": markdown,
        "source_id": source_id,
        "structural_hints": {
            "has_headings": True,
            "has_lists": False,
            "has_tables": False,
            "natural_boundaries": [],
            "file_path": None,
            "modified_at": "2026-03-15T10:00:00+00:00",
            "file_size_bytes": len(markdown.encode()),
            "extra_metadata": None,
        },
        "normalizer_version": "1.0.0",
    }
    return json.dumps(obj)


def _make_meta_line(has_more: bool = False, next_cursor: str | None = None) -> str:
    return json.dumps({"has_more": has_more, "next_cursor": next_cursor})


@contextmanager
def _mock_stream(lines: list[str], status_code: int = 200):
    """Context manager that mimics httpx response.stream() with NDJSON lines."""
    class FakeResponse:
        def raise_for_status(self):
            if status_code >= 400:
                import httpx
                raise httpx.HTTPStatusError(
                    f"HTTP {status_code}",
                    request=MagicMock(),
                    response=MagicMock(status_code=status_code, text="error"),
                )

        def iter_lines(self):
            yield from lines

    yield FakeResponse()


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestFilesystemHelperAdapterConstruction:
    def test_requires_api_key(self):
        with pytest.raises(ValueError, match="api_key is required"):
            FilesystemHelperAdapter(api_url="http://host:8000", api_key="")

    def test_adapter_id_uses_directory_id(self):
        adapter = FilesystemHelperAdapter(
            api_url="http://host:8000", api_key="secret", directory_id="vault"
        )
        assert adapter.adapter_id == "filesystem_helper:vault"

    def test_adapter_id_default_directory_id(self):
        adapter = FilesystemHelperAdapter(api_url="http://host:8000", api_key="secret")
        assert adapter.adapter_id == "filesystem_helper:default"

    def test_domain_is_documents(self):
        adapter = FilesystemHelperAdapter(api_url="http://host:8000", api_key="secret")
        assert adapter.domain == Domain.DOCUMENTS

    def test_normalizer_version(self):
        adapter = FilesystemHelperAdapter(api_url="http://host:8000", api_key="secret")
        assert adapter.normalizer_version == "1.0.0"

    def test_service_url_has_filesystem_suffix(self):
        adapter = FilesystemHelperAdapter(api_url="http://host:8000", api_key="secret")
        assert adapter._service_url == "http://host:8000/filesystem"

    def test_trailing_slash_stripped_from_api_url(self):
        adapter = FilesystemHelperAdapter(api_url="http://host:8000/", api_key="secret")
        assert adapter._service_url == "http://host:8000/filesystem"

    def test_stream_always_in_fetch_params(self):
        adapter = FilesystemHelperAdapter(api_url="http://host:8000", api_key="secret")
        assert adapter._fetch_params.get("stream") is True

    def test_optional_extensions_in_fetch_params(self):
        adapter = FilesystemHelperAdapter(
            api_url="http://host:8000", api_key="secret", extensions=[".md", ".txt"]
        )
        assert adapter._fetch_params["extensions"] == [".md", ".txt"]

    def test_none_extensions_not_in_fetch_params(self):
        adapter = FilesystemHelperAdapter(api_url="http://host:8000", api_key="secret")
        assert "extensions" not in adapter._fetch_params

    def test_optional_max_size_mb_in_fetch_params(self):
        adapter = FilesystemHelperAdapter(
            api_url="http://host:8000", api_key="secret", max_size_mb=5.0
        )
        assert adapter._fetch_params["max_size_mb"] == 5.0

    def test_custom_page_size_in_fetch_params(self):
        adapter = FilesystemHelperAdapter(
            api_url="http://host:8000", api_key="secret", page_size=10
        )
        assert adapter._fetch_params["page_size"] == 10

    def test_default_page_size_not_in_fetch_params(self):
        """Default page_size=50 is omitted to keep the body minimal."""
        adapter = FilesystemHelperAdapter(api_url="http://host:8000", api_key="secret")
        assert "page_size" not in adapter._fetch_params


# ---------------------------------------------------------------------------
# fetch() — NDJSON streaming
# ---------------------------------------------------------------------------

class TestFilesystemHelperAdapterFetch:
    def _make_adapter(self) -> FilesystemHelperAdapter:
        return FilesystemHelperAdapter(
            api_url="http://host:8000", api_key="secret-key"
        )

    def test_fetch_yields_normalized_content(self):
        adapter = self._make_adapter()
        lines = [_make_content_line("a.md", "# A"), _make_meta_line()]

        with patch.object(adapter._client, "stream", return_value=_mock_stream(lines)):
            results = list(adapter.fetch(""))

        assert len(results) == 1
        assert isinstance(results[0], NormalizedContent)
        assert results[0].source_id == "a.md"
        assert results[0].markdown == "# A"

    def test_fetch_yields_multiple_items(self):
        adapter = self._make_adapter()
        lines = [
            _make_content_line("a.md", "A"),
            _make_content_line("b.md", "B"),
            _make_meta_line(),
        ]

        with patch.object(adapter._client, "stream", return_value=_mock_stream(lines)):
            results = list(adapter.fetch(""))

        assert len(results) == 2
        assert results[0].source_id == "a.md"
        assert results[1].source_id == "b.md"

    def test_fetch_empty_page_yields_nothing(self):
        adapter = self._make_adapter()
        lines = [_make_meta_line(has_more=False)]

        with patch.object(adapter._client, "stream", return_value=_mock_stream(lines)):
            results = list(adapter.fetch(""))

        assert results == []

    def test_fetch_stops_at_meta_line(self):
        """Content after the meta line is never yielded."""
        adapter = self._make_adapter()
        lines = [
            _make_content_line("a.md"),
            _make_meta_line(has_more=False),
            _make_content_line("b.md"),  # should never be yielded
        ]

        with patch.object(adapter._client, "stream", return_value=_mock_stream(lines)):
            results = list(adapter.fetch(""))

        assert len(results) == 1
        assert results[0].source_id == "a.md"

    def test_fetch_skips_blank_lines(self):
        adapter = self._make_adapter()
        lines = ["", _make_content_line("a.md"), "   ", _make_meta_line()]

        with patch.object(adapter._client, "stream", return_value=_mock_stream(lines)):
            results = list(adapter.fetch(""))

        assert len(results) == 1

    def test_fetch_sends_post_to_filesystem_fetch_endpoint(self):
        adapter = self._make_adapter()
        lines = [_make_meta_line()]

        captured = {}

        @contextmanager
        def capture_stream(method, url, json=None, headers=None):
            captured["method"] = method
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            with _mock_stream(lines) as resp:
                yield resp

        with patch.object(adapter._client, "stream", side_effect=capture_stream):
            list(adapter.fetch("my-cursor"))

        assert captured["method"] == "POST"
        assert captured["url"].endswith("/filesystem/fetch")

    def test_fetch_sends_source_ref_in_body(self):
        adapter = self._make_adapter()
        lines = [_make_meta_line()]

        captured_json = {}

        @contextmanager
        def capture_stream(method, url, json=None, headers=None):
            captured_json.update(json or {})
            with _mock_stream(lines) as resp:
                yield resp

        with patch.object(adapter._client, "stream", side_effect=capture_stream):
            list(adapter.fetch("2026-03-15T10:00:00+00:00"))

        assert captured_json["source_ref"] == "2026-03-15T10:00:00+00:00"

    def test_fetch_sends_stream_true_in_body(self):
        adapter = self._make_adapter()
        lines = [_make_meta_line()]

        captured_json = {}

        @contextmanager
        def capture_stream(method, url, json=None, headers=None):
            captured_json.update(json or {})
            with _mock_stream(lines) as resp:
                yield resp

        with patch.object(adapter._client, "stream", side_effect=capture_stream):
            list(adapter.fetch(""))

        assert captured_json.get("stream") is True

    def test_fetch_sends_bearer_token(self):
        adapter = self._make_adapter()
        lines = [_make_meta_line()]

        captured_headers = {}

        @contextmanager
        def capture_stream(method, url, json=None, headers=None):
            captured_headers.update(headers or {})
            with _mock_stream(lines) as resp:
                yield resp

        with patch.object(adapter._client, "stream", side_effect=capture_stream):
            list(adapter.fetch(""))

        assert captured_headers.get("Authorization") == "Bearer secret-key"

    def test_fetch_raises_on_http_error(self):
        adapter = self._make_adapter()

        with patch.object(
            adapter._client, "stream", return_value=_mock_stream([], status_code=401)
        ):
            import httpx
            with pytest.raises(httpx.HTTPStatusError):
                list(adapter.fetch(""))

    def test_fetch_raises_on_malformed_json(self):
        adapter = self._make_adapter()
        lines = ["{not valid json"]

        with patch.object(adapter._client, "stream", return_value=_mock_stream(lines)):
            with pytest.raises(ValueError):
                list(adapter.fetch(""))

    def test_fetch_raises_on_invalid_normalized_content(self):
        """Content line missing required 'markdown' field raises ValidationError."""
        adapter = self._make_adapter()
        bad_line = json.dumps({
            "source_id": "note.md",
            "structural_hints": {
                "has_headings": False, "has_lists": False, "has_tables": False,
                "natural_boundaries": [],
            },
            "normalizer_version": "1.0.0",
        })
        lines = [bad_line, _make_meta_line()]

        from pydantic import ValidationError
        with patch.object(adapter._client, "stream", return_value=_mock_stream(lines)):
            with pytest.raises(ValidationError):
                list(adapter.fetch(""))

    def test_fetch_includes_extensions_when_configured(self):
        adapter = FilesystemHelperAdapter(
            api_url="http://host:8000", api_key="secret", extensions=[".md"]
        )
        lines = [_make_meta_line()]
        captured_json = {}

        @contextmanager
        def capture_stream(method, url, json=None, headers=None):
            captured_json.update(json or {})
            with _mock_stream(lines) as resp:
                yield resp

        with patch.object(adapter._client, "stream", side_effect=capture_stream):
            list(adapter.fetch(""))

        assert captured_json.get("extensions") == [".md"]

    def test_fetch_has_more_true_logs_debug(self, caplog):
        """has_more=True in the meta line is logged at DEBUG level."""
        import logging
        adapter = self._make_adapter()
        lines = [_make_meta_line(has_more=True, next_cursor="2026-03-15T11:00:00+00:00")]

        with patch.object(adapter._client, "stream", return_value=_mock_stream(lines)):
            with caplog.at_level(logging.DEBUG, logger="context_library.adapters.filesystem_helper"):
                list(adapter.fetch(""))

        assert any("has_more=True" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# _collector_name property
# ---------------------------------------------------------------------------

class TestFilesystemHelperAdapterCollectorName:
    def test_collector_name_is_filesystem(self):
        """Test that _collector_name returns the correct value for filesystem helper."""
        adapter = FilesystemHelperAdapter(
            api_url="http://host:8000", api_key="secret"
        )
        assert adapter._collector_name == "filesystem"
