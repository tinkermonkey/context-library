# Persistence Design

How Context Library stores, links, and maintains data across its dual-storage architecture.

---

## Storage Architecture

Context Library uses two storage engines with distinct responsibilities:

**SQLite** is the source of truth. It holds all canonical data: source versions, chunk records, lineage metadata, adapter configurations, and domain-specific metadata. Every structured or relational query — version diffs, provenance tracing, source history, state transitions — runs against SQLite.

**LanceDB** is a derived vector index. It holds embedded chunk vectors alongside a small set of denormalized metadata fields used for filtered search. It is rebuildable from SQLite at any time. If LanceDB is lost, corrupted, or needs to be regenerated (e.g., after changing embedding models), the rebuild is a scan-and-embed pass over the SQLite `chunks` table.

The **join key** between the two stores is `chunk_hash` — the content hash of each chunk's normalized markdown. This is the only field that must be consistent across both stores.

---

## SQLite Schema

### `schema_version`

Tracks the current schema version for migration management.

```sql
CREATE TABLE schema_version (
    version             INTEGER PRIMARY KEY,
    applied_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

This table enables versioned schema migrations. On startup, the application checks the current version and runs any pending migration scripts. Using a dedicated table (rather than SQLite's `PRAGMA user_version`) provides an audit trail and integrates naturally with the application's migration framework.

### `adapters`

Registry of configured adapters and their current normalizer versions.

```sql
CREATE TABLE adapters (
    adapter_id          TEXT PRIMARY KEY,
    domain              TEXT NOT NULL,
    adapter_type        TEXT NOT NULL,       -- gmail, obsidian, spotify, todoist, etc.
    normalizer_version  TEXT NOT NULL,
    config              TEXT,                -- JSON, adapter-specific configuration
    enabled             BOOLEAN NOT NULL DEFAULT 1,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### `sources`

Registry of known sources and their current state.

```sql
CREATE TABLE sources (
    source_id           TEXT PRIMARY KEY,
    adapter_id          TEXT NOT NULL,
    domain              TEXT NOT NULL,
    origin_ref          TEXT NOT NULL,       -- URL, file path, message ID, etc.
    display_name        TEXT,
    current_version     INTEGER NOT NULL DEFAULT 0,
    last_fetched_at     DATETIME,
    poll_strategy       TEXT NOT NULL,       -- push | pull | webhook
    poll_interval_sec   INTEGER,             -- for pull-based sources
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (adapter_id) REFERENCES adapters(adapter_id)
);

CREATE INDEX idx_sources_adapter ON sources(adapter_id);
CREATE INDEX idx_sources_domain ON sources(domain);
```

**Note on `updated_at`:** Triggers automatically update this column on every UPDATE statement. Unlike `created_at`, which is set only on INSERT, `updated_at` reflects the most recent modification time due to triggers executing `UPDATE sources SET updated_at = CURRENT_TIMESTAMP`.

### `source_versions`

The full normalized markdown for every version of every source. This is the document store.

```sql
CREATE TABLE source_versions (
    source_id           TEXT NOT NULL,
    version             INTEGER NOT NULL,
    markdown            TEXT NOT NULL,
    chunk_hashes        TEXT NOT NULL,       -- JSON array of chunk hashes in this version
    adapter_id          TEXT NOT NULL,
    normalizer_version  TEXT NOT NULL,
    fetch_timestamp     DATETIME NOT NULL,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_id, version),
    FOREIGN KEY (adapter_id) REFERENCES adapters(adapter_id)
);

CREATE INDEX idx_source_versions_adapter_id ON source_versions(adapter_id);
```

**Note on indexes:** The composite PRIMARY KEY (source_id, version) creates an index with `source_id` as the leading column, making the single-column index on `source_id` redundant. SQLite's leftmost prefix rule means queries filtering by `source_id` already use the primary key index efficiently.

### `chunks`

The canonical record for every chunk. One row per unique chunk content. This is the single source of truth for chunk existence and metadata.

```sql
CREATE TABLE chunks (
    chunk_hash          TEXT PRIMARY KEY,
    source_id           TEXT NOT NULL,
    source_version      INTEGER NOT NULL,
    chunk_index         INTEGER NOT NULL,
    content             TEXT NOT NULL,       -- normalized markdown text
    context_header      TEXT,                -- heading breadcrumb trail (not included in hash)
    domain              TEXT NOT NULL,       -- messages | notes | events | tasks
    adapter_id          TEXT NOT NULL,
    fetch_timestamp     DATETIME NOT NULL,
    normalizer_version  TEXT NOT NULL,
    parent_chunk_hash   TEXT,                -- hash of the chunk this replaced (version chain)
    domain_metadata     TEXT,                -- JSON, domain-specific fields
    chunk_type          TEXT DEFAULT 'standard', -- standard | oversized | table_part
    retired_at          DATETIME,            -- set when chunk is superseded by a new version
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id, source_version) REFERENCES source_versions(source_id, version),
    UNIQUE (source_id, source_version, chunk_index)
);

CREATE INDEX idx_chunks_source ON chunks(source_id, source_version);
CREATE INDEX idx_chunks_domain ON chunks(domain);
CREATE INDEX idx_chunks_parent ON chunks(parent_chunk_hash);
CREATE INDEX idx_chunks_retired ON chunks(retired_at);
CREATE INDEX idx_chunks_adapter ON chunks(adapter_id);
```

**Note on chunk indexing:** The UNIQUE constraint on (source_id, source_version, chunk_index) prevents duplicate or misordered chunks within a source version. Each index position within a version is claimed by exactly one chunk.

### Domain Metadata Tables

Domain-specific metadata is stored as JSON in `chunks.domain_metadata` for flexibility. If query performance on specific domain fields becomes a bottleneck, these can be promoted to dedicated tables with foreign keys to `chunks.chunk_hash`. Starting with JSON keeps the schema simple and avoids premature optimization.

Example of what `domain_metadata` contains per domain:

**Messages:**
```json
{
    "thread_id": "thread_abc123",
    "message_id": "msg_456",
    "sender": "alice@example.com",
    "recipients": ["bob@example.com"],
    "timestamp": "2025-03-01T10:30:00Z",
    "in_reply_to": "msg_455",
    "subject": "Re: Project update",
    "is_thread_root": false
}
```

**Notes:**
```json
{
    "created_at": "2025-03-01T09:00:00Z",
    "modified_at": "2025-03-01T14:00:00Z",
    "source_app": "obsidian",
    "tags": ["project-context-library", "architecture"],
    "title": "Persistence design notes",
    "is_handwritten_origin": false
}
```

**Events:**
```json
{
    "event_type": "music_listen",
    "window_start": "2025-03-01T08:00:00Z",
    "window_end": "2025-03-01T09:00:00Z",
    "item_count": 12,
    "summary_text": "12 tracks, mostly jazz, during morning run",
    "raw_metrics": {"avg_hr": 155, "peak_hr": 172}
}
```

**Tasks:**
```json
{
    "task_id": "task_789",
    "project": "context-library",
    "workstream": "persistence",
    "state": "in_progress",
    "previous_state": "open",
    "state_changed_at": "2025-03-01T11:00:00Z",
    "assignee": "tinkermonkey",
    "due_date": "2025-03-15",
    "priority": 1
}
```

---

## LanceDB Schema

The LanceDB table is a denormalized projection of SQLite's `chunks` table plus the embedding vector. It contains only what's needed for vector search with metadata filtering.

### `chunk_vectors`

```
chunk_hash        STRING        -- join key back to SQLite
vector            VECTOR[dim]   -- embedding (dimension depends on model)
content           STRING        -- denormalized for reranking without round-trip
domain            STRING        -- filtered search: scope to domain
source_id         STRING        -- filtered search: scope to source
source_version    INT           -- filtered search: scope to version
created_at        TIMESTAMP     -- filtered search: time-range queries
```

### `lancedb_sync_log` (SQLite)

A lightweight SQLite table to track which chunks have been synchronized to LanceDB. This enables drift detection between the two stores.

```sql
CREATE TABLE lancedb_sync_log (
    chunk_hash      TEXT PRIMARY KEY,
    synced_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chunk_hash) REFERENCES chunks(chunk_hash)
);

CREATE INDEX idx_lancedb_sync_log_synced_at ON lancedb_sync_log(synced_at);
```

This table is consulted during drift detection checks to identify chunks that should be in LanceDB but aren't (orphaned in SQLite) or chunks in LanceDB that have been retired in SQLite.

**Why these fields are denormalized:**

- `content` — Cross-encoder reranking needs the text. A round-trip to SQLite per candidate would add latency on every retrieval query.
- `domain` — Most queries are scoped to a domain ("find relevant messages" vs "find relevant notes"). Filtering at the vector search level avoids retrieving and discarding irrelevant chunks.
- `source_id` — Supports source-scoped search ("find similar content within this document").
- `source_version` — Supports version-scoped search ("search only the latest version of everything").
- `created_at` — Supports time-windowed search ("what was I working on last week").

Fields like `adapter_id`, `normalizer_version`, `parent_chunk_hash`, and `domain_metadata` are **not** denormalized into LanceDB because they're never used as vector search filters. They're only needed for provenance queries, which run against SQLite directly.

---

## Write Path

Writes are one-directional: SQLite first, LanceDB second. SQLite is the commit point.

```
1. Adapter fetches raw content from source
2. Normalizer converts to markdown
3. Differ compares against previous version in source_versions table
   └─ If no meaningful change → update last_fetched_at on sources table, stop
4. Write new row to source_versions (source_id, version+1, markdown)
5. Domain chunker produces chunks from the new markdown
6. For each chunk:
   a. Compute chunk_hash = hash(content)
   b. Check if chunk_hash exists in chunks table
      └─ If yes → this content already exists, skip embedding
      └─ If no  → insert into chunks table ← THIS IS THE COMMIT POINT
7. Update sources.current_version
8. Identify retired chunks (hashes in version N-1 not in version N)
   └─ Set retired_at on those rows in chunks table
9. Embed new chunks → bulk insert into LanceDB chunk_vectors
10. Delete retired chunk_hashes from LanceDB
```

If step 9 or 10 fails, the data is safe in SQLite. Retry embedding without re-fetching. If LanceDB is inconsistent, rebuild from SQLite.

---

## Read Paths

### Retrieval Query (semantic search)

The hot path for RAG. Hits LanceDB first, enriches from SQLite only if needed.

```
1. Embed the user's query
2. Search LanceDB chunk_vectors:
   - Vector similarity (cosine / L2)
   - Metadata filters (domain, source_id, created_at range, etc.)
   - Top-K candidates
3. Rerank candidates using cross-encoder on content field (from LanceDB, no round-trip)
4. Return top results with chunk_hash, content, and basic metadata
5. OPTIONAL: If the caller needs full lineage or domain_metadata,
   batch-fetch from SQLite chunks table by chunk_hash
```

For most retrieval use cases, steps 1-4 are sufficient. The LanceDB content + denormalized fields are enough to build LLM context. Step 5 only happens for provenance-enriched retrieval (e.g., "find relevant context and show me where it came from").

### Provenance Query (what changed, where did this come from)

Pure SQLite. LanceDB is never involved.

**Version diff — "what changed between version 3 and version 4 of this document":**

```sql
-- Get chunk hashes for both versions
SELECT chunk_hashes FROM source_versions
WHERE source_id = ? AND version IN (3, 4);

-- Added chunks: in v4 but not in v3
-- Removed chunks: in v3 but not in v4
-- Unchanged: in both
```

Then fetch the actual content for added/removed chunks from the `chunks` table to show the diff.

**Source history — "show me all versions of this URL":**

```sql
SELECT version, fetch_timestamp, normalizer_version, chunk_hashes
FROM source_versions
WHERE source_id = ?
ORDER BY version;
```

**Lineage trace — "where did this retrieved chunk come from":**

```sql
SELECT c.*, s.origin_ref, s.display_name, a.adapter_type
FROM chunks c
JOIN sources s ON c.source_id = s.source_id
JOIN adapters a ON c.adapter_id = a.adapter_id
WHERE c.chunk_hash = ?;
```

**Version chain — "show me the history of this chunk":**

```sql
WITH RECURSIVE chain AS (
    SELECT * FROM chunks WHERE chunk_hash = ?
    UNION ALL
    SELECT c.* FROM chunks c
    JOIN chain ch ON c.chunk_hash = ch.parent_chunk_hash
)
SELECT * FROM chain ORDER BY created_at;
```

**Bulk queries — "which chunks were produced by normalizer v2.1 and may need reprocessing":**

```sql
SELECT chunk_hash, source_id, source_version
FROM chunks
WHERE normalizer_version = '2.1'
AND retired_at IS NULL;
```

---

## Consistency Model

### Invariants

1. **Every chunk_hash in LanceDB exists in SQLite.** The reverse is not guaranteed — SQLite may contain chunks that haven't been embedded yet (step 9 pending) or that failed embedding.
2. **SQLite is always authoritative.** If there's a conflict between the two stores, SQLite wins.
3. **Retired chunks may linger in LanceDB.** Post-retrieval filtering against `retired_at` in SQLite catches any stale results. Lazy cleanup is fine.

### Failure Modes

| Failure | Impact | Recovery |
|---------|--------|----------|
| Step 9 fails (embedding) | Chunks exist in SQLite but aren't searchable | Retry: query unembedded chunks, embed, insert into LanceDB |
| Step 10 fails (LanceDB delete) | Stale chunks return in search results | Post-retrieval filter on `retired_at`; or periodic cleanup sweep |
| LanceDB corruption | Vector search unavailable | Full rebuild from SQLite `chunks` table |
| SQLite corruption | Data loss | Standard SQLite backup/WAL recovery. This is your real backup target. |
| Embedding model change | All vectors are stale | Truncate LanceDB, re-embed all non-retired chunks from SQLite |
| Normalizer version change | Some source markdowns may produce different chunks | Re-ingest affected sources; old chunks get retired, new ones created |

### Drift Detection

To verify LanceDB hasn't drifted from SQLite:

```sql
-- Find chunks that should be in LanceDB but aren't
SELECT chunk_hash FROM chunks
WHERE retired_at IS NULL
AND chunk_hash NOT IN (SELECT chunk_hash FROM lancedb_sync_log);

-- Find chunks in LanceDB that have been retired
SELECT chunk_hash FROM lancedb_sync_log
WHERE chunk_hash IN (SELECT chunk_hash FROM chunks WHERE retired_at IS NOT NULL);
```

A lightweight `lancedb_sync_log` table (just chunk_hash + synced_at) enables this check. Run it periodically or on startup.

---

## LanceDB Rebuild Procedure

When a full rebuild is needed (model change, corruption, index tuning):

```
1. Create a new LanceDB table (or drop and recreate)
2. Query SQLite: SELECT chunk_hash, content, domain, source_id,
   source_version, created_at FROM chunks WHERE retired_at IS NULL
3. Batch embed content (respect rate limits if using API-based embedder)
4. Bulk insert into LanceDB with vectors + metadata
5. Swap the active table reference
6. Update lancedb_sync_log
```

This is an offline operation that doesn't affect SQLite writes. New chunks arriving during rebuild are queued and inserted after the rebuild completes.

---

## Storage Layout

On disk, the data directory looks like:

```
~/.context-library/
├── context_library.db        -- SQLite database (source of truth)
├── context_library.db-wal    -- SQLite write-ahead log
├── context_library.db-shm    -- SQLite shared memory
├── vectors/                  -- LanceDB data directory
│   └── chunk_vectors.lance/  -- Lance format files
└── backups/                  -- SQLite backups (periodic)
```

SQLite is configured with:
- WAL mode for concurrent reads during writes
- Foreign keys enabled
- Journal size limit to prevent unbounded WAL growth
- Periodic `VACUUM` on a maintenance schedule

LanceDB is configured with:
- IVF-PQ indexing once the chunk count exceeds a threshold (~10K chunks)
- Below that threshold, brute-force search is fast enough
- Index rebuild triggered after significant chunk count changes

---

## Backup Strategy

**SQLite** is the critical backup target. Standard SQLite backup approaches apply:
- WAL checkpointing on a schedule
- Periodic `.backup` command to a separate file
- The backup file is a complete, self-contained copy of all data

**LanceDB** does not need independent backup. It's fully rebuildable from SQLite. Including it in backups is optional (saves rebuild time on restore but not required for data integrity).

---

## Migration Path

If the schema needs to evolve:

**SQLite migrations** follow a standard versioned migration pattern. The `schema_version` table tracks the current version, and migration scripts run on startup if needed. The application compares the current schema version against pending migrations and executes any that haven't been applied yet. This provides an audit trail (via the `applied_at` timestamp) and integrates with the application's migration framework.

SQLite's `ALTER TABLE` limitations (no column drops, limited type changes) mean some migrations require create-new-table-and-copy patterns. The migration runner handles these via explicit SQL scripts or, where the overhead is acceptable, Python code.

**LanceDB changes** (new metadata columns, dimension changes) are handled by rebuild. Drop the LanceDB table, recreate with the new schema, re-embed from SQLite. This is the same procedure as an embedding model change. The `lancedb_sync_log` table is cleared during rebuild to ensure all chunks are re-embedded.
