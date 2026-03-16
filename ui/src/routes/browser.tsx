import { useMemo, useCallback, useState, useRef, useEffect } from 'react';
import { useNavigate, useRouterState } from '@tanstack/react-router';
import { createColumnHelper } from '@tanstack/react-table';
import type { ColumnDef } from '@tanstack/react-table';
import { Button, ButtonGroup, Modal } from 'flowbite-react';
import { DataTable, type FetchParams } from '../components/DataTable';
import type { SourceSummary, ChunkResponse, VersionSummary } from '../types/api';
import { useAdapters } from '../hooks/useAdapters';
import { useSource } from '../hooks/useSources';
import { useChunkProvenance } from '../hooks/useChunks';
import { useVersionHistory, useVersionDiff } from '../hooks/useSources';
import { fetchSources, fetchChunks, fetchVersionHistory } from '../api/client';
import type { BrowserPageSearch } from '../router';

const DOMAINS = ['messages', 'notes', 'events', 'tasks', 'health', 'documents'] as const;

// ── Sources Table ──────────────────────────────────────────────
const sourceColumnHelper = createColumnHelper<SourceSummary>();

function buildSourceColumns(): ColumnDef<SourceSummary, unknown>[] {
  return [
    sourceColumnHelper.accessor('source_id', {
      header: 'Source ID',
      cell: (info) => (
        <code className="text-xs">
          {info.getValue<string>().substring(0, 16)}…
        </code>
      ),
    }) as ColumnDef<SourceSummary, unknown>,
    sourceColumnHelper.accessor('adapter_id', {
      header: 'Adapter',
    }) as ColumnDef<SourceSummary, unknown>,
    sourceColumnHelper.accessor('display_name', {
      header: 'Name',
      cell: (info) => info.getValue() || '(unnamed)',
    }) as ColumnDef<SourceSummary, unknown>,
    sourceColumnHelper.accessor('chunk_count', {
      header: 'Chunks',
    }) as ColumnDef<SourceSummary, unknown>,
    sourceColumnHelper.accessor('current_version', {
      header: 'Version',
    }) as ColumnDef<SourceSummary, unknown>,
    sourceColumnHelper.accessor('last_fetched_at', {
      header: 'Last Fetched',
      cell: (info) => {
        const date = info.getValue<string | null>();
        return date ? new Date(date).toLocaleString() : '—';
      },
    }) as ColumnDef<SourceSummary, unknown>,
    sourceColumnHelper.accessor('poll_strategy', {
      header: 'Poll Strategy',
    }) as ColumnDef<SourceSummary, unknown>,
  ];
}

function SourceDetailPanel({ source }: { source: SourceSummary }) {
  const navigate = useNavigate();
  const routerState = useRouterState();
  const { data: detail, isLoading } = useSource(source.source_id);

  if (isLoading) {
    return <div className="text-gray-500">Loading...</div>;
  }

  const currentSearch = (routerState.location.search ?? {}) as BrowserPageSearch;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <span className="text-sm font-semibold">Source ID:</span>
          <code className="block text-xs text-gray-600 break-all">{source.source_id}</code>
        </div>
        <div>
          <span className="text-sm font-semibold">Adapter:</span>
          <span className="block text-sm text-gray-600">{source.adapter_id}</span>
        </div>
        <div>
          <span className="text-sm font-semibold">Domain:</span>
          <span className="block text-sm text-gray-600">{source.domain}</span>
        </div>
        <div>
          <span className="text-sm font-semibold">Adapter Type:</span>
          <span className="block text-sm text-gray-600">{detail?.adapter_type || '—'}</span>
        </div>
        <div>
          <span className="text-sm font-semibold">Origin Ref:</span>
          <code className="block text-xs text-gray-600 break-all">{source.origin_ref}</code>
        </div>
        <div>
          <span className="text-sm font-semibold">Display Name:</span>
          <span className="block text-sm text-gray-600">{source.display_name || '—'}</span>
        </div>
        <div>
          <span className="text-sm font-semibold">Current Version:</span>
          <span className="block text-sm text-gray-600">{source.current_version}</span>
        </div>
        <div>
          <span className="text-sm font-semibold">Chunk Count:</span>
          <span className="block text-sm text-gray-600">{source.chunk_count}</span>
        </div>
        <div>
          <span className="text-sm font-semibold">Last Fetched:</span>
          <span className="block text-sm text-gray-600">
            {source.last_fetched_at ? new Date(source.last_fetched_at).toLocaleString() : '—'}
          </span>
        </div>
        <div>
          <span className="text-sm font-semibold">Poll Strategy:</span>
          <span className="block text-sm text-gray-600">{source.poll_strategy}</span>
        </div>
        {detail?.poll_interval_sec != null && (
          <div>
            <span className="text-sm font-semibold">Poll Interval:</span>
            <span className="block text-sm text-gray-600">{detail.poll_interval_sec}s</span>
          </div>
        )}
        <div>
          <span className="text-sm font-semibold">Normalizer Version:</span>
          <span className="block text-sm text-gray-600">{detail?.normalizer_version || '—'}</span>
        </div>
      </div>
      <div className="flex gap-2 pt-2 border-t">
        <Button
          size="sm"
          onClick={() => {
            navigate({
              to: '/browser',
              search: { ...currentSearch, table: 'chunks', source_id: source.source_id, page: 0 },
            });
          }}
        >
          View Chunks
        </Button>
        <Button
          size="sm"
          color="gray"
          onClick={() => {
            navigate({
              to: '/browser',
              search: { ...currentSearch, table: 'versions', source_id: source.source_id, page: 0 },
            });
          }}
        >
          Version History
        </Button>
      </div>
    </div>
  );
}

// ── Versions Table ────────────────────────────────────────────
const versionColumnHelper = createColumnHelper<VersionSummary>();

function buildVersionColumns(): ColumnDef<VersionSummary, unknown>[] {
  return [
    versionColumnHelper.accessor('version', {
      header: 'Version',
      cell: (info) => `v${info.getValue<number>()}`,
    }) as ColumnDef<VersionSummary, unknown>,
    versionColumnHelper.accessor('chunk_hash_count', {
      header: 'Chunks',
    }) as ColumnDef<VersionSummary, unknown>,
    versionColumnHelper.accessor('fetch_timestamp', {
      header: 'Fetch Timestamp',
      cell: (info) => {
        const timestamp = info.getValue<string>();
        return new Date(timestamp).toLocaleString();
      },
    }) as ColumnDef<VersionSummary, unknown>,
  ];
}

function VersionDetailPanel({
  version,
  onCompareClick
}: {
  version: VersionSummary;
  onCompareClick: (v: VersionSummary) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <span className="text-sm font-semibold">Version:</span>
          <span className="block text-sm text-gray-600">v{version.version}</span>
        </div>
        <div>
          <span className="text-sm font-semibold">Chunk Count:</span>
          <span className="block text-sm text-gray-600">{version.chunk_hash_count}</span>
        </div>
        <div>
          <span className="text-sm font-semibold">Adapter:</span>
          <span className="block text-sm text-gray-600">{version.adapter_id}</span>
        </div>
        <div>
          <span className="text-sm font-semibold">Normalizer Version:</span>
          <span className="block text-sm text-gray-600">{version.normalizer_version}</span>
        </div>
        <div className="col-span-2">
          <span className="text-sm font-semibold">Fetch Timestamp:</span>
          <span className="block text-sm text-gray-600">
            {new Date(version.fetch_timestamp).toLocaleString()}
          </span>
        </div>
      </div>
      <div className="flex gap-2 pt-2 border-t">
        <Button
          size="sm"
          onClick={() => onCompareClick(version)}
        >
          Compare with Another Version
        </Button>
      </div>
    </div>
  );
}

// ── Chunks Table ───────────────────────────────────────────────
const chunkColumnHelper = createColumnHelper<ChunkResponse>();

function buildChunkColumns(domain: string): ColumnDef<ChunkResponse, unknown>[] {
  const base: ColumnDef<ChunkResponse, unknown>[] = [
    (chunkColumnHelper.accessor('chunk_hash', {
      header: 'Hash',
      cell: (info) => (
        <code className="text-xs">
          {info.getValue<string>().substring(0, 12)}…
        </code>
      ),
    }) as ColumnDef<ChunkResponse, unknown>),
    (chunkColumnHelper.accessor('content', {
      header: 'Content',
      cell: (info) => {
        const content = info.getValue<string>();
        const preview = content.substring(0, 200);
        return (
          <div className="text-sm text-gray-700 line-clamp-2">
            {preview}
            {content.length > 200 ? '…' : ''}
          </div>
        );
      },
    }) as ColumnDef<ChunkResponse, unknown>),
    (chunkColumnHelper.accessor('chunk_type', {
      header: 'Type',
    }) as ColumnDef<ChunkResponse, unknown>),
    (chunkColumnHelper.accessor('lineage', {
      header: 'Version',
      cell: (info) => {
        const lineage = info.getValue();
        return (
          <span className="text-sm text-gray-600">
            v{lineage.source_version_id || '—'}
          </span>
        );
      },
    }) as ColumnDef<ChunkResponse, unknown>),
  ];

  // Add domain-specific metadata columns
  const domainExtras: Record<string, ColumnDef<ChunkResponse, unknown>[]> = {
    events: [
      (chunkColumnHelper.display({
        id: 'start_date',
        header: 'Start Date',
        cell: (info) => {
          const row = info.row.original;
          const startDate = row.domain_metadata?.start_date;
          return <span className="text-sm">{startDate ? String(startDate) : '—'}</span>;
        },
      }) as ColumnDef<ChunkResponse, unknown>),
      (chunkColumnHelper.display({
        id: 'end_date',
        header: 'End Date',
        cell: (info) => {
          const row = info.row.original;
          const endDate = row.domain_metadata?.end_date;
          return <span className="text-sm">{endDate ? String(endDate) : '—'}</span>;
        },
      }) as ColumnDef<ChunkResponse, unknown>),
      (chunkColumnHelper.display({
        id: 'duration',
        header: 'Duration',
        cell: (info) => {
          const row = info.row.original;
          const duration = row.domain_metadata?.duration_minutes;
          return <span className="text-sm">{duration ? `${duration}m` : '—'}</span>;
        },
      }) as ColumnDef<ChunkResponse, unknown>),
    ],
    tasks: [
      (chunkColumnHelper.display({
        id: 'status',
        header: 'Status',
        cell: (info) => {
          const row = info.row.original;
          const status = row.domain_metadata?.status;
          return (
            <span className="text-sm inline-block px-2 py-1 bg-blue-100 text-blue-800 rounded">
              {status ? String(status) : '—'}
            </span>
          );
        },
      }) as ColumnDef<ChunkResponse, unknown>),
      (chunkColumnHelper.display({
        id: 'due_date',
        header: 'Due Date',
        cell: (info) => {
          const row = info.row.original;
          const dueDate = row.domain_metadata?.due_date;
          return <span className="text-sm">{dueDate ? String(dueDate) : '—'}</span>;
        },
      }) as ColumnDef<ChunkResponse, unknown>),
      (chunkColumnHelper.display({
        id: 'priority',
        header: 'Priority',
        cell: (info) => {
          const row = info.row.original;
          const priority = row.domain_metadata?.priority;
          return (
            <span className="text-sm inline-block px-2 py-1 bg-purple-100 text-purple-800 rounded">
              {priority ? String(priority) : '—'}
            </span>
          );
        },
      }) as ColumnDef<ChunkResponse, unknown>),
    ],
    messages: [
      (chunkColumnHelper.display({
        id: 'thread_id',
        header: 'Thread',
        cell: (info) => {
          const row = info.row.original;
          const threadId = row.domain_metadata?.thread_id;
          return <code className="text-xs">{threadId ? String(threadId).substring(0, 12) : '—'}</code>;
        },
      }) as ColumnDef<ChunkResponse, unknown>),
      (chunkColumnHelper.display({
        id: 'sender',
        header: 'Sender',
        cell: (info) => {
          const row = info.row.original;
          const sender = row.domain_metadata?.sender;
          return <span className="text-sm">{sender ? String(sender) : '—'}</span>;
        },
      }) as ColumnDef<ChunkResponse, unknown>),
    ],
    notes: [
      (chunkColumnHelper.display({
        id: 'heading',
        header: 'Heading',
        cell: (info) => {
          const row = info.row.original;
          const heading = row.domain_metadata?.heading;
          return <span className="text-sm">{heading ? String(heading) : '—'}</span>;
        },
      }) as ColumnDef<ChunkResponse, unknown>),
      (chunkColumnHelper.display({
        id: 'level',
        header: 'Level',
        cell: (info) => {
          const row = info.row.original;
          const level = row.domain_metadata?.level;
          return (
            <span className="text-sm inline-block px-2 py-1 bg-gray-100 text-gray-800 rounded">
              {level ? `H${level}` : '—'}
            </span>
          );
        },
      }) as ColumnDef<ChunkResponse, unknown>),
    ],
    health: [
      (chunkColumnHelper.display({
        id: 'metric_type',
        header: 'Metric Type',
        cell: (info) => {
          const row = info.row.original;
          const metricType = row.domain_metadata?.metric_type;
          return <span className="text-sm">{metricType ? String(metricType) : '—'}</span>;
        },
      }) as ColumnDef<ChunkResponse, unknown>),
      (chunkColumnHelper.display({
        id: 'value',
        header: 'Value',
        cell: (info) => {
          const row = info.row.original;
          const value = row.domain_metadata?.value;
          return <span className="text-sm font-mono">{value ? String(value) : '—'}</span>;
        },
      }) as ColumnDef<ChunkResponse, unknown>),
    ],
  };

  return [...base, ...(domainExtras[domain] ?? [])];
}

function ChunkDetailPanel({ chunk }: { chunk: ChunkResponse }) {
  const { data: prov, isLoading: provLoading } = useChunkProvenance(
    chunk.chunk_hash,
    chunk.lineage.source_id
  );

  return (
    <div className="space-y-6">
      {/* Full Content */}
      <div>
        <h4 className="font-semibold text-sm mb-2">Full Content</h4>
        <pre className="bg-gray-100 p-3 rounded text-xs overflow-auto max-h-40 whitespace-pre-wrap break-words">
          {chunk.content}
        </pre>
      </div>

      {/* Context Header */}
      {chunk.context_header && (
        <div>
          <h4 className="font-semibold text-sm mb-2">Context</h4>
          <pre className="bg-gray-100 p-3 rounded text-xs overflow-auto">
            {chunk.context_header}
          </pre>
        </div>
      )}

      {/* Domain Metadata */}
      {chunk.domain_metadata && (
        <div>
          <h4 className="font-semibold text-sm mb-2">Domain Metadata</h4>
          <pre className="bg-gray-100 p-3 rounded text-xs overflow-auto max-h-32">
            {JSON.stringify(chunk.domain_metadata, null, 2)}
          </pre>
        </div>
      )}

      {/* Cross References */}
      {chunk.cross_refs && chunk.cross_refs.length > 0 && (
        <div>
          <h4 className="font-semibold text-sm mb-2">Cross References</h4>
          <div className="space-y-1">
            {chunk.cross_refs.map((ref, i) => (
              <code key={i} className="block text-xs text-gray-600 break-all">
                {ref}
              </code>
            ))}
          </div>
        </div>
      )}

      {/* Provenance */}
      <div>
        <h4 className="font-semibold text-sm mb-2">Provenance</h4>
        {provLoading ? (
          <div className="text-gray-500 text-sm">Loading provenance...</div>
        ) : prov ? (
          <div className="space-y-2 bg-gray-50 p-3 rounded text-sm">
            <div>
              <span className="font-semibold">Source:</span> {prov.source_origin_ref}
            </div>
            <div>
              <span className="font-semibold">Adapter:</span> {prov.adapter_type}
            </div>
            {prov.version_chain && prov.version_chain.length > 0 && (
              <div>
                <h5 className="font-semibold text-xs mt-2 mb-1">Version Chain:</h5>
                <div className="space-y-1">
                  {prov.version_chain.map((item, i) => (
                    <div key={i} className="bg-white p-2 rounded border text-xs">
                      <code className="block">{item.chunk_hash.substring(0, 12)}…</code>
                      <div className="text-gray-600 text-xs">{item.chunk_type}</div>
                      <div className="text-gray-500 text-xs line-clamp-1">
                        {item.content.substring(0, 60)}
                        {item.content.length > 60 ? '…' : ''}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="text-gray-500 text-sm">No provenance data</div>
        )}
      </div>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────
export default function BrowserPage() {
  const navigate = useNavigate();
  const routerState = useRouterState();

  const search = useMemo(
    () => (routerState.location.search ?? {}) as BrowserPageSearch,
    [routerState.location.search]
  );
  const activeDomain = (search.domain as string) ?? 'messages';
  const tableType = (search.table as string) ?? 'sources';
  const adapterFilter = (search.adapter_id as string) ?? undefined;
  const sourceIdFilter = (search.source_id as string) ?? undefined;

  // Use a ref to hold current search params without triggering callback updates on every URL change
  const searchRef = useRef<BrowserPageSearch>(search);
  useEffect(() => {
    searchRef.current = search;
  }, [search]);

  const { data: adapters } = useAdapters();

  // Diff modal state
  const [diffModalOpen, setDiffModalOpen] = useState(false);
  const [selectedVersionForDiff, setSelectedVersionForDiff] = useState<VersionSummary | null>(null);
  const [compareWithVersion, setCompareWithVersion] = useState<VersionSummary | null>(null);

  // Handle version comparison
  const handleVersionDiffClick = (selectedVersion: VersionSummary) => {
    setSelectedVersionForDiff(selectedVersion);
    setDiffModalOpen(true);
  };

  // Type-safe callback for DataTable to update search params
  // Note: params from DataTable may contain filter_* keys that pass through validation
  const handleDataTableSearchParamsChange = useCallback(
    (params: Record<string, unknown>) => {
      navigate({
        to: '/browser',
        search: params as BrowserPageSearch,
      });
    },
    [navigate]
  );

  // Handle domain tab change
  const handleDomainChange = useCallback(
    (domain: string) => {
      navigate({
        to: '/browser',
        search: { ...searchRef.current, domain, page: 0 },
      });
    },
    [navigate]
  );

  // Handle table type change
  const handleTableTypeChange = useCallback(
    (table: string) => {
      navigate({
        to: '/browser',
        search: { ...searchRef.current, table, page: 0 },
      });
    },
    [navigate]
  );

  // ── Sources Table ──────────────────────────────────────────────
  const sourceColumns = useMemo(() => buildSourceColumns(), []);

  const sourceAdapterList = useMemo(() => {
    if (!adapters) return [];
    return adapters.adapters.map((a) => a.adapter_id);
  }, [adapters]);

  const sourceFacets = useMemo(
    () => [
      { column: 'adapter_id', label: 'Adapter', values: sourceAdapterList },
      { column: 'poll_strategy', label: 'Poll Strategy', values: ['push', 'poll', 'manual'] },
    ],
    [sourceAdapterList]
  );

  const sourceFetchFn = useCallback(
    async (params: FetchParams) => {
      const filterAdapterId = params.filters?.adapter_id?.[0];
      const response = await fetchSources({
        domain: activeDomain,
        adapter_id: filterAdapterId || adapterFilter,
        limit: params.pageSize,
        offset: params.page * params.pageSize,
      });
      return {
        rows: response.sources,
        total: response.total,
      };
    },
    [activeDomain, adapterFilter]
  );

  // ── Chunks Table ───────────────────────────────────────────────
  const chunkColumns = useMemo(() => buildChunkColumns(activeDomain), [activeDomain]);

  const chunkAdapterList = useMemo(() => {
    if (!adapters) return [];
    return adapters.adapters.map((a) => a.adapter_id);
  }, [adapters]);

  const chunkFacets = useMemo(
    () => [
      { column: 'adapter_id', label: 'Adapter', values: chunkAdapterList },
      { column: 'chunk_type', label: 'Chunk Type', values: ['message', 'note', 'event', 'task', 'record'] },
    ],
    [chunkAdapterList]
  );

  const chunkFetchFn = useCallback(
    async (params: FetchParams) => {
      const filterAdapterId = params.filters?.adapter_id?.[0];
      const response = await fetchChunks({
        domain: activeDomain,
        adapter_id: filterAdapterId || adapterFilter,
        source_id: sourceIdFilter,
        limit: params.pageSize,
        offset: params.page * params.pageSize,
      });
      return {
        rows: response.chunks,
        total: response.total,
      };
    },
    [activeDomain, adapterFilter, sourceIdFilter]
  );

  // ── Versions Table ────────────────────────────────────────────────
  const versionColumns = useMemo(() => buildVersionColumns(), []);

  const versionFetchFn = useCallback(
    async (params: FetchParams) => {
      if (!sourceIdFilter) {
        return { rows: [], total: 0 };
      }
      const response = await fetchVersionHistory(sourceIdFilter);
      const versions = response.versions || [];
      // Client-side pagination: slice the versions based on page and pageSize
      const start = params.page * params.pageSize;
      const end = start + params.pageSize;
      const paginated = versions.slice(start, end);
      return {
        rows: paginated,
        total: versions.length,
      };
    },
    [sourceIdFilter]
  );

  return (
    <div className="p-8">
      <h1 className="text-4xl font-bold mb-2">Data Browser</h1>
      <p className="text-gray-600 mb-8">Browse all sources, chunks, and versions by domain</p>

      {/* Domain Tabs */}
      <div className="mb-8 border-b border-gray-200">
        <ButtonGroup>
          {DOMAINS.map((domain) => (
            <Button
              key={domain}
              onClick={() => handleDomainChange(domain)}
              color={activeDomain === domain ? 'blue' : 'gray'}
              className={activeDomain === domain ? '' : 'border border-gray-300'}
            >
              {domain.charAt(0).toUpperCase() + domain.slice(1)}
            </Button>
          ))}
        </ButtonGroup>
      </div>

      {/* Table Type Selector */}
      <div className="mb-6">
        <ButtonGroup>
          <Button
            onClick={() => handleTableTypeChange('sources')}
            color={tableType === 'sources' ? 'blue' : 'gray'}
            className={tableType === 'sources' ? '' : 'border border-gray-300'}
          >
            Sources
          </Button>
          <Button
            onClick={() => handleTableTypeChange('chunks')}
            color={tableType === 'chunks' ? 'blue' : 'gray'}
            className={tableType === 'chunks' ? '' : 'border border-gray-300'}
          >
            Chunks
          </Button>
          <Button
            onClick={() => handleTableTypeChange('versions')}
            color={tableType === 'versions' ? 'blue' : 'gray'}
            className={tableType === 'versions' ? '' : 'border border-gray-300'}
            disabled={!sourceIdFilter}
            title={!sourceIdFilter ? 'Select a source first to view versions' : ''}
          >
            Versions
          </Button>
        </ButtonGroup>
      </div>

      {/* Sources Table */}
      {tableType === 'sources' && (
        <DataTable<SourceSummary>
          columns={sourceColumns}
          fetchFn={sourceFetchFn}
          facets={sourceFacets}
          searchable={false}
          queryKey={`sources-${activeDomain}`}
          rowKey={(row) => row.source_id}
          defaultPageSize={25}
          renderDetail={(source) => <SourceDetailPanel source={source} />}
          onSearchParamsChange={handleDataTableSearchParamsChange}
        />
      )}

      {/* Chunks Table */}
      {tableType === 'chunks' && (
        <DataTable<ChunkResponse>
          columns={chunkColumns}
          fetchFn={chunkFetchFn}
          facets={chunkFacets}
          searchable={false}
          queryKey={`chunks-${activeDomain}`}
          rowKey={(row) => row.chunk_hash}
          defaultPageSize={25}
          renderDetail={(chunk) => <ChunkDetailPanel chunk={chunk} />}
          onSearchParamsChange={handleDataTableSearchParamsChange}
        />
      )}

      {/* Versions Table */}
      {tableType === 'versions' && sourceIdFilter && (
        <DataTable<VersionSummary>
          columns={versionColumns}
          fetchFn={versionFetchFn}
          facets={[]}
          searchable={false}
          queryKey={`versions-${sourceIdFilter}`}
          rowKey={(row) => String(row.version)}
          defaultPageSize={25}
          renderDetail={(version) => (
            <VersionDetailPanel
              version={version}
              onCompareClick={handleVersionDiffClick}
            />
          )}
          onSearchParamsChange={handleDataTableSearchParamsChange}
        />
      )}

      {/* Version Diff Modal */}
      {sourceIdFilter && (
        <Modal
          show={diffModalOpen}
          onClose={() => {
            setDiffModalOpen(false);
            setSelectedVersionForDiff(null);
            setCompareWithVersion(null);
          }}
          size="2xl"
        >
          <div className="relative bg-white rounded-lg shadow p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-semibold">Compare Versions</h3>
              <button
                onClick={() => {
                  setDiffModalOpen(false);
                  setSelectedVersionForDiff(null);
                  setCompareWithVersion(null);
                }}
                className="text-gray-400 hover:text-gray-600"
              >
                ✕
              </button>
            </div>
            <div className="space-y-4">
              {!compareWithVersion ? (
                <div className="space-y-4">
                  <p className="text-sm text-gray-600">
                    Selected version: <strong>v{selectedVersionForDiff?.version}</strong> ({selectedVersionForDiff?.chunk_hash_count} chunks)
                  </p>
                  <p className="text-sm text-gray-700 font-semibold">Select another version to compare with:</p>
                  <VersionComparisonSelector
                    sourceId={sourceIdFilter}
                    currentVersion={selectedVersionForDiff?.version}
                    onSelect={(v) => {
                      setCompareWithVersion(v);
                    }}
                  />
                </div>
              ) : (
                <VersionDiffView
                  selectedVersion={selectedVersionForDiff}
                  compareVersion={compareWithVersion}
                  sourceId={sourceIdFilter}
                  onBack={() => {
                    setCompareWithVersion(null);
                  }}
                />
              )}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

// ── Version Comparison Component ────────────────────────────────
function VersionComparisonSelector({
  sourceId,
  currentVersion,
  onSelect,
}: {
  sourceId: string;
  currentVersion?: number;
  onSelect: (v: VersionSummary) => void;
}) {
  const { data: history, isLoading } = useVersionHistory(sourceId);

  if (isLoading) {
    return <div className="text-gray-500">Loading versions...</div>;
  }

  const otherVersions = (history?.versions ?? []).filter(
    (v) => v.version !== currentVersion
  );

  if (otherVersions.length === 0) {
    return <div className="text-gray-500 text-sm">No other versions to compare.</div>;
  }

  return (
    <div className="space-y-2 max-h-64 overflow-y-auto">
      {otherVersions.map((version) => (
        <button
          key={version.version}
          onClick={() => onSelect(version)}
          className="w-full text-left p-2 border border-gray-200 rounded hover:bg-blue-50 hover:border-blue-300"
        >
          <div className="flex justify-between items-center">
            <span className="font-semibold">v{version.version}</span>
            <span className="text-xs text-gray-500">{version.chunk_hash_count} chunks</span>
          </div>
          <div className="text-xs text-gray-600">
            {new Date(version.fetch_timestamp).toLocaleString()}
          </div>
        </button>
      ))}
    </div>
  );
}

// ── Version Diff View Component ────────────────────────────────
function VersionDiffView({
  selectedVersion,
  compareVersion,
  sourceId,
  onBack,
}: {
  selectedVersion: VersionSummary | null;
  compareVersion: VersionSummary | null;
  sourceId: string;
  onBack: () => void;
}) {
  const { data: diffData, isLoading, isError, error } = useVersionDiff(
    sourceId,
    selectedVersion?.version ?? 0,
    compareVersion?.version ?? 0
  );

  if (isLoading) {
    return <div className="text-gray-500">Computing diff...</div>;
  }

  if (isError) {
    return (
      <div className="bg-red-50 p-3 rounded border border-red-200">
        <p className="text-red-900 font-semibold text-sm">Error loading diff</p>
        <p className="text-red-800 text-xs mt-1">
          {error instanceof Error ? error.message : 'An unexpected error occurred'}
        </p>
        <button
          onClick={onBack}
          className="mt-2 text-blue-600 hover:text-blue-800 text-sm"
        >
          ← Back
        </button>
      </div>
    );
  }

  const diff_result = diffData;

  return (
    <div className="space-y-4">
      <div className="flex gap-2 items-center mb-4">
        <button
          onClick={onBack}
          className="text-blue-600 hover:text-blue-800 text-sm"
        >
          ← Back
        </button>
        <span className="text-sm text-gray-600">
          Comparing v{selectedVersion?.version} → v{compareVersion?.version}
        </span>
      </div>

      {diff_result && (
        <>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div className="bg-green-50 p-3 rounded border border-green-200">
              <span className="font-semibold text-green-900">Added</span>
              <div className="text-green-700">{diff_result.added_hashes.length} chunks</div>
            </div>
            <div className="bg-red-50 p-3 rounded border border-red-200">
              <span className="font-semibold text-red-900">Removed</span>
              <div className="text-red-700">{diff_result.removed_hashes.length} chunks</div>
            </div>
            <div className="bg-gray-50 p-3 rounded border border-gray-200">
              <span className="font-semibold text-gray-900">Unchanged</span>
              <div className="text-gray-700">{diff_result.unchanged_hashes.length} chunks</div>
            </div>
          </div>

          {diff_result.added_chunks.length > 0 && (
            <div>
              <h5 className="font-semibold text-sm mb-2 text-green-900">Added Chunks</h5>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {diff_result.added_chunks.map((chunk) => (
                  <div key={chunk.chunk_hash} className="bg-green-50 p-2 rounded border border-green-200 text-xs">
                    <code className="block text-green-900">{chunk.chunk_hash.substring(0, 12)}…</code>
                    <div className="text-green-800 line-clamp-2">{chunk.content.substring(0, 100)}…</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {diff_result.removed_chunks.length > 0 && (
            <div>
              <h5 className="font-semibold text-sm mb-2 text-red-900">Removed Chunks</h5>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {diff_result.removed_chunks.map((chunk) => (
                  <div key={chunk.chunk_hash} className="bg-red-50 p-2 rounded border border-red-200 text-xs">
                    <code className="block text-red-900">{chunk.chunk_hash.substring(0, 12)}…</code>
                    <div className="text-red-800 line-clamp-2">{chunk.content.substring(0, 100)}…</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
