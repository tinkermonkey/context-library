PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
PRAGMA user_version=1;

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    adapter_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (adapter_id) REFERENCES adapters(id)
);

CREATE TABLE IF NOT EXISTS adapters (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    config TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    raw_content BLOB NOT NULL,
    normalized_content TEXT NOT NULL,
    diff TEXT,
    fetched_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(id),
    UNIQUE (source_id, version_number)
);

CREATE TABLE IF NOT EXISTS chunks (
    hash TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    domain TEXT NOT NULL,
    content TEXT NOT NULL,
    domain_metadata TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(id),
    FOREIGN KEY (source_id, source_version) REFERENCES source_versions(source_id, version_number)
);
