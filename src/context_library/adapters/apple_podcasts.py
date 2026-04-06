"""Apple Podcasts adapter for dual-endpoint, dual-domain podcast ingestion.

This adapter ingests both listen history and transcripts from an Apple Podcasts
helper service, yielding content to different domains:

- **Listen History**: Events domain (Domain.EVENTS)
  Each item represents an episode the user has played or is tracking.
  Source ID: `podcasts/listen/{id}`

- **Transcripts**: Documents domain (Domain.DOCUMENTS)
  Each item is a full episode transcript.
  Source ID: `podcasts/transcript/{id}`

Both endpoints are fetched independently; one endpoint failure yields a
PartialFetchError while both endpoints failing yields AllEndpointsFailedError.

Expected Local Service API Contract
====================================

GET /podcasts/listen-history?since=
  Query parameters:
    - since (optional): ISO 8601 timestamp; return episodes whose play state
      changed after this time

  Response: JSON array of listen history items
    [
      {
        "id": "<episode-id>",
        "showTitle": "<podcast name>",
        "episodeTitle": "<episode name>",
        "episodeGuid": "<guid>",
        "feedUrl": "<feed-url | null>",
        "enclosureUrl": "<enclosure-url | null>",
        "listenedAt": "<ISO 8601>",
        "durationSeconds": <int>,
        "playedSeconds": <int>,
        "completed": <bool>
      }
    ]

GET /podcasts/transcripts?since=
  Query parameters:
    - since (optional): ISO 8601 timestamp; return transcripts for episodes
      whose play state changed after this time

  Response: JSON array of transcript items
    [
      {
        "id": "<episode-id>",
        "source": "podcasts",
        "showTitle": "<podcast name>",
        "episodeTitle": "<episode name>",
        "episodeGuid": "<guid>",
        "publishedDate": "<YYYY-MM-DD>",
        "transcript": "<full transcript text>",
        "transcriptSource": "apple" | "whisper",
        "transcriptCreatedAt": "<ISO 8601>",
        "playStateTs": "<ISO 8601>",
        "durationSeconds": <int>
      }
    ]

Security:
  A Bearer API token is REQUIRED: Authorization: Bearer <api_key>
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterator

from context_library.adapters.base import (
    BaseAdapter,
    EndpointFetchError,
    AllEndpointsFailedError,
    PartialFetchError,
)
from context_library.storage.models import (
    Domain,
    EventMetadata,
    DocumentMetadata,
    NormalizedContent,
    PollStrategy,
    StructuralHints,
)

logger = logging.getLogger(__name__)

# Optional import guard
HAS_HTTPX = False
try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    pass


class ApplePodcastsAdapter(BaseAdapter):
    """Adapter for consuming Apple Podcasts data via local or remote HTTP REST API.

    Fetches both listen history and transcripts from a macOS helper process that reads
    Apple Podcasts data. Listen history items are yielded as events; transcript items
    are yielded as documents.

    Each endpoint is fetched independently, allowing partial data retrieval when
    one endpoint fails.
    """

    @property
    def domain(self) -> Domain:
        return Domain.EVENTS

    @property
    def poll_strategy(self) -> PollStrategy:
        return PollStrategy.PULL

    @property
    def normalizer_version(self) -> str:
        return "1.0.0"

    def __init__(
        self,
        api_url: str,
        api_key: str,
        device_id: str = "default",
    ) -> None:
        """Initialize ApplePodcastsAdapter.

        Args:
            api_url: Base URL of the helper API (e.g., "http://192.168.1.50:7123")
            api_key: Required API key for Bearer token authentication
            device_id: Device identifier for adapter_id computation (default: "default")

        Raises:
            ImportError: If httpx is not installed
            ValueError: If api_key is empty
        """
        if not HAS_HTTPX:
            raise ImportError(
                "Apple Podcasts adapter requires 'httpx' package. "
                "Install with: pip install context-library[apple-podcasts]"
            )
        if not api_key:
            raise ValueError("api_key is required for ApplePodcastsAdapter")

        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._device_id = device_id

    @property
    def adapter_id(self) -> str:
        return f"apple_podcasts:{self._device_id}"

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize both listen history and transcripts from Apple Podcasts.

        Args:
            source_ref: ISO 8601 timestamp for incremental fetch, or empty string for full fetch

        Yields:
            NormalizedContent: Normalized podcast data with appropriate domain overrides

        Raises:
            AllEndpointsFailedError: If all endpoints fail
            PartialFetchError: If some endpoints fail but others succeed
            httpx.HTTPStatusError: Auth errors (401/403) propagate immediately
        """
        since = source_ref if source_ref else None
        params = {"since": since} if since else {}
        headers = {"Authorization": f"Bearer {self._api_key}"}

        failed_endpoints = []
        total_endpoints = 2

        # Fetch listen history (Domain.EVENTS)
        try:
            yield from self._fetch_listen_history(params, headers)
        except httpx.HTTPStatusError:
            raise
        except EndpointFetchError:
            failed_endpoints.append("/podcasts/listen-history")

        # Fetch transcripts (Domain.DOCUMENTS with domain override)
        try:
            yield from self._fetch_transcripts(params, headers)
        except httpx.HTTPStatusError:
            raise
        except EndpointFetchError:
            failed_endpoints.append("/podcasts/transcripts")

        # Raise appropriate error based on failure count
        if failed_endpoints:
            if len(failed_endpoints) == total_endpoints:
                raise AllEndpointsFailedError(
                    total_endpoints,
                    f"All {total_endpoints} Apple Podcasts endpoints failed. "
                    "Check API connectivity, credentials, and service status.",
                )
            else:
                raise PartialFetchError(
                    failed_endpoints,
                    total_endpoints,
                    f"Partial fetch from Apple Podcasts: {len(failed_endpoints)}/{total_endpoints} "
                    "endpoint(s) failed. Successful endpoints provided partial data.",
                )

    def _fetch_listen_history(
        self,
        params: dict[str, Any],
        headers: dict[str, str],
    ) -> Iterator[NormalizedContent]:
        """Fetch and process listen history from /podcasts/listen-history endpoint.

        Raises:
            httpx.HTTPStatusError: Auth errors (401/403) are immediately re-raised
            EndpointFetchError: If the endpoint fails for any other reason
        """
        try:
            response = httpx.get(
                f"{self._api_url}/podcasts/listen-history",
                params=params,
                headers=headers,
                timeout=120.0,
            )
            response.raise_for_status()

            items = response.json()
            if not isinstance(items, list):
                raise ValueError(f"Expected list from /podcasts/listen-history, got {type(items)}")

            for idx, item in enumerate(items):
                try:
                    yield from self._process_listen_history_item(item)
                except (ValueError, KeyError) as e:
                    item_id = item.get("id", f"<index {idx}>") if isinstance(item, dict) else f"<index {idx}>"
                    logger.error(f"Skipping malformed listen history item (ID: {item_id}): {e}")
                    continue

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                logger.error(
                    f"Authentication error from Apple Podcasts API /podcasts/listen-history: "
                    f"{e.response.status_code} {e.response.text}"
                )
                raise
            logger.error(f"HTTP error from Apple Podcasts API /podcasts/listen-history: {e.response.status_code}")
            raise EndpointFetchError(f"HTTP {e.response.status_code} from /podcasts/listen-history")
        except httpx.RequestError as e:
            logger.error(
                f"Request error connecting to Apple Podcasts API at {self._api_url}/podcasts/listen-history: {e}"
            )
            raise EndpointFetchError(f"Network error at /podcasts/listen-history: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from /podcasts/listen-history: {e}")
            raise EndpointFetchError(f"JSON decode error at /podcasts/listen-history: {e}")
        except ValueError as e:
            logger.error(f"Invalid response schema from /podcasts/listen-history: {e}")
            raise EndpointFetchError(f"Invalid schema at /podcasts/listen-history: {e}")

    def _fetch_transcripts(
        self,
        params: dict[str, Any],
        headers: dict[str, str],
    ) -> Iterator[NormalizedContent]:
        """Fetch and process transcripts from /podcasts/transcripts endpoint.

        Raises:
            httpx.HTTPStatusError: Auth errors (401/403) are immediately re-raised
            EndpointFetchError: If the endpoint fails for any other reason
        """
        try:
            response = httpx.get(
                f"{self._api_url}/podcasts/transcripts",
                params=params,
                headers=headers,
                timeout=120.0,
            )
            response.raise_for_status()

            items = response.json()
            if not isinstance(items, list):
                raise ValueError(f"Expected list from /podcasts/transcripts, got {type(items)}")

            for idx, item in enumerate(items):
                try:
                    yield from self._process_transcript_item(item)
                except (ValueError, KeyError) as e:
                    item_id = item.get("id", f"<index {idx}>") if isinstance(item, dict) else f"<index {idx}>"
                    logger.error(f"Skipping malformed transcript item (ID: {item_id}): {e}")
                    continue

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                logger.error(
                    f"Authentication error from Apple Podcasts API /podcasts/transcripts: "
                    f"{e.response.status_code} {e.response.text}"
                )
                raise
            logger.error(f"HTTP error from Apple Podcasts API /podcasts/transcripts: {e.response.status_code}")
            raise EndpointFetchError(f"HTTP {e.response.status_code} from /podcasts/transcripts")
        except httpx.RequestError as e:
            logger.error(
                f"Request error connecting to Apple Podcasts API at {self._api_url}/podcasts/transcripts: {e}"
            )
            raise EndpointFetchError(f"Network error at /podcasts/transcripts: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from /podcasts/transcripts: {e}")
            raise EndpointFetchError(f"JSON decode error at /podcasts/transcripts: {e}")
        except ValueError as e:
            logger.error(f"Invalid response schema from /podcasts/transcripts: {e}")
            raise EndpointFetchError(f"Invalid schema at /podcasts/transcripts: {e}")

    def _process_listen_history_item(self, item: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single listen history item and yield NormalizedContent.

        Args:
            item: Listen history item from the API

        Raises:
            KeyError: If required fields are missing
            ValueError: If fields fail validation
        """
        item_id = item["id"]
        if not item_id:
            raise ValueError("Listen history item 'id' must not be empty")

        show_title = item.get("showTitle", "")
        episode_title = item.get("episodeTitle", "")
        if not episode_title:
            raise ValueError("Listen history item 'episodeTitle' must not be empty")

        episode_guid = item.get("episodeGuid")
        feed_url = item.get("feedUrl")
        enclosure_url = item.get("enclosureUrl")
        listened_at = item.get("listenedAt")
        duration_seconds = item.get("durationSeconds", 0)
        played_seconds = item.get("playedSeconds", 0)
        completed = item.get("completed", False)

        # Format title as "{showTitle} — {episodeTitle}"
        title = f"{show_title} — {episode_title}" if show_title else episode_title

        # Convert duration to minutes
        duration_minutes = int(duration_seconds // 60) if duration_seconds else None

        # Build event metadata
        now = datetime.now(timezone.utc).isoformat()
        event_metadata: dict[str, Any] = {
            "event_id": f"listen/{item_id}",
            "title": title,
            "start_date": listened_at,
            "end_date": listened_at,
            "duration_minutes": duration_minutes,
            "host": None,
            "invitees": [],
            "date_first_observed": now,
            "source_type": "podcast_listen",
        }

        try:
            EventMetadata.model_validate(event_metadata)
        except ValueError as e:
            logger.error(f"EventMetadata validation failed for listen history {item_id}: {e}")
            raise

        # Build markdown representation
        event_heading = f"Listened to **{episode_title}**"
        if show_title:
            event_heading += f" from *{show_title}*"

        event_lines = [event_heading, f"- Listened: {listened_at}"]
        if duration_minutes is not None:
            event_lines.append(f"- Duration: {duration_minutes} min")
        event_lines.append(f"- Played: {played_seconds}s / {duration_seconds}s ({int(100 * played_seconds / duration_seconds) if duration_seconds else 0}%)")
        if completed:
            event_lines.append("- Status: Completed")

        yield NormalizedContent(
            markdown="\n".join(event_lines),
            source_id=f"podcasts/listen/{item_id}",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=True,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata={
                    **event_metadata,
                    "durationSeconds": duration_seconds,
                    "playedSeconds": played_seconds,
                    "completed": completed,
                    "episodeGuid": episode_guid,
                    "feedUrl": feed_url,
                    "enclosureUrl": enclosure_url,
                },
            ),
            normalizer_version=self.normalizer_version,
            domain=Domain.EVENTS,
        )

    def _process_transcript_item(self, item: dict[str, Any]) -> Iterator[NormalizedContent]:
        """Process a single transcript item and yield NormalizedContent.

        Empty transcript text yields nothing (no content yielded for that item).

        Args:
            item: Transcript item from the API

        Raises:
            KeyError: If required fields are missing
            ValueError: If fields fail validation
        """
        item_id = item["id"]
        if not item_id:
            raise ValueError("Transcript item 'id' must not be empty")

        show_title = item.get("showTitle", "")
        episode_title = item.get("episodeTitle", "")
        if not episode_title:
            raise ValueError("Transcript item 'episodeTitle' must not be empty")

        transcript = item.get("transcript", "")
        # Empty transcript yields nothing
        if not transcript or not transcript.strip():
            logger.debug(f"Skipping transcript {item_id}: empty transcript text")
            return

        episode_guid = item.get("episodeGuid")
        published_date = item.get("publishedDate")  # YYYY-MM-DD format
        transcript_source = item.get("transcriptSource", "apple")
        transcript_created_at = item.get("transcriptCreatedAt")
        play_state_ts = item.get("playStateTs")
        duration_seconds = item.get("durationSeconds", 0)

        # Convert duration to minutes
        duration_minutes = int(duration_seconds // 60) if duration_seconds else None

        # Convert publishedDate (YYYY-MM-DD) to ISO 8601 timestamp by appending T00:00:00Z
        modified_at = None
        if published_date:
            modified_at = f"{published_date}T00:00:00Z"

        # Build document metadata
        doc_metadata: dict[str, Any] = {
            "document_id": str(item_id),
            "title": episode_title,
            "author": show_title,
            "document_type": "text/plain",
            "source_type": "podcast_transcript",
            "created_at": transcript_created_at,
            "modified_at": modified_at,
        }

        try:
            DocumentMetadata.model_validate(doc_metadata)
        except ValueError as e:
            logger.error(f"DocumentMetadata validation failed for transcript {item_id}: {e}")
            raise

        # Build markdown with episode metadata header
        markdown_lines = [f"# {episode_title}"]
        if show_title:
            markdown_lines.append(f"*{show_title}*\n")
        if published_date:
            markdown_lines.append(f"Published: {published_date}")
        if duration_minutes is not None:
            markdown_lines.append(f"Duration: {duration_minutes} minutes")
        markdown_lines.append(f"Transcript source: {transcript_source}\n")
        markdown_lines.append(transcript)

        yield NormalizedContent(
            markdown="\n".join(markdown_lines),
            source_id=f"podcasts/transcript/{item_id}",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata={
                    **doc_metadata,
                    "transcriptSource": transcript_source,
                    "episodeGuid": episode_guid,
                    "durationSeconds": duration_seconds,
                    "playStateTs": play_state_ts,
                },
            ),
            normalizer_version=self.normalizer_version,
            domain=Domain.DOCUMENTS,
        )
