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

const BASE = import.meta.env.DEV ? '/api' : (import.meta.env.VITE_API_BASE_URL || '/api');

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

// ── Sources ──────────────────────────────────────────────────────

export const fetchSources = (params: SourceQueryParams) => {
  const qs = new URLSearchParams(filterDefined(params as Record<string, unknown>));
  return apiFetch<SourceListResponse>(`/sources?${qs}`);
};

export const fetchSource = (sourceId: string) =>
  apiFetch<SourceDetailResponse>(`/sources/${encodeURIComponent(sourceId)}`);

export const fetchSourceChunks = (sourceId: string, version?: number) => {
  const versionQs = version != null ? `?version=${version}` : '';
  return apiFetch<ChunkListResponse>(`/sources/${encodeURIComponent(sourceId)}/chunks${versionQs}`);
};

export const fetchVersionHistory = (sourceId: string) =>
  apiFetch<VersionHistoryResponse>(`/sources/${encodeURIComponent(sourceId)}/versions`);

export const fetchVersionDetail = (sourceId: string, version: number) =>
  apiFetch<VersionDetailResponse>(`/sources/${encodeURIComponent(sourceId)}/versions/${version}`);

export const fetchVersionDiff = (sourceId: string, fromVersion: number, toVersion: number) =>
  apiFetch<VersionDiffResponse>(
    `/sources/${encodeURIComponent(sourceId)}/diff?from_version=${fromVersion}&to_version=${toVersion}`
  );

// ── Chunks ───────────────────────────────────────────────────────

export const fetchChunks = (params: ChunkQueryParams) => {
  const qs = new URLSearchParams(filterDefined(params as Record<string, unknown>));
  return apiFetch<TopLevelChunkListResponse>(`/chunks?${qs}`);
};

export const fetchChunk = (hash: string, sourceId?: string) => {
  const sourceQs = sourceId ? `?source_id=${encodeURIComponent(sourceId)}` : '';
  return apiFetch<ChunkResponse>(`/chunks/${encodeURIComponent(hash)}${sourceQs}`);
};

export const fetchChunkProvenance = (hash: string, sourceId?: string) => {
  const sourceQs = sourceId ? `?source_id=${encodeURIComponent(sourceId)}` : '';
  return apiFetch<ChunkProvenanceResponse>(`/chunks/${encodeURIComponent(hash)}/provenance${sourceQs}`);
};

export const fetchChunkVersionChain = (hash: string, sourceId: string) => {
  return apiFetch<ChunkVersionChainResponse>(`/chunks/${encodeURIComponent(hash)}/version-chain?source_id=${encodeURIComponent(sourceId)}`);
};

// ── Query ────────────────────────────────────────────────────────

export const postQuery = (request: QueryRequest) =>
  apiFetch<QueryResponse>('/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
