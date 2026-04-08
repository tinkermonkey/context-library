/**
 * TypeScript interfaces mirroring backend Pydantic schemas.
 * All fields match the backend server/schemas.py exactly.
 */

// ── Health ──────────────────────────────────────────────────────

export interface EndpointDeliveryStatus {
  cursor: string | null;
  has_more: boolean;
}

export interface CollectorDeliveryStatus {
  cursor: string | null;  // simple collectors: last delivery cursor
  has_more: boolean;      // simple collectors: more pages exist
  has_pending: boolean;   // simple collectors: stash loaded (PagedCollectors only)
  endpoints: Record<string, EndpointDeliveryStatus> | null;  // multi-endpoint collectors
}

export interface CollectorStatus {
  name: string;           // adapter_id, e.g. "apple_music:default"
  adapter_type: string;   // class name, e.g. "AppleMusicAdapter"
  enabled: boolean;
  healthy: boolean | null;
  error: string | null;
  delivery: CollectorDeliveryStatus | null;  // null if /status unavailable
}

export interface HelperHealth {
  reachable: boolean;
  probed_at: string;      // ISO 8601 UTC
  collectors: CollectorStatus[];
  error: string | null;
  watermark: string | null;  // last successful delivery; null if never
}

export interface HealthResponse {
  status: string;
  vector_count: number;
  embedding_model: string;
  embedding_dimension: number;
  sqlite_ok: boolean;
  chromadb_ok: boolean;
  helper: HelperHealth | null;
}

// ── Stats ────────────────────────────────────────────────────────

export interface DomainStats {
  domain: string;
  source_count: number;
  active_chunk_count: number;
}

export interface DatasetStatsResponse {
  total_sources: number;
  total_active_chunks: number;
  retired_chunk_count: number;
  sync_queue_pending_insert: number;
  sync_queue_pending_delete: number;
  by_domain: DomainStats[];
}

export interface AdapterStats {
  adapter_id: string;
  adapter_type: string;
  domain: string;
  source_count: number;
  active_chunk_count: number;
}

export interface AdapterStatsResponse {
  adapters: AdapterStats[];
}

// ── Adapters ────────────────────────────────────────────────────

export interface AdapterResponse {
  adapter_id: string;
  adapter_type: string;
  domain: string;
  normalizer_version: string;
  config: Record<string, unknown> | null;
  _links: Record<string, string>;
}

export interface AdapterListResponse {
  adapters: AdapterResponse[];
  total: number;
}

// ── Sources ──────────────────────────────────────────────────────

export interface SourceSummary {
  source_id: string;
  adapter_id: string;
  adapter_type: string;
  domain: string;
  origin_ref: string;
  display_name: string | null;
  current_version: number;
  last_fetched_at: string | null;
  poll_strategy: string;
  chunk_count: number;
  created_at: string;
  updated_at: string;
  _links: Record<string, string>;
}

export interface SourceListResponse {
  sources: SourceSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface SourceDetailResponse extends SourceSummary {
  adapter_type: string;
  poll_interval_sec: number | null;
  normalizer_version: string;
  created_at: string;
  updated_at: string;
}

// ── Lineage and Chunks ───────────────────────────────────────────

export interface LineageResponse {
  chunk_hash: string;
  source_id: string;
  source_version_id: number;
  adapter_id: string;
  domain: string;
  normalizer_version: string;
  embedding_model_id: string;
}

export interface ChunkResponse {
  chunk_hash: string;
  content: string;
  context_header: string | null;
  chunk_index: number;
  chunk_type: string;
  domain_metadata: Record<string, unknown> | null;
  cross_refs: string[];
  lineage: LineageResponse;
  _links: Record<string, string>;
}

export interface ChunkListResponse {
  source_id: string;
  version: number | null;
  chunks: ChunkResponse[];
}

export interface TopLevelChunkListResponse {
  chunks: ChunkResponse[];
  total: number;
  limit: number;
  offset: number;
}

// ── Versioning ───────────────────────────────────────────────────

export interface VersionSummary {
  source_id: string;
  version: number;
  chunk_hash_count: number;
  added_chunks: number;
  removed_chunks: number;
  unchanged_chunks: number;
  adapter_id: string;
  normalizer_version: string;
  fetch_timestamp: string;
  _links: Record<string, string>;
}

export interface VersionHistoryResponse {
  source_id: string;
  versions: VersionSummary[];
}

export interface VersionDetailResponse {
  source_id: string;
  version: number;
  markdown: string;
  chunk_hashes: string[];
  adapter_id: string;
  normalizer_version: string;
  fetch_timestamp: string;
  _links: Record<string, string>;
}

export interface ChunkVersionChainItem {
  chunk_hash: string;
  content: string;
  context_header: string | null;
  chunk_index: number;
  chunk_type: string;
}

export interface VersionDiffResponse {
  source_id: string;
  from_version: number;
  to_version: number;
  added_hashes: string[];
  removed_hashes: string[];
  unchanged_hashes: string[];
  added_chunks: ChunkVersionChainItem[];
  removed_chunks: ChunkVersionChainItem[];
}

// ── Provenance ───────────────────────────────────────────────────

export interface ChunkVersionChainResponse {
  chunk_hash: string;
  source_id: string;
  chain: ChunkVersionChainItem[];
}

export interface ChunkProvenanceResponse {
  chunk: ChunkResponse;
  lineage: LineageResponse;
  source_origin_ref: string;
  adapter_type: string;
  version_chain: ChunkVersionChainItem[];
  _links: Record<string, string>;
}

// ── Query ────────────────────────────────────────────────────────

export interface QueryRequest {
  query: string;
  top_k?: number;
  domain_filter?: string | null;
  source_filter?: string | null;
  rerank?: boolean;
  rerank_top_k?: number | null;
}

export interface QueryResultItem {
  chunk_text: string;
  chunk_hash: string;
  context_header: string | null;
  chunk_index: number;
  chunk_type: string;
  source_id: string;
  source_version_id: number;
  domain: string;
  adapter_id: string;
  embedding_model: string;
  similarity_score: number;
}

export interface QueryResponse {
  results: QueryResultItem[];
  total: number;
}

// ── Query parameter types ────────────────────────────────────────

export interface SourceQueryParams {
  adapter_id?: string;
  domain?: string;
  source_id_prefix?: string;
  limit?: number;
  offset?: number;
}

export interface ChunkQueryParams {
  source_id?: string;
  adapter_id?: string;
  domain?: string;
  limit?: number;
  offset?: number;
  metadata_filter?: Record<string, string>;
}

// ── Domain-Specific Metadata ────────────────────────────────────

/**
 * Document domain metadata structure.
 * Extracted from chunk domain_metadata for documents.
 */
export interface DocumentMetadata {
  document_type: string;
  author: string | null;
  tags: string[];
  file_size: number | null;
  modified_date: string | null;
}

/**
 * Extract document metadata from domain_metadata with safety checks.
 */
export function extractDocumentMetadata(domainMetadata: Record<string, unknown>): DocumentMetadata {
  let tags: string[] = [];
  if (Array.isArray(domainMetadata.tags)) {
    tags = domainMetadata.tags.every((item) => typeof item === 'string')
      ? (domainMetadata.tags as string[])
      : [];
  }

  return {
    document_type: typeof domainMetadata.document_type === 'string' ? domainMetadata.document_type : 'unknown',
    author: typeof domainMetadata.author === 'string' ? domainMetadata.author : null,
    tags,
    file_size: typeof domainMetadata.file_size === 'number' ? domainMetadata.file_size : null,
    modified_date: typeof domainMetadata.modified_date === 'string' ? domainMetadata.modified_date : null,
  };
}
