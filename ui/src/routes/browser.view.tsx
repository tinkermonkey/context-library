import { Suspense, useState } from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import { useSourceChunks } from '../hooks/useChunks';
import { getDomainView } from '../views/registry';
import { ErrorBoundary } from '../components/ErrorBoundary';

/**
 * Domain view route handler.
 *
 * Fetches source chunks and metadata, then dispatches to the appropriate
 * domain-specific view component based on the domain parameter.
 * Implements server-side pagination to avoid loading entire datasets into browser memory.
 */
export default function DomainViewPage() {
  const params = useParams({ from: '/browser/view/$domain/$sourceId' });
  const navigate = useNavigate();

  const { domain, sourceId } = params;

  // Pagination state
  const [offset, setOffset] = useState(0);
  const pageSize = 50;

  // Fetch chunks with pagination
  const { data: chunksData, isLoading: chunksLoading, isError: chunksError, error: chunksErrorObj } = useSourceChunks(sourceId, undefined, pageSize, offset);

  // Get the domain view component
  const viewEntry = getDomainView(domain);
  const ViewComponent = viewEntry.component;

  if (chunksLoading) {
    return (
      <div className="p-8">
        <div className="text-gray-600">Loading {viewEntry.label}…</div>
      </div>
    );
  }

  if (chunksError) {
    return (
      <div className="p-8">
        <div className="bg-red-50 p-4 rounded border border-red-200">
          <p className="text-red-900 font-semibold">Failed to load data</p>
          <p className="text-red-800 text-sm mt-1">
            {chunksErrorObj instanceof Error ? chunksErrorObj.message : 'An unexpected error occurred'}
          </p>
        </div>
      </div>
    );
  }

  if (!chunksData) {
    return (
      <div className="p-8">
        <div className="text-gray-600">No data available</div>
      </div>
    );
  }

  const chunks = chunksData.chunks || [];

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">{viewEntry.label}</h1>
        <p className="text-gray-600">
          Source: <code className="text-xs bg-gray-100 px-2 py-1 rounded">{sourceId}</code>
        </p>
      </div>

      <ErrorBoundary>
        <Suspense fallback={<div className="text-gray-600">Loading view…</div>}>
          <ViewComponent sourceId={sourceId} chunks={chunks} />
        </Suspense>
      </ErrorBoundary>

      {/* Pagination controls */}
      <div className="mt-8 pt-6 border-t border-gray-200 flex items-center justify-between">
        <div className="text-sm text-gray-600">
          {chunksData && chunksData.total > 0 ? (
            <>
              Showing {offset + 1}-{Math.min(offset + pageSize, chunksData.total)} of {chunksData.total} chunks
            </>
          ) : chunksData ? (
            <>No chunks</>
          ) : null}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setOffset(Math.max(0, offset - pageSize))}
            disabled={offset === 0 || chunksLoading}
            className="px-4 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Previous
          </button>
          <button
            onClick={() => setOffset(offset + pageSize)}
            disabled={!chunksData || offset + pageSize >= chunksData.total || chunksLoading}
            className="px-4 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      </div>

      {/* Navigation back to chunks */}
      <div className="mt-4">
        <button
          onClick={() => navigate({ to: '/browser', search: { table: 'chunks', source_id: sourceId } })}
          className="text-blue-600 hover:underline text-sm bg-none border-none cursor-pointer p-0"
        >
          ← Back to chunk view
        </button>
      </div>
    </div>
  );
}
