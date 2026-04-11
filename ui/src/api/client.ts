/**
 * Typed API client for the context library backend.
 * One exported function per backend endpoint.
 */

import type {
  HealthResponse,
  DatasetStatsResponse,
  AdapterStatsResponse,
  AdapterResponse,
  AdapterListResponse,
  AdapterResetResponse,
  SourceListResponse,
  SourceDetailResponse,
  ChunkListResponse,
  VersionHistoryResponse,
  VersionDetailResponse,
  VersionDiffResponse,
  TopLevelChunkListResponse,
  ChunkResponse,
  ChunkProvenanceResponse,
  ChunkVersionChainResponse,
  QueryRequest,
  QueryResponse,
  SourceQueryParams,
  ChunkQueryParams,
} from '../types/api';

const BASE = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? '/api' : '');

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`API error ${res.status}: ${errorText}`);
  }
  return res.json();
}

function filterDefined(obj: Record<string, unknown>): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [key, value] of Object.entries(obj)) {
    if (value !== undefined && value !== null) {
      result[key] = String(value);
    }
  }
  return result;
}

// ── Health ──────────────────────────────────────────────────────

export const fetchHealth = () => apiFetch<HealthResponse>('/health');

// ── Stats ────────────────────────────────────────────────────────

export const fetchStats = () => apiFetch<DatasetStatsResponse>('/stats');

export const fetchAdapterStats = () => apiFetch<AdapterStatsResponse>('/stats/adapters');

// ── Adapters ────────────────────────────────────────────────────

export const fetchAdapters = () => apiFetch<AdapterListResponse>('/adapters');

export const fetchAdapter = (adapterId: string) =>
  apiFetch<AdapterResponse>(`/adapters/${encodeURIComponent(adapterId)}`);

export const resetAdapter = (adapterId: string) =>
  apiFetch<AdapterResetResponse>(`/adapters/${encodeURIComponent(adapterId)}/reset`, {
    method: 'POST',
  });

// ── Sources ──────────────────────────────────────────────────────

export const fetchSources = (params: SourceQueryParams) => {
  const qs = new URLSearchParams(filterDefined(params as Record<string, unknown>));
  return apiFetch<SourceListResponse>(`/sources?${qs}`);
};

export const fetchSource = (sourceId: string) =>
  apiFetch<SourceDetailResponse>(`/sources/${encodeURIComponent(sourceId)}`);

export const fetchSourceChunks = (sourceId: string, version?: number, limit?: number, offset?: number) => {
  const params: Record<string, string> = {};
  if (version != null) params.version = String(version);
  if (limit != null) params.limit = String(limit);
  if (offset != null) params.offset = String(offset);
  const qs = Object.keys(params).length > 0 ? `?${new URLSearchParams(params)}` : '';
  return apiFetch<ChunkListResponse>(`/sources/${encodeURIComponent(sourceId)}/chunks${qs}`);
};

export const fetchVersionHistory = (sourceId: string) =>
  apiFetch<VersionHistoryResponse>(`/sources/${encodeURIComponent(sourceId)}/versions`);

export const fetchVersionDetail = (sourceId: string, version: number) =>
  apiFetch<VersionDetailResponse>(`/sources/${encodeURIComponent(sourceId)}/versions/${version}`);

export const fetchVersionDiff = (sourceId: string, fromVersion: number, toVersion: number) => {
  const qs = new URLSearchParams({
    from_version: String(fromVersion),
    to_version: String(toVersion),
  });
  return apiFetch<VersionDiffResponse>(`/sources/${encodeURIComponent(sourceId)}/diff?${qs}`);
};

// ── Chunks ───────────────────────────────────────────────────────

export const fetchChunks = (params: ChunkQueryParams) => {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) {
      if (key === "metadata_filter" && typeof value === "object") {
        // Handle metadata_filter as special case: add as repeating params
        for (const [mkey, mvalue] of Object.entries(value)) {
          if (mvalue !== undefined && mvalue !== null) {
            qs.append("metadata_filter", `${mkey}:${mvalue}`);
          }
        }
      } else {
        qs.append(key, String(value));
      }
    }
  }
  return apiFetch<TopLevelChunkListResponse>(`/chunks?${qs}`);
};

export const fetchChunk = (hash: string, sourceId?: string) => {
  const qs = sourceId ? `?${new URLSearchParams({ source_id: sourceId })}` : '';
  return apiFetch<ChunkResponse>(`/chunks/${encodeURIComponent(hash)}${qs}`);
};

export const fetchChunkProvenance = (hash: string, sourceId?: string) => {
  const qs = sourceId ? `?${new URLSearchParams({ source_id: sourceId })}` : '';
  return apiFetch<ChunkProvenanceResponse>(`/chunks/${encodeURIComponent(hash)}/provenance${qs}`);
};

export const fetchChunkVersionChain = (hash: string, sourceId: string) => {
  const qs = new URLSearchParams({ source_id: sourceId });
  return apiFetch<ChunkVersionChainResponse>(
    `/chunks/${encodeURIComponent(hash)}/version-chain?${qs}`
  );
};

// ── Query ────────────────────────────────────────────────────────

export const postQuery = (request: QueryRequest) =>
  apiFetch<QueryResponse>('/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
