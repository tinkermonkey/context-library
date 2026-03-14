# Context Library — Versioned RAG with Source Lineage

A retrieval-augmented generation system that tracks, versions, and diffs source documents across heterogeneous inputs. Every chunk in the vector store carries full provenance back to its origin, and content changes are detected via hash-based comparison of normalized markdown.

## Core Concepts

### Normalize → Diff → Chunk → Embed → Store

Traditional RAG pipelines treat ingestion as a one-shot operation. Context Library adds a **diff stage** between normalization and chunking so that re-ingested sources only produce new chunk versions when content actually changes. All source content is normalized to markdown before comparison, giving a stable (if imperfect) surface for detecting meaningful changes. Trivial differences like whitespace are filtered out; the goal is paragraph-level and list-level change detection, not character-perfect diffs.

### Content-Addressed Versioning

Chunks are identified by a hash of their normalized content. When a source is re-ingested and its markdown representation has changed, new chunks are hashed and compared against the previous chunk set for that source. Identical hashes mean no change. New hashes create new chunk versions. Missing hashes mark retired chunks. This makes "what changed in version N" a set-difference operation between two hash sets, with no need for positional alignment.

### Dual Storage Architecture

The vector database is an **index**, not the source of truth. Full normalized markdown is stored in a document store (keyed by source ID and version), and the vector store holds embedded chunks with pointers back. This separation enables:

- Reconstructing the full document at any version for diffing
- Re-chunking or re-embedding without re-fetching from origin
- Answering provenance queries without vector search

---

## Domain Model

Sources are organized into four top-level **domains**, each with its own chunking strategy, metadata schema, and retrieval semantics. Adapters are the ingestion layer; domains are the semantic layer.

### Messages

Email, SMS, chat messages, forum posts, Slack threads. Chunks preserve conversational threading — individual messages are natural chunk boundaries, but thread metadata (participants, reply chains, timestamps) is carried as structured context so retrieval can reconstruct conversations.

**Adapters:** Gmail, IMAP, Slack, Discord, iMessage export, forum scrapers.

### Notes

Freeform text fragments with timestamps. The most document-like domain — standard semantic chunking with overlap works well. Includes digitized handwritten notes (photos → markdown via vision LLM), Apple Notes, Obsidian vaults, plain text files.

**Adapters:** Apple Notes, Obsidian, filesystem (markdown/txt), photo-to-text (LLM), web clippings.

### Events

Structured occurrences with timestamps — music listens, health metrics, location check-ins, workout logs. These aren't "chunked" in the traditional text sense; instead, they're batched into time-windowed summaries that get embedded as natural-language descriptions.

**Example chunk:** *"On March 1, listened to 12 tracks (mostly jazz) during a 45-minute run. Average HR 155 bpm, peak 172."*

**Adapters:** Apple Health, Spotify/Last.fm, Google Location History, Strava.

### Tasks

Action items with lifecycle state (open, in-progress, done) organized into projects and workstreams. Versioning here tracks state transitions, not just text changes — a task moving from "open" to "done" is a meaningful version event. Includes recommended actions surfaced by the system itself.

**Adapters:** Todoist, Apple Reminders, GitHub Issues, Jira, Linear, manual entry.

---

## Adapter Contract

Every adapter implements a common interface regardless of domain:

```
fetch(source_ref) → RawContent + SourceMetadata
normalize(raw)    → Markdown + StructuralHints
identity(ref)     → StableSourceID
poll_strategy()   → Push | Pull(interval) | Webhook
domain()          → Messages | Notes | Events | Tasks
```

Adding a new source is: implement the interface, declare the domain, register. The domain layer handles chunking strategy, metadata enrichment, and retrieval semantics from there.

### Normalizer Requirements

Normalizers must be **deterministic enough** — the same input should produce the same markdown on repeated runs. Perfect reproducibility isn't required, but the system includes sanity checks for common failure modes:

- Whitespace-only diffs are discarded
- Heading-level fluctuations are normalized
- Link formatting is canonicalized
- Encoding artifacts are cleaned

Bugs in normalization will surface as phantom version bumps, which are detectable and fixable downstream.

---

## Data Lineage

Every chunk in the store carries a full provenance record:

```
adapter_id          → which adapter produced this
source_id           → stable identity of the origin (URL, file path, message ID, etc.)
source_version      → version counter for this source
fetch_timestamp     → when the raw content was retrieved
normalizer_version  → version of the normalizer that produced the markdown
domain              → messages | notes | events | tasks
chunk_hash          → content hash of this chunk's normalized markdown
chunk_index         → position within the source's chunk sequence
parent_chunk_hash   → previous version's hash (null if new), enables version chain
domain_metadata     → domain-specific fields (thread_id, task_state, event_window, etc.)
```

This supports queries like:

- "Show me everything from this URL across all versions"
- "Which chunks were produced by normalizer v2.1 and may need reprocessing?"
- "What changed in my notes between last Tuesday and today?"
- "Trace this retrieved chunk back to its original source"

---

## Project Structure

```
src/context_library/
├── adapters/
│   ├── base.py              # BaseAdapter abstract class
│   ├── _watching.py         # Shared filesystem watcher utility
│   ├── filesystem.py        # Plain markdown files
│   ├── filesystem_rich.py   # PDF/Office/image ingestion via MarkItDown
│   ├── obsidian.py          # Obsidian vault (frontmatter, wikilinks)
│   ├── obsidian_tasks.py    # Obsidian tasks plugin
│   ├── email.py             # IMAP/EmailEngine
│   ├── caldav.py            # CalDAV calendars
│   ├── apple_reminders.py   # Apple Reminders via context-helpers
│   ├── apple_health.py      # Apple Health via context-helpers
│   ├── apple_imessage.py    # iMessage via context-helpers
│   ├── apple_notes.py       # Apple Notes via context-helpers
│   └── apple_music.py       # Apple Music via context-helpers
├── core/
│   ├── pipeline.py          # Orchestrates fetch → diff → chunk → embed → store
│   ├── differ.py            # Hash-based change detection
│   └── embedder.py          # Sentence-transformers embedding
├── domains/
│   ├── base.py              # BaseDomain abstract class
│   ├── registry.py          # Domain → chunker lookup
│   ├── messages.py          # Thread-aware chunking
│   ├── notes.py             # Heading-based hierarchical chunking
│   ├── events.py            # Time-window batching
│   └── tasks.py             # State-transition versioning
├── storage/
│   ├── models.py            # Pydantic data models
│   ├── document_store.py    # SQLite source-of-truth
│   ├── vector_store.py      # VectorStore abstract port
│   ├── chromadb_store.py    # ChromaDB implementation
│   └── schema.sql           # SQLite schema
├── retrieval/
│   ├── query.py             # Semantic search
│   └── reranker.py          # Cross-encoder reranking
└── server/
    ├── app.py               # FastAPI app factory + lifespan
    ├── config.py            # ServerConfig (CTX_ env vars)
    ├── schemas.py           # Request/response models
    ├── webhook_adapter.py   # Passthrough adapter for webhook payloads
    └── routes/
        ├── health.py        # GET /health
        ├── ingest.py        # POST /webhooks/ingest, POST /ingest/apple
        ├── retrieve.py      # POST /query
        ├── adapters.py      # GET /adapters, /adapters/{id}
        ├── sources.py       # GET /sources, /sources/{id}, versions, chunks, diff
        ├── chunks.py        # GET /chunks/{hash}, provenance, version-chain
        └── stats.py         # GET /stats
```

---

## Running the Server

The server exposes the ingestion pipeline and all retrieval/inspection endpoints over HTTP. Data is persisted in two named Docker volumes — SQLite as the source of truth and ChromaDB as the search index.

### Docker (recommended)

```bash
# With webhook authentication (recommended)
WEBHOOK_SECRET=your-random-secret docker compose up --build

# With Apple macOS bridge also configured
WEBHOOK_SECRET=your-random-secret \
APPLE_HELPER_URL=http://192.168.1.x:7123 \
APPLE_HELPER_API_KEY=your-helper-key \
docker compose up --build

# Without webhook auth (ingestion endpoint is open)
docker compose up --build
```

The server starts on `http://localhost:8000`. The embedding model (`all-MiniLM-L6-v2`) is baked into the image at build time, so the first request does not incur a download delay.

To run in the background:

```bash
WEBHOOK_SECRET=your-random-secret docker compose up --build -d
docker compose logs -f   # tail logs
docker compose down      # stop and remove containers (volumes are preserved)
```

### Local (development)

```bash
pip install -e ".[server]"

# Minimal — uses /data/sqlite and /data/chromadb by default
uvicorn context_library.server.app:app --reload

# Override storage paths and enable auth
CTX_SQLITE_DB_PATH=./local.db \
CTX_CHROMADB_PATH=./local_chroma \
CTX_WEBHOOK_SECRET=dev-secret \
uvicorn context_library.server.app:app --reload
```

### Environment variables

All variables use the `CTX_` prefix. Every variable has a default and none are strictly required.

| Variable | Default | Description |
|---|---|---|
| `CTX_SQLITE_DB_PATH` | `/data/sqlite/documents.db` | SQLite database path |
| `CTX_CHROMADB_PATH` | `/data/chromadb` | ChromaDB persistence directory |
| `CTX_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model for embedding |
| `CTX_ENABLE_RERANKER` | `false` | Enable cross-encoder reranking on `/query` |
| `CTX_RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Reranker model (only used if reranker enabled) |
| `CTX_WEBHOOK_SECRET` | `""` (no auth) | Bearer token required on ingest endpoints. If unset, endpoints are open. |
| `CTX_HOST` | `0.0.0.0` | Bind address |
| `CTX_PORT` | `8000` | Bind port |
| `CTX_APPLE_HELPER_URL` | `""` | Base URL of the macOS bridge service (context-helpers) |
| `CTX_APPLE_HELPER_API_KEY` | `""` | Bearer token for the macOS bridge — must match `server.api_key` in context-helpers config |

### macOS Bridge (context-helpers)

Apple data sources (Reminders, iMessage, Notes, Health, Music) require native macOS access and cannot run in Docker. The [`context-helpers`](../context-helpers) service runs on macOS, exposes those sources over HTTP, and the server pulls from it via `POST /ingest/apple`.

See [context-helpers/README.md](../context-helpers/README.md) for setup instructions.

### Endpoints

#### Ingestion

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/webhooks/ingest` | Bearer token (if secret set) | Push pre-normalized content from any adapter |
| `POST` | `/ingest/apple` | Bearer token (if secret set) | Pull from all configured Apple helper adapters |
| `GET` | `/health` | None | Check SQLite and ChromaDB connectivity |

#### Search

| Method | Path | Description |
|---|---|---|
| `POST` | `/query` | Semantic search with optional domain/source filter and reranking |

#### Inspection

| Method | Path | Description |
|---|---|---|
| `GET` | `/adapters` | List all registered adapters |
| `GET` | `/adapters/{adapter_id}` | Adapter detail |
| `GET` | `/sources` | List sources (filter by `domain`, `adapter_id`; paginate with `limit`/`offset`) |
| `GET` | `/sources/{source_id}` | Source detail with active chunk count |
| `GET` | `/sources/{source_id}/versions` | Version history |
| `GET` | `/sources/{source_id}/versions/{version}` | Single version with full markdown and chunk hashes |
| `GET` | `/sources/{source_id}/chunks` | Active chunks for a source (optionally scoped to a `version`) |
| `GET` | `/sources/{source_id}/diff` | Hash-set diff between two versions (`from_version`, `to_version` required) |
| `GET` | `/chunks/{chunk_hash}` | Chunk by content hash |
| `GET` | `/chunks/{chunk_hash}/provenance` | Full provenance: lineage, source origin, version chain |
| `GET` | `/chunks/{chunk_hash}/version-chain` | Ancestry chain via `parent_chunk_hash` (`source_id` required) |
| `GET` | `/stats` | Dataset-level counts by domain, retired chunks, sync queue depth |

All detail responses include a `_links` object with URLs to related resources, so the API is traversable without consulting docs.

#### Example traversal

```bash
# 1. See what's in the dataset
curl http://localhost:8000/stats

# 2. List sources in the notes domain
curl "http://localhost:8000/sources?domain=notes"

# 3. Inspect a source and its version history
curl http://localhost:8000/sources/my-source-id
curl http://localhost:8000/sources/my-source-id/versions

# 4. Diff two versions
curl "http://localhost:8000/sources/my-source-id/diff?from_version=1&to_version=2"

# 5. Trace a retrieved chunk back to its origin
curl http://localhost:8000/chunks/<chunk_hash>/provenance?source_id=my-source-id

# 6. Semantic search
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "meeting notes from last week", "top_k": 5, "domain_filter": "notes"}'

# 7. Push content via webhook
curl -X POST http://localhost:8000/webhooks/ingest \
  -H "Authorization: Bearer your-random-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "adapter_id": "my-adapter",
    "domain": "notes",
    "normalizer_version": "1.0.0",
    "items": [{"source_id": "doc-1", "markdown": "# Hello\nWorld", "structural_hints": {}}]
  }'

# 8. Pull from Apple macOS bridge
curl -X POST http://localhost:8000/ingest/apple \
  -H "Authorization: Bearer your-random-secret"
```

### Available Adapters

| Adapter | Domain | Extra | Notes |
|---|---|---|---|
| `FilesystemAdapter` | Notes | *(core)* | Markdown files |
| `FilesystemRichAdapter` | Notes | `rich-fs` | PDF, Office, images via MarkItDown |
| `ObsidianAdapter` | Notes | `obsidian` | Vault with frontmatter/wikilinks |
| `EmailAdapter` | Messages | `email` | IMAP via EmailEngine |
| `CaldavAdapter` | Events | `caldav` | CalDAV calendars |
| `AppleRemindersAdapter` | Tasks | `apple-reminders` | Via context-helpers bridge |
| `AppleHealthAdapter` | Events | `apple-health` | Via context-helpers bridge |
| `AppleiMessageAdapter` | Messages | `apple-imessage` | Via context-helpers bridge |
| `AppleNotesAdapter` | Notes | `apple-notes` | Via context-helpers bridge |
| `AppleMusicAdapter` | Events | `apple-music` | Via context-helpers bridge |

### Design Documentation

- [Architecture](./documentation/Architecture.md) — System design and component structure
- [Persistence Design](./documentation/persistence-design.md) — Dual-storage architecture and data consistency
- [Chunking Strategy](./documentation/chunking-strategy.md) — Content-aware chunking for each domain
- [Roadmap](./documentation/roadmap.md) — Implementation phases and status

---

## Design Principles

1. **Adapters are cheap to write.** The interface is small and the domain layer does the heavy lifting.
2. **Versioning is hash-based.** No complex diffing algorithms — set operations on content hashes tell you what changed.
3. **"Good enough" normalization.** Perfection isn't the goal. Phantom diffs are detectable and tolerable. Ship the normalizer, fix it when it lies.
4. **The vector store is an index, not a database.** Full content lives in the document store. You can re-embed everything without re-fetching.
5. **Domains encode semantics, adapters encode access.** A Gmail adapter knows how to fetch email. The Messages domain knows how to chunk conversations. They don't need to know about each other beyond a declared mapping.
