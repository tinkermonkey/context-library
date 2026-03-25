import type { ComponentType, ReactNode } from 'react';
import { useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import type { SourceSummary } from '../types/api';
import { useSources } from '../hooks/useSources';
import { BaseCatalogCard } from '../components/catalog/BaseCatalogCard';
import type { CatalogCardProps } from '../components/catalog/BaseCatalogCard';

interface BaseCatalogViewProps {
  domain: string;
  CardComponent?: ComponentType<CatalogCardProps>;
}

/**
 * Generic domain catalog view.
 *
 * Fetches all sources for a domain and renders them as a clickable card grid.
 * Clicking a card navigates to the domain-specific single-source view.
 *
 * Accepts an optional CardComponent override — domain-specific catalogs pass
 * their own card (e.g. DocumentsCatalogCard) while all other domains fall back
 * to BaseCatalogCard.
 */
export function BaseCatalogView({ domain, CardComponent = BaseCatalogCard }: BaseCatalogViewProps): ReactNode {
  const navigate = useNavigate();
  const [limit, setLimit] = useState(50);

  const { data, isLoading, isError } = useSources({ domain, limit, offset: 0 });
  const sources = data?.sources ?? [];
  const total = data?.total ?? 0;

  const openSource = (source: SourceSummary): void => {
    void navigate({
      to: '/browser/view/$domain/$sourceId',
      params: { domain, sourceId: source.source_id },
    });
  };

  if (isLoading && sources.length === 0) {
    return (
      <div className="text-center py-8 text-gray-600">
        <p>Loading…</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-sm text-red-900">Failed to load catalog</p>
      </div>
    );
  }

  if (sources.length === 0) {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-8 text-center">
        <p className="text-sm text-yellow-800">No sources found for this domain.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="text-sm text-gray-600">
        Showing {sources.length} of {total} source(s)
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {sources.map((source) => (
          <CardComponent key={source.source_id} source={source} onSelect={openSource} />
        ))}
      </div>

      {limit < total && (
        <div className="flex justify-center pt-4">
          <button
            onClick={() => setLimit((l) => l + 50)}
            disabled={isLoading}
            className="px-6 py-2 border border-blue-600 text-blue-600 text-sm font-medium rounded-md hover:bg-blue-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? 'Loading…' : 'Load more'}
          </button>
        </div>
      )}
    </div>
  );
}
