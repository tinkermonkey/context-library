"""Tests for the AppleMusicAdapter."""

import pytest

from context_library.adapters.apple_music import AppleMusicAdapter
from context_library.storage.models import Domain, PollStrategy, NormalizedContent, DocumentMetadata


class TestAppleMusicAdapterInitialization:
    """Tests for AppleMusicAdapter initialization."""

    def test_init_default_parameters(self):
        """__init__ uses default parameters when not provided."""
        adapter = AppleMusicAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"
        assert adapter._api_key == "test-token"
        assert adapter._device_id == "default"

    def test_init_requires_api_key(self):
        """__init__ raises ValueError when api_key is empty."""
        with pytest.raises(ValueError, match="api_key is required"):
            AppleMusicAdapter(api_url="http://127.0.0.1:7123", api_key="")

    def test_init_custom_parameters(self):
        """__init__ accepts and stores custom parameters."""
        adapter = AppleMusicAdapter(
            api_url="http://localhost:8000",
            api_key="test_key",
            device_id="macbook-pro-m1",
        )
        assert adapter._api_url == "http://localhost:8000"
        assert adapter._api_key == "test_key"
        assert adapter._device_id == "macbook-pro-m1"

    def test_init_strips_trailing_slash_from_url(self):
        """__init__ strips trailing slash from api_url."""
        adapter = AppleMusicAdapter(api_url="http://127.0.0.1:7123/", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"

    def test_init_no_trailing_slash(self):
        """__init__ leaves api_url unchanged if no trailing slash."""
        adapter = AppleMusicAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"


class TestAppleMusicAdapterProperties:
    """Tests for AppleMusicAdapter properties."""

    def test_adapter_id_format_default(self):
        """adapter_id has correct format: apple_music:{device_id}."""
        adapter = AppleMusicAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.adapter_id == "apple_music:default"

    def test_adapter_id_format_custom_device(self):
        """adapter_id uses custom device_id."""
        adapter = AppleMusicAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test-token",
            device_id="macbook-pro-m1"
        )
        assert adapter.adapter_id == "apple_music:macbook-pro-m1"

    def test_adapter_id_distinct_from_apple_music_library_adapter(self):
        """adapter_id is distinct from AppleMusicLibraryAdapter's apple_music_library:{device_id}."""
        adapter = AppleMusicAdapter(api_url="http://127.0.0.1:7123", api_key="test-token", device_id="device-1")
        # AppleMusicLibraryAdapter would have "apple_music_library:device-1"
        assert adapter.adapter_id == "apple_music:device-1"
        assert not adapter.adapter_id.startswith("apple_music_library:")

    def test_adapter_id_deterministic(self):
        """adapter_id is deterministic for the same configuration."""
        adapter1 = AppleMusicAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test-token",
            device_id="device-1"
        )
        adapter2 = AppleMusicAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test-token",
            device_id="device-1"
        )
        assert adapter1.adapter_id == adapter2.adapter_id

    def test_different_devices_different_ids(self):
        """Different device IDs produce different adapter_ids."""
        adapter1 = AppleMusicAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test-token",
            device_id="mac-1"
        )
        adapter2 = AppleMusicAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test-token",
            device_id="mac-2"
        )
        assert adapter1.adapter_id != adapter2.adapter_id

    def test_domain_property(self):
        """domain property returns Domain.DOCUMENTS."""
        adapter = AppleMusicAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.domain == Domain.DOCUMENTS

    def test_poll_strategy_property(self):
        """poll_strategy property returns PollStrategy.PULL."""
        adapter = AppleMusicAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.poll_strategy == PollStrategy.PULL

    def test_normalizer_version_property(self):
        """normalizer_version property returns '1.0.0'."""
        adapter = AppleMusicAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.normalizer_version == "1.0.0"


class TestAppleMusicAdapterFetch:
    """Tests for AppleMusicAdapter.fetch() method."""

    def test_fetch_single_track(self, mock_apple_music_endpoints):
        """fetch() yields NormalizedContent for a single track."""
        adapter = AppleMusicAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
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
        assert results[0].source_id == "music/track-1"
        assert "Bohemian Rhapsody" in results[0].markdown
        assert "Queen" in results[0].markdown
        assert results[0].domain == Domain.DOCUMENTS

    def test_fetch_multiple_tracks(self, mock_apple_music_endpoints):
        """fetch() yields NormalizedContent for multiple tracks."""
        adapter = AppleMusicAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
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
        assert results[0].source_id == "music/track-1"
        assert results[1].source_id == "music/track-2"

    def test_fetch_incremental_with_since(self, mock_apple_music_endpoints):
        """fetch() passes 'since' query parameter for incremental fetch."""
        adapter = AppleMusicAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        list(adapter.fetch("2026-03-06T10:00:00Z"))

        # Verify the request was made with the 'since' parameter
        request = mock_apple_music_endpoints.requests[0]
        assert request["params"]["since"] == "2026-03-06T10:00:00Z"

    def test_fetch_with_api_key_auth(self, mock_apple_music_endpoints):
        """fetch() sends Authorization header when api_key is provided."""
        adapter = AppleMusicAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test_token_123"
        )

        list(adapter.fetch(""))

        # Verify the request was made with Authorization header
        request = mock_apple_music_endpoints.requests[0]
        assert request["headers"]["Authorization"] == "Bearer test_token_123"

    def test_fetch_document_metadata_contains_required_fields(self, mock_apple_music_endpoints):
        """fetch() produces DocumentMetadata that passes model_validate."""
        adapter = AppleMusicAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Bohemian Rhapsody",
                "artist": "Queen",
                "album": "A Night at the Opera",
                "genre": "Rock",
                "duration_seconds": 354,
                "play_count": 42,
            }
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 1

        extra_metadata = results[0].structural_hints.extra_metadata
        assert extra_metadata["document_id"] == "track-1"
        assert extra_metadata["title"] == "Bohemian Rhapsody"
        assert extra_metadata["author"] == "Queen"
        assert extra_metadata["album"] == "A Night at the Opera"
        assert extra_metadata["genre"] == "Rock"
        assert extra_metadata["duration_minutes"] == 5
        assert extra_metadata["play_count"] == 42
        assert extra_metadata["source_type"] == "apple_music"
        assert extra_metadata["document_type"] == "audio/mpeg"

        # Verify DocumentMetadata validation passes
        DocumentMetadata.model_validate(extra_metadata)

    def test_fetch_with_null_optional_fields(self, mock_apple_music_endpoints):
        """fetch() handles null values for optional fields."""
        adapter = AppleMusicAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Untitled",
                "artist": None,
                "album": None,
                "genre": None,
                "duration_seconds": None,
                "play_count": 0,
            }
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 1
        assert "Untitled" in results[0].markdown
        assert results[0].structural_hints.extra_metadata["duration_minutes"] is None

    def test_fetch_empty_response(self, mock_apple_music_endpoints):
        """fetch() handles empty track list."""
        adapter = AppleMusicAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [])

        results = list(adapter.fetch(""))
        assert len(results) == 0

    def test_fetch_skips_malformed_track(self, mock_apple_music_endpoints):
        """fetch() skips malformed track and continues with next."""
        adapter = AppleMusicAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Valid Track",
                "artist": "Artist",
                "duration_seconds": 180,
                "play_count": 5,
            },
            {
                "id": "track-2",
                # Missing required 'title' field
                "artist": "Bad Artist",
            },
            {
                "id": "track-3",
                "title": "Another Valid Track",
                "artist": "Another Artist",
                "duration_seconds": 240,
                "play_count": 3,
            },
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 2
        assert results[0].source_id == "music/track-1"
        assert results[1].source_id == "music/track-3"

    def test_fetch_authorization_error_propagates(self, mock_apple_music_endpoints):
        """fetch() propagates HTTP 401 auth errors."""
        adapter = AppleMusicAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="invalid-token"
        )

        mock_apple_music_endpoints.set_status("http://127.0.0.1:7123/music/tracks", 401)

        with pytest.raises(Exception):  # httpx.HTTPStatusError
            list(adapter.fetch(""))

    def test_fetch_invalid_json_response(self, mock_apple_music_endpoints):
        """fetch() raises error when API returns invalid JSON."""
        adapter = AppleMusicAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_endpoints.set_raw_response("http://127.0.0.1:7123/music/tracks", "<html>error</html>", "text/html")

        with pytest.raises(Exception):  # json.JSONDecodeError or ValueError
            list(adapter.fetch(""))

    def test_fetch_only_yields_documents_domain(self, mock_apple_music_endpoints):
        """fetch() only yields DOCUMENTS domain content, never EVENTS."""
        adapter = AppleMusicAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        mock_apple_music_endpoints.set_response("http://127.0.0.1:7123/music/tracks", [
            {
                "id": "track-1",
                "title": "Song With Play Event",
                "artist": "Artist",
                "played_at": "2026-03-06T10:00:00Z",  # Has play event data
                "duration_seconds": 180,
                "play_count": 5,
            }
        ])

        results = list(adapter.fetch(""))
        # AppleMusicAdapter should only yield 1 item (documents), not 2 (documents + events)
        assert len(results) == 1
        assert results[0].domain == Domain.DOCUMENTS


class TestAppleMusicAdapterImportGuard:
    """Tests for AppleMusicAdapter import guard."""

    def test_import_error_without_httpx(self, monkeypatch):
        """AppleMusicAdapter raises ImportError if httpx is not installed."""
        monkeypatch.setattr("context_library.adapters.apple_music.HAS_HTTPX", False)

        with pytest.raises(ImportError, match="httpx is required"):
            AppleMusicAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")


class TestAppleMusicAdapterImportability:
    """Tests for AppleMusicAdapter importability."""

    def test_importable_from_context_library_adapters(self):
        """AppleMusicAdapter is importable from context_library.adapters."""
        from context_library.adapters import AppleMusicAdapter as ImportedAdapter
        assert ImportedAdapter is AppleMusicAdapter

    def test_adapter_in_registry(self):
        """AppleMusicAdapter is registered in the adapter registry."""
        from context_library.config.loader import _instantiate_local_adapter
        from context_library.config.models import LocalAdapterConfig, Domain

        # This should not raise an error
        config = LocalAdapterConfig(
            adapter_type="apple_music",
            adapter_id="apple_music:test",
            domain=Domain.DOCUMENTS,
            config={"api_url": "http://test:7123", "api_key": "test-key", "device_id": "test"},
        )

        adapter = _instantiate_local_adapter(config)
        assert isinstance(adapter, AppleMusicAdapter)
        assert adapter.adapter_id == "apple_music:test"
