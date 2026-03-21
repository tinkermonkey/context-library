import { Suspense } from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import { useSourceChunks } from '../hooks/useChunks';
import { getDomainView } from '../views/registry';

/**
 * Domain view route handler.
 *
 * Fetches source chunks and metadata, then dispatches to the appropriate
 * domain-specific view component based on the domain parameter.
 */
export default function DomainViewPage() {
  const params = useParams({ from: '/browser/view/$domain/$sourceId' });
  const navigate = useNavigate();

  const { domain, sourceId } = params;

  // Fetch chunks
  const { data: chunksData, isLoading: chunksLoading, isError: chunksError, error: chunksErrorObj } = useSourceChunks(sourceId);

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
        {sourceData.display_name && (
          <p className="text-gray-600 mt-1">{sourceData.display_name}</p>
        )}
      </div>

      <Suspense fallback={<div className="text-gray-600">Loading view…</div>}>
        <ViewComponent sourceId={sourceId} chunks={chunks} />
      </Suspense>

      {/* Navigation back to chunks */}
      <div className="mt-8 pt-6 border-t border-gray-200">
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
