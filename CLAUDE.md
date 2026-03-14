# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

```bash
# Install (editable, with dev tools)
pip install -e ".[dev]"

# Install with specific adapter extras
pip install -e ".[obsidian,email,apple-health,caldav]"

# Run all tests
.venv/bin/pytest

# Run tests for a specific module
.venv/bin/pytest tests/storage/
.venv/bin/pytest tests/core/test_pipeline.py

# Run a single test
.venv/bin/pytest tests/storage/test_document_store.py::test_init_memory_database -v

# Lint
.venv/bin/ruff check src/ tests/

# Type check
.venv/bin/mypy src/context_library/
```

Python path is configured in `pyproject.toml` so pytest discovers `src/` automatically.

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

### Four Domains

Each adapter declares one domain, which determines its chunking strategy:

- **Messages** (`domains/messages.py`): One chunk per message, strips quoted replies, preserves thread context
- **Notes** (`domains/notes.py`): Heading-based hierarchical chunking via mistune AST, keeps code blocks/tables atomic
- **Events** (`domains/events.py`): One-event-per-chunk with time-window batching
- **Tasks** (`domains/tasks.py`): One-task-per-chunk with lifecycle state tracking

### Data Models

All in `storage/models.py` using Pydantic v2. Key types: `NormalizedContent`, `Chunk`, `SourceVersion`, `DiffResult`, `LineageRecord`, `ChunkVectorData`. Validators enforce ISO 8601 timestamps and SHA-256 hash formats.

### SQLite Schema

Defined in `storage/schema.sql`. Uses WAL mode, foreign keys ON, compound primary keys for deduplication. The `lancedb_sync_log` table tracks pending vector store operations for consistency recovery.
