/**
 * Typed API client for the context library backend.
 * One exported function per backend endpoint.
 */

import type {
  HealthResponse,
  DatasetStatsResponse,
  AdapterStatsResponse,
  AdapterListResponse,
  SourceListResponse,
  SourceDetailResponse,
  ChunkListResponse,
  VersionHistoryResponse,
  VersionDiffResponse,
  TopLevelChunkListResponse,
  ChunkResponse,
  ChunkProvenanceResponse,
  QueryRequest,
  QueryResponse,
  SourceQueryParams,
  ChunkQueryParams,
} from '../types/api';

const BASE = import.meta.env.DEV ? '/api' : '';

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
  apiFetch<AdapterListResponse>(`/adapters/${adapterId}`);

// ── Sources ──────────────────────────────────────────────────────

export const fetchSources = (params: SourceQueryParams) => {
  const qs = new URLSearchParams(filterDefined(params as Record<string, unknown>));
  return apiFetch<SourceListResponse>(`/sources?${qs}`);
};

export const fetchSource = (sourceId: string) =>
  apiFetch<SourceDetailResponse>(`/sources/${sourceId}`);

export const fetchSourceChunks = (sourceId: string, version?: number) => {
  const versionQs = version != null ? `?version=${version}` : '';
  return apiFetch<ChunkListResponse>(`/sources/${sourceId}/chunks${versionQs}`);
};

export const fetchVersionHistory = (sourceId: string) =>
  apiFetch<VersionHistoryResponse>(`/sources/${sourceId}/versions`);

export const fetchVersionDetail = (sourceId: string, version: number) =>
  apiFetch<VersionHistoryResponse>(`/sources/${sourceId}/versions/${version}`);

export const fetchVersionDiff = (sourceId: string, fromVersion: number, toVersion: number) =>
  apiFetch<VersionDiffResponse>(
    `/sources/${sourceId}/diff?from_version=${fromVersion}&to_version=${toVersion}`
  );

// ── Chunks ───────────────────────────────────────────────────────

export const fetchChunks = (params: ChunkQueryParams) => {
  const qs = new URLSearchParams(filterDefined(params as Record<string, unknown>));
  return apiFetch<TopLevelChunkListResponse>(`/chunks?${qs}`);
};

export const fetchChunk = (hash: string, sourceId?: string) => {
  const sourceQs = sourceId ? `?source_id=${sourceId}` : '';
  return apiFetch<ChunkResponse>(`/chunks/${hash}${sourceQs}`);
};

export const fetchChunkProvenance = (hash: string, sourceId?: string) => {
  const sourceQs = sourceId ? `?source_id=${sourceId}` : '';
  return apiFetch<ChunkProvenanceResponse>(`/chunks/${hash}/provenance${sourceQs}`);
};

export const fetchChunkVersionChain = (hash: string, sourceId?: string) => {
  const sourceQs = sourceId ? `?source_id=${sourceId}` : '';
  return apiFetch<ChunkProvenanceResponse>(`/chunks/${hash}/version-chain${sourceQs}`);
};

// ── Query ────────────────────────────────────────────────────────

export const postQuery = (request: QueryRequest) =>
  apiFetch<QueryResponse>('/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
