PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
PRAGMA user_version=1;

CREATE TABLE IF NOT EXISTS sources (
    source_id           TEXT PRIMARY KEY,
    adapter_id          TEXT NOT NULL,
    domain              TEXT NOT NULL,
    origin_ref          TEXT NOT NULL,
    display_name        TEXT,
    current_version     INTEGER NOT NULL DEFAULT 0,
    last_fetched_at     DATETIME,
    poll_strategy       TEXT NOT NULL,
    poll_interval_sec   INTEGER,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sources_adapter ON sources(adapter_id);
CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources(domain);

CREATE TABLE IF NOT EXISTS adapters (
    adapter_id          TEXT PRIMARY KEY,
    domain              TEXT NOT NULL,
    adapter_type        TEXT NOT NULL,
    normalizer_version  TEXT NOT NULL,
    config              TEXT,
    enabled             BOOLEAN NOT NULL DEFAULT 1,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_versions (
    source_id           TEXT NOT NULL,
    version             INTEGER NOT NULL,
    markdown            TEXT NOT NULL,
    chunk_hashes        TEXT NOT NULL,
    adapter_id          TEXT NOT NULL,
    normalizer_version  TEXT NOT NULL,
    fetch_timestamp     DATETIME NOT NULL,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_id, version)
);

CREATE INDEX IF NOT EXISTS idx_source_versions_source_id ON source_versions(source_id);
CREATE INDEX IF NOT EXISTS idx_source_versions_adapter_id ON source_versions(adapter_id);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_hash          TEXT PRIMARY KEY,
    source_id           TEXT NOT NULL,
    source_version      INTEGER NOT NULL,
    chunk_index         INTEGER NOT NULL,
    content             TEXT NOT NULL,
    context_header      TEXT,
    domain              TEXT NOT NULL,
    adapter_id          TEXT NOT NULL,
    fetch_timestamp     DATETIME NOT NULL,
    normalizer_version  TEXT NOT NULL,
    parent_chunk_hash   TEXT,
    domain_metadata     TEXT,
    chunk_type          TEXT DEFAULT 'standard',
    retired_at          DATETIME,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id, source_version) REFERENCES source_versions(source_id, version)
);

CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_id, source_version);
CREATE INDEX IF NOT EXISTS idx_chunks_domain ON chunks(domain);
CREATE INDEX IF NOT EXISTS idx_chunks_parent ON chunks(parent_chunk_hash);
CREATE INDEX IF NOT EXISTS idx_chunks_retired ON chunks(retired_at);
CREATE INDEX IF NOT EXISTS idx_chunks_adapter ON chunks(adapter_id);
