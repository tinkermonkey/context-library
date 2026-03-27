"""YouTubeWatchHistoryAdapter — ingests YouTube watch history from a Google Takeout export.

Parses the ``watch-history.json`` file produced by Google Takeout and yields one
EVENTS-domain ``NormalizedContent`` per watched video.  Each watch event becomes its
own source (keyed ``youtube/watch/{video_id}/{watched_at_iso}``) so that rewatches are
stored as separate events.

Google Takeout format (watch-history.json)
==========================================
A JSON array of activity objects.  Each watch looks like::

    {
      "header": "YouTube",
      "title": "Watched Some Video Title",
      "titleUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      "subtitles": [
        {
          "name": "Channel Name",
          "url": "https://www.youtube.com/channel/UCxxxxxxxxxx"
        }
      ],
      "time": "2024-01-15T14:30:00.000Z",
      "products": ["YouTube"],
      "activityControls": ["YouTube watch history"]
    }

Non-watch items (searches, ad views) lack ``titleUrl`` or have a non-watch URL and are
skipped.  Deleted videos lack ``subtitles`` — channel fields will be ``None``.

Incremental fetching
====================
The adapter maintains an internal high-water mark (``self._cursor``) across poll cycles.
On each call to ``fetch(source_ref)``, items with ``time <= cursor`` are skipped.  The
cursor is updated to the maximum ``time`` seen after processing.  On server restart the
cursor resets to ``""``, but the differ prevents duplicate chunk storage.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Iterator
from urllib.parse import parse_qs, urlparse

from context_library.adapters.base import BaseAdapter
from context_library.storage.models import (
    Domain,
    EventMetadata,
    NormalizedContent,
    PollStrategy,
    StructuralHints,
)

logger = logging.getLogger(__name__)


class YouTubeWatchHistoryAdapter(BaseAdapter):
    """Ingests YouTube watch history from a Google Takeout watch-history.json file.

    Each watched video is emitted as an EVENTS-domain NormalizedContent item.
    EventMetadata fields are populated from the Takeout data; YouTube-specific
    fields (video_id, channel_id, url) are preserved as extra keys in
    domain_metadata via the EventsDomain merge pattern.
    """

    #: Signals the background poller to run this adapter on poll_interval_sec cadence.
    background_poll: bool = True

    def __init__(
        self,
        takeout_path: str,
        account_id: str = "default",
    ) -> None:
        """Initialize YouTubeWatchHistoryAdapter.

        Args:
            takeout_path: Filesystem path to the Google Takeout watch-history.json file.
            account_id: Logical account identifier used in adapter_id (default: "default").

        Raises:
            ValueError: If takeout_path is empty.
        """
        if not takeout_path:
            raise ValueError("takeout_path is required for YouTubeWatchHistoryAdapter")

        self._takeout_path = takeout_path
        self._account_id = account_id
        self._cursor: str = ""   # ISO 8601 high-water mark; persisted in-memory across polls

    @property
    def adapter_id(self) -> str:
        return f"youtube_watch_history:{self._account_id}"

    @property
    def domain(self) -> Domain:
        return Domain.EVENTS

    @property
    def poll_strategy(self) -> PollStrategy:
        return PollStrategy.PULL

    @property
    def normalizer_version(self) -> str:
        return "1.0.0"

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Parse watch-history.json and yield one NormalizedContent per new watch event.

        Args:
            source_ref: ISO 8601 timestamp used as lower bound for incremental fetch.
                The background poller always passes ``""``; the adapter falls back to
                the internal ``self._cursor`` for watermarking.

        Yields:
            NormalizedContent (domain=EVENTS) for each watch event newer than the cursor.

        Raises:
            OSError: If takeout_path cannot be read.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        effective_since = source_ref or self._cursor
        since: datetime | None = None
        if effective_since:
            since = datetime.fromisoformat(effective_since.replace("Z", "+00:00"))

        with open(self._takeout_path, encoding="utf-8") as fh:
            history: list[dict] = json.load(fh)

        if not isinstance(history, list):
            raise ValueError(
                f"watch-history.json must be a JSON array, got {type(history).__name__}"
            )

        max_watched_at: datetime | None = None

        # Takeout orders items newest-first; process all and filter by cursor
        for item in history:
            try:
                content = self._process_item(item, since)
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("Skipping malformed watch history item: %s", exc)
                continue

            if content is None:
                continue

            # Track high-water mark using the start_date stored in extra_metadata
            item_time_str = item.get("time", "")
            if item_time_str:
                item_dt = datetime.fromisoformat(item_time_str.replace("Z", "+00:00"))
                if max_watched_at is None or item_dt > max_watched_at:
                    max_watched_at = item_dt

            yield content

        if max_watched_at is not None:
            self._cursor = max_watched_at.isoformat()

    def _process_item(
        self,
        item: dict,
        since: datetime | None,
    ) -> NormalizedContent | None:
        """Convert a single Takeout history item to NormalizedContent.

        Returns None for non-watch items or items before the cursor.
        """
        title_url = item.get("titleUrl", "")
        if not title_url:
            return None   # Search, ad, or other non-watch activity

        video_id = _extract_video_id(title_url)
        if not video_id:
            return None   # Not a standard watch URL (e.g., youtube.com/shorts/ redirect)

        time_str = item.get("time")
        if not time_str:
            return None

        watched_at = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        if since is not None and watched_at <= since:
            return None   # Already ingested

        # Strip "Watched " prefix that Takeout adds to video titles
        raw_title = item.get("title", f"YouTube video {video_id}")
        title = raw_title.removeprefix("Watched ")
        if not title:
            title = f"YouTube video {video_id}"

        # Channel info is in subtitles[0]; absent for deleted videos
        subtitles = item.get("subtitles") or []
        channel: str | None = None
        channel_id: str | None = None
        if subtitles and isinstance(subtitles[0], dict):
            channel = subtitles[0].get("name")
            channel_url = subtitles[0].get("url", "")
            channel_id = _extract_channel_id(channel_url)

        watched_at_iso = watched_at.isoformat()
        now = datetime.now(timezone.utc).isoformat()

        event_metadata = EventMetadata(
            event_id=f"{video_id}@{watched_at_iso}",
            title=title,
            start_date=watched_at_iso,
            date_first_observed=now,
            source_type="youtube_watch_history",
        )

        # Merge validated EventMetadata fields with YouTube-specific extras.
        # EventsDomain chunker preserves extra keys via {**meta.model_dump(), **meta_dict}.
        extra_metadata: dict = {
            **event_metadata.model_dump(),
            "video_id": video_id,
            "channel": channel,
            "channel_id": channel_id,
            "url": title_url,
        }

        return NormalizedContent(
            markdown=_build_watch_markdown(title, watched_at_iso, channel, title_url),
            source_id=f"youtube/watch/{video_id}/{watched_at_iso}",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata=extra_metadata,
            ),
            normalizer_version=self.normalizer_version,
        )


# ── Module-level helpers ────────────────────────────────────────────────────

def _extract_video_id(url: str) -> str | None:
    """Extract video_id from a youtube.com/watch?v=... URL."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if "youtube.com" not in parsed.netloc:
        return None
    if parsed.path != "/watch":
        return None
    qs = parse_qs(parsed.query)
    ids = qs.get("v", [])
    return ids[0] if ids else None


def _extract_channel_id(url: str) -> str | None:
    """Extract channel ID from a youtube.com/channel/UC... URL."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "channel":
        return parts[1]
    return None


def _build_watch_markdown(
    title: str,
    watched_at: str,
    channel: str | None,
    url: str,
) -> str:
    """Build a markdown representation of a watch event."""
    lines = [f"# {title}", ""]
    lines.append(f"**Watched:** {watched_at}")
    if channel:
        lines.append(f"**Channel:** {channel}")
    lines.append(f"**URL:** {url}")
    return "\n".join(lines)
