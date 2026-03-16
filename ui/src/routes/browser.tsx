import { useMemo, useCallback } from 'react';
import { createColumnHelper } from '@tanstack/react-table';
import type { ColumnDef } from '@tanstack/react-table';
import { fetchSources } from '../api/client';
import { DataTable, type FetchParams } from '../components/DataTable';
import type { SourceSummary } from '../types/api';
import { useStats } from '../hooks/useStats';

const columnHelper = createColumnHelper<SourceSummary>();

export default function BrowserPage() {
  const { data: stats } = useStats();

  // Column definitions
  const columns: ColumnDef<SourceSummary, unknown>[] = useMemo(
    () => [
      columnHelper.accessor('source_id', {
        header: 'Source ID',
        cell: (info) => <code className="text-xs">{info.getValue()}</code>,
      }),
      columnHelper.accessor('display_name', {
        header: 'Name',
        cell: (info) => info.getValue() || '(unnamed)',
      }),
      columnHelper.accessor('adapter_id', {
        header: 'Adapter',
        cell: (info) => info.getValue(),
      }),
      columnHelper.accessor('domain', {
        header: 'Domain',
        cell: (info) => <span className="inline-block bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs">{info.getValue()}</span>,
      }),
      columnHelper.accessor('chunk_count', {
        header: 'Chunks',
        cell: (info) => info.getValue(),
      }),
      columnHelper.accessor('current_version', {
        header: 'Version',
        cell: (info) => info.getValue(),
      }),
      columnHelper.accessor('last_fetched_at', {
        header: 'Last Fetched',
        cell: (info) => {
          const date = info.getValue();
          return date ? new Date(date).toLocaleString() : '—';
        },
      }),
    ] as ColumnDef<SourceSummary, unknown>[],
    []
  );

  // Facet configurations from stats
  const facets = useMemo(() => {
    if (!stats) return [];
    const domains = Array.from(new Set(stats.by_domain.map((d) => d.domain)));
    return [
      {
        column: 'domain',
        label: 'Domain',
        values: domains,
      },
    ];
  }, [stats]);

  // Data fetching function that wraps the API client
  const fetchFn = useCallback(
    async (params: FetchParams) => {
      const response = await fetchSources({
        domain: params.filters?.domain?.[0],
        limit: params.pageSize,
        offset: params.page * params.pageSize,
      });
      return {
        rows: response.sources,
        total: response.total,
      };
    },
    []
  );

  return (
    <div className="p-8">
      <h1 className="text-4xl font-bold mb-2">Data Browser</h1>
      <p className="text-gray-600 mb-6">Browse all sources, chunks, and versions</p>

      <DataTable<SourceSummary>
        columns={columns}
        fetchFn={fetchFn}
        facets={facets}
        searchable={false}
        queryKey="sources-browser"
        rowKey={(row) => row.source_id}
        defaultPageSize={25}
      />
    </div>
  );
}
