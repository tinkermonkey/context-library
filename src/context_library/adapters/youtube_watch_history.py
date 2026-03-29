"""YouTubeWatchHistoryAdapter — ingests YouTube watch history from the macOS helper service.

The macOS helper (context-helpers) exposes a ``GET /youtube/history`` endpoint that
runs ``yt-dlp --cookies-from-browser`` against the YouTube history feed and returns
recently-watched videos with an approximate ``watched_at`` timestamp.  This adapter
fetches that data incrementally and yields one EVENTS-domain ``NormalizedContent``
per watch event.

Expected Local Service API Contract
====================================
``GET /youtube/history``

  Query parameters:
    - since (optional): ISO 8601 timestamp; return only videos first-seen after this time

  Response: JSON array of video objects::

    [
      {
        "video_id":   "<string>",
        "title":      "<string>",
        "channel":    "<string | null>",
        "channel_id": "<string | null>",
        "url":        "<string>",
        "watched_at": "<ISO 8601>",
        "duration":   <int | null>,
        "upload_date": "<YYYYMMDD | null>",
        "thumbnail":  "<string | null>"
      }
    ]

  Results are sorted ASC by ``watched_at`` and bounded by the helper's
  ``push_page_size`` (default 50).

Security
=========
A Bearer API token is REQUIRED: ``Authorization: Bearer <api_key>``
"""

import json
import logging
from datetime import datetime, timezone
from typing import Iterator

from context_library.adapters.base import BaseAdapter
from context_library.storage.models import (
    Domain,
    EventMetadata,
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


class YouTubeWatchHistoryAdapter(BaseAdapter):
    """Ingests YouTube watch history from the macOS helper's /youtube/history endpoint.

    Each watched video is emitted as an EVENTS-domain NormalizedContent item.
    EventMetadata fields are populated from the helper response; YouTube-specific
    fields (video_id, channel_id, url) are preserved as extra keys in
    domain_metadata via the EventsDomain merge pattern.
    """

    #: Signals the background poller to run this adapter on poll_interval_sec cadence.
    background_poll: bool = True

    def __init__(
        self,
        api_url: str,
        api_key: str,
        account_id: str = "default",
    ) -> None:
        """Initialize YouTubeWatchHistoryAdapter.

        Args:
            api_url: Base URL of the macOS helper API (e.g., ``"http://192.168.1.50:7123"``).
            api_key: Required bearer token for API authentication.
            account_id: Logical account identifier used in adapter_id (default: ``"default"``).

        Raises:
            ImportError: If httpx is not installed.
            ValueError: If api_key is empty.
        """
        if not HAS_HTTPX:
            raise ImportError(
                "httpx is required for YouTubeWatchHistoryAdapter. "
                "Install with: pip install httpx"
            )
        if not api_key:
            raise ValueError("api_key is required for YouTubeWatchHistoryAdapter")

        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._account_id = account_id
        # yt-dlp has an internal 120s timeout; give the helper a comfortable margin.
        self._client = httpx.Client(timeout=150.0)

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
        return "1.1.0"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._client.close()
        return False

    def __del__(self) -> None:
        if hasattr(self, "_client"):
            self._client.close()

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch watch history from the helper API and yield NormalizedContent.

        Args:
            source_ref: ISO 8601 lower-bound for incremental fetch, or ``""`` for all.

        Yields:
            NormalizedContent (domain=EVENTS) for each watched video.

        Raises:
            httpx.HTTPStatusError: On auth errors (401/403) or other HTTP failures.
            httpx.RequestError: On network errors.
            json.JSONDecodeError: If the API returns invalid JSON.
        """
        since = source_ref if source_ref else None
        videos = self._fetch_history(since)

        for idx, video in enumerate(videos):
            try:
                content = self._process_video(video)
            except (ValueError, KeyError, TypeError) as exc:
                vid = video.get("video_id", f"<index {idx}>") if isinstance(video, dict) else f"<index {idx}>"
                logger.warning("Skipping malformed watch history entry (video_id=%s): %s", vid, exc)
                continue

            if content is not None:
                yield content

    def _fetch_history(self, since: str | None) -> list[dict]:
        """Call ``GET /youtube/history`` on the helper and return the video list."""
        params: dict = {}
        if since:
            params["since"] = since

        headers = {"Authorization": f"Bearer {self._api_key}"}

        try:
            response = self._client.get(
                f"{self._api_url}/youtube/history",
                params=params,
                headers=headers,
            )
            response.raise_for_status()

            videos = response.json()
            if not isinstance(videos, list):
                raise ValueError(
                    f"Helper /youtube/history response must be a list, got {type(videos).__name__}"
                )
            if videos and not isinstance(videos[0], dict):
                raise ValueError(
                    f"Helper /youtube/history response items must be dicts, got {type(videos[0]).__name__}"
                )
            return videos

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                logger.error(
                    "Authentication error from YouTube history helper: %s %s",
                    exc.response.status_code,
                    exc.response.text,
                )
            else:
                logger.error(
                    "HTTP error from YouTube history helper: %s %s",
                    exc.response.status_code,
                    exc.response.text,
                )
            raise
        except httpx.RequestError as exc:
            logger.error(
                "Network error connecting to YouTube history helper at %s/youtube/history: %s",
                self._api_url,
                exc,
            )
            raise
        except json.JSONDecodeError as exc:
            logger.error(
                "Invalid JSON from YouTube history helper /youtube/history: %s", exc
            )
            raise

    def _process_video(self, video: dict) -> NormalizedContent | None:
        """Convert a single helper video dict to NormalizedContent.

        Returns None for entries with no usable video_id or watched_at.
        """
        video_id: str | None = video.get("video_id")
        if not video_id:
            return None

        watched_at: str | None = video.get("watched_at")
        if not watched_at:
            return None

        title: str = video.get("title") or f"YouTube video {video_id}"
        channel: str | None = video.get("channel")
        channel_id: str | None = video.get("channel_id")
        url: str = video.get("url") or f"https://www.youtube.com/watch?v={video_id}"

        now = datetime.now(timezone.utc).isoformat()

        event_metadata = EventMetadata(
            event_id=f"{video_id}@{watched_at}",
            title=title,
            start_date=watched_at,
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
            "url": url,
        }

        return NormalizedContent(
            markdown=_build_watch_markdown(title, watched_at, channel, url),
            source_id=f"youtube/watch/{video_id}/{watched_at}",
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
