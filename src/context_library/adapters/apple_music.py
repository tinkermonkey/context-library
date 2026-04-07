"""AppleMusicAdapter — ingests Apple Music library data from a macOS helper service.

This adapter handles the Apple Music library catalog as persistent documents,
mapping tracks to DOCUMENTS domain with music-specific metadata.

Expected Local Service API Contract:
====================================

  GET /music/tracks
    Query parameters:
      - since (optional): ISO 8601 timestamp; only tracks last played after this time

    Response: JSON array of track objects
    [
      {
        "id": "<string>",
        "title": "<string>",
        "artist": "<string | null>",
        "album": "<string | null>",
        "played_at": "<ISO 8601>",
        "duration_seconds": <int | null>,
        "play_count": <int>
      }
    ]

Security:
  A Bearer API token is REQUIRED: Authorization: Bearer <api_key>
"""

import logging
from typing import Any, Iterator

from context_library.adapters.base import BaseAdapter, EndpointFetchError
from context_library.adapters.apple_music_base import AppleMusicBaseMixin
from context_library.storage.models import (
    Domain,
    DocumentMetadata,
    NormalizedContent,
    PollStrategy,
    StructuralHints,
)

logger = logging.getLogger(__name__)


class AppleMusicAdapter(AppleMusicBaseMixin, BaseAdapter):
    """Adapter that ingests Apple Music library catalog from a macOS helper service.

    Treats the music library as a persistent document collection, with each track
    as a document in the catalog. Yields DOCUMENTS domain content only.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        device_id: str = "default",
    ) -> None:
        """Initialize AppleMusicAdapter.

        Args:
            api_url: Base URL of the macOS helper API (e.g., "http://192.168.1.50:7123")
            api_key: Required bearer token for API authentication
            device_id: Device identifier for adapter_id generation (default: "default")

        Raises:
            ImportError: If httpx is not installed.
            ValueError: If api_key is empty.
        """
        if not api_key:
            raise ValueError("api_key is required for AppleMusicAdapter")

        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._device_id = device_id
        self._init_httpx_client()

    @property
    def adapter_id(self) -> str:
        return f"apple_music:{self._device_id}"

    @property
    def domain(self) -> Domain:
        return Domain.DOCUMENTS

    @property
    def poll_strategy(self) -> PollStrategy:
        return PollStrategy.PULL

    @property
    def normalizer_version(self) -> str:
        return "1.0.0"

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize Apple Music library catalog from the macOS helper API.

        Errors in track processing (schema mismatches, missing fields) are caught
        and logged; the adapter continues processing remaining tracks. If all tracks
        are malformed, raises EndpointFetchError to signal complete failure.

        Args:
            source_ref: ISO 8601 timestamp for incremental ingestion, or empty string for initial

        Yields:
            NormalizedContent for each track in the library

        Raises:
            httpx.HTTPStatusError: If the API request fails (auth errors 401/403 propagate immediately)
            httpx.RequestError: If a network error occurs
            json.JSONDecodeError: If the API returns invalid JSON
            ValueError: If the helper API returns unexpected response schema
            EndpointFetchError: If all tracks are malformed and none can be processed
        """
        since = source_ref if source_ref else None
        tracks = self._fetch_tracks(self._api_url, self._api_key, since)

        successful_count = 0
        for idx, track in enumerate(tracks):
            try:
                yield self._process_track(track)
                successful_count += 1
            except (ValueError, KeyError, TypeError) as e:
                track_id = track.get("id", f"<index {idx}>") if isinstance(track, dict) else f"<index {idx}>"
                logger.error(f"Skipping malformed track (ID: {track_id}): {e}")
                continue

        # If all tracks were malformed, signal complete failure
        if tracks and successful_count == 0:
            raise EndpointFetchError(
                f"All {len(tracks)} tracks from /music/tracks were malformed and could not be processed. "
                "This may indicate a helper API schema change or malformed response."
            )

    def _process_track(self, track: dict[str, Any]) -> NormalizedContent:
        """Process a single track and yield a DOCUMENTS NormalizedContent.

        Args:
            track: Track dictionary from the API

        Returns:
            NormalizedContent for the track document

        Raises:
            KeyError: If required fields are missing
            ValueError: If fields fail validation
        """
        track_id = track["id"]
        if not track_id:
            raise ValueError("Track 'id' must not be empty")

        title = track["title"]
        if not title:
            raise ValueError("Track 'title' must not be empty")

        artist = track.get("artist")
        album = track.get("album")
        duration_seconds = track.get("duration_seconds")
        play_count = track.get("play_count", 0)

        duration_minutes = int(duration_seconds // 60) if duration_seconds is not None else None

        # ── Library catalog document (DOCUMENTS domain) ──────────────────
        doc_metadata: dict[str, Any] = {
            "document_id": str(track_id),
            "title": title,
            "document_type": "audio/mpeg",
            "source_type": "apple_music",
            "author": artist,
            "album": album,
            "play_count": play_count,
            "duration_minutes": duration_minutes,
        }

        try:
            DocumentMetadata.model_validate(doc_metadata)
        except ValueError as e:
            logger.error(f"DocumentMetadata validation failed for track {track_id}: {e}")
            raise

        return NormalizedContent(
            markdown=self._build_track_markdown(title, artist, album, duration_minutes, play_count),
            source_id=f"music/{track_id}",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=True,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata=doc_metadata,
            ),
            normalizer_version=self.normalizer_version,
            domain=Domain.DOCUMENTS,
        )
