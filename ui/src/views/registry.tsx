import type { ComponentType } from 'react';
import type { ChunkResponse } from '../types/api';
import { GenericChunkTable as GenericChunkTableComponent } from '../components/GenericChunkTable';
import { ThreadView } from './ThreadView';
import { TimeSeriesView } from './TimeSeriesView';
import { HealthMetricsView } from './HealthMetricsView';
import { TaskListView } from './TaskListView';
import { DocumentView } from './DocumentView';

/**
 * All supported domains as the source of truth.
 * Typed as const to enable deriving the DomainType union from this array.
 */
export const ALL_DOMAINS = ['messages', 'notes', 'events', 'tasks', 'health', 'documents'] as const;

/**
 * Supported domain types, derived from ALL_DOMAINS to ensure type and runtime array stay synchronized.
 * Ensures all domain keys are typed and typos are caught at compile time.
 */
export type DomainType = (typeof ALL_DOMAINS)[number];

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
  /**
   * Optional: metadata field key for sub-type dispatch (e.g., "health_type").
   *
   * RESERVED FOR FUTURE USE: Currently informational only. To implement subtype dispatch:
   * 1. Read the subtypeKey from the registry entry
   * 2. Extract the field value from chunk.domain_metadata[subtypeKey]
   * 3. Create a subtypeViews map and populate it in the registry
   * 4. Update getDomainView() to return subtype-specific components based on the metadata
   * 5. Update the view dispatcher (e.g., browser.view.tsx) to consume subtypeViews
   *
   * The HealthMetricsView currently dispatches internally via a switch statement
   * on the health_type metadata field rather than via the registry.
   */
  subtypeKey?: string;
}

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
    component: DocumentView,
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
  },
  documents: {
    component: DocumentView,
    label: 'Document',
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
  // Type guard: only access registry if domain is a known DomainType
  if (domain in registry) {
    return registry[domain as DomainType];
  }
  return {
    component: GenericChunkTableComponent,
    label: 'Chunks',
  };
}
