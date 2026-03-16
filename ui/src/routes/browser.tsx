import { useMemo, useCallback } from 'react';
import { useNavigate, useRouterState } from '@tanstack/react-router';
import { createColumnHelper } from '@tanstack/react-table';
import type { ColumnDef } from '@tanstack/react-table';
import { Button } from 'flowbite-react';
import { DataTable, type FetchParams } from '../components/DataTable';
import type { SourceSummary, ChunkResponse } from '../types/api';
import { useAdapters } from '../hooks/useAdapters';
import { useSource } from '../hooks/useSources';
import { useChunkProvenance } from '../hooks/useChunks';
import { fetchSources, fetchChunks } from '../api/client';

const DOMAINS = ['messages', 'notes', 'events', 'tasks', 'health'] as const;

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
  const { data: detail, isLoading } = useSource(source.source_id);

  if (isLoading) {
    return <div className="text-gray-500">Loading...</div>;
  }

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
            const routerState = (window as any).__routerState;
            const currentSearch = routerState?.location.search || {};
            navigate({
              search: { ...currentSearch, table: 'chunks', source_id: source.source_id },
            } as any);
          }}
        >
          View Chunks
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
        const preview = content.substring(0, 100);
        return (
          <div className="text-sm text-gray-700 line-clamp-2">
            {preview}
            {content.length > 100 ? '…' : ''}
          </div>
        );
      },
    }) as ColumnDef<ChunkResponse, unknown>),
    (chunkColumnHelper.accessor('chunk_type', {
      header: 'Type',
    }) as ColumnDef<ChunkResponse, unknown>),
    (chunkColumnHelper.accessor('lineage', {
      header: 'Created',
      cell: (info) => {
        const lineage = info.getValue();
        return (
          <span className="text-sm text-gray-600">
            {lineage.source_version_id || '—'}
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
  const params = (routerState.location.search ?? {}) as Record<string, unknown>;

  const activeDomain = (params.domain as string) ?? 'messages';
  const tableType = (params.table as string) ?? 'sources';
  const adapterFilter = (params.adapter_id as string) ?? undefined;
  const sourceIdFilter = (params.source_id as string) ?? undefined;

  const { data: adapters } = useAdapters();

  // Handle domain tab change
  const handleDomainChange = useCallback(
    (domain: string) => {
      const currentParams = (routerState.location.search ?? {}) as Record<string, unknown>;
      navigate({
        search: { ...currentParams, domain, page: 0 } as never,
      });
    },
    [navigate, routerState.location.search]
  );

  // Handle table type change
  const handleTableTypeChange = useCallback(
    (table: string) => {
      const currentParams = (routerState.location.search ?? {}) as Record<string, unknown>;
      navigate({
        search: { ...currentParams, table, page: 0 } as never,
      });
    },
    [navigate, routerState.location.search]
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

  const chunkFacets = useMemo(
    () => [
      { column: 'chunk_type', label: 'Chunk Type', values: ['message', 'note', 'event', 'task', 'record'] },
    ],
    []
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

  return (
    <div className="p-8">
      <h1 className="text-4xl font-bold mb-2">Data Browser</h1>
      <p className="text-gray-600 mb-8">Browse all sources, chunks, and versions by domain</p>

      {/* Domain Tabs */}
      <div className="mb-8 border-b border-gray-200">
        <div className="flex gap-8">
          {DOMAINS.map((domain) => (
            <button
              key={domain}
              onClick={() => handleDomainChange(domain)}
              className={`py-2 px-1 font-medium text-sm transition-colors ${
                activeDomain === domain
                  ? 'text-blue-600 border-b-2 border-blue-600'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              {domain.charAt(0).toUpperCase() + domain.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Table Type Selector */}
      <div className="mb-6 flex gap-2">
        <Button
          onClick={() => handleTableTypeChange('sources')}
          color={tableType === 'sources' ? 'blue' : 'light'}
        >
          Sources
        </Button>
        <Button
          onClick={() => handleTableTypeChange('chunks')}
          color={tableType === 'chunks' ? 'blue' : 'light'}
        >
          Chunks
        </Button>
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
        />
      )}
    </div>
  );
}
