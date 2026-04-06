"""AppleMusicLibraryAdapter — ingests Apple Music data from the macOS helper service.

This adapter handles both types of Apple Music data from a single /tracks fetch:

  1. Library catalog  (DOCUMENTS domain) — one persistent document per track,
     keyed by source_id ``music/library/<track_id>``.  Captures title, artist,
     album, genre, duration, and play count.

  2. Play events (EVENTS domain) — one event per track play, keyed by
     source_id ``music/play/<track_id>``.  Records the most-recent played_at
     timestamp reported by the helper.

Both are yielded from a single ``fetch()`` call so that the /tracks endpoint is
hit only once per ingest cycle.  The pipeline handles the mixed domains via the
``domain`` field on each NormalizedContent item.

Expected Local Service API Contract:
====================================

  GET /music/tracks
    Query parameters:
      - since (optional): ISO 8601 timestamp; only tracks last played after this time

    Response: JSON array of track objects (only tracks played at least once)
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
from datetime import datetime, timezone
from typing import Any, Iterator

from context_library.adapters.base import BaseAdapter
from context_library.adapters.apple_music_base import AppleMusicBaseMixin
from context_library.storage.models import (
    Domain,
    DocumentMetadata,
    EventMetadata,
    NormalizedContent,
    PollStrategy,
    StructuralHints,
)

logger = logging.getLogger(__name__)


class AppleMusicLibraryAdapter(AppleMusicBaseMixin, BaseAdapter):
    """Adapter that ingests Apple Music library catalog from a macOS helper service.

    Treats each track as a persistent document in the catalog, preserving
    metadata like artist, album, duration, and play count.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        device_id: str = "default",
        include_events: bool = True,
    ) -> None:
        """Initialize AppleMusicLibraryAdapter.

        Args:
            api_url: Base URL of the macOS helper API (e.g., "http://192.168.1.50:7123")
            api_key: Required bearer token for API authentication
            device_id: Device identifier for adapter_id generation (default: "default")
            include_events: If True, yield both documents and play events; if False, only yield documents (default: True)

        Raises:
            ImportError: If httpx is not installed.
            ValueError: If api_key is empty.
        """
        if not api_key:
            raise ValueError("api_key is required for AppleMusicLibraryAdapter")

        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._device_id = device_id
        self._include_events = include_events
        self._init_httpx_client()

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

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize Apple Music library catalog from the macOS helper API.

        Args:
            source_ref: ISO 8601 timestamp for incremental ingestion, or empty string for initial

        Yields:
            NormalizedContent for each track in the library

        Raises:
            httpx.HTTPStatusError: If the API request fails (auth errors 401/403 propagate immediately)
            httpx.RequestError: If a network error occurs
            json.JSONDecodeError: If the API returns invalid JSON
            ValueError: If the helper API returns unexpected response schema
        """
        since = source_ref if source_ref else None
        tracks = self._fetch_tracks(self._api_url, self._api_key, since)

        for idx, track in enumerate(tracks):
            try:
                yield from self._process_track(track)
            except (ValueError, KeyError, TypeError) as e:
                track_id = track.get("id", f"<index {idx}>") if isinstance(track, dict) else f"<index {idx}>"
                logger.error(f"Skipping malformed track (ID: {track_id}): {e}")
                continue

    def _process_track(self, track: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single track and yield both a library document and a play event.

        Yields:
            NormalizedContent (domain=DOCUMENTS) — persistent library catalog entry
            NormalizedContent (domain=EVENTS)    — most-recent play event (when played_at present)

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
        genre = track.get("genre")
        duration_seconds = track.get("duration_seconds")
        play_count = track.get("play_count", 0)
        played_at = track.get("played_at")

        duration_minutes = int(duration_seconds // 60) if duration_seconds is not None else None

        # ── 1. Library catalog document (DOCUMENTS domain) ──────────────────
        doc_metadata: dict[str, Any] = {
            "document_id": str(track_id),
            "title": title,
            "document_type": "audio/mpeg",
            "source_type": "apple_music",
            "author": artist,
            "album": album,
            "genre": genre,
            "play_count": play_count,
            "duration_minutes": duration_minutes,
        }

        try:
            DocumentMetadata.model_validate(doc_metadata)
        except ValueError as e:
            logger.error(f"DocumentMetadata validation failed for track {track_id}: {e}")
            raise

        yield NormalizedContent(
            markdown=self._build_track_markdown(title, artist, album, duration_minutes, play_count, genre),
            source_id=f"music/library/{track_id}",
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

        # ── 2. Play event (EVENTS domain, optional) ────────────────────────────────────
        if not self._include_events or not played_at:
            return

        now = datetime.now(timezone.utc).isoformat()
        event_metadata: dict[str, Any] = {
            "event_id": f"play/{track_id}",
            "title": f"Listened to {title}" + (f" by {artist}" if artist else ""),
            "start_date": played_at,
            "end_date": played_at,
            "duration_minutes": duration_minutes,
            "host": None,
            "invitees": [],
            "date_first_observed": now,
            "source_type": "apple_music",
            "library_source_id": f"music/library/{track_id}",
        }

        try:
            EventMetadata.model_validate(event_metadata)
        except ValueError as e:
            logger.error(f"EventMetadata validation failed for track {track_id}: {e}")
            raise

        event_heading = f"Listened to **{title}**" + (f" by {artist}" if artist else "")
        event_lines = [event_heading, f"- Played: {played_at}"]
        if duration_minutes is not None:
            event_lines.append(f"- Duration: {duration_minutes} min")

        yield NormalizedContent(
            markdown="\n".join(event_lines),
            source_id=f"music/play/{track_id}",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=True,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata=event_metadata,
            ),
            normalizer_version=self.normalizer_version,
            domain=Domain.EVENTS,
        )
