"""Tests for YouTubeTranscriptAdapter."""

from unittest.mock import MagicMock, patch

import pytest

from context_library.adapters.youtube_transcripts import (
    YouTubeTranscriptAdapter,
    _build_transcript_markdown,
    _format_timestamp,
    _merge_segments,
)
from context_library.storage.models import Domain, DocumentMetadata, PollStrategy


# ── Fixtures ────────────────────────────────────────────────────────────────

def _make_mock_store(watch_chunks=None, transcript_sources=None):
    """Build a minimal mock DocumentStore for YouTubeTranscriptAdapter tests."""
    store = MagicMock()

    # list_chunks returns (chunks, total)
    watch_chunk_list = watch_chunks or []
    store.list_chunks.return_value = (watch_chunk_list, len(watch_chunk_list))

    # list_sources returns (sources, total)
    transcript_source_list = transcript_sources or []
    store.list_sources.return_value = (transcript_source_list, len(transcript_source_list))

    return store


def _make_watch_chunk(video_id: str, title: str = "Test Video", channel: str = "Test Channel"):
    """Build a minimal mock ChunkWithLineageContext for a watch event."""
    chunk = MagicMock()
    chunk.chunk.domain_metadata = {
        "video_id": video_id,
        "title": title,
        "channel": channel,
        "channel_id": f"UC{video_id}",
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "start_date": "2024-01-15T14:30:00+00:00",
    }
    return chunk


SAMPLE_SEGMENTS = [
    {"text": "Hello everyone welcome to this tutorial", "start": 0.0, "duration": 3.5},
    {"text": "Today we are going to learn about Python programming", "start": 3.5, "duration": 4.0},
    {"text": "Python is a great language for beginners", "start": 7.5, "duration": 3.0},
]


# ── Initialization tests ────────────────────────────────────────────────────

class TestYouTubeTranscriptAdapterInitialization:
    def test_init_requires_youtube_transcript_api(self):
        """Raises ImportError when youtube-transcript-api is not installed."""
        store = _make_mock_store()
        with patch("context_library.adapters.youtube_transcripts.HAS_YOUTUBE_TRANSCRIPT_API", False):
            with pytest.raises(ImportError, match="youtube-transcript-api"):
                YouTubeTranscriptAdapter(document_store=store)

    def test_init_default_parameters(self):
        store = _make_mock_store()
        with patch("context_library.adapters.youtube_transcripts.HAS_YOUTUBE_TRANSCRIPT_API", True):
            adapter = YouTubeTranscriptAdapter(document_store=store)
        assert adapter._account_id == "default"
        assert adapter._chunk_words == 350
        assert adapter._languages == ["en"]
        assert adapter._watch_history_adapter_id == "youtube_watch_history:default"

    def test_init_custom_parameters(self):
        store = _make_mock_store()
        with patch("context_library.adapters.youtube_transcripts.HAS_YOUTUBE_TRANSCRIPT_API", True):
            adapter = YouTubeTranscriptAdapter(
                document_store=store,
                watch_history_adapter_id="youtube_watch_history:work",
                account_id="work",
                chunk_words=200,
                languages=["en", "es"],
            )
        assert adapter._account_id == "work"
        assert adapter._chunk_words == 200
        assert adapter._languages == ["en", "es"]
        assert adapter._watch_history_adapter_id == "youtube_watch_history:work"

    def test_background_poll_flag(self):
        store = _make_mock_store()
        with patch("context_library.adapters.youtube_transcripts.HAS_YOUTUBE_TRANSCRIPT_API", True):
            adapter = YouTubeTranscriptAdapter(document_store=store)
        assert adapter.background_poll is True


# ── Property tests ──────────────────────────────────────────────────────────

class TestYouTubeTranscriptAdapterProperties:
    def setup_method(self):
        store = _make_mock_store()
        with patch("context_library.adapters.youtube_transcripts.HAS_YOUTUBE_TRANSCRIPT_API", True):
            self.adapter = YouTubeTranscriptAdapter(document_store=store)

    def test_adapter_id_default(self):
        assert self.adapter.adapter_id == "youtube_transcripts:default"

    def test_domain(self):
        assert self.adapter.domain == Domain.DOCUMENTS

    def test_poll_strategy(self):
        assert self.adapter.poll_strategy == PollStrategy.PULL

    def test_normalizer_version(self):
        assert self.adapter.normalizer_version == "1.0.0"


# ── Fetch tests ─────────────────────────────────────────────────────────────

class TestYouTubeTranscriptAdapterFetch:
    def _make_adapter(self, store):
        with patch("context_library.adapters.youtube_transcripts.HAS_YOUTUBE_TRANSCRIPT_API", True):
            return YouTubeTranscriptAdapter(document_store=store)

    def test_fetch_yields_nothing_when_no_watch_history(self):
        store = _make_mock_store(watch_chunks=[], transcript_sources=[])
        adapter = self._make_adapter(store)

        with patch("context_library.adapters.youtube_transcripts.HAS_YOUTUBE_TRANSCRIPT_API", True):
            results = list(adapter.fetch(""))

        assert results == []

    def test_fetch_skips_already_indexed_videos(self):
        watch_chunks = [_make_watch_chunk("abc123")]
        existing_sources = [{"source_id": "youtube/transcript/abc123"}]
        store = _make_mock_store(watch_chunks=watch_chunks, transcript_sources=existing_sources)
        adapter = self._make_adapter(store)

        with patch("context_library.adapters.youtube_transcripts.HAS_YOUTUBE_TRANSCRIPT_API", True):
            results = list(adapter.fetch(""))

        assert results == []

    def test_fetch_fetches_pending_video(self):
        watch_chunks = [_make_watch_chunk("abc123")]
        store = _make_mock_store(watch_chunks=watch_chunks, transcript_sources=[])
        adapter = self._make_adapter(store)

        mock_transcript_api = MagicMock()
        mock_transcript = MagicMock()
        mock_transcript.fetch.return_value = SAMPLE_SEGMENTS
        mock_transcript_api.list_transcripts.return_value.find_transcript.return_value = mock_transcript

        with patch("context_library.adapters.youtube_transcripts.YouTubeTranscriptApi", mock_transcript_api):
            with patch("context_library.adapters.youtube_transcripts.HAS_YOUTUBE_TRANSCRIPT_API", True):
                results = list(adapter.fetch(""))

        assert len(results) == 1
        assert results[0].source_id == "youtube/transcript/abc123"
        # domain is inferred from adapter.domain by the pipeline; NormalizedContent.domain is None
        # for single-domain adapters (only multi-domain adapters set it explicitly per item)
        assert adapter.domain == Domain.DOCUMENTS

    def test_fetch_source_id_format(self):
        watch_chunks = [_make_watch_chunk("vid999")]
        store = _make_mock_store(watch_chunks=watch_chunks, transcript_sources=[])
        adapter = self._make_adapter(store)

        mock_api = MagicMock()
        mock_api.list_transcripts.return_value.find_transcript.return_value.fetch.return_value = SAMPLE_SEGMENTS

        with patch("context_library.adapters.youtube_transcripts.YouTubeTranscriptApi", mock_api):
            with patch("context_library.adapters.youtube_transcripts.HAS_YOUTUBE_TRANSCRIPT_API", True):
                results = list(adapter.fetch(""))

        assert results[0].source_id == "youtube/transcript/vid999"

    def test_fetch_document_metadata_fields(self):
        watch_chunks = [_make_watch_chunk("abc123", title="My Video", channel="My Channel")]
        store = _make_mock_store(watch_chunks=watch_chunks, transcript_sources=[])
        adapter = self._make_adapter(store)

        mock_api = MagicMock()
        mock_api.list_transcripts.return_value.find_transcript.return_value.fetch.return_value = SAMPLE_SEGMENTS

        with patch("context_library.adapters.youtube_transcripts.YouTubeTranscriptApi", mock_api):
            with patch("context_library.adapters.youtube_transcripts.HAS_YOUTUBE_TRANSCRIPT_API", True):
                results = list(adapter.fetch(""))

        extra = results[0].structural_hints.extra_metadata
        assert extra["document_type"] == "video/transcript"
        assert extra["source_type"] == "youtube_transcript"
        assert extra["video_id"] == "abc123"
        assert extra["title"] == "My Video"
        assert extra["channel"] == "My Channel"

        # Must be valid DocumentMetadata
        doc_meta = DocumentMetadata.model_validate(extra)
        assert doc_meta.document_id == "abc123"
        assert doc_meta.video_id == "abc123"

    def test_fetch_skips_videos_with_no_transcript(self):
        watch_chunks = [_make_watch_chunk("abc123")]
        store = _make_mock_store(watch_chunks=watch_chunks, transcript_sources=[])
        adapter = self._make_adapter(store)

        from youtube_transcript_api import NoTranscriptFound  # type: ignore[import]
        mock_api = MagicMock()
        mock_api.list_transcripts.return_value.find_transcript.side_effect = NoTranscriptFound(
            "abc123", ["en"], MagicMock()
        )

        with patch("context_library.adapters.youtube_transcripts.YouTubeTranscriptApi", mock_api):
            with patch("context_library.adapters.youtube_transcripts.HAS_YOUTUBE_TRANSCRIPT_API", True):
                results = list(adapter.fetch(""))

        assert results == []

    def test_fetch_skips_videos_with_disabled_transcripts(self):
        watch_chunks = [_make_watch_chunk("abc123")]
        store = _make_mock_store(watch_chunks=watch_chunks, transcript_sources=[])
        adapter = self._make_adapter(store)

        from youtube_transcript_api import TranscriptsDisabled  # type: ignore[import]
        mock_api = MagicMock()
        mock_api.list_transcripts.side_effect = TranscriptsDisabled("abc123")

        with patch("context_library.adapters.youtube_transcripts.YouTubeTranscriptApi", mock_api):
            with patch("context_library.adapters.youtube_transcripts.HAS_YOUTUBE_TRANSCRIPT_API", True):
                results = list(adapter.fetch(""))

        assert results == []

    def test_fetch_continues_after_single_failure(self):
        watch_chunks = [_make_watch_chunk("fail_vid"), _make_watch_chunk("ok_vid")]
        store = _make_mock_store(watch_chunks=watch_chunks, transcript_sources=[])
        adapter = self._make_adapter(store)

        call_count = 0

        def side_effect(video_id):
            nonlocal call_count
            call_count += 1
            if video_id == "fail_vid":
                raise RuntimeError("Unexpected error")
            mock = MagicMock()
            mock.find_transcript.return_value.fetch.return_value = SAMPLE_SEGMENTS
            return mock

        mock_api = MagicMock()
        mock_api.list_transcripts.side_effect = side_effect

        with patch("context_library.adapters.youtube_transcripts.YouTubeTranscriptApi", mock_api):
            with patch("context_library.adapters.youtube_transcripts.HAS_YOUTUBE_TRANSCRIPT_API", True):
                results = list(adapter.fetch(""))

        assert len(results) == 1  # Only ok_vid succeeded

    def test_fetch_chunk_without_video_id_is_skipped(self):
        chunk = MagicMock()
        chunk.chunk.domain_metadata = {"title": "No video ID here"}
        store = _make_mock_store(watch_chunks=[chunk], transcript_sources=[])
        adapter = self._make_adapter(store)

        with patch("context_library.adapters.youtube_transcripts.HAS_YOUTUBE_TRANSCRIPT_API", True):
            results = list(adapter.fetch(""))

        assert results == []

    def test_fetch_transcript_markdown_contains_content(self):
        watch_chunks = [_make_watch_chunk("abc123", title="Great Talk")]
        store = _make_mock_store(watch_chunks=watch_chunks, transcript_sources=[])
        adapter = self._make_adapter(store)

        mock_api = MagicMock()
        mock_api.list_transcripts.return_value.find_transcript.return_value.fetch.return_value = SAMPLE_SEGMENTS

        with patch("context_library.adapters.youtube_transcripts.YouTubeTranscriptApi", mock_api):
            with patch("context_library.adapters.youtube_transcripts.HAS_YOUTUBE_TRANSCRIPT_API", True):
                results = list(adapter.fetch(""))

        md = results[0].markdown
        assert "Great Talk" in md
        assert "Transcript" in md
        assert "[0:00]" in md

    def test_fetch_skips_data_validation_errors_and_continues(self):
        """Verifies that TypeError, ValueError, KeyError are caught and logged, not propagated."""
        watch_chunks = [_make_watch_chunk("fail_vid"), _make_watch_chunk("ok_vid")]
        store = _make_mock_store(watch_chunks=watch_chunks, transcript_sources=[])
        adapter = self._make_adapter(store)

        call_count = 0

        def side_effect(video_id):
            nonlocal call_count
            call_count += 1
            if video_id == "fail_vid":
                raise TypeError("Malformed metadata: expected dict")
            mock = MagicMock()
            mock.find_transcript.return_value.fetch.return_value = SAMPLE_SEGMENTS
            return mock

        mock_api = MagicMock()
        mock_api.list_transcripts.side_effect = side_effect

        with patch("context_library.adapters.youtube_transcripts.YouTubeTranscriptApi", mock_api):
            with patch("context_library.adapters.youtube_transcripts.HAS_YOUTUBE_TRANSCRIPT_API", True):
                results = list(adapter.fetch(""))

        # Should process both videos: fail_vid logs and skips, ok_vid succeeds
        assert len(results) == 1  # Only ok_vid succeeded
        assert call_count == 2  # Both videos were attempted


# ── Helper function tests ───────────────────────────────────────────────────

class TestMergeSegments:
    def test_empty_segments(self):
        assert _merge_segments([], 350) == []

    def test_single_segment_becomes_one_block(self):
        segs = [{"text": "Hello world", "start": 0.0, "duration": 2.0}]
        blocks = _merge_segments(segs, 350)
        assert len(blocks) == 1
        assert blocks[0]["text"] == "Hello world"
        assert blocks[0]["start"] == 0.0

    def test_segments_merged_to_target_words(self):
        # 5 segments of 10 words each; target=20 → should split into blocks of ~20 words
        segs = [
            {"text": " ".join([f"word{i}" for i in range(10)]), "start": float(j * 5), "duration": 5.0}
            for j in range(5)
        ]
        blocks = _merge_segments(segs, 20)
        # With 50 total words and target 20, expect multiple blocks
        assert len(blocks) > 1

    def test_block_start_and_end_are_set(self):
        segs = [
            {"text": "First segment", "start": 0.0, "duration": 3.0},
            {"text": "Second segment", "start": 3.0, "duration": 3.0},
        ]
        blocks = _merge_segments(segs, 1)   # tiny target → one block per segment
        assert blocks[0]["start"] == 0.0
        assert blocks[0]["end"] == 3.0

    def test_skips_empty_text_segments(self):
        segs = [
            {"text": "Hello", "start": 0.0, "duration": 2.0},
            {"text": "", "start": 2.0, "duration": 1.0},
            {"text": "World", "start": 3.0, "duration": 2.0},
        ]
        blocks = _merge_segments(segs, 350)
        assert len(blocks) == 1
        assert "Hello" in blocks[0]["text"]
        assert "World" in blocks[0]["text"]


class TestFormatTimestamp:
    def test_under_one_minute(self):
        assert _format_timestamp(45.0) == "0:45"

    def test_exactly_one_minute(self):
        assert _format_timestamp(60.0) == "1:00"

    def test_multiple_minutes(self):
        assert _format_timestamp(150.0) == "2:30"

    def test_over_one_hour(self):
        assert _format_timestamp(3661.0) == "1:01:01"

    def test_zero(self):
        assert _format_timestamp(0.0) == "0:00"


class TestBuildTranscriptMarkdown:
    def test_includes_title_as_heading(self):
        md = _build_transcript_markdown("My Video", "Channel", "https://yt.com", None, [])
        assert "# My Video" in md

    def test_includes_channel(self):
        md = _build_transcript_markdown("Title", "My Channel", "https://yt.com", None, [])
        assert "My Channel" in md

    def test_omits_channel_when_none(self):
        md = _build_transcript_markdown("Title", None, "https://yt.com", None, [])
        assert "Channel" not in md

    def test_includes_transcript_section(self):
        blocks = [{"text": "Hello world", "start": 0.0, "end": 3.0}]
        md = _build_transcript_markdown("Title", None, "https://yt.com", None, blocks)
        assert "## Transcript" in md
        assert "[0:00]" in md
        assert "Hello world" in md

    def test_multiple_blocks_have_timestamps(self):
        blocks = [
            {"text": "First block", "start": 0.0, "end": 60.0},
            {"text": "Second block", "start": 60.0, "end": 120.0},
        ]
        md = _build_transcript_markdown("Title", None, "https://yt.com", None, blocks)
        assert "[0:00]" in md
        assert "[1:00]" in md

    def test_includes_watched_at(self):
        md = _build_transcript_markdown("Title", None, "https://yt.com", "2024-01-15T14:30:00+00:00", [])
        assert "2024-01-15" in md
