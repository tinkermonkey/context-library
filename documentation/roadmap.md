Looks like the filesystem has reset on me — I can’t create files at the moment. Here’s the full roadmap document for you to copy directly into ROADMAP.md:

Roadmap
A phased plan to reach a functional MVP of Context Library. Each phase builds on the previous one and ends with a demonstrable capability. Phases are ordered by dependency, not estimated duration.

Phase 1 — Foundation
Goal: Ingest a single local file, chunk it, embed it, store it, and retrieve it by semantic search.
This phase proves the core pipeline works end to end with the simplest possible source: a markdown file on disk.
Capabilities:
	∙	Ingest a local markdown file and normalize it (trivial for markdown — the normalizer is essentially a pass-through with whitespace cleanup)
	∙	Parse the markdown into a block tree and chunk it using the structure-aware algorithm (respecting headings, code blocks, tables as atomic units)
	∙	Compute chunk hashes for each chunk
	∙	Store the full markdown and chunk records in SQLite
	∙	Embed chunks and store vectors in LanceDB
	∙	Query by natural language and retrieve relevant chunks with source attribution
	∙	Return results with context headers (heading breadcrumb trail) showing where in the document each chunk lives
What this proves: The dual-storage architecture works. SQLite and LanceDB are linked by chunk_hash. A semantic query returns results traceable to a specific file.

Phase 2 — Versioning
Goal: Re-ingest a changed file and answer “what changed” deterministically.
Capabilities:
	∙	Re-ingest a previously ingested file and detect that it has changed via markdown-level comparison
	∙	Identify which chunks are new, which are retired, and which are unchanged using hash set comparison
	∙	Store the new version in SQLite with its own chunk set while preserving the previous version
	∙	Link new chunks to their predecessors via parent_chunk_hash where content evolved (same structural position, different hash)
	∙	Skip re-embedding for unchanged chunks
	∙	Answer the query “what changed between version 1 and version 2 of this file” with a concrete list of added, removed, and unchanged chunks
	∙	Answer the query “show me all versions of this file” with a version history timeline
What this proves: Content-addressed versioning works. The system can track document evolution over time and report on it without diffing raw text — just set operations on hashes.

Phase 3 — Multi-Source Ingestion
Goal: Ingest from multiple file types through the adapter pattern and demonstrate that different source formats converge into the same pipeline.
Capabilities:
	∙	Ingest plain text files (.txt) through a text adapter that normalizes to markdown
	∙	Ingest HTML files through an HTML adapter that converts to markdown (stripping navigation, scripts, etc.)
	∙	Ingest PDF files through a PDF adapter that extracts text and normalizes to markdown
	∙	All adapters produce the same output shape: normalized markdown + source metadata
	∙	All sources flow through the same chunking, hashing, embedding, and storage pipeline
	∙	Retrieval queries return results from across all ingested sources, with lineage showing which adapter and original format each chunk came from
	∙	The adapter registry is in place: adding a new file-type adapter requires implementing the adapter interface and registering it
What this proves: The uniform adapter pattern works. Disparate formats are normalized into a single searchable corpus with full provenance.

Phase 4 — Domain Layer
Goal: Introduce the four domain classifications and demonstrate that domain-aware chunking produces meaningfully different results than one-size-fits-all chunking.
Capabilities:
	∙	Notes domain: Standard semantic chunking with temporal metadata. Local markdown and text files are classified as notes with created/modified timestamps.
	∙	Messages domain: Thread-aware chunking where individual messages are natural boundaries. Demonstrate with a sample email export (e.g., mbox or exported Gmail) or chat log. Chunks carry thread context (participants, subject, timestamps) rather than heading breadcrumbs.
	∙	Events domain: Time-windowed batching of structured records into natural-language summaries. Demonstrate with a sample data export (e.g., a CSV of music listens or workout logs). The “chunk” is a generated summary of a time window, not a text split.
	∙	Tasks domain: Task-level chunking where each task is a chunk carrying state metadata. Demonstrate with a sample task export (e.g., Todoist JSON export). State transitions between versions are tracked as meaningful changes even when text content has not changed.
	∙	Domain-specific metadata is stored in SQLite and queryable
	∙	Retrieval can be scoped to a specific domain (“search only my messages” vs “search everything”)
What this proves: The domain layer adds real value on top of the adapter/chunking pipeline. Messages, notes, events, and tasks are chunked and indexed in ways that respect their inherent structure, and retrieval quality improves because of it.

Phase 5 — Scheduling and Change Detection
Goal: Move from manual “ingest this file” to automated monitoring of sources for changes.
Capabilities:
	∙	A scheduler watches registered sources and re-ingests them on a configurable interval (pull-based polling)
	∙	Filesystem watcher detects changes to local files and directories and triggers re-ingestion (push-based for local sources)
	∙	The diff stage correctly identifies “no meaningful change” and skips reprocessing (no phantom version bumps for whitespace-only or formatting-only changes)
	∙	A simple dashboard or log shows: which sources were checked, which had changes, which produced new versions
	∙	Batch re-ingestion is efficient: only changed sources produce new chunks, only new chunks are embedded
What this proves: The system can run continuously and maintain an up-to-date index without manual intervention. The diff stage prevents wasteful reprocessing.

Phase 6 — Web and Remote Adapters
Goal: Extend beyond local files to web-based and remote sources.
Capabilities:
	∙	Web scraper adapter: Ingest a URL, extract main content (stripping nav, ads, boilerplate), normalize to markdown. Track the URL as a source and detect content changes on re-scrape.
	∙	Browser bookmarks adapter: Import bookmarks from a browser export, scrape each bookmarked URL, and ingest the content. New bookmarks trigger ingestion; removed bookmarks retire their chunks.
	∙	Email adapter: Connect to an email account (IMAP or exported archive) and ingest messages into the Messages domain with proper threading.
	∙	Remote sources work with the same versioning, chunking, and retrieval pipeline as local files
	∙	Source metadata carries origin URLs and fetch timestamps for remote provenance
What this proves: The system handles heterogeneous, remote sources alongside local files. The adapter pattern scales to network-based ingestion with the same guarantees.

Phase 7 — Desktop Application
Goal: Package Context Library as a standalone desktop application that a non-technical user could install and run.
Capabilities:
	∙	Tauri shell wrapping a local web UI for browsing, searching, and managing the Context Library corpus
	∙	Python backend bundled as a PyInstaller sidecar, launched and managed by Tauri
	∙	Source management: add/remove sources, configure polling intervals, view ingestion status
	∙	Search interface: natural language queries with results showing matched chunks, source attribution, and version history
	∙	Version explorer: select a source, browse its versions, see what changed between any two versions
	∙	Domain-scoped views: filter by messages, notes, events, or tasks
	∙	System runs entirely locally — no cloud services required (assuming local embedding model)
What this proves: Context Library is usable as a product, not just a pipeline. The Tauri + Python sidecar architecture delivers a native desktop experience.

Phase 8 — Image and Multimodal Content
Goal: Handle non-text content by converting it to text before it enters the standard pipeline.
Capabilities:
	∙	Photos of handwritten notes are processed by a vision LLM to produce markdown text, which is then chunked and indexed normally. The original image path is preserved in lineage metadata.
	∙	Documents containing inline images maintain the image reference bundled with its descriptive context (caption, alt text, surrounding paragraph) as an atomic chunk.
	∙	PDF pages with mixed text and images extract both, with images processed through vision LLM for description.
	∙	The Notes domain handles photo-to-text as a first-class ingestion path.
What this proves: The system’s “normalize everything to markdown” philosophy extends to visual content through LLM-assisted conversion, maintaining the same versioning and retrieval guarantees.

MVP Boundary
Phases 1 through 5 constitute the MVP. At that point, Context Library can:
	∙	Ingest files in multiple formats through uniform adapters
	∙	Normalize all content to markdown and chunk it with structure-aware, domain-specific strategies
	∙	Version every chunk via content hashing and track changes over time
	∙	Store full provenance from source to chunk with traceable lineage
	∙	Answer semantic queries across the entire corpus with source attribution
	∙	Answer “what changed” queries deterministically via hash set comparison
	∙	Monitor sources for changes and re-ingest automatically
	∙	Scope all of the above across four domain-specific models: messages, notes, events, and tasks
Phases 6 through 8 extend reach (more sources, desktop packaging, multimodal) but the core value proposition is complete at phase 5.

What’s Explicitly Deferred
These are capabilities that belong in the system eventually but are not part of the MVP:
	∙	Cross-reference detection between chunks (“as shown in the table above” linking). Useful for retrieval context enrichment but heuristic-heavy and not required for core value.
	∙	Reranking pipeline. MVP uses raw vector similarity. Cross-encoder reranking improves quality but can be layered on without architectural changes.
	∙	Access control and multi-user. Context Library is single-user/local-first for MVP.
	∙	Plugin/extension API. Third-party adapters are a goal but MVP adapters are built-in.
	∙	Sync/backup to cloud. Local-only for MVP. SQLite’s portability makes this straightforward to add later.
	∙	Natural language version queries. “What changed in my project notes this week” as a query the LLM can answer by combining retrieval with version diff data. Powerful but depends on solid retrieval and versioning being in place first.

The key structural decision here is drawing the MVP line after phase 5 rather than phase 7. The desktop app (phase 7) is important for usability, but the core value — versioned RAG with source lineage across domain-specific adapters — is fully demonstrable at phase 5 via CLI or a simple API. Packaging it pretty can come after the engine works.​​​​​​​​​​​​​​​​
