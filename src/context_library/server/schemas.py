"""Request and response models for the server API."""

from pydantic import BaseModel, Field

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


# ── Health ─────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str
    vector_count: int
    embedding_model: str
    embedding_dimension: int
