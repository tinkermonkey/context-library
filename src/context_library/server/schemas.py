"""Request and response models for the server API."""

from pydantic import BaseModel, ConfigDict, Field

from context_library.storage.models import Domain, StructuralHints


# ── Webhook ingestion ──────────────────────────────────────────────


class WebhookItem(BaseModel):
    """A single content item within a webhook payload."""

    source_id: str
    markdown: str
    structural_hints: StructuralHints


class WebhookIngestRequest(BaseModel):
    """Webhook ingestion payload — pre-normalized content from external sources.

    The caller identifies itself via adapter_id + domain + normalizer_version,
    then provides one or more content items to ingest.
    """

    adapter_id: str
    domain: Domain
    normalizer_version: str = "1.0.0"
    items: list[WebhookItem] = Field(min_length=1, max_length=10000)


class IngestError(BaseModel):
    """Structured error from the ingestion pipeline.

    Different error types include different optional fields:
    - ChunkingError: source_id_attr
    - EmbeddingError: chunk_hash, chunk_index
    - StorageError: store_type, inconsistent
    """

    model_config = {"extra": "allow"}

    source_id: str
    error_type: str
    message: str
    chunk_hash: str | None = None
    chunk_index: int | None = None
    store_type: str | None = None
    inconsistent: bool | None = None


class WebhookIngestResponse(BaseModel):
    status: str
    sources_processed: int
    sources_failed: int
    chunks_added: int
    chunks_removed: int
    chunks_unchanged: int
    errors: list[IngestError]


# ── Retrieval ──────────────────────────────────────────────────────


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=10, gt=0)
    domain_filter: Domain | None = None
    source_filter: str | None = None
    rerank: bool = False
    rerank_top_k: int | None = Field(default=None, gt=0)


class QueryResultItem(BaseModel):
    chunk_text: str
    chunk_hash: str
    context_header: str | None
    chunk_index: int
    chunk_type: str
    source_id: str
    source_version_id: int
    domain: str
    adapter_id: str
    embedding_model: str
    similarity_score: float


class QueryResponse(BaseModel):
    results: list[QueryResultItem]
    total: int


# ── Apple helper ingestion ─────────────────────────────────────────


class AppleAdapterResult(BaseModel):
    adapter_id: str
    status: str
    sources_processed: int
    sources_failed: int
    chunks_added: int
    chunks_removed: int
    chunks_unchanged: int
    errors: list[IngestError]


class AppleIngestResponse(BaseModel):
    adapters_run: int
    results: list[AppleAdapterResult]


# ── Health ─────────────────────────────────────────────────────────


class CollectorStatus(BaseModel):
    """Health status of a single configured adapter / helper collector."""

    name: str               # adapter_id, e.g. "apple_music:default"
    adapter_type: str       # class name, e.g. "AppleMusicAdapter"
    enabled: bool
    healthy: bool | None = None   # None = helper didn't report per-collector
    error: str | None = None


class HelperHealth(BaseModel):
    """Health status of the context-helper service."""

    reachable: bool
    probed_at: str                          # ISO 8601 UTC
    collectors: list[CollectorStatus] = []
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    vector_count: int
    embedding_model: str
    embedding_dimension: int
    sqlite_ok: bool = True
    chromadb_ok: bool = True
    helper: HelperHealth | None = None


# ── Adapters ────────────────────────────────────────────────────────


class AdapterResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    adapter_id: str
    adapter_type: str
    domain: str
    normalizer_version: str
    config: dict | None = None
    links: dict[str, str] = Field(default_factory=dict, alias="_links")


class AdapterListResponse(BaseModel):
    adapters: list[AdapterResponse]
    total: int


# ── Sources ─────────────────────────────────────────────────────────


class SourceSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_id: str
    adapter_id: str
    adapter_type: str
    domain: str
    origin_ref: str
    display_name: str | None
    current_version: int
    last_fetched_at: str | None
    poll_strategy: str
    chunk_count: int
    created_at: str
    updated_at: str
    links: dict[str, str] = Field(default_factory=dict, alias="_links")


class SourceListResponse(BaseModel):
    sources: list[SourceSummary]
    total: int
    limit: int
    offset: int


class SourceDetailResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_id: str
    adapter_id: str
    adapter_type: str
    domain: str
    origin_ref: str
    display_name: str | None
    current_version: int
    last_fetched_at: str | None
    poll_strategy: str
    poll_interval_sec: int | None
    normalizer_version: str
    created_at: str
    updated_at: str
    chunk_count: int
    links: dict[str, str] = Field(default_factory=dict, alias="_links")


class VersionSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_id: str
    version: int
    chunk_hash_count: int
    added_chunks: int
    removed_chunks: int
    unchanged_chunks: int
    adapter_id: str
    normalizer_version: str
    fetch_timestamp: str
    links: dict[str, str] = Field(default_factory=dict, alias="_links")


class VersionHistoryResponse(BaseModel):
    source_id: str
    versions: list[VersionSummary]


class VersionDetailResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_id: str
    version: int
    markdown: str
    chunk_hashes: list[str]
    adapter_id: str
    normalizer_version: str
    fetch_timestamp: str
    links: dict[str, str] = Field(default_factory=dict, alias="_links")


# ── Chunks ──────────────────────────────────────────────────────────


class LineageResponse(BaseModel):
    chunk_hash: str
    source_id: str
    source_version_id: int
    adapter_id: str
    domain: str
    normalizer_version: str
    embedding_model_id: str


class ChunkResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    chunk_hash: str
    content: str
    context_header: str | None
    chunk_index: int
    chunk_type: str
    domain_metadata: dict | None
    cross_refs: list[str]
    lineage: LineageResponse
    links: dict[str, str] = Field(default_factory=dict, alias="_links")


class ChunkListResponse(BaseModel):
    source_id: str
    version: int | None
    chunks: list[ChunkResponse]
    total: int | None = None
    limit: int | None = None
    offset: int | None = None


class ChunkVersionChainItem(BaseModel):
    chunk_hash: str
    content: str
    context_header: str | None
    chunk_index: int
    chunk_type: str


class ChunkVersionChainResponse(BaseModel):
    chunk_hash: str
    source_id: str
    chain: list[ChunkVersionChainItem]


class ChunkProvenanceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    chunk: ChunkResponse
    lineage: LineageResponse
    source_origin_ref: str
    adapter_type: str
    version_chain: list[ChunkVersionChainItem]
    links: dict[str, str] = Field(default_factory=dict, alias="_links")


class VersionDiffResponse(BaseModel):
    source_id: str
    from_version: int
    to_version: int
    added_hashes: list[str]
    removed_hashes: list[str]
    unchanged_hashes: list[str]
    added_chunks: list[ChunkVersionChainItem]
    removed_chunks: list[ChunkVersionChainItem]


# ── Stats ────────────────────────────────────────────────────────────


class DomainStats(BaseModel):
    domain: str
    source_count: int
    active_chunk_count: int


class DatasetStatsResponse(BaseModel):
    total_sources: int
    total_active_chunks: int
    retired_chunk_count: int
    sync_queue_pending_insert: int
    sync_queue_pending_delete: int
    by_domain: list[DomainStats]


# ── Top-level chunks listing ────────────────────────────────────────


class TopLevelChunkListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    chunks: list[ChunkResponse]
    total: int
    limit: int
    offset: int


# ── Adapter stats ────────────────────────────────────────────────────


class AdapterStats(BaseModel):
    adapter_id: str
    adapter_type: str
    domain: str
    source_count: int
    active_chunk_count: int


class AdapterStatsResponse(BaseModel):
    adapters: list[AdapterStats]
