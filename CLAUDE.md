# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

```bash
# Install (editable, with dev tools)
pip install -e ".[dev]"

# Install with specific adapter extras
pip install -e ".[server,obsidian,email,apple-reminders,apple-imessage,apple-notes,apple-health,apple-music,caldav]"

# Run all tests
pytest

# Run tests for a specific module
pytest tests/storage/
pytest tests/core/test_pipeline.py

# Run a single test
pytest tests/storage/test_document_store.py::test_init_memory_database -v

# Lint
ruff check src/ tests/

# Type check
mypy src/context_library/
```

Python path is configured in `pyproject.toml` so pytest discovers `src/` automatically.

## Running the Server

```bash
# Docker (recommended)
WEBHOOK_SECRET=your-secret docker compose up

# With Apple macOS bridge
WEBHOOK_SECRET=your-secret \
APPLE_HELPER_URL=http://192.168.1.x:7123 \
APPLE_HELPER_API_KEY=your-helper-key \
docker compose up

# Local (requires pip install -e ".[server]")
CTX_WEBHOOK_SECRET=your-secret uvicorn context_library.server.app:app --reload
```

Key environment variables (all prefixed `CTX_`):
- `CTX_WEBHOOK_SECRET` — Bearer token required on all endpoints
- `CTX_APPLE_HELPER_URL` — Base URL of the macOS bridge (context-helpers)
- `CTX_APPLE_HELPER_API_KEY` — Must match `server.api_key` in context-helpers config.yaml
- `CTX_ENABLE_RERANKER` — Set to `true` to enable cross-encoder reranking

## Architecture

**Hexagonal architecture** with three layers: adapters (ingestion), core (processing), storage (persistence).

### Pipeline Flow

```
Adapter.fetch() → Adapter.normalize() → Differ.diff() → Domain.chunk() → Embedder.embed() → Store
```

The `IngestionPipeline` in `core/pipeline.py` orchestrates this flow. Per-source error isolation means one failing source doesn't block others.

### Key Abstractions

| Port (Interface) | Location | Purpose |
|---|---|---|
| `BaseAdapter` | `adapters/base.py` | Content ingestion contract: fetch, normalize, identity, poll_strategy, domain |
| `BaseDomain` | `domains/base.py` | Domain-specific chunking: `chunk(NormalizedContent) → List[Chunk]` |
| `VectorStore` | `storage/vector_store.py` | Abstract vector storage port (search, add, delete) |
| `DocumentStore` | `storage/document_store.py` | SQLite source-of-truth for content, versions, chunks, lineage |

### Dual-Storage Architecture

- **DocumentStore (SQLite):** Source of truth. Stores full markdown, versions, chunks, lineage records.
- **VectorStore (ChromaDB):** Search index only — fully rebuildable from SQLite via sync log.

### Content-Addressed Versioning

Chunks are identified by SHA-256 hash of normalized content (`compute_chunk_hash` in `storage/models.py`). Diffing uses set operations on hash sets — no positional alignment needed. The normalization rules (whitespace collapsing, line-ending normalization) are critical for deterministic hashing.

### Eight Domains

Each adapter declares one domain, which determines its chunking strategy:

- **Messages** (`domains/messages.py`): One chunk per message, strips quoted replies, preserves thread context
- **Notes** (`domains/notes.py`): Heading-based hierarchical chunking via mistune AST, keeps code blocks/tables atomic
- **Events** (`domains/events.py`): One-event-per-chunk with time-window batching
- **Tasks** (`domains/tasks.py`): One-task-per-chunk with lifecycle state tracking
- **Health** (`domains/health.py`): Time-series health metrics with date-stamped context headers, groups records within configurable windows
- **Documents** (`domains/documents.py`): Whole-document chunking with metadata-rich context headers; used for filesystem files and music library catalog
- **People** (`domains/people.py`): One-contact-per-chunk with contact-aware context headers and natural-language prose rendering; excludes sensitive identifiers
- **Location** (`domains/location.py`): Geospatial chunking for place visits and current location snapshots with place-name context headers or lat/lng fallback

### Data Models

All in `storage/models.py` using Pydantic v2. Key types: `NormalizedContent`, `Chunk`, `SourceVersion`, `DiffResult`, `LineageRecord`, `ChunkVectorData`. Validators enforce ISO 8601 timestamps and SHA-256 hash formats.

### SQLite Schema

Defined in `storage/schema.sql`. Uses WAL mode, foreign keys ON, compound primary keys for deduplication. The `lancedb_sync_log` table tracks pending vector store operations for consistency recovery.

## Server

The FastAPI server (`src/context_library/server/`) exposes the pipeline over HTTP for push-based ingestion and semantic search.

### Running locally

```bash
pip install -e ".[server]"
uvicorn context_library.server.app:app --host 0.0.0.0 --port 8000
```

### Running with Docker

```bash
# Build and start (data persisted in named volumes)
WEBHOOK_SECRET=your-secret docker compose up --build

# Without webhook auth
docker compose up --build
```

### Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/webhooks/ingest` | Push pre-normalized content from external sources (EmailEngine, Apple helpers) |
| `POST` | `/query` | Semantic search with optional domain/source filtering and reranking |
| `GET` | `/health` | Validates SQLite and ChromaDB connectivity |

Webhook auth: if `CTX_WEBHOOK_SECRET` is set, requests to `/webhooks/ingest` must include `Authorization: Bearer <secret>`.

### Environment variables

All variables use the `CTX_` prefix (set in env or `.env` file):

| Variable | Default | Description |
|---|---|---|
| `CTX_SQLITE_DB_PATH` | `/data/sqlite/documents.db` | SQLite database path |
| `CTX_CHROMADB_PATH` | `/data/chromadb` | ChromaDB persistence directory |
| `CTX_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model (pre-downloaded in Docker image) |
| `CTX_ENABLE_RERANKER` | `false` | Enable cross-encoder reranking on `/query` |
| `CTX_RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Reranker model (only used if reranker enabled) |
| `CTX_WEBHOOK_SECRET` | `""` (no auth) | Bearer token required on `/webhooks/ingest` |
| `CTX_HOST` | `0.0.0.0` | Bind address |
| `CTX_PORT` | `8000` | Bind port |
| `CTX_HELPER_OURA_ENABLED` | `false` | Enable OuraAdapter for Oura Ring health data |
