import { useState, useMemo, useCallback } from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import { useQueryClient } from '@tanstack/react-query';
import { createColumnHelper } from '@tanstack/react-table';
import type { ColumnDef } from '@tanstack/react-table';
import { Button, Checkbox, Spinner } from 'flowbite-react';
import { DataTable, type FetchParams } from '../components/DataTable';
import type { VersionSummary, VersionDiffResponse, VersionHistoryResponse } from '../types/api';
import { useVersionHistory, useVersionDiff } from '../hooks/useSources';

// ── Versions Table Column Definitions ──────────────────────────────
const versionColumnHelper = createColumnHelper<VersionSummary>();

function buildVersionColumns(
  selectedVersions: number[],
  onSelectionChange: (version: number, selected: boolean) => void
): ColumnDef<VersionSummary, unknown>[] {
  return [
    // Selection checkbox column
    versionColumnHelper.display({
      id: 'select',
      header: '',
      cell: (info) => {
        const version = info.row.original.version;
        const isSelected = selectedVersions.includes(version);
        return (
          <Checkbox
            checked={isSelected}
            onChange={(e) => {
              onSelectionChange(version, e.currentTarget.checked);
            }}
            disabled={selectedVersions.length >= 2 && !isSelected}
          />
        );
      },
    }) as ColumnDef<VersionSummary, unknown>,

    versionColumnHelper.accessor('version', {
      header: 'Version',
      cell: (info) => `v${info.getValue<number>()}`,
    }) as ColumnDef<VersionSummary, unknown>,

    versionColumnHelper.accessor('fetch_timestamp', {
      header: 'Fetched At',
      cell: (info) => {
        const timestamp = info.getValue<string>();
        return new Date(timestamp).toLocaleString();
      },
    }) as ColumnDef<VersionSummary, unknown>,

    versionColumnHelper.accessor('chunk_hash_count', {
      header: 'Chunks',
      cell: (info) => {
        return <span className="font-semibold">{info.getValue<number>()}</span>;
      },
    }) as ColumnDef<VersionSummary, unknown>,

    versionColumnHelper.display({
      id: 'changes',
      header: 'Changes',
      cell: (info) => {
        const version = info.row.original;
        const added = version.added_chunks || 0;
        const removed = version.removed_chunks || 0;
        const unchanged = version.unchanged_chunks || 0;

        if (added === 0 && removed === 0) {
          return <span className="text-gray-500 text-sm">—</span>;
        }

        return (
          <div className="flex gap-1 text-xs">
            {added > 0 && <span className="text-green-700 font-medium">+{added}</span>}
            {removed > 0 && <span className="text-red-700 font-medium">-{removed}</span>}
            {unchanged > 0 && <span className="text-gray-600">{unchanged}○</span>}
          </div>
        );
      },
    }) as ColumnDef<VersionSummary, unknown>,
  ];
}

// ── Diff View Component ────────────────────────────────────────────
function DiffView({ diff }: { diff: VersionDiffResponse }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-green-50 p-4 rounded border border-green-200">
          <span className="text-sm font-semibold text-green-900">Added</span>
          <div className="text-2xl font-bold text-green-700 mt-1">{diff.added_hashes.length}</div>
        </div>
        <div className="bg-red-50 p-4 rounded border border-red-200">
          <span className="text-sm font-semibold text-red-900">Removed</span>
          <div className="text-2xl font-bold text-red-700 mt-1">{diff.removed_hashes.length}</div>
        </div>
        <div className="bg-gray-50 p-4 rounded border border-gray-200">
          <span className="text-sm font-semibold text-gray-900">Unchanged</span>
          <div className="text-2xl font-bold text-gray-700 mt-1">{diff.unchanged_hashes.length}</div>
        </div>
      </div>

      {diff.added_chunks.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold text-green-900 mb-3">Added Chunks ({diff.added_chunks.length})</h3>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {diff.added_chunks.map((chunk) => (
              <div key={chunk.chunk_hash} className="border-l-4 border-green-500 bg-green-50 p-3 rounded">
                <code className="text-xs text-gray-600 font-mono">{chunk.chunk_hash.substring(0, 12)}…</code>
                <div className="text-sm text-gray-700 mt-2 whitespace-pre-wrap break-words">
                  {chunk.content.substring(0, 300)}
                  {chunk.content.length > 300 ? '…' : ''}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {diff.removed_chunks.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold text-red-900 mb-3">Removed Chunks ({diff.removed_chunks.length})</h3>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {diff.removed_chunks.map((chunk) => (
              <div key={chunk.chunk_hash} className="border-l-4 border-red-500 bg-red-50 p-3 rounded">
                <code className="text-xs text-gray-600 font-mono">{chunk.chunk_hash.substring(0, 12)}…</code>
                <div className="text-sm text-gray-700 mt-2 whitespace-pre-wrap break-words">
                  {chunk.content.substring(0, 300)}
                  {chunk.content.length > 300 ? '…' : ''}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {diff.unchanged_hashes.length > 0 && (
        <div className="bg-gray-50 p-3 rounded border border-gray-200">
          <span className="text-sm text-gray-700">
            <span className="font-semibold">{diff.unchanged_hashes.length}</span> chunks unchanged
          </span>
        </div>
      )}
    </div>
  );
}

// ── Versions History Page Component ────────────────────────────────
export default function BrowserVersionsPage() {
  const { sourceId } = useParams({ from: '/browser/versions/$sourceId' });
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Version selection state
  const [selectedVersions, setSelectedVersions] = useState<number[]>([]);
  const [showDiff, setShowDiff] = useState(false);

  // Fetch version history
  const {
    isLoading: historyLoading,
    isError: historyError,
    error: historyErrorObj,
  } = useVersionHistory(sourceId);

  // Fetch diff only when we have exactly 2 selected versions and user wants to see it
  const [from, to] = selectedVersions.length === 2 ? selectedVersions : [0, 0];
  const {
    data: diffData,
    isLoading: diffLoading,
    isError: diffError,
    error: diffErrorObj,
  } = useVersionDiff(sourceId, from, to, showDiff && selectedVersions.length === 2);

  const handleVersionSelectionChange = useCallback(
    (version: number, selected: boolean) => {
      if (selected) {
        // Add version, but limit to 2 maximum
        setSelectedVersions((prev) => {
          if (prev.length >= 2) {
            return [prev[1], version]; // Replace the first with the new one
          }
          return [...prev, version].sort((a, b) => a - b); // Keep sorted
        });
      } else {
        // Remove version
        setSelectedVersions((prev) => prev.filter((v) => v !== version));
        setShowDiff(false); // Hide diff when deselecting
      }
    },
    []
  );

  const versionColumns = useMemo(
    () => buildVersionColumns(selectedVersions, handleVersionSelectionChange),
    [selectedVersions, handleVersionSelectionChange]
  );

  const versionFetchFn = useCallback(
    async (params: FetchParams) => {
      const cachedData = queryClient.getQueryData<VersionHistoryResponse>(
        ['version-history', sourceId]
      );
      const versions = cachedData?.versions || [];
      const start = params.page * params.pageSize;
      const end = start + params.pageSize;
      const paginated = versions.slice(start, end);
      return {
        rows: paginated,
        total: versions.length,
      };
    },
    [sourceId, queryClient]
  );

  if (historyLoading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-screen">
        <div className="flex items-center gap-2">
          <Spinner />
          <span className="text-gray-600">Loading versions...</span>
        </div>
      </div>
    );
  }

  if (historyError) {
    return (
      <div className="p-8">
        <div className="bg-red-50 p-4 rounded border border-red-200">
          <p className="text-red-900 font-semibold">Failed to load versions</p>
          <p className="text-red-800 text-sm mt-1">
            {historyErrorObj instanceof Error ? historyErrorObj.message : 'An unexpected error occurred'}
          </p>
          <Button
            size="sm"
            color="gray"
            onClick={() => navigate({ to: '/browser', search: { page: 0 } })}
            className="mt-4"
          >
            Back to Browser
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-8">
        <Button
          size="sm"
          color="gray"
          onClick={() => navigate({ to: '/browser', search: { page: 0 } })}
          className="mb-4"
        >
          ← Back to Browser
        </Button>
        <h1 className="text-4xl font-bold mb-2">Version History</h1>
        <p className="text-gray-600">Select two versions to compare</p>
      </div>

      {/* Versions Table */}
      <div className="mb-8">
        <DataTable<VersionSummary>
          columns={versionColumns}
          fetchFn={versionFetchFn}
          facets={[]}
          searchable={false}
          queryKey={`versions-${sourceId}`}
          rowKey={(row) => String(row.version)}
          defaultPageSize={25}
          onSearchParamsChange={() => {}}
        />
      </div>

      {/* Compare Button */}
      {selectedVersions.length === 2 && (
        <div className="mb-8">
          <Button
            onClick={() => setShowDiff(true)}
            disabled={diffLoading}
            className="gap-2"
          >
            {diffLoading && <Spinner size="sm" />}
            Compare v{selectedVersions[0]} → v{selectedVersions[1]}
          </Button>
        </div>
      )}

      {/* Diff View */}
      {showDiff && selectedVersions.length === 2 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-2xl font-bold">
              Diff: v{selectedVersions[0]} → v{selectedVersions[1]}
            </h2>
            <Button
              size="sm"
              color="gray"
              onClick={() => setShowDiff(false)}
            >
              Hide Diff
            </Button>
          </div>

          {diffLoading ? (
            <div className="flex items-center gap-2 text-gray-600">
              <Spinner />
              Computing diff...
            </div>
          ) : diffError ? (
            <div className="bg-red-50 p-4 rounded border border-red-200">
              <p className="text-red-900 font-semibold">Failed to load diff</p>
              <p className="text-red-800 text-sm mt-1">
                {diffErrorObj instanceof Error ? diffErrorObj.message : 'An unexpected error occurred'}
              </p>
            </div>
          ) : diffData ? (
            <DiffView diff={diffData} />
          ) : null}
        </div>
      )}
    </div>
  );
}
