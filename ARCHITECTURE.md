# Architecture

Context Library is a versioned RAG (retrieval-augmented generation) pipeline. Every piece of ingested content is normalized to markdown, chunked according to its semantic domain, embedded, and stored in two complementary stores. Re-ingestion detects changes at the chunk level using content hashes, so only genuinely new or modified chunks are re-embedded.

---

## System Topology

```mermaid
graph TB
    subgraph Sources["External Sources"]
        FS[Filesystem / Obsidian]
        EM[Email / IMAP]
        CD[CalDAV]
        AH[Apple context-helpers<br/>macOS bridge :7123]
    end

    subgraph Server["context-library server :8000"]
        WH["POST /webhooks/ingest<br/>(push — any adapter)"]
        AP["POST /ingest/apple<br/>(pull — Apple adapters)"]
        QY["POST /query<br/>(semantic search)"]
        IN["GET /adapters · /sources<br/>/chunks · /stats<br/>(inspection)"]
    end

    subgraph Pipeline["Ingestion Pipeline"]
        ADP["Adapter<br/>fetch() → NormalizedContent"]
        DIF["Differ<br/>hash-set change detection"]
        DOM["Domain Chunker<br/>Notes · Messages · Events · Tasks"]
        EMB["Embedder<br/>all-MiniLM-L6-v2"]
    end

    subgraph Storage["Storage Layer"]
        SQL[(SQLite<br/>source of truth)]
        CHR[(ChromaDB<br/>search index)]
    end

    FS & EM & CD -->|direct adapter| WH
    AH -->|HTTP pull| AP
    WH & AP --> ADP
    ADP --> DIF
    DIF -->|changed| DOM
    DOM --> EMB
    DOM -->|chunks + versions + lineage| SQL
    EMB -->|vectors + metadata| CHR
    DIF -->|unchanged| SQL
    QY --> EMB
    EMB -->|query vector| CHR
    CHR -->|chunk hashes| SQL
    SQL -->|full chunks + lineage| QY
    IN --> SQL
```

---

## Adapter Layer

Every content source is an adapter. Adapters implement a single contract and declare which semantic domain they belong to. The domain declaration is what determines chunking strategy — an adapter that produces email never needs to know how email is chunked.

### BaseAdapter contract

```python
class BaseAdapter(ABC):
    adapter_id: str          # deterministic, unique across all instances
    domain: Domain           # MESSAGES | NOTES | EVENTS | TASKS
    normalizer_version: str  # bump when normalization logic changes
    poll_strategy: PollStrategy  # PUSH | PULL | WEBHOOK

    def fetch(source_ref: str) -> Iterator[NormalizedContent]: ...
    def register(document_store: DocumentStore) -> str: ...
```

`fetch()` is a generator — it yields one `NormalizedContent` per logical source (e.g., one per file, one per email thread). Each yielded item carries a `source_id`, a markdown string, and `StructuralHints` (boolean flags for headings, lists, tables, and an array of natural boundary positions).

### Implemented adapters

| Adapter | Domain | Poll strategy | Source |
|---|---|---|---|
| `FilesystemAdapter` | Notes | Pull | Local `.md` files |
| `FilesystemRichAdapter` | Notes | Pull | PDF, Office, images via MarkItDown |
| `ObsidianAdapter` | Notes | Pull | Obsidian vault (frontmatter, wikilinks) |
| `ObsidianTasksAdapter` | Tasks | Pull | Obsidian Tasks plugin |
| `EmailAdapter` | Messages | Pull | IMAP via EmailEngine REST API |
| `CaldavAdapter` | Events | Pull | CalDAV calendars |
| `AppleRemindersAdapter` | Tasks | Pull | macOS context-helpers bridge |
| `AppleHealthAdapter` | Events | Pull | macOS context-helpers bridge |
| `AppleiMessageAdapter` | Messages | Pull | macOS context-helpers bridge |
| `AppleNotesAdapter` | Notes | Pull | macOS context-helpers bridge |
| `AppleMusicAdapter` | Events | Pull | macOS context-helpers bridge |

### Adapter class hierarchy

```mermaid
classDiagram
    class BaseAdapter {
        <<abstract>>
        +adapter_id str
        +domain Domain
        +normalizer_version str
        +poll_strategy PollStrategy
        +fetch(source_ref) Iterator~NormalizedContent~
        +register(document_store) str
    }

    class FilesystemAdapter { +directory Path }
    class FilesystemRichAdapter { +directory Path }
    class ObsidianAdapter { +vault_path Path }
    class ObsidianTasksAdapter { +vault_path Path }
    class EmailAdapter { +emailengine_url str; +account_id str }
    class CaldavAdapter { +caldav_url str }

    class AppleRemindersAdapter { +api_url str; +api_key str }
    class AppleHealthAdapter { +api_url str; +api_key str; +activity_type str }
    class AppleiMessageAdapter { +api_url str; +api_key str }
    class AppleNotesAdapter { +api_url str; +api_key str }
    class AppleMusicAdapter { +api_url str; +api_key str }

    FilesystemAdapter --|> BaseAdapter
    FilesystemRichAdapter --|> BaseAdapter
    ObsidianAdapter --|> BaseAdapter
    ObsidianTasksAdapter --|> BaseAdapter
    EmailAdapter --|> BaseAdapter
    CaldavAdapter --|> BaseAdapter
    AppleRemindersAdapter --|> BaseAdapter
    AppleHealthAdapter --|> BaseAdapter
    AppleiMessageAdapter --|> BaseAdapter
    AppleNotesAdapter --|> BaseAdapter
    AppleMusicAdapter --|> BaseAdapter
```

---

## macOS Bridge Pattern

Apple data sources (Reminders, Health, iMessage, Notes, Music) require native macOS APIs that cannot run in Docker. The companion [`context-helpers`](../context-helpers) service runs on macOS, exposes those sources over a local HTTP API, and context-library pulls from it at ingest time.

```mermaid
sequenceDiagram
    participant CL as context-library :8000
    participant AA as Apple Adapter
    participant CH as context-helpers :7123<br/>(macOS)
    participant OS as macOS APIs

    CL->>AA: pipeline.ingest(adapter, domain_chunker)
    AA->>CH: GET /reminders?since=... <br/>Authorization: Bearer api_key
    CH->>OS: EventKit / HealthKit / Messages
    OS-->>CH: native data
    CH-->>AA: JSON response
    AA-->>CL: Iterator[NormalizedContent]
```

All five Apple adapters follow this pattern, varying only in the endpoint they call (`/reminders`, `/workouts`, `/messages`, `/notes`, `/tracks`) and the metadata they extract.

Configured via two environment variables on the context-library server:
- `CTX_APPLE_HELPER_URL` — base URL of the macOS bridge (e.g., `http://192.168.1.x:7123`)
- `CTX_APPLE_HELPER_API_KEY` — must match `server.api_key` in context-helpers `config.yaml`

If either variable is absent at startup, the Apple adapters are not registered and `POST /ingest/apple` returns a 404.

---

## Ingestion Pipeline

The `IngestionPipeline` in `core/pipeline.py` orchestrates the full flow. Each source is processed independently — a failure on one does not block others.

```mermaid
flowchart TD
    A([adapter.fetch]) --> B[NormalizedContent\nmarkdown + structural_hints]
    B --> C{get_latest_version\nfrom SQLite}
    C -->|first ingest| E
    C -->|prev version exists| D[Differ\nhash-set comparison]
    D -->|unchanged| U[update last_fetched_at\nskip everything else]
    D -->|changed| E[Domain Chunker\nNotes · Messages · Events · Tasks]
    E --> F[compute chunk_hash\nSHA-256 of normalized content]
    F --> G[split chunks into\nadded · removed · unchanged]
    G --> H[Embedder\nembed added chunks only\ncontext_header prepended]
    H --> I[build LineageRecords\nadapter · source · version · model]
    I --> J[(SQLite writes\ncreate_source_version\nwrite_chunks\nwrite_sync_log\nretire_chunks)]
    J --> K[(ChromaDB writes\nadd_vectors for added\ndelete_vectors for removed)]
    K --> L([return stats\nsources_processed · chunks_added\nchunks_removed · chunks_unchanged])
    U --> L
```

### Key pipeline invariants

**Context headers are embedded but not hashed.** Each chunk stores a `context_header` (e.g., the heading breadcrumb `# Section > ## Subsection` for a notes chunk, or `Subject — Sender` for a message). The embedding input is `context_header + "\n\n" + content`, but the SHA-256 hash is computed on `content` only. This means changing the heading of a section doesn't invalidate unchanged body chunks.

**Only added chunks are re-embedded.** Unchanged chunks carry their original `embedding_model_id` in the lineage record, so if the embedding model is swapped, old chunks are identifiable and can be selectively re-embedded.

**SQLite writes precede vector writes.** If the vector write fails after SQLite succeeds, `StorageError(inconsistent=True)` is raised. The `lancedb_sync_log` table records all pending inserts and deletes, so the vector store can be rebuilt from SQLite at any time.

---

## Domain Layer

The four domains encode semantic chunking knowledge. Every adapter declares one domain; the pipeline looks up the corresponding chunker via the domain registry.

```mermaid
classDiagram
    class BaseDomain {
        <<abstract>>
        +hard_limit int
        +chunk(content NormalizedContent) list~Chunk~
        #_split_if_needed(text) list~str~
        #_apply_cross_references(chunks) list~Chunk~
    }

    class NotesDomain {
        +soft_limit int
        Heading-based hierarchical chunking
        via mistune AST. Code blocks and
        tables are atomic. Context header
        is the heading breadcrumb path.
    }

    class MessagesDomain {
        Strips quoted replies. One chunk
        per message. Context header is
        subject and sender.
    }

    class EventsDomain {
        Time-window batching. Produces
        natural-language summaries of
        activity windows.
    }

    class TasksDomain {
        One chunk per task. Tracks
        lifecycle state transitions
        (open → in_progress → done).
    }

    NotesDomain --|> BaseDomain
    MessagesDomain --|> BaseDomain
    EventsDomain --|> BaseDomain
    TasksDomain --|> BaseDomain
```

### Domain → adapter mapping

```mermaid
graph LR
    subgraph NOTES["Notes domain"]
        F[FilesystemAdapter]
        FR[FilesystemRichAdapter]
        OB[ObsidianAdapter]
        AN[AppleNotesAdapter]
    end
    subgraph MESSAGES["Messages domain"]
        EM[EmailAdapter]
        IM[AppleiMessageAdapter]
    end
    subgraph EVENTS["Events domain"]
        CA[CaldavAdapter]
        AH[AppleHealthAdapter]
        AM[AppleMusicAdapter]
    end
    subgraph TASKS["Tasks domain"]
        OT[ObsidianTasksAdapter]
        AR[AppleRemindersAdapter]
    end
```

---

## Dual Storage Architecture

```mermaid
graph TD
    subgraph SQLite["SQLite — source of truth"]
        AD[adapters\nadapter_id · domain · config]
        SO[sources\nsource_id · current_version · poll_strategy]
        SV[source_versions\nimmutable snapshots\nfull markdown · chunk_hashes JSON]
        CK[chunks\ncontent · context_header · domain_metadata\nchunk_type · retired_at]
        LG[lineage\nchunk_hash → source · version · adapter · model]
        SL[lancedb_sync_log\npending inserts and deletes]
    end

    subgraph ChromaDB["ChromaDB — search index"]
        VEC[vectors\nchunk_hash · embedding · domain\nsource_id · source_version]
    end

    AD --> SO --> SV --> CK --> LG
    CK -.->|sync log tracks| SL
    SL -.->|rebuildable from| VEC
    CK -->|embedded content| VEC
```

**SQLite** stores everything: the full normalized markdown for every version, all chunk text, lineage records, and a sync log of pending vector operations. It is the authoritative record and can fully reconstruct the ChromaDB index.

**ChromaDB** stores only what is needed for similarity search: the embedding vector, chunk hash (join key back to SQLite), domain, source ID, and version. It is treated as disposable — if it diverges from SQLite, the sync log contains the operations needed to repair it.

### Content-addressed chunk identity

Chunks are identified by `SHA-256(normalize(content))`. Normalization collapses whitespace, strips trailing spaces per line, and normalizes line endings. The same logical content always produces the same hash regardless of which adapter, source, or version produced it — enabling cross-source deduplication and stable version diffing via set operations.

```
added   = curr_hashes − prev_hashes   → new chunks to embed and store
removed = prev_hashes − curr_hashes   → old chunks to retire and delete from vectors
unchanged = curr_hashes ∩ prev_hashes → carry forward, no re-embedding needed
```

### Consistency and recovery

| Failure point | Outcome | Recovery |
|---|---|---|
| Adapter fetch fails | `ChunkingError` logged; source skipped | Re-run ingest |
| SQLite write fails | `StorageError(inconsistent=False)` | Re-run ingest |
| ChromaDB write fails after SQLite succeeds | `StorageError(inconsistent=True)` logged | Replay `lancedb_sync_log` |
| All sources fail | `AllSourcesFailedError` raised | Check adapter config |
| ChromaDB fully lost | Rebuild from SQLite via sync log | Full re-embed |

---

## Retrieval Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant QR as POST /query
    participant EM as Embedder
    participant CH as ChromaDB
    participant SQ as SQLite
    participant RR as Reranker (optional)

    C->>QR: {query, top_k, domain_filter?, source_filter?}
    QR->>EM: embed_query(query)
    EM-->>QR: query_vector [384 dims]
    QR->>CH: search(query_vector, top_k, filters)
    CH-->>QR: [{chunk_hash, similarity_score}]
    loop for each result
        QR->>SQ: get_chunk_by_hash(chunk_hash)
        QR->>SQ: get_lineage(chunk_hash)
        SQ-->>QR: Chunk + LineageRecord
    end
    opt reranking enabled
        QR->>RR: rerank(query, candidates, rerank_top_k)
        RR-->>QR: reordered candidates
    end
    QR-->>C: [{chunk_text, chunk_hash, context_header,<br/>source_id, domain, similarity_score, ...}]
```

Retrieval enriches vector search results with full chunk content and lineage from SQLite. Chunks that appear in the vector store but not SQLite (inconsistency) are skipped with a warning. Retired chunks are lazily cleaned up on read.

---

## SQLite Schema

```mermaid
erDiagram
    adapters {
        text adapter_id PK
        text domain
        text adapter_type
        text normalizer_version
        text config
    }

    sources {
        text source_id PK
        text adapter_id FK
        text domain
        text origin_ref
        text display_name
        int current_version
        datetime last_fetched_at
        text poll_strategy
        int poll_interval_sec
    }

    source_versions {
        text source_id PK_FK
        int version PK
        text markdown
        text chunk_hashes
        text adapter_id FK
        text normalizer_version
        datetime fetch_timestamp
    }

    chunks {
        text chunk_hash PK
        text source_id PK_FK
        int source_version PK_FK
        int chunk_index
        text content
        text context_header
        text domain
        text chunk_type
        text domain_metadata
        text parent_chunk_hash FK
        datetime retired_at
    }

    lancedb_sync_log {
        int id PK
        text chunk_hash
        text operation
        datetime synced_at
    }

    adapters ||--o{ sources : "registers"
    sources ||--o{ source_versions : "has"
    source_versions ||--o{ chunks : "contains"
    chunks ||--o{ chunks : "parent_chunk_hash"
    chunks ||--o{ lancedb_sync_log : "tracked by"
```

The composite primary key on `chunks` (`chunk_hash, source_id, source_version`) means the same content hash can exist across multiple sources and versions. The `parent_chunk_hash` self-reference enables version chain traversal — following ancestry from the current chunk back to its original form.

---

## Server Layer

The FastAPI server initializes all pipeline components during lifespan startup and stores them on `app.state` for route access. All blocking database and embedding operations are dispatched via `asyncio.to_thread`.

```mermaid
graph TD
    subgraph Startup["lifespan startup"]
        DS[DocumentStore\nSQLite WAL]
        EM[Embedder\nsentence-transformers]
        DF[Differ]
        VS[ChromaDBVectorStore]
        PL[IngestionPipeline\nDS + EM + DF + VS]
        RR[Reranker\noptional]
        AA[Apple Adapters\noptional — if CTX_APPLE_HELPER_URL set]
    end

    subgraph Routes
        R1["POST /webhooks/ingest"]
        R2["POST /ingest/apple"]
        R3["POST /query"]
        R4["GET /health"]
        R5["GET /adapters · /sources\n/chunks · /stats"]
    end

    PL --> R1
    PL & AA --> R2
    EM & VS & DS & RR --> R3
    DS & VS --> R4
    DS --> R5
```

`POST /webhooks/ingest` and `POST /ingest/apple` both authenticate via a constant-time Bearer token comparison against `CTX_WEBHOOK_SECRET`. All read endpoints (`/adapters`, `/sources`, `/chunks`, `/stats`) are unauthenticated — place a reverse proxy with access controls in front if the server is internet-facing.
