"""Tests for FilesystemHelperAdapter — streaming NDJSON fetch with multi-page drain,
tombstone deletion, opaque-cursor passthrough, and commit-ack."""

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


def _make_tombstone_line(source_id: str = "gone.md", modified_at: str | None = None) -> str:
    return json.dumps({"op": "delete", "source_id": source_id, "modified_at": modified_at})


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


class _StreamRecorder:
    """Replays a queue of NDJSON page-line-lists across successive stream() calls.

    Each call to the recorder pops the next list of lines and records the request
    (params, body, headers). This lets tests drive the multi-page drain loop, where
    fetch() opens one stream per page.
    """

    def __init__(self, pages: list[list[str]]):
        self._pages = list(pages)
        self.calls: list[dict] = []

    def __call__(self, method, url, params=None, json=None, headers=None):
        self.calls.append(
            {"method": method, "url": url, "params": params, "json": json, "headers": headers}
        )
        lines = self._pages.pop(0) if self._pages else [_make_meta_line()]
        return _mock_stream(lines)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestFilesystemHelperAdapterConstruction:
    def test_requires_api_key(self):
        with pytest.raises(ValueError, match="api_key is required"):
            FilesystemHelperAdapter(api_url="http://host:8000", api_key="")

    def test_rejects_invalid_max_pages(self):
        with pytest.raises(ValueError, match="max_pages must be >= 1"):
            FilesystemHelperAdapter(api_url="http://host:8000", api_key="k", max_pages=0)

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

    def test_base_url_has_no_suffix(self):
        adapter = FilesystemHelperAdapter(api_url="http://host:8000", api_key="secret")
        assert adapter._base_url == "http://host:8000"

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
# fetch() — single-page NDJSON streaming
# ---------------------------------------------------------------------------

class TestFilesystemHelperAdapterFetch:
    def _make_adapter(self) -> FilesystemHelperAdapter:
        return FilesystemHelperAdapter(api_url="http://host:8000", api_key="secret-key")

    def test_fetch_yields_normalized_content(self):
        adapter = self._make_adapter()
        rec = _StreamRecorder([[_make_content_line("a.md", "# A"), _make_meta_line()]])
        with patch.object(adapter._client, "stream", side_effect=rec):
            results = list(adapter.fetch(""))

        assert len(results) == 1
        assert isinstance(results[0], NormalizedContent)
        assert results[0].source_id == "a.md"
        assert results[0].markdown == "# A"

    def test_fetch_yields_multiple_items(self):
        adapter = self._make_adapter()
        rec = _StreamRecorder(
            [[_make_content_line("a.md", "A"), _make_content_line("b.md", "B"), _make_meta_line()]]
        )
        with patch.object(adapter._client, "stream", side_effect=rec):
            results = list(adapter.fetch(""))

        assert [r.source_id for r in results] == ["a.md", "b.md"]

    def test_fetch_empty_page_yields_nothing(self):
        adapter = self._make_adapter()
        rec = _StreamRecorder([[_make_meta_line(has_more=False)]])
        with patch.object(adapter._client, "stream", side_effect=rec):
            results = list(adapter.fetch(""))
        assert results == []

    def test_fetch_stops_at_meta_line(self):
        """Content after the meta line in the same page is never yielded."""
        adapter = self._make_adapter()
        rec = _StreamRecorder(
            [[_make_content_line("a.md"), _make_meta_line(has_more=False), _make_content_line("b.md")]]
        )
        with patch.object(adapter._client, "stream", side_effect=rec):
            results = list(adapter.fetch(""))
        assert [r.source_id for r in results] == ["a.md"]

    def test_fetch_skips_blank_lines(self):
        adapter = self._make_adapter()
        rec = _StreamRecorder([["", _make_content_line("a.md"), "   ", _make_meta_line()]])
        with patch.object(adapter._client, "stream", side_effect=rec):
            results = list(adapter.fetch(""))
        assert len(results) == 1

    def test_fetch_sends_post_to_filesystem_fetch_endpoint(self):
        adapter = self._make_adapter()
        rec = _StreamRecorder([[_make_meta_line()]])
        with patch.object(adapter._client, "stream", side_effect=rec):
            list(adapter.fetch("my-cursor"))
        assert rec.calls[0]["method"] == "POST"
        assert rec.calls[0]["url"].endswith("/filesystem/fetch")

    def test_fetch_sends_source_ref_in_body(self):
        adapter = self._make_adapter()
        rec = _StreamRecorder([[_make_meta_line()]])
        with patch.object(adapter._client, "stream", side_effect=rec):
            list(adapter.fetch("42"))
        assert rec.calls[0]["json"]["source_ref"] == "42"

    def test_fetch_sends_stream_true_in_body(self):
        adapter = self._make_adapter()
        rec = _StreamRecorder([[_make_meta_line()]])
        with patch.object(adapter._client, "stream", side_effect=rec):
            list(adapter.fetch(""))
        assert rec.calls[0]["json"].get("stream") is True

    def test_fetch_sends_bearer_token(self):
        adapter = self._make_adapter()
        rec = _StreamRecorder([[_make_meta_line()]])
        with patch.object(adapter._client, "stream", side_effect=rec):
            list(adapter.fetch(""))
        assert rec.calls[0]["headers"].get("Authorization") == "Bearer secret-key"

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
        rec = _StreamRecorder([["{not valid json"]])
        with patch.object(adapter._client, "stream", side_effect=rec):
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
        rec = _StreamRecorder([[bad_line, _make_meta_line()]])
        from pydantic import ValidationError
        with patch.object(adapter._client, "stream", side_effect=rec):
            with pytest.raises(ValidationError):
                list(adapter.fetch(""))

    def test_fetch_includes_extensions_when_configured(self):
        adapter = FilesystemHelperAdapter(
            api_url="http://host:8000", api_key="secret", extensions=[".md"]
        )
        rec = _StreamRecorder([[_make_meta_line()]])
        with patch.object(adapter._client, "stream", side_effect=rec):
            list(adapter.fetch(""))
        assert rec.calls[0]["json"].get("extensions") == [".md"]

    def test_fetch_synthesizes_extra_metadata(self):
        """Content with extra_metadata=None gets synthesized DocumentMetadata."""
        adapter = self._make_adapter()
        rec = _StreamRecorder([[_make_content_line("notes/my-file.md"), _make_meta_line()]])
        with patch.object(adapter._client, "stream", side_effect=rec):
            results = list(adapter.fetch(""))
        meta = results[0].structural_hints.extra_metadata
        assert meta is not None
        assert meta["document_id"] == "notes/my-file.md"
        assert meta["title"] == "my file"
        assert meta["source_type"] == "filesystem"


# ---------------------------------------------------------------------------
# fetch() — multi-page drain
# ---------------------------------------------------------------------------

class TestFilesystemHelperAdapterDrain:
    def _make_adapter(self, **kw) -> FilesystemHelperAdapter:
        return FilesystemHelperAdapter(api_url="http://host:8000", api_key="k", **kw)

    def test_drains_all_pages_in_one_fetch(self):
        """has_more=True triggers immediate follow-up requests within one fetch()."""
        adapter = self._make_adapter()
        pages = [
            [_make_content_line("a.md"), _make_meta_line(has_more=True, next_cursor="1")],
            [_make_content_line("b.md"), _make_meta_line(has_more=True, next_cursor="2")],
            [_make_content_line("c.md"), _make_meta_line(has_more=False, next_cursor="3")],
        ]
        rec = _StreamRecorder(pages)
        with patch.object(adapter._client, "stream", side_effect=rec):
            results = list(adapter.fetch(""))

        assert [r.source_id for r in results] == ["a.md", "b.md", "c.md"]
        assert len(rec.calls) == 3
        # Cursor advanced and the final next_cursor persisted.
        assert adapter._cursor == "3"

    def test_drain_passes_next_cursor_back_verbatim(self):
        """The opaque next_cursor from each page is echoed in the next request body."""
        adapter = self._make_adapter()
        pages = [
            [_make_meta_line(has_more=True, next_cursor="100")],
            [_make_meta_line(has_more=True, next_cursor="200")],
            [_make_meta_line(has_more=False, next_cursor="300")],
        ]
        rec = _StreamRecorder(pages)
        with patch.object(adapter._client, "stream", side_effect=rec):
            list(adapter.fetch(""))

        sent_refs = [c["json"]["source_ref"] for c in rec.calls]
        # First request starts empty, then echoes each opaque token verbatim.
        assert sent_refs == ["", "100", "200"]

    def test_drain_budget_caps_run(self):
        """max_pages caps the drain and the run is not silently truncated."""
        adapter = self._make_adapter(max_pages=2)
        # Three pages available, but only 2 should be fetched.
        pages = [
            [_make_content_line("a.md"), _make_meta_line(has_more=True, next_cursor="1")],
            [_make_content_line("b.md"), _make_meta_line(has_more=True, next_cursor="2")],
            [_make_content_line("c.md"), _make_meta_line(has_more=False, next_cursor="3")],
        ]
        rec = _StreamRecorder(pages)
        with patch.object(adapter._client, "stream", side_effect=rec):
            with patch("context_library.adapters.filesystem_helper.logger") as mock_log:
                results = list(adapter.fetch(""))

        assert [r.source_id for r in results] == ["a.md", "b.md"]
        assert len(rec.calls) == 2
        # Cursor persisted at the capped page so the next fetch resumes from there.
        assert adapter._cursor == "2"
        # Capping is logged at WARNING (not silent).
        assert mock_log.warning.called
        assert any("drain budget" in str(c.args[0]) for c in mock_log.warning.call_args_list)

    def test_persisted_cursor_resumes_next_fetch(self):
        """A second fetch("") starts from the persisted cursor, not from empty."""
        adapter = self._make_adapter()
        first = _StreamRecorder([[_make_meta_line(has_more=False, next_cursor="55")]])
        with patch.object(adapter._client, "stream", side_effect=first):
            list(adapter.fetch(""))
        assert adapter._cursor == "55"

        second = _StreamRecorder([[_make_meta_line(has_more=False, next_cursor="56")]])
        with patch.object(adapter._client, "stream", side_effect=second):
            list(adapter.fetch(""))
        assert second.calls[0]["json"]["source_ref"] == "55"

    def test_explicit_source_ref_overrides_persisted_cursor(self):
        """A non-empty source_ref (forced replay) overrides the persisted cursor."""
        adapter = self._make_adapter()
        adapter._cursor = "99"
        rec = _StreamRecorder([[_make_meta_line(has_more=False, next_cursor="100")]])
        with patch.object(adapter._client, "stream", side_effect=rec):
            list(adapter.fetch("7"))
        assert rec.calls[0]["json"]["source_ref"] == "7"

    def test_stream_without_meta_line_stops_drain(self):
        """A page that ends without a meta line stops the drain (no infinite loop)."""
        adapter = self._make_adapter()
        rec = _StreamRecorder([[_make_content_line("a.md")]])  # no meta line
        with patch.object(adapter._client, "stream", side_effect=rec):
            results = list(adapter.fetch(""))
        assert [r.source_id for r in results] == ["a.md"]
        assert len(rec.calls) == 1


# ---------------------------------------------------------------------------
# fetch() — tombstones
# ---------------------------------------------------------------------------

class TestFilesystemHelperAdapterTombstones:
    def _make_adapter(self) -> FilesystemHelperAdapter:
        return FilesystemHelperAdapter(api_url="http://host:8000", api_key="k")

    def test_tombstone_yields_empty_markdown_content(self):
        adapter = self._make_adapter()
        rec = _StreamRecorder([[_make_tombstone_line("gone.md", "2026-01-01T00:00:00+00:00"), _make_meta_line()]])
        with patch.object(adapter._client, "stream", side_effect=rec):
            results = list(adapter.fetch(""))

        assert len(results) == 1
        tomb = results[0]
        assert tomb.source_id == "gone.md"
        assert tomb.markdown == ""
        # extra_metadata is synthesized so the chunker's guard is satisfied.
        assert tomb.structural_hints.extra_metadata is not None
        assert tomb.structural_hints.extra_metadata["document_id"] == "gone.md"
        assert tomb.structural_hints.modified_at == "2026-01-01T00:00:00+00:00"

    def test_tombstone_interleaved_with_content(self):
        adapter = self._make_adapter()
        rec = _StreamRecorder([[
            _make_content_line("keep.md", "# Keep"),
            _make_tombstone_line("gone.md"),
            _make_meta_line(),
        ]])
        with patch.object(adapter._client, "stream", side_effect=rec):
            results = list(adapter.fetch(""))

        assert [r.source_id for r in results] == ["keep.md", "gone.md"]
        assert results[0].markdown == "# Keep"
        assert results[1].markdown == ""

    def test_tombstone_missing_source_id_skipped(self):
        adapter = self._make_adapter()
        bad = json.dumps({"op": "delete", "modified_at": None})
        rec = _StreamRecorder([[bad, _make_content_line("ok.md"), _make_meta_line()]])
        with patch.object(adapter._client, "stream", side_effect=rec):
            results = list(adapter.fetch(""))
        assert [r.source_id for r in results] == ["ok.md"]


# ---------------------------------------------------------------------------
# fetch() — commit-ack request shape
# ---------------------------------------------------------------------------

class TestFilesystemHelperAdapterAckRequest:
    def _make_adapter(self) -> FilesystemHelperAdapter:
        return FilesystemHelperAdapter(api_url="http://host:8000", api_key="k")

    def test_fetch_sends_ack_true_query_param_by_default(self):
        adapter = self._make_adapter()
        rec = _StreamRecorder([[_make_meta_line(has_more=False, next_cursor="9")]])
        with patch.object(adapter._client, "stream", side_effect=rec):
            list(adapter.fetch(""))
        assert rec.calls[0]["params"] == {"ack": "true"}

    def test_fetch_stages_pending_ack_cursor(self):
        adapter = self._make_adapter()
        rec = _StreamRecorder([[_make_meta_line(has_more=False, next_cursor="77")]])
        with patch.object(adapter._client, "stream", side_effect=rec):
            list(adapter.fetch(""))
        assert adapter._pending_ack_cursor == "77"

    def test_fetch_ack_disabled_via_extra_body(self):
        adapter = self._make_adapter()
        rec = _StreamRecorder([[_make_meta_line(has_more=False, next_cursor="9")]])
        with patch.object(adapter._client, "stream", side_effect=rec):
            list(adapter.fetch("", extra_body={"ack": False}))
        assert rec.calls[0]["params"] is None
        assert adapter._pending_ack_cursor is None

    def test_ack_control_flag_not_leaked_into_body(self):
        adapter = self._make_adapter()
        rec = _StreamRecorder([[_make_meta_line()]])
        with patch.object(adapter._client, "stream", side_effect=rec):
            list(adapter.fetch("", extra_body={"ack": True, "foo": "bar"}))
        assert "ack" not in rec.calls[0]["json"]
        assert rec.calls[0]["json"].get("foo") == "bar"


# ---------------------------------------------------------------------------
# ack() — POSTs to the helper ack endpoint
# ---------------------------------------------------------------------------

class TestFilesystemHelperAdapterAck:
    def _make_adapter(self) -> FilesystemHelperAdapter:
        return FilesystemHelperAdapter(api_url="http://host:8000", api_key="secret-key")

    def test_ack_posts_to_collectors_filesystem_ack(self):
        adapter = self._make_adapter()
        adapter._pending_ack_cursor = "42"
        mock_resp = MagicMock()
        with patch.object(adapter._client, "post", return_value=mock_resp) as mock_post:
            adapter.ack()

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://host:8000/collectors/filesystem/ack"
        assert kwargs["json"] == {"cursor": "42"}
        assert kwargs["headers"]["Authorization"] == "Bearer secret-key"
        mock_resp.raise_for_status.assert_called_once()

    def test_ack_clears_pending_cursor_on_success(self):
        adapter = self._make_adapter()
        adapter._pending_ack_cursor = "42"
        with patch.object(adapter._client, "post", return_value=MagicMock()):
            adapter.ack()
        assert adapter._pending_ack_cursor is None

    def test_ack_noop_when_no_pending_cursor(self):
        adapter = self._make_adapter()
        adapter._pending_ack_cursor = None
        with patch.object(adapter._client, "post") as mock_post:
            adapter.ack()
        mock_post.assert_not_called()

    def test_ack_propagates_http_error(self):
        adapter = self._make_adapter()
        adapter._pending_ack_cursor = "42"
        import httpx
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "boom", request=MagicMock(), response=MagicMock(status_code=500, text="err")
        )
        with patch.object(adapter._client, "post", return_value=mock_resp):
            with pytest.raises(httpx.HTTPStatusError):
                adapter.ack()
        # Pending cursor is NOT cleared on failure, so a later ack can retry.
        assert adapter._pending_ack_cursor == "42"

    def test_fetch_then_ack_commits_drained_cursor(self):
        """End-to-end: fetch drains pages, ack commits the final cursor."""
        adapter = self._make_adapter()
        pages = [
            [_make_content_line("a.md"), _make_meta_line(has_more=True, next_cursor="1")],
            [_make_content_line("b.md"), _make_meta_line(has_more=False, next_cursor="2")],
        ]
        rec = _StreamRecorder(pages)
        with patch.object(adapter._client, "stream", side_effect=rec):
            list(adapter.fetch(""))
        assert adapter._pending_ack_cursor == "2"

        with patch.object(adapter._client, "post", return_value=MagicMock()) as mock_post:
            adapter.ack()
        assert mock_post.call_args.kwargs["json"] == {"cursor": "2"}


# ---------------------------------------------------------------------------
# _collector_name property
# ---------------------------------------------------------------------------

class TestFilesystemHelperAdapterCollectorName:
    def test_collector_name_is_filesystem(self):
        adapter = FilesystemHelperAdapter(api_url="http://host:8000", api_key="secret")
        assert adapter._collector_name == "filesystem"
