"""AppleMusicLibraryAdapter for ingesting Apple Music library catalog from a macOS helper service.

This adapter consumes an HTTP REST API served by a macOS helper process that reads
from iTunes Library.xml and exposes the music catalog as a collection of documents.

Expected Local Service API Contract:
====================================

The macOS helper service should expose the following HTTP endpoint:

  GET /tracks
    Query parameters:
      - since (optional): ISO 8601 timestamp; return only tracks modified after this time

    Response: JSON array of track objects
    Status: 200 OK
    Content-Type: application/json

    Example response body:
    [
      {
        "id": "<string>",
        "title": "<string>",
        "artist": "<string | null>",
        "album": "<string | null>",
        "duration_seconds": <int | null>,
        "play_count": <int>
      }
    ]

Security:
  The helper binds to 0.0.0.0 for network access from remote servers.
  A Bearer API token is REQUIRED: Authorization: Bearer <api_key>

This adapter:
- Fetches the music catalog from the local macOS helper API
- Maps track fields to DocumentMetadata (title = title, artist = author)
- Yields NormalizedContent with DocumentMetadata in extra_metadata
- Each track is treated as a persistent document rather than a time-stamped event
"""

import logging
from datetime import datetime, timezone
from typing import Any, Iterator

from context_library.adapters.base import BaseAdapter
from context_library.storage.models import (
    Domain,
    DocumentMetadata,
    NormalizedContent,
    PollStrategy,
    StructuralHints,
)

logger = logging.getLogger(__name__)

HAS_HTTPX = False
try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    pass


class AppleMusicLibraryAdapter(BaseAdapter):
    """Adapter that ingests Apple Music library catalog from a macOS helper service.

    Treats each track as a persistent document in the catalog, preserving
    metadata like artist, album, duration, and play count.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        device_id: str = "default",
    ) -> None:
        """Initialize AppleMusicLibraryAdapter.

        Args:
            api_url: Base URL of the macOS helper API (e.g., "http://192.168.1.50:7123")
            api_key: Required bearer token for API authentication
            device_id: Device identifier for adapter_id generation (default: "default")

        Raises:
            ImportError: If httpx is not installed.
            ValueError: If api_key is empty.
        """
        if not HAS_HTTPX:
            raise ImportError(
                "httpx is required for AppleMusicLibraryAdapter. "
                "Install with: pip install context-library[apple-music]"
            )
        if not api_key:
            raise ValueError("api_key is required for AppleMusicLibraryAdapter")

        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._device_id = device_id
        self._client = httpx.Client(timeout=30.0)

    @property
    def adapter_id(self) -> str:
        return f"apple_music_library:{self._device_id}"

    @property
    def domain(self) -> Domain:
        return Domain.DOCUMENTS

    @property
    def poll_strategy(self) -> PollStrategy:
        return PollStrategy.PULL

    @property
    def normalizer_version(self) -> str:
        return "1.0.0"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._client.close()
        return False

    def __del__(self) -> None:
        if hasattr(self, "_client"):
            self._client.close()

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize Apple Music library catalog from the macOS helper API.

        Args:
            source_ref: ISO 8601 timestamp for incremental ingestion, or empty string for initial

        Yields:
            NormalizedContent for each track in the library

        Raises:
            httpx.HTTPError: If the API request fails
            ValueError: If the helper API returns unexpected response schema
        """
        since = source_ref if source_ref else None
        tracks = self._fetch_tracks(since)

        for idx, track in enumerate(tracks):
            try:
                yield from self._process_track(track)
            except (ValueError, KeyError) as e:
                track_id = track.get("id", f"<index {idx}>")
                logger.error(f"Skipping malformed track (ID: {track_id}): {e}")
                continue

    def _fetch_tracks(self, since: str | None) -> list[dict]:
        params = {}
        if since:
            params["since"] = since

        headers = {"Authorization": f"Bearer {self._api_key}"}

        response = self._client.get(
            f"{self._api_url}/tracks",
            params=params,
            headers=headers,
        )
        response.raise_for_status()

        tracks = response.json()
        if not isinstance(tracks, list):
            raise ValueError(
                f"macOS helper API 'tracks' response must be a list, got {type(tracks).__name__}"
            )

        return tracks

    def _process_track(self, track: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single track from the library and yield NormalizedContent.

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
        play_count = track.get("play_count", 1)

        duration_minutes = int(duration_seconds // 60) if duration_seconds else None

        now = datetime.now(timezone.utc).isoformat()

        document_metadata: dict[str, Any] = {
            "document_id": str(track_id),
            "title": title,
            "document_type": "audio/mpeg",
            "source_type": "apple_music",
            "date_first_observed": now,
            "author": artist,
            # Music-specific extras preserved alongside DocumentMetadata fields:
            "album": album,
            "play_count": play_count,
            "duration_minutes": duration_minutes,
        }

        # Validate via DocumentMetadata (will raise ValueError on bad data)
        try:
            DocumentMetadata.model_validate(document_metadata)
        except ValueError as e:
            logger.error(f"DocumentMetadata validation failed for track {track_id}: {e}")
            raise

        markdown = self._build_track_markdown(title, artist, album, duration_minutes, play_count)

        structural_hints = StructuralHints(
            has_headings=False,
            has_lists=True,
            has_tables=False,
            natural_boundaries=(),
            extra_metadata=document_metadata,
        )

        yield NormalizedContent(
            markdown=markdown,
            source_id=f"music/library/{track_id}",
            structural_hints=structural_hints,
            normalizer_version=self.normalizer_version,
        )

    def _build_track_markdown(
        self,
        title: str,
        artist: str | None,
        album: str | None,
        duration_minutes: int | None,
        play_count: int,
    ) -> str:
        """Build markdown representation of a track."""
        lines = [f"**{title}**"]

        if artist:
            lines.append(f"- Artist: {artist}")
        if album:
            lines.append(f"- Album: {album}")
        if duration_minutes is not None:
            lines.append(f"- Duration: {duration_minutes} min")
        lines.append(f"- Play count: {play_count}")

        return "\n".join(lines)
