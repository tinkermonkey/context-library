import type { ComponentType } from 'react';
import type { ChunkResponse, SourceDetailResponse } from '../types/api';
import { GenericChunkTable as GenericChunkTableComponent } from '../components/GenericChunkTable';

/**
 * Props passed to all domain view components.
 */
export interface DomainViewProps {
  sourceId: string;
  chunks: ChunkResponse[];
  source: SourceDetailResponse;
}

/**
 * Registry entry for a domain view.
 * Maps a domain to its display component and metadata.
 */
export interface RegistryEntry {
  /** React component that renders the domain view */
  component: ComponentType<DomainViewProps>;
  /** Human-readable label for this domain (e.g., "Thread", "Document") */
  label: string;
  /** Optional: domain_metadata field key for sub-type dispatch (e.g., "health_type") */
  subtypeKey?: string;
}

/**
 * Placeholder components - to be replaced with actual implementations in Phase 2-5.
 */
const ThreadView: ComponentType<DomainViewProps> = () => (
  <div className="p-4 bg-blue-50 border border-blue-200 rounded">
    <p className="text-sm text-blue-900">Thread view coming in Phase 2</p>
  </div>
);
const DocumentView: ComponentType<DomainViewProps> = () => (
  <div className="p-4 bg-blue-50 border border-blue-200 rounded">
    <p className="text-sm text-blue-900">Document view coming in Phase 2</p>
  </div>
);
const TimeSeriesView: ComponentType<DomainViewProps> = () => (
  <div className="p-4 bg-blue-50 border border-blue-200 rounded">
    <p className="text-sm text-blue-900">Timeline view coming in Phase 3</p>
  </div>
);
const TaskListView: ComponentType<DomainViewProps> = () => (
  <div className="p-4 bg-blue-50 border border-blue-200 rounded">
    <p className="text-sm text-blue-900">Task list view coming in Phase 4</p>
  </div>
);
const HealthMetricsView: ComponentType<DomainViewProps> = () => (
  <div className="p-4 bg-blue-50 border border-blue-200 rounded">
    <p className="text-sm text-blue-900">Health metrics view coming in Phase 5</p>
  </div>
);
const DocumentCatalogView: ComponentType<DomainViewProps> = () => (
  <div className="p-4 bg-blue-50 border border-blue-200 rounded">
    <p className="text-sm text-blue-900">Document catalog view coming in Phase 5</p>
  </div>
);

/**
 * Domain view registry.
 * Maps each domain to its page-level React component reference.
 */
const registry: Record<string, RegistryEntry> = {
  messages: {
    component: ThreadView,
    label: 'Thread',
  },
  notes: {
    component: DocumentView,
    label: 'Document',
  },
  events: {
    component: TimeSeriesView,
    label: 'Timeline',
  },
  tasks: {
    component: TaskListView,
    label: 'Tasks',
  },
  health: {
    component: HealthMetricsView,
    label: 'Metrics',
    subtypeKey: 'health_type',
  },
  documents: {
    component: DocumentCatalogView,
    label: 'Catalog',
  },
};

/**
 * Get the domain view registry entry for a given domain.
 *
 * Supports fallback to GenericChunkTable for any unrecognized domain.
 *
 * @param domain - The domain string (e.g., "messages", "health")
 * @returns The registry entry with component reference and metadata
 */
export function getDomainView(domain: string): RegistryEntry {
  return registry[domain] ?? {
    component: GenericChunkTableComponent,
    label: 'Chunks',
  };
}
