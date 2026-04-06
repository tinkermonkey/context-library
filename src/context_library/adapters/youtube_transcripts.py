"""YouTubeTranscriptAdapter — fetches transcripts for watched YouTube videos.

Uses **read-from-store coupling**: on each poll cycle this adapter queries the
DocumentStore for ``video_id`` values present in watch-history chunks but not yet
indexed as transcript sources, then fetches the missing transcripts via the
``youtube-transcript-api`` library.

No event bus or shared state beyond the DocumentStore is required.  The set of
already-indexed transcript sources acts as the persistent cursor — on server restart
the adapter re-derives this set from the store and only fetches genuinely new videos.

Transcript chunking
===================
Raw captions arrive as 3–5 second segments from the API.  This adapter merges them
into ``chunk_words``-word blocks (default ~350 words) with inline ``[MM:SS]`` timestamp
markers so retrieval results show which part of the video the text is from.  The merged
transcript is yielded as a single DOCUMENTS-domain ``NormalizedContent`` per video and
the ``DocumentsDomain`` chunker handles further splitting if the video is very long.

Unavailable transcripts
=======================
Videos with disabled or non-existent transcripts (``TranscriptsDisabled``,
``NoTranscriptFound``) are logged and skipped; they will be retried on the next poll
cycle.  This handles the common case of transcripts not yet generated for recently
watched videos.

Dependencies
============
Requires ``youtube-transcript-api``::

    pip install context-library[youtube]
"""

import logging
from datetime import datetime, timezone
from typing import Iterator

from context_library.adapters.base import BaseAdapter
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import (
    Domain,
    DocumentMetadata,
    NormalizedContent,
    PollStrategy,
    StructuralHints,
)

logger = logging.getLogger(__name__)

HAS_YOUTUBE_TRANSCRIPT_API = False
try:
    from youtube_transcript_api import (  # type: ignore[import]
        NoTranscriptFound,
        TranscriptsDisabled,
        YouTubeTranscriptApi,
    )

    HAS_YOUTUBE_TRANSCRIPT_API = True
except ImportError:
    pass


class YouTubeTranscriptAdapter(BaseAdapter):
    """Fetches and indexes transcripts for YouTube videos found in watch history.

    Queries the DocumentStore for video_ids from watch history chunks that do not
    yet have a corresponding transcript source, then fetches each missing transcript
    via youtube-transcript-api and yields it as a DOCUMENTS-domain NormalizedContent.
    """

    #: Signals the background poller to run this adapter on poll_interval_sec cadence.
    background_poll: bool = True

    def __init__(
        self,
        document_store: DocumentStore,
        watch_history_adapter_id: str = "youtube_watch_history:default",
        account_id: str = "default",
        chunk_words: int = 350,
        languages: list[str] | None = None,
    ) -> None:
        """Initialize YouTubeTranscriptAdapter.

        Args:
            document_store: DocumentStore instance used to discover pending video_ids.
                Injected at construction — the read-from-store coupling point.
            watch_history_adapter_id: adapter_id of the companion watch history adapter
                whose chunks are queried for video_ids.
            account_id: Logical account identifier used in adapter_id.
            chunk_words: Target word count per merged transcript block (default 350).
                Blocks are split at this boundary; actual size varies by segment length.
            languages: Ordered list of caption language codes to prefer (default ["en"]).
                youtube-transcript-api tries each in order and falls back to auto-generated
                captions when no manual transcript is available.

        Raises:
            ImportError: If youtube-transcript-api is not installed.
        """
        if not HAS_YOUTUBE_TRANSCRIPT_API:
            raise ImportError(
                "youtube-transcript-api is required for YouTubeTranscriptAdapter. "
                "Install with: pip install context-library[youtube]"
            )

        self._document_store = document_store
        self._watch_history_adapter_id = watch_history_adapter_id
        self._account_id = account_id
        self._chunk_words = chunk_words
        self._languages = languages or ["en"]

    @property
    def adapter_id(self) -> str:
        return f"youtube_transcripts:{self._account_id}"

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
        """Discover pending video_ids and yield a transcript NormalizedContent for each.

        Phase 1: collect all video_ids from watch history chunks.
        Phase 2: collect all already-indexed transcript source_ids from the store.
        Phase 3: fetch transcripts for video_ids in the difference set.

        Args:
            source_ref: Unused — the store state is the authoritative cursor.

        Yields:
            NormalizedContent (domain=DOCUMENTS) for each successfully fetched transcript.
        """
        # Phase 1: all video_ids present in watch history
        watch_meta = self._collect_watch_metadata()
        watched_video_ids = set(watch_meta.keys())

        if not watched_video_ids:
            logger.debug("No watch history chunks found for adapter_id=%s", self._watch_history_adapter_id)
            return

        # Phase 2: video_ids that already have a transcript source
        indexed_video_ids = self._collect_indexed_video_ids()

        pending = watched_video_ids - indexed_video_ids
        logger.info(
            "YouTubeTranscriptAdapter: %d watched, %d indexed, %d pending",
            len(watched_video_ids),
            len(indexed_video_ids),
            len(pending),
        )

        # Phase 3: fetch transcripts for pending video_ids
        for video_id in pending:
            try:
                meta_dict = watch_meta.get(video_id, {})
                if not isinstance(meta_dict, dict):
                    meta_dict = {}
                content = self._fetch_transcript(video_id, meta_dict)
                if content is not None:
                    yield content
            except (ValueError, KeyError, TypeError) as exc:
                # Data validation errors (malformed API response or metadata) are logged and skipped
                logger.warning("Skipping transcript for video_id=%s due to malformed data: %s", video_id, exc)
                continue
            except Exception as exc:
                # Unexpected API or processing errors are logged and skipped per the per-source error isolation pattern
                logger.warning("Transcript fetch failed for video_id=%s: %s", video_id, exc)
                continue

    # ── Private helpers ─────────────────────────────────────────────────────

    def _collect_watch_metadata(self) -> dict[str, dict]:
        """Page through all watch history chunks and build a video_id → metadata map.

        When the same video_id appears in multiple watch events (rewatches), the most
        recent event's metadata is kept (latest start_date wins).

        Returns:
            Dict mapping video_id to a metadata dict with keys:
            title, channel, channel_id, url, watched_at (ISO 8601).
        """
        result: dict[str, dict] = {}
        offset = 0
        batch = 1000

        while True:
            chunks, total = self._document_store.list_chunks(
                adapter_id=self._watch_history_adapter_id,
                limit=batch,
                offset=offset,
            )

            for chunk_ctx in chunks:
                meta = chunk_ctx.chunk.domain_metadata
                if not isinstance(meta, dict):
                    continue
                video_id = meta.get("video_id")
                if not isinstance(video_id, str):
                    continue

                watched_at = meta.get("start_date", "")
                watched_at_str = watched_at if isinstance(watched_at, str) else ""
                existing = result.get(video_id)
                # Keep most recent watch event's metadata
                if existing is None or watched_at_str > existing.get("watched_at", ""):
                    result[video_id] = {
                        "title": meta.get("title", f"YouTube video {video_id}"),
                        "channel": meta.get("channel"),
                        "channel_id": meta.get("channel_id"),
                        "url": meta.get("url"),
                        "watched_at": watched_at_str,
                    }

            offset += batch
            if offset >= total:
                break

        return result

    def _collect_indexed_video_ids(self) -> set[str]:
        """Page through all transcript sources and return the set of indexed video_ids.

        Source IDs have the form ``youtube/transcript/{video_id}``.
        """
        indexed: set[str] = set()
        offset = 0
        batch = 1000

        while True:
            sources, total = self._document_store.list_sources(
                adapter_id=self.adapter_id,
                limit=batch,
                offset=offset,
            )

            for source in sources:
                source_id: str = source.get("source_id", "")
                prefix = "youtube/transcript/"
                if source_id.startswith(prefix):
                    indexed.add(source_id[len(prefix):])

            offset += batch
            if offset >= total:
                break

        return indexed

    def _fetch_transcript(
        self, video_id: str, watch_meta: dict
    ) -> NormalizedContent | None:
        """Fetch and normalize a single video transcript.

        Args:
            video_id: YouTube video ID.
            watch_meta: Metadata dict from _collect_watch_metadata (may be empty).

        Returns:
            NormalizedContent or None if no transcript is available.
        """
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)  # type: ignore[attr-defined]
            transcript = transcript_list.find_transcript(self._languages)
            segments = transcript.fetch()
        except TranscriptsDisabled:
            logger.debug("Transcripts disabled for video_id=%s", video_id)
            return None
        except NoTranscriptFound:
            logger.debug("No transcript found for video_id=%s (languages=%s)", video_id, self._languages)
            return None

        title = watch_meta.get("title") or f"YouTube video {video_id}"
        channel = watch_meta.get("channel")
        channel_id = watch_meta.get("channel_id")
        url = watch_meta.get("url") or f"https://www.youtube.com/watch?v={video_id}"
        watched_at = watch_meta.get("watched_at")
        now = datetime.now(timezone.utc).isoformat()

        blocks = _merge_segments(segments, self._chunk_words)
        markdown = _build_transcript_markdown(title, channel, url, watched_at, blocks)

        doc_meta = DocumentMetadata(
            document_id=video_id,
            title=title,
            document_type="video/transcript",
            source_type="youtube_transcript",
            date_first_observed=now,
            video_id=video_id,
            channel=channel,
            channel_id=channel_id,
            url=url,
            published_at=watched_at,
        )

        return NormalizedContent(
            markdown=markdown,
            source_id=f"youtube/transcript/{video_id}",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata=doc_meta.model_dump(exclude_none=True),
            ),
            normalizer_version=self.normalizer_version,
        )


# ── Module-level helpers ────────────────────────────────────────────────────

def _merge_segments(segments: list[dict], target_words: int) -> list[dict]:
    """Merge raw caption segments into ~target_words-word blocks.

    Args:
        segments: List of dicts with keys ``text``, ``start``, ``duration``.
        target_words: Target word count per output block.

    Returns:
        List of dicts with keys ``text``, ``start`` (seconds float), ``end`` (seconds float).
    """
    blocks: list[dict] = []
    current_texts: list[str] = []
    current_words = 0
    block_start = 0.0

    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue

        word_count = len(text.split())
        seg_start = float(seg.get("start", 0.0))

        if current_words + word_count > target_words and current_texts:
            blocks.append({
                "text": " ".join(current_texts),
                "start": block_start,
                "end": seg_start,
            })
            current_texts = [text]
            current_words = word_count
            block_start = seg_start
        else:
            if not current_texts:
                block_start = seg_start
            current_texts.append(text)
            current_words += word_count

    if current_texts:
        last = segments[-1] if segments else {}
        end = float(last.get("start", block_start)) + float(last.get("duration", 0.0))
        blocks.append({
            "text": " ".join(current_texts),
            "start": block_start,
            "end": end,
        })

    return blocks


def _format_timestamp(seconds: float) -> str:
    """Format a float seconds value as MM:SS or H:MM:SS."""
    total_secs = int(seconds)
    hours, remainder = divmod(total_secs, 3600)
    mins, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def _build_transcript_markdown(
    title: str,
    channel: str | None,
    url: str,
    watched_at: str | None,
    blocks: list[dict],
) -> str:
    """Build a markdown document for a video transcript."""
    lines = [f"# {title}", ""]
    if channel:
        lines.append(f"**Channel:** {channel}")
    lines.append(f"**URL:** {url}")
    if watched_at:
        lines.append(f"**Watched:** {watched_at}")
    lines.append("")

    if blocks:
        lines.append("## Transcript")
        lines.append("")
        for block in blocks:
            ts = _format_timestamp(block["start"])
            lines.append(f"[{ts}] {block['text']}")
            lines.append("")

    return "\n".join(lines)
