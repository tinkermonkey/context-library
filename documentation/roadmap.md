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

## Phase 2: Scheduler and Multi-Source Adapters

Phase 2 adds automated ingestion scheduling and support for additional data sources beyond plain markdown files on disk.

### Planned Features

- **Scheduler Components** (`src/context_library/scheduler/poller.py`, `src/context_library/scheduler/watcher.py`) — Automated polling and file system watching for continuous ingestion of new and modified content.

- **Email Adapter** — Integration for ingesting and indexing email content as a retrievable source. Uses [EmailEngine](https://github.com/postalsys/emailengine), a headless email client that exposes a unified REST API over IMAP, SMTP, Gmail API, and MS Graph API, abstracting provider-specific auth flows. For direct IMAP/SMTP access, [email-oauth2-proxy](https://github.com/simonrob/email-oauth2-proxy) provides transparent OAuth 2.0 (SASL XOAUTH2) proxying for providers including Gmail, Outlook, Yahoo, and Fastmail, with support for headless deployments and secrets-manager-backed credential storage. Credentials are never stored in plaintext; short-lived access tokens and refresh tokens are managed by the OAuth layer.

- **Shared Filesystem Watcher** (`src/context_library/adapters/_watching.py`) — Internal utility module shared by the Filesystem and Obsidian adapters. Wraps [watchdog](https://github.com/gorakhargosh/watchdog) (cross-platform, event-driven) or [watchfiles](https://github.com/samuelcolvin/watchfiles) (Rust-backed, lower latency) behind a thin adapter-facing interface: each adapter instantiates its own watcher pointed at its own path scope — there is no shared singleton. The module encapsulates watchdog `Observer` lifecycle, translates `FileSystemEvent` objects into `SourceRef` values the pipeline understands, and maps to `PollStrategy.PUSH` so the Scheduler routes events through its existing `handle_webhook` path rather than a polling loop. Code is shared at import time; OS-level watchers remain independent per adapter.

- **Filesystem Adapter** (`src/context_library/adapters/filesystem_rich.py`) — Extends the MVP filesystem adapter to handle non-markdown file formats by converting them to markdown at ingestion time. [MarkItDown](https://github.com/microsoft/markitdown) (Microsoft) converts PDFs, Office documents (docx, xlsx, pptx), images, HTML, and audio files into LLM-ready markdown; [Pandoc](https://pandoc.org/) serves as a fallback for formats MarkItDown does not cover (e.g. LaTeX, EPUB, RST, ODT). Uses `_watching.py` for filesystem event capture. Filesystem metadata — MIME type, file size, creation/modification timestamps, and directory hierarchy — is captured and stored as chunk metadata to augment retrieval.

- **Obsidian Adapter** (`src/context_library/adapters/obsidian.py`) — Ingests an Obsidian vault using `_watching.py` for filesystem event capture, without any format conversion since vault notes are already markdown. Vault-specific metadata is extracted using [obsidiantools](https://github.com/mfarragher/obsidiantools) (graph-level analytics: backlinks, wikilinks, note connectivity) and [obsidianmd-parser](https://pypi.org/project/obsidianmd-parser/) (per-note: YAML frontmatter, tags, Dataview fields, aliases). Extracted metadata — tags, aliases, frontmatter properties, wikilink graph edges, and creation/modification dates — is stored alongside chunks to enable metadata-filtered retrieval and graph-aware ranking.

- **Messages Domain** (`src/context_library/domains/messages.py`) — Domain implementation for chunking and indexing conversational message content with thread and author preservation.

---

## Phase 3: Extended Domain Support

Phase 3 expands domain coverage to handle additional content types and data structures beyond notes.

### Planned Features

- **Events Domain** (`src/context_library/domains/events.py`) — Domain implementation for calendar events, meeting notes, and temporal content with time-aware chunking.

- **Tasks Domain** (`src/context_library/domains/tasks.py`) — Domain implementation for structured task lists with hierarchy preservation and status-aware filtering.

- **Additional Adapters** — Further integrations for specialized data sources and APIs.

---

## Phase 4: Advanced Retrieval and Optimization

Phase 4 enhances retrieval capabilities with ranking, provenance tracking, and performance optimization for large-scale deployments.

### Planned Features

- **Reranker** (`src/context_library/retrieval/reranker.py`) — Cross-encoder-based result ranking to improve semantic search quality beyond vector similarity.

- **Provenance API** (`src/context_library/retrieval/provenance.py`) — Detailed tracking of retrieved content lineage with source attribution, version history, and confidence scoring.

- **Cross-Reference Detection** — Automatic identification and linking of related content across multiple domains and sources.

- **Performance Optimization** — LanceDB IVF-PQ indexing for efficient vector search at scale and query latency improvements.

---

## Out of Scope for Phase 1

The following files exist in the codebase but represent reserved interfaces for future cross-domain abstraction and are explicitly deferred:

- **Versioner** (`src/context_library/core/versioner.py`) — Reserved for generalized source version management and content-addressed chunk hashing across all domains.

- **Chunker** (`src/context_library/core/chunker.py`) — Reserved for a unified chunking orchestrator that delegates to domain-specific implementations; currently domain chunking is handled directly by individual domain classes.
