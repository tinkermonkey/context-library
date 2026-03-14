# Context Library Roadmap

## Phase 1: MVP Foundation (Complete)

Phase 1 establishes the core architecture for semantic document retrieval from multiple sources. This MVP phase implements the critical path from source-agnostic data ingestion through semantic search.

### Phase 1 Components

- **Data Models** (`src/context_library/storage/models.py`) — Pydantic models defining pipeline data structures with immutable, content-addressed identity for sources, chunks, embeddings, and lineage tracking.

- **Document Store** (`src/context_library/storage/document_store.py`) — SQLite-backed document store serving as the system's source of truth for adapter registration, source tracking, version history, chunk storage, and vector store synchronization.

- **Adapter Contract** (`src/context_library/adapters/base.py`) — Abstract base class defining the adapter interface contract for normalizing diverse data sources to a common markdown representation.

- **Filesystem Adapter** (`src/context_library/adapters/filesystem.py`) — Concrete adapter implementation for discovering and normalizing local markdown files and directories into the pipeline.

- **Domain Contract** (`src/context_library/domains/base.py`) — Abstract base class defining the domain-specific chunking contract for parsing and segmenting normalized content.

- **Notes Domain** (`src/context_library/domains/notes.py`) — Concrete domain implementation for freeform markdown notes with heading-based hierarchy chunking and code/table preservation.

- **Differ** (`src/context_library/core/differ.py`) — Stateless change detector using SHA-256 content hashing to identify new, modified, and deleted sources since last ingestion run.

- **Embedder** (`src/context_library/core/embedder.py`) — Vector embedding service wrapping sentence-transformers for batch conversion of chunk text to dense semantic vectors.

- **Pipeline Orchestrator** (`src/context_library/core/pipeline.py`) — Coordinates the complete ingestion workflow: fetch → normalize → diff → chunk → embed → store with error handling and resumability.

- **Retrieval Query** (`src/context_library/retrieval/query.py`) — Semantic search interface providing vector similarity queries with optional metadata filtering over the document store.

---

## Phase 2: Multi-Source Adapters (Complete)

Phase 2 added support for additional data sources beyond plain markdown files on disk.

### Delivered

- **Shared Filesystem Watcher** (`src/context_library/adapters/_watching.py`) — Internal utility module shared by the Filesystem and Obsidian adapters. Wraps [watchdog](https://github.com/gorakhargosh/watchdog) behind a thin adapter-facing interface; each adapter instantiates its own watcher pointed at its own path scope. Maps to `PollStrategy.PUSH`.

- **Rich Filesystem Adapter** (`src/context_library/adapters/filesystem_rich.py`) — Extends the MVP filesystem adapter to handle non-markdown file formats by converting them to markdown at ingestion time via [MarkItDown](https://github.com/microsoft/markitdown) (PDFs, Office documents, images, HTML). Uses `_watching.py` for filesystem event capture.

- **Obsidian Adapter** (`src/context_library/adapters/obsidian.py`) — Ingests an Obsidian vault using `_watching.py` for filesystem event capture. Vault-specific metadata (frontmatter, tags, wikilinks) extracted via [obsidiantools](https://github.com/mfarragher/obsidiantools).

- **Email Adapter** (`src/context_library/adapters/email.py`) — IMAP ingestion via [EmailEngine](https://github.com/postalsys/emailengine).

- **CalDAV Adapter** (`src/context_library/adapters/caldav.py`) — Calendar event ingestion from CalDAV servers.

- **Messages Domain** (`src/context_library/domains/messages.py`) — Thread-aware chunking and indexing for conversational message content.

---

## Phase 3: Extended Domain Support (Complete)

Phase 3 expanded domain coverage to handle all four content types.

### Delivered

- **Events Domain** (`src/context_library/domains/events.py`) — One-event-per-chunk with time-window batching for calendar events, health metrics, and music listens.

- **Tasks Domain** (`src/context_library/domains/tasks.py`) — One-task-per-chunk with lifecycle state tracking (open → in-progress → done).

---

## Phase 4: Server and Retrieval (Complete)

Phase 4 delivered the FastAPI server, webhook ingestion, and advanced retrieval.

### Delivered

- **FastAPI Server** (`src/context_library/server/`) — HTTP API with webhook ingestion (`POST /webhooks/ingest`), semantic search (`POST /query`), and health check (`GET /health`). All configuration via `CTX_` environment variables.

- **Reranker** (`src/context_library/retrieval/reranker.py`) — Optional cross-encoder reranking (`cross-encoder/ms-marco-MiniLM-L-6-v2`) to improve result quality beyond vector similarity.

- **VectorStore port swap** — Replaced LanceDB with ChromaDB (`src/context_library/storage/chromadb_store.py`) as the default vector store implementation.

---

## Phase 5: macOS Bridge Integration (Complete)

Phase 5 added native macOS data sources via a companion bridge service.

### Delivered

- **`context-helpers` bridge service** — A standalone Python package (runs natively on macOS as a launchd agent) that exposes Apple data sources over HTTP. Provides endpoints for Reminders, iMessage, Notes, Health, and Music with Bearer token authentication.

- **Apple adapter suite** (`src/context_library/adapters/apple_*.py`) — Five adapters that pull from the context-helpers bridge:
  - `AppleRemindersAdapter` (Domain: Tasks) — Reminders via JXA/osascript
  - `AppleiMessageAdapter` (Domain: Messages) — iMessage chat.db
  - `AppleNotesAdapter` (Domain: Notes) — Apple Notes via apple-notes-to-sqlite
  - `AppleHealthAdapter` (Domain: Events) — HealthKit exports via healthkit-to-sqlite
  - `AppleMusicAdapter` (Domain: Events) — iTunes Library XML

- **`POST /ingest/apple` endpoint** — Triggers a pull from all configured Apple adapters and returns per-adapter ingestion results. Configured via `CTX_APPLE_HELPER_URL` and `CTX_APPLE_HELPER_API_KEY`.

---

## Planned

- **Scheduler** — Automated polling for pull-based adapters (currently triggered manually via `POST /ingest/apple` or external cron).

- **Provenance API** — Detailed source attribution and version history queries via REST.

- **Cross-Reference Detection** — Automatic linking of related content across domains and sources.

---

## Deferred

The following are reserved interfaces that have not yet been promoted to active implementation:

- **Versioner** (`src/context_library/core/versioner.py`) — Reserved for generalized source version management and content-addressed chunk hashing across all domains.

- **Chunker** (`src/context_library/core/chunker.py`) — Reserved for a unified chunking orchestrator that delegates to domain-specific implementations; currently domain chunking is handled directly by individual domain classes.
