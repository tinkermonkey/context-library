import type { ComponentType } from 'react';
import type { ChunkResponse } from '../types/api';
import { GenericChunkTable as GenericChunkTableComponent } from '../components/GenericChunkTable';
import { ThreadView } from './ThreadView';
import { TimeSeriesView } from './TimeSeriesView';
import { HealthMetricsView } from './HealthMetricsView';
import { TaskListView } from './TaskListView';
import { DocumentDetailView } from './DocumentDetailView';
import { DocumentCatalogView } from './DocumentCatalogView';
import { NotesView } from './NotesView';

/**
 * Supported domain types.
 * Ensures all domain keys are typed and typos are caught at compile time.
 */
export type DomainType = 'messages' | 'notes' | 'events' | 'tasks' | 'health' | 'documents';

/**
 * All supported domains as an array constant.
 * Useful for form options and iteration.
 */
export const ALL_DOMAINS: readonly DomainType[] = ['messages', 'notes', 'events', 'tasks', 'health', 'documents'] as const;

/**
 * Props passed to all domain view components.
 */
export interface DomainViewProps {
  sourceId: string;
  chunks: ChunkResponse[];
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
  /** Optional: components for sub-type rendering (keyed by subtype value) */
  subtypeViews?: Record<string, ComponentType<DomainViewProps>>;
}

/**
 * Health subtype view components.
 * HealthMetricsView uses these internally based on the health_type metadata field.
 * Registered here for completeness and to support future dispatching patterns.
 */
const healthSubtypeViews: Record<string, ComponentType<DomainViewProps>> = {
  sleep_summary: HealthMetricsView,
  activity_summary: HealthMetricsView,
  readiness_summary: HealthMetricsView,
  workout_session: HealthMetricsView,
  heart_rate_series: HealthMetricsView,
  spo2_summary: HealthMetricsView,
  mindfulness_session: HealthMetricsView,
  user_health_tag: HealthMetricsView,
};

/**
 * Domain view registry.
 * Maps each domain to its page-level React component reference.
 * Uses typed domain keys to ensure completeness and prevent typos.
 */
const registry: Record<DomainType, RegistryEntry> = {
  messages: {
    component: ThreadView,
    label: 'Thread',
  },
  notes: {
    component: NotesView,
    label: 'Note',
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
    subtypeViews: healthSubtypeViews,
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
 * For domains with subtypeKey and subtypeViews, the component selection
 * can be further refined by the view using the subtype metadata field.
 *
 * @param domain - The domain string (e.g., "messages", "health")
 * @returns The registry entry with component reference and metadata
 */
export function getDomainView(domain: string): RegistryEntry {
  // Type guard: only access registry if domain is a known DomainType
  if (domain in registry) {
    return registry[domain as DomainType];
  }
  return {
    component: GenericChunkTableComponent,
    label: 'Chunks',
  };
}
