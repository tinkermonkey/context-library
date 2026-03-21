import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearch } from '@tanstack/react-router';
import type { SourceSummary } from '../types/api';
import type { DomainViewProps } from './registry';
import { useSources } from '../hooks/useSources';
import { Timestamp } from '../components/shared/Timestamp';

/**
 * Get display label for a document type.
 */
function getDocumentTypeLabel(documentType: string): string {
  // Common MIME types
  if (documentType === 'text/markdown') return 'Markdown';
  if (documentType === 'text/plain') return 'Text';
  if (documentType === 'application/pdf') return 'PDF';
  if (documentType === 'audio/mpeg') return 'Music';
  if (documentType === 'audio/mp4') return 'Music';

  // For unknown types, return the type as-is
  return documentType;
}

/**
 * Determine if a source is a music library entry.
 */
function isMusicSource(source: SourceSummary): boolean {
  return (
    source.adapter_id.includes('music') ||
    source.adapter_id.includes('apple_music') ||
    source.origin_ref.includes('music')
  );
}

/**
 * Get a color class for badge based on document type.
 */
function getDocumentTypeColor(documentType: string): string {
  if (documentType === 'audio/mpeg' || documentType === 'audio/mp4') {
    return 'bg-purple-100 text-purple-800';
  }
  if (documentType === 'text/markdown' || documentType === 'text/plain') {
    return 'bg-blue-100 text-blue-800';
  }
  return 'bg-gray-100 text-gray-800';
}

/**
 * Extract all unique document types from sources.
 * Used to populate filter options.
 */
function extractDocumentTypes(sources: SourceSummary[]): string[] {
  const types = new Set<string>();

  for (const source of sources) {
    // Try to infer document_type from adapter_id
    if (source.adapter_id.includes('music') || source.adapter_id.includes('apple_music')) {
      types.add('audio/mpeg');
    } else if (source.adapter_id.includes('filesystem')) {
      types.add('text/markdown');
    }
  }

  // Always include common types even if not present in current data
  types.add('text/markdown');
  types.add('audio/mpeg');

  return Array.from(types).sort();
}

/**
 * Filter sources by document type.
 * Since document_type is in chunk metadata, we infer it from adapter_id or origin_ref.
 */
function filterSourcesByType(sources: SourceSummary[], documentTypeFilter: string): SourceSummary[] {
  if (!documentTypeFilter) {
    return sources;
  }

  return sources.filter((source) => {
    // Infer document_type from adapter_id and origin_ref
    let sourceType = '';

    if (source.adapter_id.includes('music') || source.adapter_id.includes('apple_music')) {
      sourceType = 'audio/mpeg';
    } else if (source.adapter_id.includes('filesystem')) {
      sourceType = 'text/markdown';
    }

    return sourceType === documentTypeFilter;
  });
}

/**
 * Render a single catalog entry card.
 */
function CatalogEntryCard({
  source,
  onSelect,
}: {
  source: SourceSummary;
  onSelect: (source: SourceSummary) => void;
}): ReactNode {
  // Infer document type from adapter_id
  let documentType = 'text/markdown';
  if (source.adapter_id.includes('music') || source.adapter_id.includes('apple_music')) {
    documentType = 'audio/mpeg';
  }

  const isMusicEntry = isMusicSource(source);
  const displayName = source.display_name || source.origin_ref;

  return (
    <div
      onClick={() => onSelect(source)}
      className={`
        border border-gray-200 rounded-lg p-4 bg-white hover:shadow-md
        transition-all cursor-pointer hover:border-blue-300
        ${isMusicEntry ? 'border-l-4 border-l-purple-500' : 'border-l-4 border-l-blue-500'}
      `}
    >
      {/* Header: Name and Type Badge */}
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-gray-900 truncate">{displayName}</h3>
          <p className="text-xs text-gray-500 truncate mt-1">{source.origin_ref}</p>
        </div>
        <div className={`px-2 py-1 rounded text-xs font-medium whitespace-nowrap ${getDocumentTypeColor(documentType)}`}>
          {getDocumentTypeLabel(documentType)}
        </div>
      </div>

      {/* Metadata Grid */}
      <div className="grid grid-cols-2 gap-3 text-sm">
        {/* Chunk Count */}
        <div>
          <span className="font-semibold text-gray-700">Chunks:</span>
          <div className="mt-1 text-gray-600">{source.chunk_count}</div>
        </div>

        {/* Last Fetched */}
        <div>
          <span className="font-semibold text-gray-700">Updated:</span>
          <div className="mt-1">
            {source.last_fetched_at ? (
              <Timestamp value={source.last_fetched_at} granularity="date" />
            ) : (
              <span className="text-gray-400">—</span>
            )}
          </div>
        </div>

        {/* Source Type */}
        <div>
          <span className="font-semibold text-gray-700">Source:</span>
          <div className="mt-1 text-gray-600">
            {isMusicEntry ? '🎵 Music Library' : '📄 Filesystem'}
          </div>
        </div>

        {/* Adapter */}
        <div>
          <span className="font-semibold text-gray-700">Adapter:</span>
          <div className="mt-1 text-xs text-gray-600 truncate">{source.adapter_id}</div>
        </div>
      </div>
    </div>
  );
}

/**
 * Document Catalog View Component.
 *
 * Displays documents domain as a source-level catalog with:
 * - Per-entry display: display_name, document_type, chunk count, last fetched date
 * - Filtering by document_type (inferred from adapter_id)
 * - Pagination with "Load more" button
 * - Visual differentiation between music library and filesystem documents
 * - Click-through to DocumentView route for each source
 *
 * Note: This component diverges from standard DomainViewProps usage.
 * It receives chunks and source props but primarily uses the sources listing API.
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function DocumentCatalogView(_props: DomainViewProps): ReactNode {
  const navigate = useNavigate({ from: '/browser/view/$domain/$sourceId' });
  const search = useSearch({ from: '/browser/view/$domain/$sourceId' });

  // Extract filter value from URL search params
  const documentTypeFilter = (search as { documentType?: string }).documentType || '';

  // Local state for filter control (UI-only, not source of truth)
  const [pendingDocumentType, setPendingDocumentType] = useState<string>(documentTypeFilter);

  // Pagination state
  const [limit, setLimit] = useState(50);

  // Sync pending state with URL params on external navigation
  useEffect(() => {
    setPendingDocumentType(documentTypeFilter);
  }, [documentTypeFilter]);

  // Fetch sources with current pagination
  const { data: sourcesData, isLoading, isError } = useSources({
    domain: 'documents',
    limit,
  });

  // Memoize allSources to prevent dependency array issues
  const allSources = useMemo(() => sourcesData?.sources ?? [], [sourcesData?.sources]);
  const totalSources = sourcesData?.total ?? 0;

  // Apply document type filter
  const filteredSources = useMemo(
    () => filterSourcesByType(allSources, documentTypeFilter),
    [allSources, documentTypeFilter]
  );

  // Extract available document types for filter dropdown
  const availableDocumentTypes = useMemo(() => extractDocumentTypes(allSources), [allSources]);

  /**
   * Apply filter by updating URL search params.
   */
  const applyFilter = (): void => {
    void navigate({
      to: '.',
      search: (prev: Record<string, unknown>) => {
        const newSearch = { ...prev };
        if (pendingDocumentType) {
          (newSearch as { documentType: string }).documentType = pendingDocumentType;
        } else {
          delete (newSearch as { documentType?: string }).documentType;
        }
        return newSearch;
      },
    });
  };

  /**
   * Clear filter.
   */
  const clearFilter = (): void => {
    setPendingDocumentType('');
    void navigate({
      to: '.',
      search: (prev: Record<string, unknown>) => {
        const newSearch = { ...prev };
        delete (newSearch as { documentType?: string }).documentType;
        return newSearch;
      },
    });
  };

  /**
   * Load more sources.
   */
  const loadMore = (): void => {
    setLimit((prevLimit) => prevLimit + 50);
  };

  /**
   * Navigate to document detail view for a source.
   */
  const openDocument = (source: SourceSummary): void => {
    void navigate({
      to: '/browser/view/$domain/$sourceId',
      params: { domain: 'documents', sourceId: source.source_id },
    });
  };

  // Loading state
  if (isLoading && allSources.length === 0) {
    return (
      <div className="text-center py-8 text-gray-600">
        <p>Loading document catalog…</p>
      </div>
    );
  }

  // Error state
  if (isError) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-sm text-red-900">Failed to load document catalog</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Filter Controls */}
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <div className="flex flex-col gap-4">
          {/* Title */}
          <h3 className="font-semibold text-gray-900">Filters</h3>

          {/* Filter Inputs */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Document Type Filter */}
            <div>
              <label htmlFor="document-type-filter" className="block text-sm font-medium text-gray-700 mb-2">
                Document Type
              </label>
              <select
                id="document-type-filter"
                value={pendingDocumentType}
                onChange={(e) => setPendingDocumentType(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
              >
                <option value="">All types</option>
                {availableDocumentTypes.map((type) => (
                  <option key={type} value={type}>
                    {getDocumentTypeLabel(type)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Filter Actions */}
          <div className="flex gap-2 pt-2">
            <button
              onClick={applyFilter}
              className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 transition-colors"
            >
              Apply Filter
            </button>
            {documentTypeFilter && (
              <button
                onClick={clearFilter}
                className="px-4 py-2 border border-gray-300 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50 transition-colors"
              >
                Clear Filter
              </button>
            )}
          </div>

          {/* Filter Summary */}
          <div className="text-xs text-gray-600 pt-2">
            Showing {filteredSources.length} of {totalSources} document(s)
            {documentTypeFilter && (
              <span className="font-semibold">
                {' '}
                — filtered by type: {getDocumentTypeLabel(documentTypeFilter)}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Catalog Grid or Empty State */}
      {filteredSources.length === 0 ? (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-8 text-center">
          <p className="text-sm text-yellow-800">
            {filteredSources.length === 0 && totalSources > 0
              ? 'No documents match the selected filter.'
              : 'No documents found.'}
          </p>
        </div>
      ) : (
        <>
          {/* Catalog Entries Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredSources.map((source) => (
              <CatalogEntryCard key={source.source_id} source={source} onSelect={openDocument} />
            ))}
          </div>

          {/* Load More Button */}
          {limit < totalSources && (
            <div className="flex justify-center pt-4">
              <button
                onClick={loadMore}
                disabled={isLoading}
                className="px-6 py-2 border border-blue-600 text-blue-600 text-sm font-medium rounded-md hover:bg-blue-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? 'Loading…' : 'Load more'}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
