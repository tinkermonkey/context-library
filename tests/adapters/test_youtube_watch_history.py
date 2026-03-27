"""Tests for YouTubeWatchHistoryAdapter."""

import json
import os
import tempfile

import pytest

from context_library.adapters.youtube_watch_history import (
    YouTubeWatchHistoryAdapter,
    _build_watch_markdown,
    _extract_channel_id,
    _extract_video_id,
)
from context_library.storage.models import Domain, EventMetadata, PollStrategy


# ── Fixtures ────────────────────────────────────────────────────────────────

WATCH_ITEM = {
    "header": "YouTube",
    "title": "Watched Some Great Tutorial",
    "titleUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "subtitles": [
        {
            "name": "Example Channel",
            "url": "https://www.youtube.com/channel/UCxxxxxxxxxx",
        }
    ],
    "time": "2024-01-15T14:30:00.000Z",
    "products": ["YouTube"],
    "activityControls": ["YouTube watch history"],
}

SEARCH_ITEM = {
    "header": "YouTube",
    "title": "Searched for python tutorial",
    "time": "2024-01-14T10:00:00.000Z",
    # No titleUrl — search activity
}

DELETED_VIDEO_ITEM = {
    "header": "YouTube",
    "title": "Watched Deleted video",
    "titleUrl": "https://www.youtube.com/watch?v=XXXXXXXXXXX",
    # No subtitles — deleted video
    "time": "2024-01-13T09:00:00.000Z",
}


def _make_takeout_file(items: list[dict]) -> str:
    """Write items to a temp file and return its path."""
    fh = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(items, fh)
    fh.close()
    return fh.name


# ── Initialization tests ────────────────────────────────────────────────────

class TestYouTubeWatchHistoryAdapterInitialization:
    def test_init_default_parameters(self):
        adapter = YouTubeWatchHistoryAdapter(takeout_path="/tmp/watch-history.json")
        assert adapter._takeout_path == "/tmp/watch-history.json"
        assert adapter._account_id == "default"
        assert adapter._cursor == ""

    def test_init_custom_account_id(self):
        adapter = YouTubeWatchHistoryAdapter(
            takeout_path="/tmp/watch-history.json",
            account_id="personal",
        )
        assert adapter._account_id == "personal"

    def test_init_requires_takeout_path(self):
        with pytest.raises(ValueError, match="takeout_path is required"):
            YouTubeWatchHistoryAdapter(takeout_path="")

    def test_background_poll_flag(self):
        adapter = YouTubeWatchHistoryAdapter(takeout_path="/tmp/watch-history.json")
        assert adapter.background_poll is True


# ── Property tests ──────────────────────────────────────────────────────────

class TestYouTubeWatchHistoryAdapterProperties:
    def test_adapter_id_default(self):
        adapter = YouTubeWatchHistoryAdapter(takeout_path="/tmp/watch-history.json")
        assert adapter.adapter_id == "youtube_watch_history:default"

    def test_adapter_id_custom(self):
        adapter = YouTubeWatchHistoryAdapter(
            takeout_path="/tmp/watch-history.json", account_id="work"
        )
        assert adapter.adapter_id == "youtube_watch_history:work"

    def test_adapter_id_deterministic(self):
        a1 = YouTubeWatchHistoryAdapter(takeout_path="/tmp/a.json", account_id="x")
        a2 = YouTubeWatchHistoryAdapter(takeout_path="/tmp/b.json", account_id="x")
        assert a1.adapter_id == a2.adapter_id

    def test_domain(self):
        adapter = YouTubeWatchHistoryAdapter(takeout_path="/tmp/watch-history.json")
        assert adapter.domain == Domain.EVENTS

    def test_poll_strategy(self):
        adapter = YouTubeWatchHistoryAdapter(takeout_path="/tmp/watch-history.json")
        assert adapter.poll_strategy == PollStrategy.PULL

    def test_normalizer_version(self):
        adapter = YouTubeWatchHistoryAdapter(takeout_path="/tmp/watch-history.json")
        assert adapter.normalizer_version == "1.0.0"


# ── Fetch tests ─────────────────────────────────────────────────────────────

class TestYouTubeWatchHistoryAdapterFetch:
    def test_fetch_single_watch_event(self):
        path = _make_takeout_file([WATCH_ITEM])
        try:
            adapter = YouTubeWatchHistoryAdapter(takeout_path=path)
            results = list(adapter.fetch(""))
        finally:
            os.unlink(path)

        assert len(results) == 1
        content = results[0]
        assert content.source_id.startswith("youtube/watch/dQw4w9WgXcQ/")
        assert content.normalizer_version == "1.0.0"

    def test_fetch_skips_search_items(self):
        path = _make_takeout_file([WATCH_ITEM, SEARCH_ITEM])
        try:
            adapter = YouTubeWatchHistoryAdapter(takeout_path=path)
            results = list(adapter.fetch(""))
        finally:
            os.unlink(path)

        assert len(results) == 1  # SEARCH_ITEM has no titleUrl

    def test_fetch_handles_deleted_video(self):
        path = _make_takeout_file([DELETED_VIDEO_ITEM])
        try:
            adapter = YouTubeWatchHistoryAdapter(takeout_path=path)
            results = list(adapter.fetch(""))
        finally:
            os.unlink(path)

        assert len(results) == 1
        meta = results[0].structural_hints.extra_metadata
        assert meta["channel"] is None
        assert meta["channel_id"] is None

    def test_fetch_strips_watched_prefix_from_title(self):
        path = _make_takeout_file([WATCH_ITEM])
        try:
            adapter = YouTubeWatchHistoryAdapter(takeout_path=path)
            results = list(adapter.fetch(""))
        finally:
            os.unlink(path)

        meta = results[0].structural_hints.extra_metadata
        assert meta["title"] == "Some Great Tutorial"
        assert "Watched" not in meta["title"]

    def test_fetch_extracts_channel_metadata(self):
        path = _make_takeout_file([WATCH_ITEM])
        try:
            adapter = YouTubeWatchHistoryAdapter(takeout_path=path)
            results = list(adapter.fetch(""))
        finally:
            os.unlink(path)

        meta = results[0].structural_hints.extra_metadata
        assert meta["channel"] == "Example Channel"
        assert meta["channel_id"] == "UCxxxxxxxxxx"
        assert meta["video_id"] == "dQw4w9WgXcQ"
        assert "youtube.com/watch" in meta["url"]

    def test_fetch_event_metadata_valid(self):
        path = _make_takeout_file([WATCH_ITEM])
        try:
            adapter = YouTubeWatchHistoryAdapter(takeout_path=path)
            results = list(adapter.fetch(""))
        finally:
            os.unlink(path)

        meta = results[0].structural_hints.extra_metadata
        # Must be valid EventMetadata
        event_meta = EventMetadata.model_validate(meta)
        assert event_meta.source_type == "youtube_watch_history"
        assert event_meta.start_date is not None
        assert "dQw4w9WgXcQ" in event_meta.event_id

    def test_fetch_incremental_respects_source_ref(self):
        # WATCH_ITEM is 2024-01-15; provide a since after it to skip
        path = _make_takeout_file([WATCH_ITEM])
        try:
            adapter = YouTubeWatchHistoryAdapter(takeout_path=path)
            results = list(adapter.fetch("2024-01-16T00:00:00+00:00"))
        finally:
            os.unlink(path)

        assert results == []

    def test_fetch_incremental_uses_internal_cursor(self):
        path = _make_takeout_file([WATCH_ITEM])
        try:
            adapter = YouTubeWatchHistoryAdapter(takeout_path=path)
            # First fetch ingests the item
            first = list(adapter.fetch(""))
            assert len(first) == 1
            assert adapter._cursor != ""

            # Second fetch with empty source_ref uses cursor → nothing new
            second = list(adapter.fetch(""))
        finally:
            os.unlink(path)

        assert second == []

    def test_fetch_cursor_updated_after_fetch(self):
        path = _make_takeout_file([WATCH_ITEM])
        try:
            adapter = YouTubeWatchHistoryAdapter(takeout_path=path)
            assert adapter._cursor == ""
            list(adapter.fetch(""))
            assert adapter._cursor != ""
            assert "2024-01-15" in adapter._cursor
        finally:
            os.unlink(path)

    def test_fetch_multiple_events_ordered(self):
        older = {**WATCH_ITEM, "time": "2024-01-10T10:00:00.000Z", "titleUrl": "https://www.youtube.com/watch?v=AAAAAAAAAAA"}
        newer = {**WATCH_ITEM, "time": "2024-01-15T14:30:00.000Z", "titleUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
        path = _make_takeout_file([newer, older])   # Takeout is newest-first
        try:
            adapter = YouTubeWatchHistoryAdapter(takeout_path=path)
            results = list(adapter.fetch(""))
        finally:
            os.unlink(path)

        assert len(results) == 2

    def test_fetch_rewatch_creates_separate_source(self):
        rewatch = {**WATCH_ITEM, "time": "2024-02-01T10:00:00.000Z"}
        path = _make_takeout_file([rewatch, WATCH_ITEM])
        try:
            adapter = YouTubeWatchHistoryAdapter(takeout_path=path)
            results = list(adapter.fetch(""))
        finally:
            os.unlink(path)

        assert len(results) == 2
        source_ids = {r.source_id for r in results}
        assert len(source_ids) == 2  # Different timestamps → different source_ids

    def test_fetch_raises_on_missing_file(self):
        adapter = YouTubeWatchHistoryAdapter(takeout_path="/nonexistent/watch-history.json")
        with pytest.raises(OSError):
            list(adapter.fetch(""))

    def test_fetch_raises_on_invalid_json(self):
        fh = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        fh.write("not valid json{{{")
        fh.close()
        try:
            adapter = YouTubeWatchHistoryAdapter(takeout_path=fh.name)
            with pytest.raises(Exception):  # json.JSONDecodeError
                list(adapter.fetch(""))
        finally:
            os.unlink(fh.name)

    def test_fetch_markdown_contains_expected_fields(self):
        path = _make_takeout_file([WATCH_ITEM])
        try:
            adapter = YouTubeWatchHistoryAdapter(takeout_path=path)
            results = list(adapter.fetch(""))
        finally:
            os.unlink(path)

        md = results[0].markdown
        assert "Some Great Tutorial" in md
        assert "Example Channel" in md
        assert "youtube.com/watch" in md
        assert "2024-01-15" in md


# ── Helper function tests ───────────────────────────────────────────────────

class TestExtractVideoId:
    def test_standard_url(self):
        assert _extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_url_with_extra_params(self):
        assert _extract_video_id("https://www.youtube.com/watch?v=abc123&t=42s") == "abc123"

    def test_non_watch_url(self):
        assert _extract_video_id("https://www.youtube.com/channel/UCxxx") is None

    def test_search_url(self):
        assert _extract_video_id("https://www.youtube.com/results?search_query=python") is None

    def test_non_youtube_url(self):
        assert _extract_video_id("https://example.com/watch?v=foo") is None

    def test_empty_string(self):
        assert _extract_video_id("") is None


class TestExtractChannelId:
    def test_standard_channel_url(self):
        assert _extract_channel_id("https://www.youtube.com/channel/UCxxxxxxxxxx") == "UCxxxxxxxxxx"

    def test_empty_url(self):
        assert _extract_channel_id("") is None

    def test_non_channel_url(self):
        assert _extract_channel_id("https://www.youtube.com/user/someuser") is None

    def test_none_url(self):
        assert _extract_channel_id(None) is None


class TestBuildWatchMarkdown:
    def test_includes_title(self):
        md = _build_watch_markdown("My Video", "2024-01-15T14:30:00+00:00", "My Channel", "https://yt.com/watch?v=x")
        assert "# My Video" in md

    def test_includes_channel(self):
        md = _build_watch_markdown("Title", "2024-01-15T14:30:00+00:00", "My Channel", "https://yt.com")
        assert "My Channel" in md

    def test_omits_channel_line_when_none(self):
        md = _build_watch_markdown("Title", "2024-01-15T14:30:00+00:00", None, "https://yt.com")
        assert "Channel" not in md

    def test_includes_url(self):
        md = _build_watch_markdown("Title", "2024-01-15T14:30:00+00:00", None, "https://yt.com/watch?v=abc")
        assert "https://yt.com/watch?v=abc" in md
