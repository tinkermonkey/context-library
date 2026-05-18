import { useMemo, useCallback, useState, useRef, useEffect } from 'react';
import { useNavigate, useRouterState } from '@tanstack/react-router';
import { createColumnHelper } from '@tanstack/react-table';
import type { ColumnDef } from '@tanstack/react-table';
import { Button, Modal } from '@tinkermonkey/heimdall-ui';
import { DataTable, type FetchParams } from '../components/DataTable';
import type { SourceSummary, ChunkResponse, VersionSummary } from '../types/api';
import { useAdapters } from '../hooks/useAdapters';
import { useSource } from '../hooks/useSources';
import { useChunkProvenance } from '../hooks/useChunks';
import { useVersionHistory, useVersionDiff } from '../hooks/useSources';
import { fetchSources, fetchChunks, fetchVersionHistory } from '../api/client';
import type { BrowserPageSearch } from '../router';
import { ALL_DOMAINS } from '../views/registry';

const DOMAINS = ALL_DOMAINS;

// ── Sources Table ──────────────────────────────────────────────
const sourceColumnHelper = createColumnHelper<SourceSummary>();

function buildSourceColumns(onView: (source: SourceSummary) => void): ColumnDef<SourceSummary, unknown>[] {
  return [
    sourceColumnHelper.display({
      id: 'actions',
      header: '',
      cell: (info) => (
        <button
          onClick={(e) => { e.stopPropagation(); onView(info.row.original); }}
          className="px-2 py-1 text-xs font-medium bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 rounded hover:bg-green-200 dark:hover:bg-green-800 transition-colors"
        >
          View
        </button>
      ),
    }) as ColumnDef<SourceSummary, unknown>,
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
    sourceColumnHelper.accessor('adapter_type', {
      header: 'Adapter Type',
    }) as ColumnDef<SourceSummary, unknown>,
    sourceColumnHelper.accessor('domain', {
      header: 'Domain',
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
    sourceColumnHelper.accessor('created_at', {
      header: 'Created',
      cell: (info) => {
        const date = info.getValue<string>();
        return new Date(date).toLocaleString();
      },
    }) as ColumnDef<SourceSummary, unknown>,
    sourceColumnHelper.accessor('updated_at', {
      header: 'Updated',
      cell: (info) => {
        const date = info.getValue<string>();
        return new Date(date).toLocaleString();
      },
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
  const { data: detail, isLoading, isError, error } = useSource(source.source_id);

  if (isLoading) {
    return <div className="text-gray-500 dark:text-gray-400">Loading...</div>;
  }

  if (isError) {
    return (
      <div className="bg-red-50 dark:bg-red-900 p-3 rounded border border-red-200 dark:border-red-700">
        <p className="text-red-900 dark:text-red-200 font-semibold text-sm">Failed to load source details</p>
        <p className="text-red-800 dark:text-red-300 text-xs mt-1">
          {error instanceof Error ? error.message : 'An unexpected error occurred'}
        </p>
      </div>
    );
  }

  const currentSearch = (routerState.location.search ?? {}) as BrowserPageSearch;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <span className="text-sm font-semibold">Source ID:</span>
          <code className="block text-xs text-gray-600 dark:text-gray-400 break-all">{source.source_id}</code>
        </div>
        <div>
          <span className="text-sm font-semibold">Adapter:</span>
          <span className="block text-sm text-gray-600 dark:text-gray-400">{source.adapter_id}</span>
        </div>
        <div>
          <span className="text-sm font-semibold">Domain:</span>
          <span className="block text-sm text-gray-600 dark:text-gray-400">{source.domain}</span>
        </div>
        <div>
          <span className="text-sm font-semibold">Adapter Type:</span>
          <span className="block text-sm text-gray-600 dark:text-gray-400">{detail?.adapter_type || '—'}</span>
        </div>
        <div>
          <span className="text-sm font-semibold">Origin Ref:</span>
          <code className="block text-xs text-gray-600 dark:text-gray-400 break-all">{source.origin_ref}</code>
        </div>
        <div>
          <span className="text-sm font-semibold">Display Name:</span>
          <span className="block text-sm text-gray-600 dark:text-gray-400">{source.display_name || '—'}</span>
        </div>
        <div>
          <span className="text-sm font-semibold">Current Version:</span>
          <span className="block text-sm text-gray-600 dark:text-gray-400">{source.current_version}</span>
        </div>
        <div>
          <span className="text-sm font-semibold">Chunk Count:</span>
          <span className="block text-sm text-gray-600 dark:text-gray-400">{source.chunk_count}</span>
        </div>
        <div>
          <span className="text-sm font-semibold">Last Fetched:</span>
          <span className="block text-sm text-gray-600 dark:text-gray-400">
            {source.last_fetched_at ? new Date(source.last_fetched_at).toLocaleString() : '—'}
          </span>
        </div>
        <div>
          <span className="text-sm font-semibold">Poll Strategy:</span>
          <span className="block text-sm text-gray-600 dark:text-gray-400">{source.poll_strategy}</span>
        </div>
        {detail?.poll_interval_sec != null && (
          <div>
            <span className="text-sm font-semibold">Poll Interval:</span>
            <span className="block text-sm text-gray-600 dark:text-gray-400">{detail.poll_interval_sec}s</span>
          </div>
        )}
        <div>
          <span className="text-sm font-semibold">Normalizer Version:</span>
          <span className="block text-sm text-gray-600 dark:text-gray-400">{detail?.normalizer_version || '—'}</span>
        </div>
      </div>
      <div className="flex gap-2 pt-2 border-t dark:border-slate-700">
        <Button
          size="sm"
          variant="primary"
          onClick={() => {
            navigate({
              to: '/browser/view/$domain/$sourceId',
              params: { domain: source.domain, sourceId: source.source_id },
            });
          }}
        >
          View
        </Button>
        <Button
          size="sm"
          variant="secondary"
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
          variant="secondary"
          onClick={() => {
            navigate({
              to: '/browser/versions/$sourceId',
              params: { sourceId: source.source_id },
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
      header: 'Total Chunks',
    }) as ColumnDef<VersionSummary, unknown>,
    versionColumnHelper.accessor('added_chunks', {
      header: 'Added',
      cell: (info) => {
        const count = info.getValue<number>();
        return <span className="text-green-700 dark:text-green-300 font-semibold">{count}</span>;
      },
    }) as ColumnDef<VersionSummary, unknown>,
    versionColumnHelper.accessor('removed_chunks', {
      header: 'Removed',
      cell: (info) => {
        const count = info.getValue<number>();
        return <span className="text-red-700 dark:text-red-300 font-semibold">{count}</span>;
      },
    }) as ColumnDef<VersionSummary, unknown>,
    versionColumnHelper.accessor('unchanged_chunks', {
      header: 'Unchanged',
      cell: (info) => {
        const count = info.getValue<number>();
        return <span className="text-gray-700 dark:text-gray-300">{count}</span>;
      },
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
          <span className="block text-sm text-gray-600 dark:text-gray-400">v{version.version}</span>
        </div>
        <div>
          <span className="text-sm font-semibold">Total Chunks:</span>
          <span className="block text-sm text-gray-600 dark:text-gray-400">{version.chunk_hash_count}</span>
        </div>
        <div>
          <span className="text-sm font-semibold">Adapter:</span>
          <span className="block text-sm text-gray-600 dark:text-gray-400">{version.adapter_id}</span>
        </div>
        <div>
          <span className="text-sm font-semibold">Normalizer Version:</span>
          <span className="block text-sm text-gray-600 dark:text-gray-400">{version.normalizer_version}</span>
        </div>
        <div className="col-span-2">
          <span className="text-sm font-semibold">Fetch Timestamp:</span>
          <span className="block text-sm text-gray-600 dark:text-gray-400">
            {new Date(version.fetch_timestamp).toLocaleString()}
          </span>
        </div>
      </div>

      {/* Diff Summary */}
      <div className="grid grid-cols-3 gap-3 pt-2 border-t dark:border-slate-700">
        <div className="bg-green-50 dark:bg-green-900 p-3 rounded border border-green-200 dark:border-green-700">
          <span className="text-xs font-semibold text-green-900 dark:text-green-200">Added</span>
          <span className="block text-lg font-semibold text-green-700 dark:text-green-300">{version.added_chunks}</span>
        </div>
        <div className="bg-red-50 dark:bg-red-900 p-3 rounded border border-red-200 dark:border-red-700">
          <span className="text-xs font-semibold text-red-900 dark:text-red-200">Removed</span>
          <span className="block text-lg font-semibold text-red-700 dark:text-red-300">{version.removed_chunks}</span>
        </div>
        <div className="bg-gray-50 dark:bg-slate-800 p-3 rounded border border-gray-200 dark:border-slate-700">
          <span className="text-xs font-semibold text-gray-900 dark:text-gray-200">Unchanged</span>
          <span className="block text-lg font-semibold text-gray-700 dark:text-gray-300">{version.unchanged_chunks}</span>
        </div>
      </div>

      <div className="flex gap-2 pt-2 border-t dark:border-slate-700">
        <Button
          size="sm"
          variant="primary"
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
          <div className="text-sm text-gray-700 dark:text-gray-300 line-clamp-2">
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
          <span className="text-sm text-gray-600 dark:text-gray-400">
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
            <span className="text-sm inline-block px-2 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded">
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
            <span className="text-sm inline-block px-2 py-1 bg-purple-100 dark:bg-purple-900 text-purple-800 dark:text-purple-200 rounded">
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
            <span className="text-sm inline-block px-2 py-1 bg-gray-100 dark:bg-slate-700 text-gray-800 dark:text-gray-200 rounded">
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
  const navigate = useNavigate();
  const { data: prov, isLoading: provLoading, isError: provError, error: provErrorObj } = useChunkProvenance(
    chunk.chunk_hash,
    chunk.lineage.source_id
  );

  return (
    <div className="space-y-6">
      {/* Navigation */}
      <div className="flex gap-2">
        <Button
          size="sm"
          variant="primary"
          onClick={() => {
            void navigate({
              to: '/browser/view/$domain/$sourceId',
              params: { domain: chunk.lineage.domain, sourceId: chunk.lineage.source_id },
            });
          }}
        >
          View Source
        </Button>
      </div>

      {/* Full Content */}
      <div>
        <h4 className="font-semibold text-sm mb-2">Full Content</h4>
        <pre className="bg-gray-100 dark:bg-slate-800 p-3 rounded text-xs overflow-auto max-h-40 whitespace-pre-wrap break-words text-gray-900 dark:text-gray-200">
          {chunk.content}
        </pre>
      </div>

      {/* Context Header */}
      {chunk.context_header && (
        <div>
          <h4 className="font-semibold text-sm mb-2">Context</h4>
          <pre className="bg-gray-100 dark:bg-slate-800 p-3 rounded text-xs overflow-auto text-gray-900 dark:text-gray-200">
            {chunk.context_header}
          </pre>
        </div>
      )}

      {/* Domain Metadata */}
      {chunk.domain_metadata && (
        <div>
          <h4 className="font-semibold text-sm mb-2">Domain Metadata</h4>
          <pre className="bg-gray-100 dark:bg-slate-800 p-3 rounded text-xs overflow-auto max-h-32 text-gray-900 dark:text-gray-200">
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
              <code key={i} className="block text-xs text-gray-600 dark:text-gray-400 break-all">
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
          <div className="text-gray-500 dark:text-gray-400 text-sm">Loading provenance...</div>
        ) : provError ? (
          <div className="bg-red-50 dark:bg-red-900 p-3 rounded border border-red-200 dark:border-red-700">
            <p className="text-red-900 dark:text-red-200 font-semibold text-sm">Failed to load provenance</p>
            <p className="text-red-800 dark:text-red-300 text-xs mt-1">
              {provErrorObj instanceof Error ? provErrorObj.message : 'An unexpected error occurred'}
            </p>
          </div>
        ) : prov ? (
          <div className="space-y-2 bg-gray-50 dark:bg-slate-800 p-3 rounded text-sm">
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
                    <div key={i} className="bg-white dark:bg-slate-700 p-2 rounded border dark:border-slate-600 text-xs">
                      <code className="block">{item.chunk_hash.substring(0, 12)}…</code>
                      <div className="text-gray-600 dark:text-gray-400 text-xs">{item.chunk_type}</div>
                      <div className="text-gray-500 dark:text-gray-400 text-xs line-clamp-1">
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
          <div className="text-gray-500 dark:text-gray-400 text-sm">No provenance data</div>
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
      // Clear source_id and adapter_id when switching domains — they're domain-specific
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { source_id, adapter_id, ...rest } = searchRef.current;
      navigate({
        to: '/browser',
        search: { ...rest, domain, page: 0 },
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
  const handleViewSource = useCallback(
    (source: SourceSummary) => {
      navigate({
        to: '/browser/view/$domain/$sourceId',
        params: { domain: source.domain, sourceId: source.source_id },
      });
    },
    [navigate]
  );

  const sourceColumns = useMemo(() => buildSourceColumns(handleViewSource), [handleViewSource]);

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
      <p className="text-gray-600 dark:text-gray-400 mb-8">Browse all sources, chunks, and versions by domain</p>

      {/* Domain Tabs */}
      <div className="mb-8 border-b border-gray-200 dark:border-slate-700 pb-3 flex items-center justify-between">
        <div className="flex gap-0">
          {DOMAINS.map((domain, index) => (
            <Button
              key={domain}
              onClick={() => handleDomainChange(domain)}
              variant={activeDomain === domain ? 'primary' : 'secondary'}
              className={`${
                index === 0
                  ? 'rounded-l-md rounded-r-none'
                  : index === DOMAINS.length - 1
                    ? 'rounded-r-md rounded-l-none'
                    : 'rounded-none'
              } ${activeDomain === domain ? '' : 'border border-gray-300'}`}
            >
              {domain.charAt(0).toUpperCase() + domain.slice(1)}
            </Button>
          ))}
        </div>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => {
            navigate({
              to: '/browser/catalog/$domain',
              params: { domain: activeDomain },
            });
          }}
        >
          Browse {activeDomain.charAt(0).toUpperCase() + activeDomain.slice(1)} Catalog →
        </Button>
      </div>

      {/* Table Type Selector */}
      <div className="mb-6">
        <div className="flex gap-0">
          {['sources', 'chunks', 'versions'].map((type, index, arr) => (
            <Button
              key={type}
              onClick={() => handleTableTypeChange(type)}
              variant={tableType === type ? 'primary' : 'secondary'}
              className={`${
                index === 0
                  ? 'rounded-l-md rounded-r-none'
                  : index === arr.length - 1
                    ? 'rounded-r-md rounded-l-none'
                    : 'rounded-none'
              } ${tableType === type ? '' : 'border border-gray-300'}`}
              disabled={type === 'versions' && !sourceIdFilter}
              title={type === 'versions' && !sourceIdFilter ? 'Select a source first to view versions' : ''}
            >
              {type.charAt(0).toUpperCase() + type.slice(1)}
            </Button>
          ))}
        </div>
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
          rowKey={(row) => `${row.chunk_hash}-${row.lineage.source_id}`}
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
          isOpen={diffModalOpen}
          onClose={() => {
            setDiffModalOpen(false);
            setSelectedVersionForDiff(null);
            setCompareWithVersion(null);
          }}
        >
          <div className="flex justify-between items-center border-b pb-3 mb-4">
            <h3 className="text-lg font-semibold text-slate-100">Compare Versions</h3>
            <button
              onClick={() => {
                setDiffModalOpen(false);
                setSelectedVersionForDiff(null);
                setCompareWithVersion(null);
              }}
              className="text-slate-400 hover:text-slate-300"
            >
              ✕
            </button>
          </div>
          <div className="space-y-4">
            {!compareWithVersion ? (
              <div className="space-y-4">
                <p className="text-sm text-slate-300">
                  Selected version: <strong>v{selectedVersionForDiff?.version}</strong> ({selectedVersionForDiff?.chunk_hash_count} chunks)
                </p>
                <p className="text-sm text-slate-200 font-semibold">Select another version to compare with:</p>
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
  const { data: history, isLoading, isError, error } = useVersionHistory(sourceId);

  if (isLoading) {
    return <div className="text-slate-400">Loading versions...</div>;
  }

  if (isError) {
    return (
      <div className="bg-red-50 dark:bg-red-900 p-3 rounded border border-red-200 dark:border-red-700">
        <p className="text-red-900 dark:text-red-200 font-semibold text-sm">Failed to load versions</p>
        <p className="text-red-800 dark:text-red-300 text-xs mt-1">
          {error instanceof Error ? error.message : 'An unexpected error occurred'}
        </p>
      </div>
    );
  }

  const otherVersions = (history?.versions ?? []).filter(
    (v) => v.version !== currentVersion
  );

  if (otherVersions.length === 0) {
    return <div className="text-slate-400 text-sm">No other versions to compare.</div>;
  }

  return (
    <div className="space-y-2 max-h-64 overflow-y-auto">
      {otherVersions.map((version) => (
        <button
          key={version.version}
          onClick={() => onSelect(version)}
          className="w-full text-left p-2 border border-slate-600 rounded hover:bg-slate-700 hover:border-slate-500"
        >
          <div className="flex justify-between items-center">
            <span className="font-semibold text-slate-100">v{version.version}</span>
            <span className="text-xs text-slate-400">{version.chunk_hash_count} chunks</span>
          </div>
          <div className="text-xs text-slate-400">
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
    return <div className="text-slate-400">Computing diff...</div>;
  }

  if (isError) {
    return (
      <div className="bg-red-50 dark:bg-red-900 p-3 rounded border border-red-200 dark:border-red-700">
        <p className="text-red-900 dark:text-red-200 font-semibold text-sm">Error loading diff</p>
        <p className="text-red-800 dark:text-red-300 text-xs mt-1">
          {error instanceof Error ? error.message : 'An unexpected error occurred'}
        </p>
        <button
          onClick={onBack}
          className="mt-2 text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 text-sm"
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
          className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 text-sm"
        >
          ← Back
        </button>
        <span className="text-sm text-slate-300">
          Comparing v{selectedVersion?.version} → v{compareVersion?.version}
        </span>
      </div>

      {diff_result && (
        <>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div className="bg-green-50 dark:bg-green-900 p-3 rounded border border-green-200 dark:border-green-700">
              <span className="font-semibold text-green-900 dark:text-green-200">Added</span>
              <div className="text-green-700 dark:text-green-300">{diff_result.added_hashes.length} chunks</div>
            </div>
            <div className="bg-red-50 dark:bg-red-900 p-3 rounded border border-red-200 dark:border-red-700">
              <span className="font-semibold text-red-900 dark:text-red-200">Removed</span>
              <div className="text-red-700 dark:text-red-300">{diff_result.removed_hashes.length} chunks</div>
            </div>
            <div className="bg-gray-50 dark:bg-slate-800 p-3 rounded border border-gray-200 dark:border-slate-700">
              <span className="font-semibold text-gray-900 dark:text-gray-200">Unchanged</span>
              <div className="text-gray-700 dark:text-gray-300">{diff_result.unchanged_hashes.length} chunks</div>
            </div>
          </div>

          {diff_result.added_chunks.length > 0 && (
            <div>
              <h5 className="font-semibold text-sm mb-2 text-green-900 dark:text-green-200">Added Chunks</h5>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {diff_result.added_chunks.map((chunk) => (
                  <div key={chunk.chunk_hash} className="bg-green-50 dark:bg-green-900 p-2 rounded border border-green-200 dark:border-green-700 text-xs">
                    <code className="block text-green-900 dark:text-green-200">{chunk.chunk_hash.substring(0, 12)}…</code>
                    <div className="text-green-800 dark:text-green-300 line-clamp-2">{chunk.content.substring(0, 100)}…</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {diff_result.removed_chunks.length > 0 && (
            <div>
              <h5 className="font-semibold text-sm mb-2 text-red-900 dark:text-red-200">Removed Chunks</h5>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {diff_result.removed_chunks.map((chunk) => (
                  <div key={chunk.chunk_hash} className="bg-red-50 dark:bg-red-900 p-2 rounded border border-red-200 dark:border-red-700 text-xs">
                    <code className="block text-red-900 dark:text-red-200">{chunk.chunk_hash.substring(0, 12)}…</code>
                    <div className="text-red-800 dark:text-red-300 line-clamp-2">{chunk.content.substring(0, 100)}…</div>
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
