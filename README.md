# Context Library — Versioned RAG with Source Lineage

A retrieval-augmented generation system that tracks, versions, and diffs source documents across heterogeneous inputs. Every chunk in the vector store carries full provenance back to its origin, and content changes are detected via hash-based comparison of normalized markdown.

## Core Concepts

### Normalize → Diff → Chunk → Embed → Store

Traditional RAG pipelines treat ingestion as a one-shot operation. Chronicle adds a **diff stage** between normalization and chunking so that re-ingested sources only produce new chunk versions when content actually changes. All source content is normalized to markdown before comparison, giving a stable (if imperfect) surface for detecting meaningful changes. Trivial differences like whitespace are filtered out; the goal is paragraph-level and list-level change detection, not character-perfect diffs.

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
chronicle/
├── core/
│   ├── pipeline.py          # Orchestrates fetch → normalize → diff → chunk → embed → store
│   ├── differ.py            # Markdown diff engine, hash comparison, change detection
│   ├── chunker.py           # Domain-aware chunking strategies
│   ├── embedder.py          # Embedding interface (swappable models)
│   └── versioner.py         # Version management, hash tracking, lineage records
├── domains/
│   ├── base.py              # Abstract domain with shared behavior
│   ├── messages.py          # Thread-aware chunking, conversation reconstruction
│   ├── notes.py             # Semantic chunking with temporal metadata
│   ├── events.py            # Time-window batching, summary generation
│   └── tasks.py             # State-transition versioning, hierarchy tracking
├── adapters/
│   ├── base.py              # Adapter interface / contract
│   ├── messages/
│   │   ├── gmail.py
│   │   ├── imap.py
│   │   └── slack.py
│   ├── notes/
│   │   ├── apple_notes.py
│   │   ├── obsidian.py
│   │   └── photo_ocr.py
│   ├── events/
│   │   ├── apple_health.py
│   │   ├── spotify.py
│   │   └── strava.py
│   └── tasks/
│       ├── todoist.py
│       ├── github_issues.py
│       └── reminders.py
├── storage/
│   ├── document_store.py    # Full markdown storage, keyed by source_id + version
│   ├── vector_store.py      # Chunk embeddings with lineage metadata
│   └── models.py            # Data classes for chunks, versions, lineage records
├── retrieval/
│   ├── query.py             # RAG query interface
│   ├── reranker.py          # Cross-encoder reranking
│   └── provenance.py        # Source tracing and version history queries
└── scheduler/
    ├── poller.py            # Scheduled re-fetch for pull-based adapters
    └── watcher.py           # Webhook/filesystem watchers for push-based adapters
```

---

## Getting Started

> **Status:** Architecture phase — not yet implemented.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed data flow and class diagrams.

---

## Design Principles

1. **Adapters are cheap to write.** The interface is small and the domain layer does the heavy lifting.
2. **Versioning is hash-based.** No complex diffing algorithms — set operations on content hashes tell you what changed.
3. **"Good enough" normalization.** Perfection isn't the goal. Phantom diffs are detectable and tolerable. Ship the normalizer, fix it when it lies.
4. **The vector store is an index, not a database.** Full content lives in the document store. You can re-embed everything without re-fetching.
5. **Domains encode semantics, adapters encode access.** A Gmail adapter knows how to fetch email. The Messages domain knows how to chunk conversations. They don't need to know about each other beyond a declared mapping.
