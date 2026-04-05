"""Tests for the ApplePodcastsAdapter."""

import pytest

from context_library.adapters.apple_podcasts import ApplePodcastsAdapter
from context_library.adapters.base import AllEndpointsFailedError, PartialFetchError
from context_library.storage.models import Domain, PollStrategy, NormalizedContent, EventMetadata, DocumentMetadata


class TestApplePodcastsAdapterInitialization:
    """Tests for ApplePodcastsAdapter initialization."""

    def test_init_default_parameters(self):
        """__init__ uses default parameters when not provided."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"
        assert adapter._api_key == "test-token"
        assert adapter._device_id == "default"

    def test_init_requires_api_key(self):
        """__init__ raises ValueError when api_key is empty."""
        with pytest.raises(ValueError, match="api_key is required"):
            ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="")

    def test_init_custom_parameters(self):
        """__init__ accepts and stores custom parameters."""
        adapter = ApplePodcastsAdapter(
            api_url="http://localhost:8000",
            api_key="test_key",
            device_id="macbook-pro-m1",
        )
        assert adapter._api_url == "http://localhost:8000"
        assert adapter._api_key == "test_key"
        assert adapter._device_id == "macbook-pro-m1"

    def test_init_strips_trailing_slash_from_url(self):
        """__init__ strips trailing slash from api_url."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123/", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"

    def test_init_no_trailing_slash(self):
        """__init__ leaves api_url unchanged if no trailing slash."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"


class TestApplePodcastsAdapterProperties:
    """Tests for ApplePodcastsAdapter properties."""

    def test_adapter_id_format_default(self):
        """adapter_id has correct format: apple_podcasts:{device_id}."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.adapter_id == "apple_podcasts:default"

    def test_adapter_id_format_custom_device(self):
        """adapter_id uses custom device_id."""
        adapter = ApplePodcastsAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test-token",
            device_id="macbook-pro-m1"
        )
        assert adapter.adapter_id == "apple_podcasts:macbook-pro-m1"

    def test_adapter_id_deterministic(self):
        """adapter_id is deterministic for the same configuration."""
        adapter1 = ApplePodcastsAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test-token",
            device_id="device-1"
        )
        adapter2 = ApplePodcastsAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test-token",
            device_id="device-1"
        )
        assert adapter1.adapter_id == adapter2.adapter_id

    def test_domain_property(self):
        """domain property returns Domain.EVENTS."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.domain == Domain.EVENTS

    def test_poll_strategy_property(self):
        """poll_strategy property returns PollStrategy.PULL."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.poll_strategy == PollStrategy.PULL

    def test_normalizer_version_property(self):
        """normalizer_version property returns '1.0.0'."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.normalizer_version == "1.0.0"


class TestApplePodcastsAdapterFetchListenHistory:
    """Tests for ApplePodcastsAdapter.fetch() with listen history."""

    def test_fetch_listen_history_single_item(self, mock_all_podcasts_endpoints):
        """fetch() yields NormalizedContent for a single listen history item."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_podcasts_endpoints.set_response("http://127.0.0.1:7123/podcasts/listen-history", [
            {
                "id": "ep-1",
                "showTitle": "Tech Talk",
                "episodeTitle": "Intro to Python",
                "episodeGuid": "guid-1",
                "feedUrl": "https://techtalk.example/feed",
                "listenedAt": "2026-03-20T10:00:00+00:00",
                "durationSeconds": 3600,
                "playedSeconds": 3600,
                "completed": True,
            }
        ])

        results = list(adapter.fetch(""))
        assert len(results) >= 1
        # Find the listen history item
        listen_items = [r for r in results if r.source_id == "podcasts/listen/ep-1"]
        assert len(listen_items) == 1
        item = listen_items[0]
        assert isinstance(item, NormalizedContent)
        assert item.domain == Domain.EVENTS
        assert "Tech Talk" in item.markdown
        assert "Intro to Python" in item.markdown

    def test_fetch_listen_history_multiple_items(self, mock_all_podcasts_endpoints):
        """fetch() yields NormalizedContent for multiple listen history items."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_podcasts_endpoints.set_response("http://127.0.0.1:7123/podcasts/listen-history", [
            {
                "id": "ep-1",
                "showTitle": "Tech Talk",
                "episodeTitle": "Intro to Python",
                "episodeGuid": "guid-1",
                "feedUrl": "https://techtalk.example/feed",
                "listenedAt": "2026-03-20T10:00:00+00:00",
                "durationSeconds": 3600,
                "playedSeconds": 3600,
                "completed": True,
            },
            {
                "id": "ep-2",
                "showTitle": "Science Hour",
                "episodeTitle": "Black Holes",
                "episodeGuid": "guid-2",
                "feedUrl": "https://science.example/feed",
                "listenedAt": "2026-03-21T14:30:00+00:00",
                "durationSeconds": 7200,
                "playedSeconds": 5400,
                "completed": False,
            },
        ])

        results = list(adapter.fetch(""))
        listen_items = [r for r in results if "listen" in r.source_id]
        assert len(listen_items) == 2
        assert listen_items[0].source_id == "podcasts/listen/ep-1"
        assert listen_items[1].source_id == "podcasts/listen/ep-2"

    def test_fetch_listen_history_title_format(self, mock_all_podcasts_endpoints):
        """fetch() formats listen history title as '{showTitle} — {episodeTitle}'."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_podcasts_endpoints.set_response("http://127.0.0.1:7123/podcasts/listen-history", [
            {
                "id": "ep-1",
                "showTitle": "Tech Talk",
                "episodeTitle": "Intro to Python",
                "episodeGuid": "guid-1",
                "feedUrl": None,
                "listenedAt": "2026-03-20T10:00:00+00:00",
                "durationSeconds": 3600,
                "playedSeconds": 3600,
                "completed": True,
            }
        ])

        results = list(adapter.fetch(""))
        listen_items = [r for r in results if "listen" in r.source_id]
        assert len(listen_items) == 1
        # The title should be formatted as "{showTitle} — {episodeTitle}" in the metadata
        metadata_dict = listen_items[0].structural_hints.extra_metadata
        assert metadata_dict["title"] == "Tech Talk — Intro to Python"

    def test_fetch_listen_history_with_since_parameter(self, mock_all_podcasts_endpoints):
        """fetch() passes 'since' query parameter for incremental fetch."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_podcasts_endpoints.set_response("http://127.0.0.1:7123/podcasts/listen-history", [])

        list(adapter.fetch("2026-03-06T10:00:00Z"))

        # Check listen history request
        request = None
        for r in mock_all_podcasts_endpoints.requests:
            if "/podcasts/listen-history" in r["url"]:
                request = r
                break

        assert request is not None
        assert request["params"]["since"] == "2026-03-06T10:00:00Z"

    def test_fetch_listen_history_with_api_key_auth(self, mock_all_podcasts_endpoints):
        """fetch() sends Authorization header with Bearer token."""
        adapter = ApplePodcastsAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test_token_123"
        )

        mock_all_podcasts_endpoints.set_response("http://127.0.0.1:7123/podcasts/listen-history", [])

        list(adapter.fetch(""))

        # Check listen history request
        request = None
        for r in mock_all_podcasts_endpoints.requests:
            if "/podcasts/listen-history" in r["url"]:
                request = r
                break

        assert request is not None
        assert request["headers"]["Authorization"] == "Bearer test_token_123"

    def test_fetch_listen_history_metadata_validation(self, mock_all_podcasts_endpoints):
        """fetch() produces EventMetadata that passes model_validate."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_podcasts_endpoints.set_response("http://127.0.0.1:7123/podcasts/listen-history", [
            {
                "id": "ep-1",
                "showTitle": "Tech Talk",
                "episodeTitle": "Intro to Python",
                "episodeGuid": "guid-1",
                "feedUrl": "https://techtalk.example/feed",
                "listenedAt": "2026-03-20T10:00:00+00:00",
                "durationSeconds": 3600,
                "playedSeconds": 3600,
                "completed": True,
            }
        ])

        results = list(adapter.fetch(""))
        listen_items = [r for r in results if "listen" in r.source_id]
        metadata_dict = listen_items[0].structural_hints.extra_metadata

        # This should not raise if EventMetadata validation passes
        metadata = EventMetadata.model_validate(metadata_dict)
        assert metadata.event_id == "listen/ep-1"
        assert metadata.source_type == "podcast_listen"

    def test_fetch_listen_history_extra_metadata(self, mock_all_podcasts_endpoints):
        """fetch() includes extra metadata fields in listen history."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_podcasts_endpoints.set_response("http://127.0.0.1:7123/podcasts/listen-history", [
            {
                "id": "ep-1",
                "showTitle": "Tech Talk",
                "episodeTitle": "Intro to Python",
                "episodeGuid": "guid-1",
                "feedUrl": "https://techtalk.example/feed",
                "listenedAt": "2026-03-20T10:00:00+00:00",
                "durationSeconds": 3600,
                "playedSeconds": 2700,
                "completed": False,
            }
        ])

        results = list(adapter.fetch(""))
        listen_items = [r for r in results if "listen" in r.source_id]
        metadata_dict = listen_items[0].structural_hints.extra_metadata

        assert metadata_dict["durationSeconds"] == 3600
        assert metadata_dict["playedSeconds"] == 2700
        assert metadata_dict["completed"] is False
        assert metadata_dict["episodeGuid"] == "guid-1"
        assert metadata_dict["feedUrl"] == "https://techtalk.example/feed"


class TestApplePodcastsAdapterFetchTranscripts:
    """Tests for ApplePodcastsAdapter.fetch() with transcripts."""

    def test_fetch_transcript_single_item(self, mock_all_podcasts_endpoints):
        """fetch() yields NormalizedContent for a single transcript item."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_podcasts_endpoints.set_response("http://127.0.0.1:7123/podcasts/transcripts", [
            {
                "id": "ep-1",
                "source": "podcasts",
                "showTitle": "Tech Talk",
                "episodeTitle": "Intro to Python",
                "episodeGuid": "guid-1",
                "publishedDate": "2026-03-01",
                "transcript": "Welcome to the podcast. Today we discuss Python.",
                "transcriptSource": "apple",
                "transcriptCreatedAt": "2026-03-15T12:00:00+00:00",
                "playStateTs": "2026-03-20T10:00:00+00:00",
                "durationSeconds": 3600,
            }
        ])

        results = list(adapter.fetch(""))
        transcript_items = [r for r in results if r.source_id == "podcasts/transcript/ep-1"]
        assert len(transcript_items) == 1
        item = transcript_items[0]
        assert isinstance(item, NormalizedContent)
        assert item.domain == Domain.DOCUMENTS
        assert "Intro to Python" in item.markdown
        assert "Welcome to the podcast" in item.markdown

    def test_fetch_transcript_multiple_items(self, mock_all_podcasts_endpoints):
        """fetch() yields NormalizedContent for multiple transcripts."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_podcasts_endpoints.set_response("http://127.0.0.1:7123/podcasts/transcripts", [
            {
                "id": "ep-1",
                "source": "podcasts",
                "showTitle": "Tech Talk",
                "episodeTitle": "Intro to Python",
                "episodeGuid": "guid-1",
                "publishedDate": "2026-03-01",
                "transcript": "Welcome to the podcast.",
                "transcriptSource": "apple",
                "transcriptCreatedAt": "2026-03-15T12:00:00+00:00",
                "playStateTs": "2026-03-20T10:00:00+00:00",
                "durationSeconds": 3600,
            },
            {
                "id": "ep-2",
                "source": "podcasts",
                "showTitle": "Science Hour",
                "episodeTitle": "Black Holes",
                "episodeGuid": "guid-2",
                "publishedDate": "2026-03-05",
                "transcript": "Today we discuss black holes.",
                "transcriptSource": "whisper",
                "transcriptCreatedAt": "2026-03-16T14:00:00+00:00",
                "playStateTs": "2026-03-21T14:30:00+00:00",
                "durationSeconds": 7200,
            },
        ])

        results = list(adapter.fetch(""))
        transcript_items = [r for r in results if "transcript" in r.source_id]
        assert len(transcript_items) == 2
        assert transcript_items[0].source_id == "podcasts/transcript/ep-1"
        assert transcript_items[1].source_id == "podcasts/transcript/ep-2"

    def test_fetch_transcript_empty_text_yields_nothing(self, mock_all_podcasts_endpoints):
        """fetch() skips transcripts with empty text (yields nothing for that item)."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_podcasts_endpoints.set_response("http://127.0.0.1:7123/podcasts/transcripts", [
            {
                "id": "ep-1",
                "source": "podcasts",
                "showTitle": "Tech Talk",
                "episodeTitle": "Episode 1",
                "episodeGuid": "guid-1",
                "publishedDate": "2026-03-01",
                "transcript": "",  # Empty
                "transcriptSource": "apple",
                "transcriptCreatedAt": "2026-03-15T12:00:00+00:00",
                "playStateTs": "2026-03-20T10:00:00+00:00",
                "durationSeconds": 3600,
            }
        ])

        results = list(adapter.fetch(""))
        transcript_items = [r for r in results if "transcript" in r.source_id]
        assert len(transcript_items) == 0

    def test_fetch_transcript_whitespace_only_yields_nothing(self, mock_all_podcasts_endpoints):
        """fetch() skips transcripts with only whitespace."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_podcasts_endpoints.set_response("http://127.0.0.1:7123/podcasts/transcripts", [
            {
                "id": "ep-1",
                "source": "podcasts",
                "showTitle": "Tech Talk",
                "episodeTitle": "Episode 1",
                "episodeGuid": "guid-1",
                "publishedDate": "2026-03-01",
                "transcript": "   \n  \t  ",  # Whitespace only
                "transcriptSource": "apple",
                "transcriptCreatedAt": "2026-03-15T12:00:00+00:00",
                "playStateTs": "2026-03-20T10:00:00+00:00",
                "durationSeconds": 3600,
            }
        ])

        results = list(adapter.fetch(""))
        transcript_items = [r for r in results if "transcript" in r.source_id]
        assert len(transcript_items) == 0

    def test_fetch_transcript_metadata_validation(self, mock_all_podcasts_endpoints):
        """fetch() produces DocumentMetadata that passes model_validate."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_podcasts_endpoints.set_response("http://127.0.0.1:7123/podcasts/transcripts", [
            {
                "id": "ep-1",
                "source": "podcasts",
                "showTitle": "Tech Talk",
                "episodeTitle": "Intro to Python",
                "episodeGuid": "guid-1",
                "publishedDate": "2026-03-01",
                "transcript": "Welcome to the podcast.",
                "transcriptSource": "apple",
                "transcriptCreatedAt": "2026-03-15T12:00:00+00:00",
                "playStateTs": "2026-03-20T10:00:00+00:00",
                "durationSeconds": 3600,
            }
        ])

        results = list(adapter.fetch(""))
        transcript_items = [r for r in results if "transcript" in r.source_id]
        metadata_dict = transcript_items[0].structural_hints.extra_metadata

        # This should not raise if DocumentMetadata validation passes
        metadata = DocumentMetadata.model_validate(metadata_dict)
        assert metadata.document_id == "ep-1"
        assert metadata.title == "Intro to Python"
        assert metadata.author == "Tech Talk"
        assert metadata.source_type == "podcast_transcript"
        assert metadata.document_type == "text/plain"

    def test_fetch_transcript_extra_metadata(self, mock_all_podcasts_endpoints):
        """fetch() includes extra metadata fields in transcripts."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_podcasts_endpoints.set_response("http://127.0.0.1:7123/podcasts/transcripts", [
            {
                "id": "ep-1",
                "source": "podcasts",
                "showTitle": "Tech Talk",
                "episodeTitle": "Intro to Python",
                "episodeGuid": "guid-1",
                "publishedDate": "2026-03-01",
                "transcript": "Welcome to the podcast.",
                "transcriptSource": "whisper",
                "transcriptCreatedAt": "2026-03-15T12:00:00+00:00",
                "playStateTs": "2026-03-20T10:00:00+00:00",
                "durationSeconds": 3600,
            }
        ])

        results = list(adapter.fetch(""))
        transcript_items = [r for r in results if "transcript" in r.source_id]
        metadata_dict = transcript_items[0].structural_hints.extra_metadata

        assert metadata_dict["transcriptSource"] == "whisper"
        assert metadata_dict["episodeGuid"] == "guid-1"
        assert metadata_dict["durationSeconds"] == 3600
        assert metadata_dict["playStateTs"] == "2026-03-20T10:00:00+00:00"


class TestApplePodcastsAdapterDualDomain:
    """Tests for ApplePodcastsAdapter dual-domain behavior."""

    def test_fetch_yields_both_listen_and_transcript(self, mock_all_podcasts_endpoints):
        """fetch() yields both listen history (EVENTS) and transcripts (DOCUMENTS)."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_podcasts_endpoints.set_response("http://127.0.0.1:7123/podcasts/listen-history", [
            {
                "id": "ep-1",
                "showTitle": "Tech Talk",
                "episodeTitle": "Intro to Python",
                "episodeGuid": "guid-1",
                "feedUrl": None,
                "listenedAt": "2026-03-20T10:00:00+00:00",
                "durationSeconds": 3600,
                "playedSeconds": 3600,
                "completed": True,
            }
        ])

        mock_all_podcasts_endpoints.set_response("http://127.0.0.1:7123/podcasts/transcripts", [
            {
                "id": "ep-1",
                "source": "podcasts",
                "showTitle": "Tech Talk",
                "episodeTitle": "Intro to Python",
                "episodeGuid": "guid-1",
                "publishedDate": "2026-03-01",
                "transcript": "Welcome to the podcast.",
                "transcriptSource": "apple",
                "transcriptCreatedAt": "2026-03-15T12:00:00+00:00",
                "playStateTs": "2026-03-20T10:00:00+00:00",
                "durationSeconds": 3600,
            }
        ])

        results = list(adapter.fetch(""))

        # Should have both listen and transcript
        listen_items = [r for r in results if "listen" in r.source_id]
        transcript_items = [r for r in results if "transcript" in r.source_id]

        assert len(listen_items) == 1
        assert len(transcript_items) == 1
        assert listen_items[0].domain == Domain.EVENTS
        assert transcript_items[0].domain == Domain.DOCUMENTS


class TestApplePodcastsAdapterErrorHandling:
    """Tests for ApplePodcastsAdapter error handling."""

    def test_fetch_partial_failure_listen_history_down(self, mock_podcasts_httpx_get):
        """fetch() raises PartialFetchError when listen-history endpoint fails but transcripts succeeds."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        # Listen history fails
        mock_podcasts_httpx_get.set_response("http://127.0.0.1:7123/podcasts/listen-history", [], status_code=500)

        # Transcripts succeeds
        mock_podcasts_httpx_get.set_response("http://127.0.0.1:7123/podcasts/transcripts", [
            {
                "id": "ep-1",
                "source": "podcasts",
                "showTitle": "Tech Talk",
                "episodeTitle": "Intro to Python",
                "episodeGuid": "guid-1",
                "publishedDate": "2026-03-01",
                "transcript": "Welcome.",
                "transcriptSource": "apple",
                "transcriptCreatedAt": "2026-03-15T12:00:00+00:00",
                "playStateTs": "2026-03-20T10:00:00+00:00",
                "durationSeconds": 3600,
            }
        ])

        with pytest.raises(PartialFetchError) as exc_info:
            list(adapter.fetch(""))

        assert "/podcasts/listen-history" in exc_info.value.failed_endpoints
        assert exc_info.value.total_endpoints == 2

    def test_fetch_partial_failure_transcripts_down(self, mock_podcasts_httpx_get):
        """fetch() raises PartialFetchError when transcripts endpoint fails but listen-history succeeds."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        # Listen history succeeds
        mock_podcasts_httpx_get.set_response("http://127.0.0.1:7123/podcasts/listen-history", [
            {
                "id": "ep-1",
                "showTitle": "Tech Talk",
                "episodeTitle": "Intro to Python",
                "episodeGuid": "guid-1",
                "feedUrl": None,
                "listenedAt": "2026-03-20T10:00:00+00:00",
                "durationSeconds": 3600,
                "playedSeconds": 3600,
                "completed": True,
            }
        ])

        # Transcripts fails
        mock_podcasts_httpx_get.set_response("http://127.0.0.1:7123/podcasts/transcripts", [], status_code=500)

        with pytest.raises(PartialFetchError) as exc_info:
            list(adapter.fetch(""))

        assert "/podcasts/transcripts" in exc_info.value.failed_endpoints
        assert exc_info.value.total_endpoints == 2

    def test_fetch_all_endpoints_failed(self, mock_podcasts_httpx_get):
        """fetch() raises AllEndpointsFailedError when all endpoints fail."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_podcasts_httpx_get.set_response("http://127.0.0.1:7123/podcasts/listen-history", [], status_code=500)
        mock_podcasts_httpx_get.set_response("http://127.0.0.1:7123/podcasts/transcripts", [], status_code=500)

        with pytest.raises(AllEndpointsFailedError) as exc_info:
            list(adapter.fetch(""))

        assert exc_info.value.total_endpoints == 2

    def test_fetch_missing_episode_title_skips_listen_item(self, mock_all_podcasts_endpoints):
        """fetch() skips listen history items with missing episodeTitle."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_podcasts_endpoints.set_response("http://127.0.0.1:7123/podcasts/listen-history", [
            {
                "id": "ep-1",
                "showTitle": "Tech Talk",
                # Missing episodeTitle
                "episodeGuid": "guid-1",
                "feedUrl": None,
                "listenedAt": "2026-03-20T10:00:00+00:00",
                "durationSeconds": 3600,
                "playedSeconds": 3600,
                "completed": True,
            }
        ])

        results = list(adapter.fetch(""))
        listen_items = [r for r in results if "listen" in r.source_id]
        assert len(listen_items) == 0

    def test_fetch_missing_episode_title_skips_transcript(self, mock_all_podcasts_endpoints):
        """fetch() skips transcripts with missing episodeTitle."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_podcasts_endpoints.set_response("http://127.0.0.1:7123/podcasts/transcripts", [
            {
                "id": "ep-1",
                "source": "podcasts",
                "showTitle": "Tech Talk",
                # Missing episodeTitle
                "episodeGuid": "guid-1",
                "publishedDate": "2026-03-01",
                "transcript": "Welcome.",
                "transcriptSource": "apple",
                "transcriptCreatedAt": "2026-03-15T12:00:00+00:00",
                "playStateTs": "2026-03-20T10:00:00+00:00",
                "durationSeconds": 3600,
            }
        ])

        results = list(adapter.fetch(""))
        transcript_items = [r for r in results if "transcript" in r.source_id]
        assert len(transcript_items) == 0

    def test_fetch_malformed_item_skipped_continues(self, mock_all_podcasts_endpoints):
        """fetch() skips malformed items and continues to next."""
        adapter = ApplePodcastsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_all_podcasts_endpoints.set_response("http://127.0.0.1:7123/podcasts/listen-history", [
            {
                "id": "ep-1",
                "showTitle": "Tech Talk",
                "episodeTitle": "Good Episode",
                "episodeGuid": "guid-1",
                "feedUrl": None,
                "listenedAt": "2026-03-20T10:00:00+00:00",
                "durationSeconds": 3600,
                "playedSeconds": 3600,
                "completed": True,
            },
            {
                "id": "ep-2",
                # Missing episodeTitle
                "showTitle": "Tech Talk",
                "episodeGuid": "guid-2",
                "feedUrl": None,
                "listenedAt": "2026-03-21T10:00:00+00:00",
                "durationSeconds": 3600,
                "playedSeconds": 3600,
                "completed": False,
            },
            {
                "id": "ep-3",
                "showTitle": "Science Hour",
                "episodeTitle": "Another Good Episode",
                "episodeGuid": "guid-3",
                "feedUrl": None,
                "listenedAt": "2026-03-22T10:00:00+00:00",
                "durationSeconds": 7200,
                "playedSeconds": 7200,
                "completed": True,
            },
        ])

        results = list(adapter.fetch(""))
        listen_items = [r for r in results if "listen" in r.source_id]
        assert len(listen_items) == 2
        assert listen_items[0].source_id == "podcasts/listen/ep-1"
        assert listen_items[1].source_id == "podcasts/listen/ep-3"
