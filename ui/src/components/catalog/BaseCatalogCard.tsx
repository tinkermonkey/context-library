import type { ReactNode } from 'react';
import type { SourceSummary } from '../../types/api';
import { Timestamp } from '../shared/Timestamp';

export interface CatalogCardProps {
  source: SourceSummary;
  onSelect: (source: SourceSummary) => void;
}

/** Left-border accent color per domain. */
const DOMAIN_ACCENT: Record<string, string> = {
  messages:  'border-l-indigo-500',
  notes:     'border-l-yellow-500',
  events:    'border-l-green-500',
  tasks:     'border-l-red-500',
  health:    'border-l-rose-500',
  documents: 'border-l-blue-500',
};

/**
 * Generic source catalog card.
 *
 * Shows display_name, origin_ref, chunk_count, last_fetched_at, and adapter_id
 * with a domain-specific left-border accent. Domain-specific catalog cards can
 * import and extend this component for richer metadata display.
 */
export function BaseCatalogCard({ source, onSelect }: CatalogCardProps): ReactNode {
  const accent = DOMAIN_ACCENT[source.domain] ?? 'border-l-gray-400';
  const displayName = source.display_name || source.origin_ref;

  return (
    <div
      onClick={() => onSelect(source)}
      className={`border border-gray-200 rounded-lg p-4 bg-white hover:shadow-md
        transition-all cursor-pointer hover:border-blue-300 border-l-4 ${accent}`}
    >
      {/* Name + origin */}
      <div className="mb-3">
        <h3 className="text-base font-semibold text-gray-900 truncate">{displayName}</h3>
        <p className="text-xs text-gray-500 truncate mt-1">{source.origin_ref}</p>
      </div>

      {/* Metadata grid */}
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <span className="font-semibold text-gray-700">Chunks:</span>
          <div className="mt-1 text-gray-600">{source.chunk_count}</div>
        </div>
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
        <div className="col-span-2">
          <span className="font-semibold text-gray-700">Adapter:</span>
          <div className="mt-1 text-xs text-gray-600 truncate">{source.adapter_id}</div>
        </div>
      </div>
    </div>
  );
}
