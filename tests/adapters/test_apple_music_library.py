"""Tests for the AppleMusicLibraryAdapter."""

import pytest

from context_library.adapters.apple_music_library import AppleMusicLibraryAdapter
from context_library.storage.models import Domain, PollStrategy, NormalizedContent, DocumentMetadata


class TestAppleMusicLibraryAdapterInitialization:
    """Tests for AppleMusicLibraryAdapter initialization."""

    def test_init_default_parameters(self):
        """__init__ uses default parameters when not provided."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"
        assert adapter._api_key == "test-token"
        assert adapter._device_id == "default"

    def test_init_requires_api_key(self):
        """__init__ raises ValueError when api_key is empty."""
        with pytest.raises(ValueError, match="api_key is required"):
            AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="")

    def test_init_custom_parameters(self):
        """__init__ accepts and stores custom parameters."""
        adapter = AppleMusicLibraryAdapter(
            api_url="http://localhost:8000",
            api_key="test_key",
            device_id="macbook-pro-m1",
        )
        assert adapter._api_url == "http://localhost:8000"
        assert adapter._api_key == "test_key"
        assert adapter._device_id == "macbook-pro-m1"

    def test_init_strips_trailing_slash_from_url(self):
        """__init__ strips trailing slash from api_url."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123/", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"

    def test_init_no_trailing_slash(self):
        """__init__ leaves api_url unchanged if no trailing slash."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"


class TestAppleMusicLibraryAdapterProperties:
    """Tests for AppleMusicLibraryAdapter properties."""

    def test_adapter_id_format_default(self):
        """adapter_id has correct format: apple_music_library:{device_id}."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.adapter_id == "apple_music_library:default"

    def test_adapter_id_format_custom_device(self):
        """adapter_id uses custom device_id."""
        adapter = AppleMusicLibraryAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test-token",
            device_id="macbook-pro-m1"
        )
        assert adapter.adapter_id == "apple_music_library:macbook-pro-m1"

    def test_adapter_id_distinct_from_apple_music_adapter(self):
        """adapter_id is distinct from AppleMusicAdapter's apple_music:{device_id}."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token", device_id="device-1")
        # AppleMusicAdapter would have "apple_music:device-1"
        assert adapter.adapter_id == "apple_music_library:device-1"
        assert not adapter.adapter_id.startswith("apple_music:")

    def test_adapter_id_deterministic(self):
        """adapter_id is deterministic for the same configuration."""
        adapter1 = AppleMusicLibraryAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test-token",
            device_id="device-1"
        )
        adapter2 = AppleMusicLibraryAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test-token",
            device_id="device-1"
        )
        assert adapter1.adapter_id == adapter2.adapter_id

    def test_different_devices_different_ids(self):
        """Different device IDs produce different adapter_ids."""
        adapter1 = AppleMusicLibraryAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test-token",
            device_id="mac-1"
        )
        adapter2 = AppleMusicLibraryAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test-token",
            device_id="mac-2"
        )
        assert adapter1.adapter_id != adapter2.adapter_id

    def test_domain_property(self):
        """domain property returns Domain.DOCUMENTS."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.domain == Domain.DOCUMENTS

    def test_poll_strategy_property(self):
        """poll_strategy property returns PollStrategy.PULL."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.poll_strategy == PollStrategy.PULL

    def test_normalizer_version_property(self):
        """normalizer_version property returns '1.0.0'."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.normalizer_version == "1.0.0"


class TestAppleMusicLibraryAdapterFetch:
    """Tests for AppleMusicLibraryAdapter.fetch() method."""

    def test_fetch_single_track(self, mock_apple_music_library_endpoints):
        """fetch() yields NormalizedContent for a single track."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Bohemian Rhapsody",
                "artist": "Queen",
                "album": "A Night at the Opera",
                "duration_seconds": 354,
                "play_count": 42,
            }
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 1
        assert isinstance(results[0], NormalizedContent)
        assert results[0].source_id == "music/library/track-1"
        assert "Bohemian Rhapsody" in results[0].markdown
        assert "Queen" in results[0].markdown

    def test_fetch_multiple_tracks(self, mock_apple_music_library_endpoints):
        """fetch() yields NormalizedContent for multiple tracks."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Bohemian Rhapsody",
                "artist": "Queen",
                "album": "A Night at the Opera",
                "duration_seconds": 354,
                "play_count": 42,
            },
            {
                "id": "track-2",
                "title": "Stairway to Heaven",
                "artist": "Led Zeppelin",
                "album": "Led Zeppelin IV",
                "duration_seconds": 482,
                "play_count": 38,
            },
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 2
        assert results[0].source_id == "music/library/track-1"
        assert results[1].source_id == "music/library/track-2"

    def test_fetch_incremental_with_since(self, mock_apple_music_library_endpoints):
        """fetch() passes 'since' query parameter for incremental fetch."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        list(adapter.fetch("2026-03-06T10:00:00Z"))

        # Verify the request was made with the 'since' parameter
        request = mock_apple_music_library_endpoints.requests[0]
        assert request["params"]["since"] == "2026-03-06T10:00:00Z"

    def test_fetch_with_api_key_auth(self, mock_apple_music_library_endpoints):
        """fetch() sends Authorization header when api_key is provided."""
        adapter = AppleMusicLibraryAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test_token_123"
        )

        list(adapter.fetch(""))

        # Verify the request was made with Authorization header
        request = mock_apple_music_library_endpoints.requests[0]
        assert request["headers"]["Authorization"] == "Bearer test_token_123"

    def test_fetch_document_metadata_contains_required_fields(self, mock_apple_music_library_endpoints):
        """fetch() produces DocumentMetadata that passes model_validate."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Bohemian Rhapsody",
                "artist": "Queen",
                "album": "A Night at the Opera",
                "duration_seconds": 354,
                "play_count": 42,
            }
        ])

        results = list(adapter.fetch(""))
        metadata_dict = results[0].structural_hints.extra_metadata

        # This should not raise if DocumentMetadata validation passes
        metadata = DocumentMetadata.model_validate(metadata_dict)
        assert metadata.document_id == "track-1"
        assert metadata.title == "Bohemian Rhapsody"
        assert metadata.source_type == "apple_music"
        assert metadata.document_type == "audio/mpeg"
        assert metadata.author == "Queen"

    def test_fetch_extra_metadata_contains_music_fields(self, mock_apple_music_library_endpoints):
        """fetch() includes music-specific fields in extra_metadata."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Bohemian Rhapsody",
                "artist": "Queen",
                "album": "A Night at the Opera",
                "duration_seconds": 354,
                "play_count": 42,
            }
        ])

        results = list(adapter.fetch(""))
        metadata_dict = results[0].structural_hints.extra_metadata

        # Check that music-specific fields are present
        assert metadata_dict["album"] == "A Night at the Opera"
        assert metadata_dict["play_count"] == 42
        assert metadata_dict["duration_minutes"] == 5  # 354 // 60

    def test_fetch_source_id_format(self, mock_apple_music_library_endpoints):
        """fetch() generates source_id with format music/library/{track_id}."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "spotify-12345",
                "title": "Song Title",
                "artist": "Artist Name",
                "album": "Album Name",
                "duration_seconds": 180,
                "play_count": 1,
            }
        ])

        results = list(adapter.fetch(""))
        # AppleMusicLibraryAdapter uses music/library/{track_id}, not music/{track_id}
        assert results[0].source_id == "music/library/spotify-12345"

    def test_fetch_optional_fields_can_be_null(self, mock_apple_music_library_endpoints):
        """fetch() handles null values for optional music fields."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Unknown Song",
                "artist": None,
                "album": None,
                "duration_seconds": None,
                "play_count": 1,
            }
        ])

        results = list(adapter.fetch(""))
        metadata_dict = results[0].structural_hints.extra_metadata

        # Should validate even with None values
        metadata = DocumentMetadata.model_validate(metadata_dict)
        assert metadata.document_id == "track-1"
        assert metadata.author is None  # artist is None
        assert metadata_dict["album"] is None
        assert metadata_dict["duration_minutes"] is None

    def test_fetch_missing_id_field_skips_track(self, mock_apple_music_library_endpoints):
        """fetch() skips and logs tracks with missing 'id' field."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                # Missing 'id'
                "title": "Song Title",
                "artist": "Artist",
                "album": "Album",
                "duration_seconds": 180,
                "play_count": 1,
            }
        ])

        # Should not raise, just skip the malformed track
        results = list(adapter.fetch(""))
        assert len(results) == 0

    def test_fetch_missing_title_field_skips_track(self, mock_apple_music_library_endpoints):
        """fetch() skips and logs tracks with missing 'title' field."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                # Missing 'title'
                "artist": "Artist",
                "album": "Album",
                "duration_seconds": 180,
                "play_count": 1,
            }
        ])

        # Should not raise, just skip the malformed track
        results = list(adapter.fetch(""))
        assert len(results) == 0

    def test_fetch_empty_id_skips_track(self, mock_apple_music_library_endpoints):
        """fetch() skips and logs tracks with empty 'id'."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "",  # Empty
                "title": "Song Title",
                "artist": "Artist",
                "album": "Album",
                "duration_seconds": 180,
                "play_count": 1,
            }
        ])

        # Should not raise, just skip the malformed track
        results = list(adapter.fetch(""))
        assert len(results) == 0

    def test_fetch_empty_title_skips_track(self, mock_apple_music_library_endpoints):
        """fetch() skips and logs tracks with empty title."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "",  # Empty
                "artist": "Artist",
                "album": "Album",
                "duration_seconds": 180,
                "play_count": 1,
            }
        ])

        # Should not raise, just skip the malformed track
        results = list(adapter.fetch(""))
        assert len(results) == 0

    def test_fetch_malformed_track_skipped_continues(self, mock_apple_music_library_endpoints):
        """fetch() skips malformed tracks and continues to next."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Good Song",
                "artist": "Artist 1",
                "album": "Album 1",
                "duration_seconds": 180,
                "play_count": 1,
            },
            {
                "id": "",  # Malformed
                "title": "Bad Song",
                "artist": "Artist 2",
                "album": "Album 2",
                "duration_seconds": 200,
                "play_count": 2,
            },
            {
                "id": "track-3",
                "title": "Good Song 2",
                "artist": "Artist 3",
                "album": "Album 3",
                "duration_seconds": 250,
                "play_count": 3,
            },
        ])

        results = list(adapter.fetch(""))
        # Should have 2 results, skipping the malformed one in the middle
        assert len(results) == 2
        assert results[0].source_id == "music/library/track-1"
        assert results[1].source_id == "music/library/track-3"

    def test_fetch_artist_maps_to_author_in_metadata(self, mock_apple_music_library_endpoints):
        """fetch() maps track 'artist' to DocumentMetadata 'author' field."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Song",
                "artist": "The Beatles",
                "album": "Abbey Road",
                "duration_seconds": 200,
                "play_count": 10,
            }
        ])

        results = list(adapter.fetch(""))
        metadata_dict = results[0].structural_hints.extra_metadata

        # Verify artist is mapped to author
        assert metadata_dict["author"] == "The Beatles"
        metadata = DocumentMetadata.model_validate(metadata_dict)
        assert metadata.author == "The Beatles"

    def test_fetch_document_type_defaults_to_audio_mpeg(self, mock_apple_music_library_endpoints):
        """fetch() sets document_type to 'audio/mpeg' for all tracks."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Song",
                "artist": "Artist",
                "album": "Album",
                "duration_seconds": 200,
                "play_count": 1,
            }
        ])

        results = list(adapter.fetch(""))
        metadata_dict = results[0].structural_hints.extra_metadata

        assert metadata_dict["document_type"] == "audio/mpeg"

    def test_fetch_markdown_includes_title(self, mock_apple_music_library_endpoints):
        """Generated markdown includes track title in bold."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Bohemian Rhapsody",
                "artist": "Queen",
                "album": "A Night at the Opera",
                "duration_seconds": 354,
                "play_count": 42,
            }
        ])

        results = list(adapter.fetch(""))
        assert "**Bohemian Rhapsody**" in results[0].markdown

    def test_fetch_markdown_includes_artist_when_present(self, mock_apple_music_library_endpoints):
        """Generated markdown includes artist when available."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Song",
                "artist": "Queen",
                "album": "Album",
                "duration_seconds": 200,
                "play_count": 1,
            }
        ])

        results = list(adapter.fetch(""))
        assert "Artist: Queen" in results[0].markdown

    def test_fetch_markdown_excludes_artist_when_null(self, mock_apple_music_library_endpoints):
        """Generated markdown excludes artist when null."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Unknown Song",
                "artist": None,
                "album": None,
                "duration_seconds": 200,
                "play_count": 1,
            }
        ])

        results = list(adapter.fetch(""))
        assert "Artist:" not in results[0].markdown

    def test_fetch_markdown_includes_album_when_present(self, mock_apple_music_library_endpoints):
        """Generated markdown includes album when available."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Song",
                "artist": "Artist",
                "album": "Greatest Hits",
                "duration_seconds": 200,
                "play_count": 1,
            }
        ])

        results = list(adapter.fetch(""))
        assert "Album: Greatest Hits" in results[0].markdown

    def test_fetch_markdown_excludes_album_when_null(self, mock_apple_music_library_endpoints):
        """Generated markdown excludes album when null."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Song",
                "artist": "Artist",
                "album": None,
                "duration_seconds": 200,
                "play_count": 1,
            }
        ])

        results = list(adapter.fetch(""))
        assert "Album:" not in results[0].markdown

    def test_fetch_markdown_includes_duration_when_present(self, mock_apple_music_library_endpoints):
        """Generated markdown includes duration in minutes when available."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Song",
                "artist": "Artist",
                "album": "Album",
                "duration_seconds": 354,
                "play_count": 1,
            }
        ])

        results = list(adapter.fetch(""))
        # 354 // 60 = 5 minutes
        assert "Duration: 5 min" in results[0].markdown

    def test_fetch_markdown_excludes_duration_when_null(self, mock_apple_music_library_endpoints):
        """Generated markdown excludes duration when null."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Song",
                "artist": "Artist",
                "album": "Album",
                "duration_seconds": None,
                "play_count": 1,
            }
        ])

        results = list(adapter.fetch(""))
        assert "Duration:" not in results[0].markdown

    def test_fetch_markdown_includes_play_count(self, mock_apple_music_library_endpoints):
        """Generated markdown includes play count."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Favorite Song",
                "artist": "Artist",
                "album": "Album",
                "duration_seconds": 200,
                "play_count": 99,
            }
        ])

        results = list(adapter.fetch(""))
        assert "Play count: 99" in results[0].markdown

    def test_fetch_structural_hints_has_headings_false(self, mock_apple_music_library_endpoints):
        """StructuralHints.has_headings is False (no heading-level markers in markdown)."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Song",
                "artist": "Artist",
                "album": "Album",
                "duration_seconds": 200,
                "play_count": 1,
            }
        ])

        results = list(adapter.fetch(""))
        content = results[0]

        # Verify has_headings is False because markdown uses **bold** not # headings
        assert content.structural_hints.has_headings is False
        assert not content.markdown.startswith("#")
        assert "\n#" not in content.markdown

    def test_fetch_structural_hints_has_lists_true(self, mock_apple_music_library_endpoints):
        """StructuralHints.has_lists is True (markdown uses list markers)."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Song",
                "artist": "Artist",
                "album": "Album",
                "duration_seconds": 200,
                "play_count": 1,
            }
        ])

        results = list(adapter.fetch(""))
        content = results[0]

        # Verify has_lists is True because markdown contains bullet points
        assert content.structural_hints.has_lists is True


    def test_fetch_duration_zero_produces_zero_not_none(self, mock_apple_music_library_endpoints):
        """fetch() produces duration_minutes=0 when duration_seconds=0, not None."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Silence",
                "artist": "John Cage",
                "album": "4'33",
                "duration_seconds": 0,  # Edge case: zero duration
                "play_count": 5,
            }
        ])

        results = list(adapter.fetch(""))
        metadata_dict = results[0].structural_hints.extra_metadata

        # Should produce 0, not None
        assert metadata_dict["duration_minutes"] == 0
        assert metadata_dict["duration_minutes"] is not None

    def test_fetch_missing_play_count_defaults_to_zero(self, mock_apple_music_library_endpoints):
        """fetch() defaults play_count to 0 when absent from track data."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Never Played",
                "artist": "Unknown",
                "album": "Never Played Album",
                "duration_seconds": 180,
                # play_count is absent
            }
        ])

        results = list(adapter.fetch(""))
        metadata_dict = results[0].structural_hints.extra_metadata

        # Should default to 0, not 1
        assert metadata_dict["play_count"] == 0


    def test_fetch_date_first_observed_not_set_by_adapter(self, mock_apple_music_library_endpoints):
        """fetch() does not set date_first_observed in metadata (storage layer manages it)."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Song",
                "artist": "Artist",
                "album": "Album",
                "duration_seconds": 200,
                "play_count": 1,
            }
        ])

        results = list(adapter.fetch(""))
        metadata_dict = results[0].structural_hints.extra_metadata

        # Should be None (not set by adapter)
        assert metadata_dict.get("date_first_observed") is None

    def test_fetch_string_duration_seconds_skips_track(self, mock_apple_music_library_endpoints):
        """fetch() skips track if duration_seconds is a string (TypeError) and continues."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Good Song",
                "artist": "Artist 1",
                "album": "Album 1",
                "duration_seconds": 180,
                "play_count": 1,
            },
            {
                "id": "track-2",
                "title": "Bad Song",
                "artist": "Artist 2",
                "album": "Album 2",
                "duration_seconds": "180",  # String instead of int - TypeError
                "play_count": 2,
            },
            {
                "id": "track-3",
                "title": "Good Song 2",
                "artist": "Artist 3",
                "album": "Album 3",
                "duration_seconds": 250,
                "play_count": 3,
            },
        ])

        results = list(adapter.fetch(""))
        # Should have 2 results, skipping the one with string duration_seconds
        assert len(results) == 2
        assert results[0].source_id == "music/library/track-1"
        assert results[1].source_id == "music/library/track-3"

    def test_fetch_track_element_not_dict_skips_track(self, mock_apple_music_library_endpoints):
        """fetch() skips track if track element is not a dict (TypeError) and continues."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Good Song",
                "artist": "Artist 1",
                "album": "Album 1",
                "duration_seconds": 180,
                "play_count": 1,
            },
            "not-a-dict",  # This will cause TypeError when accessing track["id"]
            {
                "id": "track-3",
                "title": "Good Song 2",
                "artist": "Artist 3",
                "album": "Album 3",
                "duration_seconds": 250,
                "play_count": 3,
            },
        ])

        results = list(adapter.fetch(""))
        # Should have 2 results, skipping the string element
        assert len(results) == 2
        assert results[0].source_id == "music/library/track-1"
        assert results[1].source_id == "music/library/track-3"

    def test_fetch_http_401_error_propagates(self, mock_apple_music_library_endpoints):
        """fetch() immediately re-raises HTTP 401 (auth) errors without skipping."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="invalid-token")

        mock_apple_music_library_endpoints.set_response(
            "http://127.0.0.1:7123/music/tracks",
            {"error": "Unauthorized"},
            status_code=401,
        )

        import httpx
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            list(adapter.fetch(""))

        assert exc_info.value.response.status_code == 401

    def test_fetch_http_403_error_propagates(self, mock_apple_music_library_endpoints):
        """fetch() immediately re-raises HTTP 403 (forbidden) errors without skipping."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response(
            "http://127.0.0.1:7123/music/tracks",
            {"error": "Forbidden"},
            status_code=403,
        )

        import httpx
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            list(adapter.fetch(""))

        assert exc_info.value.response.status_code == 403

    def test_fetch_http_500_error_propagates(self, mock_apple_music_library_endpoints):
        """fetch() re-raises HTTP 500 errors."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response(
            "http://127.0.0.1:7123/music/tracks",
            {"error": "Internal Server Error"},
            status_code=500,
        )

        import httpx
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            list(adapter.fetch(""))

        assert exc_info.value.response.status_code == 500


    def test_fetch_non_list_response_raises_value_error(self, mock_apple_music_library_endpoints):
        """fetch() raises ValueError if API response is not a list."""
        adapter = AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_library_endpoints.set_response(
            "http://127.0.0.1:7123/music/tracks",
            {"error": "unexpected response format"}  # dict instead of list
        )

        with pytest.raises(ValueError, match="must be a list"):
            list(adapter.fetch(""))


class TestAppleMusicLibraryAdapterImportGuard:
    """Tests for import guard and error handling."""

    def test_import_error_without_httpx(self, monkeypatch):
        """AppleMusicLibraryAdapter raises ImportError if httpx is not installed."""
        monkeypatch.setattr(
            "context_library.adapters.apple_music_base.HAS_HTTPX",
            False
        )

        with pytest.raises(ImportError, match="httpx is required"):
            AppleMusicLibraryAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
