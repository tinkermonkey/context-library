"""Tests for YouTubeWatchHistoryAdapter (helper-bridge implementation)."""

from unittest.mock import MagicMock, patch

import pytest
import httpx
from pydantic import ValidationError

from context_library.adapters.youtube_watch_history import (
    YouTubeWatchHistoryAdapter,
    _build_watch_markdown,
)
from context_library.adapters.base import ResetResult
from context_library.storage.models import Domain, EventMetadata, PollStrategy


# ── Fixtures ─────────────────────────────────────────────────────────────────

VIDEO_ITEM = {
    "video_id": "dQw4w9WgXcQ",
    "title": "Some Great Tutorial",
    "channel": "Example Channel",
    "channel_id": "UCxxxxxxxxxx",
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "watched_at": "2024-01-15T14:30:00+00:00",
    "duration": 213,
    "upload_date": "20240115",
    "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
}

DELETED_VIDEO_ITEM = {
    "video_id": "XXXXXXXXXXX",
    "title": "Deleted Video",
    "channel": None,
    "channel_id": None,
    "url": "https://www.youtube.com/watch?v=XXXXXXXXXXX",
    "watched_at": "2024-01-13T09:00:00+00:00",
    "duration": None,
    "upload_date": None,
    "thumbnail": None,
}


def _make_mock_response(data, status_code: int = 200):
    """Return a mock httpx response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = data
    if status_code >= 400:
        import httpx
        mock.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=MagicMock(),
            response=MagicMock(status_code=status_code, text="error"),
        )
    else:
        mock.raise_for_status.return_value = None
    return mock


def _make_adapter(**kwargs) -> YouTubeWatchHistoryAdapter:
    """Create adapter with mock httpx.Client so no real HTTP is made."""
    defaults = {"api_url": "http://localhost:7123", "api_key": "test-key"}
    defaults.update(kwargs)
    with patch("httpx.Client"):
        adapter = YouTubeWatchHistoryAdapter(**defaults)
    return adapter


# ── Initialization tests ──────────────────────────────────────────────────────

class TestYouTubeWatchHistoryAdapterInitialization:
    def test_init_stores_api_url(self):
        adapter = _make_adapter(api_url="http://192.168.1.50:7123")
        assert adapter._service_url == "http://192.168.1.50:7123"

    def test_init_strips_trailing_slash(self):
        adapter = _make_adapter(api_url="http://192.168.1.50:7123/")
        assert adapter._service_url == "http://192.168.1.50:7123"

    def test_init_default_account_id(self):
        adapter = _make_adapter()
        assert adapter._account_id == "default"

    def test_init_custom_account_id(self):
        adapter = _make_adapter(account_id="personal")
        assert adapter._account_id == "personal"

    def test_init_requires_api_key(self):
        with patch("httpx.Client"):
            with pytest.raises(ValueError, match="api_key is required"):
                YouTubeWatchHistoryAdapter(api_url="http://localhost:7123", api_key="")

    def test_init_raises_without_httpx(self):
        import context_library.adapters.youtube_watch_history as mod
        original = mod.HAS_HTTPX
        try:
            mod.HAS_HTTPX = False
            with pytest.raises(ImportError, match="httpx is required"):
                YouTubeWatchHistoryAdapter(api_url="http://localhost:7123", api_key="key")
        finally:
            mod.HAS_HTTPX = original

    def test_background_poll_flag(self):
        adapter = _make_adapter()
        assert adapter.background_poll is True


# ── Property tests ────────────────────────────────────────────────────────────

class TestYouTubeWatchHistoryAdapterProperties:
    def test_adapter_id_default(self):
        adapter = _make_adapter()
        assert adapter.adapter_id == "youtube_watch_history:default"

    def test_adapter_id_custom_account(self):
        adapter = _make_adapter(account_id="work")
        assert adapter.adapter_id == "youtube_watch_history:work"

    def test_adapter_id_deterministic(self):
        a1 = _make_adapter(api_url="http://a:7123", account_id="x")
        a2 = _make_adapter(api_url="http://b:7123", account_id="x")
        assert a1.adapter_id == a2.adapter_id

    def test_domain(self):
        adapter = _make_adapter()
        assert adapter.domain == Domain.EVENTS

    def test_poll_strategy(self):
        adapter = _make_adapter()
        assert adapter.poll_strategy == PollStrategy.PULL

    def test_normalizer_version(self):
        adapter = _make_adapter()
        assert adapter.normalizer_version is not None


# ── Fetch tests ───────────────────────────────────────────────────────────────

class TestYouTubeWatchHistoryAdapterFetch:
    def _adapter_with_response(self, data, status_code: int = 200) -> YouTubeWatchHistoryAdapter:
        adapter = _make_adapter()
        adapter._client.get.return_value = _make_mock_response(data, status_code)
        return adapter

    def test_fetch_single_video(self):
        adapter = self._adapter_with_response([VIDEO_ITEM])
        results = list(adapter.fetch(""))
        assert len(results) == 1

    def test_fetch_sends_auth_header(self):
        adapter = _make_adapter(api_key="my-secret")
        adapter._client.get.return_value = _make_mock_response([])
        list(adapter.fetch(""))
        call_kwargs = adapter._client.get.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert headers.get("Authorization") == "Bearer my-secret"

    def test_fetch_sends_since_param(self):
        adapter = _make_adapter()
        adapter._client.get.return_value = _make_mock_response([])
        list(adapter.fetch("2024-01-15T00:00:00+00:00"))
        call_kwargs = adapter._client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
        assert params.get("since") == "2024-01-15T00:00:00+00:00"

    def test_fetch_no_since_when_empty_source_ref(self):
        adapter = _make_adapter()
        adapter._client.get.return_value = _make_mock_response([])
        list(adapter.fetch(""))
        call_kwargs = adapter._client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
        assert "since" not in params

    def test_fetch_calls_correct_endpoint(self):
        adapter = _make_adapter(api_url="http://helper:7123")
        adapter._client.get.return_value = _make_mock_response([])
        list(adapter.fetch(""))
        url_called = adapter._client.get.call_args[0][0]
        assert url_called == "http://helper:7123/youtube/history"

    def test_fetch_extracts_source_id(self):
        adapter = self._adapter_with_response([VIDEO_ITEM])
        results = list(adapter.fetch(""))
        assert results[0].source_id == "youtube/watch/dQw4w9WgXcQ/2024-01-15T14:30:00+00:00"

    def test_fetch_extracts_video_metadata(self):
        adapter = self._adapter_with_response([VIDEO_ITEM])
        results = list(adapter.fetch(""))
        meta = results[0].structural_hints.extra_metadata
        assert meta["video_id"] == "dQw4w9WgXcQ"
        assert meta["channel"] == "Example Channel"
        assert meta["channel_id"] == "UCxxxxxxxxxx"
        assert "youtube.com/watch" in meta["url"]

    def test_fetch_validates_event_metadata(self):
        adapter = self._adapter_with_response([VIDEO_ITEM])
        results = list(adapter.fetch(""))
        meta = results[0].structural_hints.extra_metadata
        event_meta = EventMetadata.model_validate(meta)
        assert event_meta.source_type == "youtube_watch_history"
        assert event_meta.start_date is not None
        assert "dQw4w9WgXcQ" in event_meta.event_id

    def test_fetch_handles_deleted_video(self):
        adapter = self._adapter_with_response([DELETED_VIDEO_ITEM])
        results = list(adapter.fetch(""))
        assert len(results) == 1
        meta = results[0].structural_hints.extra_metadata
        assert meta["channel"] is None
        assert meta["channel_id"] is None

    def test_fetch_markdown_contains_expected_fields(self):
        adapter = self._adapter_with_response([VIDEO_ITEM])
        results = list(adapter.fetch(""))
        md = results[0].markdown
        assert "Some Great Tutorial" in md
        assert "Example Channel" in md
        assert "youtube.com/watch" in md
        assert "2024-01-15" in md

    def test_fetch_empty_response(self):
        adapter = self._adapter_with_response([])
        results = list(adapter.fetch(""))
        assert results == []

    def test_fetch_multiple_videos(self):
        second = {**VIDEO_ITEM, "video_id": "AAAAAAAAAAA", "url": "https://www.youtube.com/watch?v=AAAAAAAAAAA"}
        adapter = self._adapter_with_response([VIDEO_ITEM, second])
        results = list(adapter.fetch(""))
        assert len(results) == 2

    def test_fetch_skips_item_without_video_id(self):
        no_id = {**VIDEO_ITEM, "video_id": None}
        adapter = self._adapter_with_response([no_id, VIDEO_ITEM])
        results = list(adapter.fetch(""))
        assert len(results) == 1

    def test_fetch_skips_item_without_watched_at(self):
        no_ts = {**VIDEO_ITEM, "watched_at": None}
        adapter = self._adapter_with_response([no_ts, VIDEO_ITEM])
        results = list(adapter.fetch(""))
        assert len(results) == 1

    def test_fetch_domain_is_events(self):
        adapter = self._adapter_with_response([VIDEO_ITEM])
        list(adapter.fetch(""))
        # domain set at adapter level, not on content
        assert adapter.domain == Domain.EVENTS

    def test_fetch_constructs_url_from_video_id_if_missing(self):
        no_url = {**VIDEO_ITEM, "url": None}
        adapter = self._adapter_with_response([no_url])
        results = list(adapter.fetch(""))
        meta = results[0].structural_hints.extra_metadata
        assert meta["url"] == f"https://www.youtube.com/watch?v={VIDEO_ITEM['video_id']}"


# ── Error handling tests ──────────────────────────────────────────────────────

class TestYouTubeWatchHistoryAdapterErrors:
    def test_fetch_raises_on_401(self):
        import httpx
        adapter = _make_adapter()
        adapter._client.get.return_value = _make_mock_response({}, status_code=401)
        with pytest.raises(httpx.HTTPStatusError):
            list(adapter.fetch(""))

    def test_fetch_raises_on_403(self):
        import httpx
        adapter = _make_adapter()
        adapter._client.get.return_value = _make_mock_response({}, status_code=403)
        with pytest.raises(httpx.HTTPStatusError):
            list(adapter.fetch(""))

    def test_fetch_raises_on_network_error(self):
        import httpx
        adapter = _make_adapter()
        adapter._client.get.side_effect = httpx.ConnectError("connection refused")
        with pytest.raises(httpx.RequestError):
            list(adapter.fetch(""))

    def test_fetch_raises_on_invalid_json(self):
        adapter = _make_adapter()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.side_effect = ValueError("not json")
        adapter._client.get.return_value = mock_resp
        with pytest.raises(Exception):
            list(adapter.fetch(""))

    def test_fetch_raises_when_response_not_list(self):
        adapter = _make_adapter()
        adapter._client.get.return_value = _make_mock_response({"error": "unexpected"})
        with pytest.raises(ValueError, match="must be a list"):
            list(adapter.fetch(""))

    def test_fetch_raises_when_response_items_not_dicts(self):
        adapter = _make_adapter()
        adapter._client.get.return_value = _make_mock_response([1, 2, 3])
        with pytest.raises(ValueError, match="items must be dicts"):
            list(adapter.fetch(""))

    def test_fetch_skips_malformed_entry_continues(self):
        # A valid item after a malformed one should still be yielded.
        malformed = {"video_id": "BAD", "watched_at": None}  # no watched_at → skipped
        adapter = _make_adapter()
        adapter._client.get.return_value = _make_mock_response([malformed, VIDEO_ITEM])
        results = list(adapter.fetch(""))
        assert len(results) == 1
        assert results[0].structural_hints.extra_metadata["video_id"] == VIDEO_ITEM["video_id"]


# ── Context manager tests ─────────────────────────────────────────────────────

class TestYouTubeWatchHistoryAdapterContextManager:
    def test_context_manager_closes_client(self):
        adapter = _make_adapter()
        with adapter as a:
            assert a is adapter
        adapter._client.close.assert_called_once()


# ── _build_watch_markdown tests ───────────────────────────────────────────────

class TestBuildWatchMarkdown:
    def test_includes_title(self):
        md = _build_watch_markdown("My Video", "2024-01-15T14:30:00+00:00", "My Channel", "https://yt.com/watch?v=x")
        assert "# My Video" in md

    def test_includes_channel_when_present(self):
        md = _build_watch_markdown("Title", "2024-01-15T14:30:00+00:00", "My Channel", "https://yt.com")
        assert "My Channel" in md

    def test_omits_channel_line_when_none(self):
        md = _build_watch_markdown("Title", "2024-01-15T14:30:00+00:00", None, "https://yt.com")
        assert "Channel" not in md

    def test_includes_watched_at(self):
        md = _build_watch_markdown("Title", "2024-01-15T14:30:00+00:00", None, "https://yt.com")
        assert "2024-01-15" in md

    def test_includes_url(self):
        md = _build_watch_markdown("Title", "2024-01-15T14:30:00+00:00", None, "https://yt.com/watch?v=abc")
        assert "https://yt.com/watch?v=abc" in md

# ── Reset tests ──────────────────────────────────────────────────────────────

class TestYouTubeWatchHistoryAdapterReset:
    def test_reset_success_returns_result(self):
        """reset() returns ResetResult on successful response."""
        adapter = _make_adapter()
        adapter._client.post.return_value = _make_mock_response(
            {"ok": True, "cleared": ["cursor"], "errors": []}
        )
        
        result = adapter.reset()
        
        assert isinstance(result, ResetResult)
        assert result.ok is True
        assert result.cleared == ["cursor"]
        assert result.errors == []
        
        # Verify POST was called to correct endpoint with auth
        adapter._client.post.assert_called_once()
        call_args = adapter._client.post.call_args
        assert "/collectors/youtube/reset" in call_args[0][0]
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-key"

    def test_reset_with_errors_returns_ok_false(self):
        """reset() returns ResetResult with ok=False when helper reports errors."""
        adapter = _make_adapter()
        adapter._client.post.return_value = _make_mock_response(
            {"ok": False, "cleared": [], "errors": ["connection_timeout", "upload_failed"]}
        )
        
        result = adapter.reset()
        
        assert result.ok is False
        assert result.cleared == []
        assert result.errors == ["connection_timeout", "upload_failed"]

    def test_reset_raises_on_http_4xx(self):
        """reset() raises HTTPStatusError on 4xx response."""
        adapter = _make_adapter()
        adapter._client.post.return_value = _make_mock_response({}, status_code=401)
        
        with pytest.raises(httpx.HTTPStatusError):
            adapter.reset()

    def test_reset_raises_on_http_5xx(self):
        """reset() raises HTTPStatusError on 5xx response."""
        adapter = _make_adapter()
        adapter._client.post.return_value = _make_mock_response({}, status_code=503)
        
        with pytest.raises(httpx.HTTPStatusError):
            adapter.reset()

    def test_reset_raises_on_malformed_json(self):
        """reset() raises ValueError when response is not valid JSON."""
        adapter = _make_adapter()
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("Invalid JSON")
        adapter._client.post.return_value = mock_response
        
        with pytest.raises(ValueError):
            adapter.reset()

    def test_reset_raises_on_missing_fields(self):
        """reset() raises ValidationError when response is missing required fields."""
        adapter = _make_adapter()
        # Missing 'ok' field
        adapter._client.post.return_value = _make_mock_response(
            {"cleared": [], "errors": []}
        )
        
        with pytest.raises(ValidationError):
            adapter.reset()

    def test_reset_raises_on_invalid_field_types(self):
        """reset() raises ValidationError when response fields have wrong types."""
        adapter = _make_adapter()
        # ok should be bool, not list
        adapter._client.post.return_value = _make_mock_response(
            {"ok": [], "cleared": [], "errors": []}
        )

        with pytest.raises(ValidationError):
            adapter.reset()
