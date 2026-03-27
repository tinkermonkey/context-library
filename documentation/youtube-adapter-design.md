# YouTube Adapter Design

## Overview

This document specifies the design for a YouTube adapter that ingests watch history as media events and fetches video transcripts for semantic indexing.

## Architecture Decision: Run in context-library directly

YouTube is a web API with no macOS dependency, so this adapter runs directly in context-library as a first-class collector — no context-helper bridge needed. OAuth tokens and API keys are stored in context-library config.

The only alternative worth considering is sourcing watch history from a **Google Takeout export** on the user's Mac, in which case a filesystem-style context-helper collector pointing at the download path would work. For ongoing sync, the API path is preferred.

## Watch History Source

The YouTube Data API v3 does **not** expose watch history via `activities` or any documented endpoint — that access was removed. Viable options:

| Source | Notes |
|---|---|
| `playlistItems.list(playlistId=HL)` | Previously worked; now blocked by YouTube |
| **Google Takeout `watch-history.json`** | Complete history; manual export or scheduled cron |
| `youtube-transcript-api` (PyPI) | For transcripts only, not history |

Recommended approach: **Google Takeout JSON** for bootstrapping full history + polling the `activities` endpoint (which returns likes, saves, channel subscriptions) to detect new watches indirectly going forward.

## Domains

### 1. Watch Events → `media` domain

Watch events are structurally identical to music listen events — `channel` maps to `artist`, `video` maps to `track`. Slot into the existing `media` domain with a `source: "youtube"` discriminator, or as a sibling `media.youtube_watches` if the domain is partitioned by source.

**Event schema:**

```json
{
  "id": "<video_id>",
  "title": "Video Title",
  "channel": "Channel Name",
  "channel_id": "UCxxxxxxx",
  "watched_at": "2026-03-27T14:00:00Z",
  "duration_seconds": 1234,
  "url": "https://youtube.com/watch?v=<video_id>"
}
```

### 2. Transcripts → `documents` domain

Transcripts live in the same domain family as Obsidian notes and filesystem files. Each video produces one document record keyed by `video_id`, stored as chunked content with timestamp anchors.

**Document schema:**

```json
{
  "id": "<video_id>",
  "title": "Video Title",
  "channel": "Channel Name",
  "published_at": "2026-01-15T00:00:00Z",
  "url": "https://youtube.com/watch?v=<video_id>",
  "transcript_chunks": [
    {
      "chunk_index": 0,
      "start_seconds": 0,
      "end_seconds": 120,
      "text": "merged segment text..."
    }
  ]
}
```

## Transcript Chunking

YouTube's raw captions arrive as 3–5 second segments. Merge these into **~300–400 word chunks** with preserved timestamp ranges. This gives time-anchored retrieval ("the part around minute 8 where they discussed X").

Use `youtube-transcript-api` (PyPI) — it handles both auto-generated and manual captions transparently.

## Two-Cursor Design

Watch events and transcripts have different update patterns and require **separate push cursors**:

- **`youtube_watches` cursor** — watermark-driven, append-only (same pattern as music listen events)
- **`youtube_transcripts` cursor** — tracks which `video_id`s have been indexed; a set of processed IDs or a `last_indexed_at` per video works better than a global watermark here, since transcript availability doesn't follow chronological order

## Pipeline Flow

1. Poll for new watch events (Takeout JSON diff or `activities` API)
2. Emit each new watch as a `media.youtube_watches` event
3. For each new `video_id`, fetch transcript via `youtube-transcript-api`
4. Chunk transcript into ~300–400 word segments with timestamp ranges
5. Index chunks into `documents.video_transcripts` with video metadata

Step 3 is reactive — triggered by new watch events, not a separate poll. Videos without available transcripts (disabled or not yet generated) should be retried once after a short delay, then skipped.

## Dependencies

```
youtube-transcript-api   # transcript fetching (unofficial but stable)
google-api-python-client # YouTube Data API v3 (optional, for activities polling)
google-auth-oauthlib     # OAuth2 flow for authenticated API access
```

## Open Questions

- Should watch events and transcript documents share a `video_id` foreign key for cross-domain retrieval, or is the `url` field sufficient as a join key?
- For Takeout ingestion: poll a configured directory path for new exports, or require a manual trigger?
- Partial watch detection: Takeout JSON does not include watch duration (only that you watched), so `watch_duration_seconds` cannot be populated from this source.
