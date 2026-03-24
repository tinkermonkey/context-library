import type { ComponentType } from 'react';
import type { ChunkResponse } from '../types/api';
import { GenericChunkTable as GenericChunkTableComponent } from '../components/GenericChunkTable';
import { ThreadView } from './ThreadView';
import { TimeSeriesView } from './TimeSeriesView';
import { HealthMetricsView } from './HealthMetricsView';
import { TaskListView } from './TaskListView';
import { DocumentView } from './DocumentView';
import { DocumentCatalogView } from './DocumentCatalogView';
import { createDomainCatalogPage } from './BaseCatalogView';

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
 * Props passed to all domain view components (single-source detail view).
 */
export interface DomainViewProps {
  sourceId: string;
  chunks: ChunkResponse[];
}

/**
 * Registry entry for a domain view.
 * Maps a domain to its display components and metadata.
 */
export interface RegistryEntry {
  /** React component that renders the domain detail view for a single source. */
  component: ComponentType<DomainViewProps>;
  /**
   * Zero-prop React component that renders the browsable catalog for this domain.
   * Self-contained: fetches its own sources and handles its own navigation.
   * Used by /browser/catalog/$domain.
   */
  catalogPage: ComponentType;
  /** Singular human-readable label (e.g. "Thread", "Document"). */
  label: string;
  /** Plural human-readable label for catalog headings (e.g. "Threads", "Documents"). */
  pluralLabel: string;
  /**
   * Optional: metadata field key for sub-type dispatch (e.g. "health_type").
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
 * Single source of truth for per-domain view components, catalog pages, and labels.
 */
const registry: Record<DomainType, RegistryEntry> = {
  messages: {
    component: ThreadView,
    catalogPage: createDomainCatalogPage('messages'),
    label: 'Thread',
    pluralLabel: 'Threads',
  },
  notes: {
    component: DocumentView,
    catalogPage: createDomainCatalogPage('notes'),
    label: 'Note',
    pluralLabel: 'Notes',
  },
  events: {
    component: TimeSeriesView,
    catalogPage: createDomainCatalogPage('events'),
    label: 'Timeline',
    pluralLabel: 'Events',
  },
  tasks: {
    component: TaskListView,
    catalogPage: createDomainCatalogPage('tasks'),
    label: 'Tasks',
    pluralLabel: 'Tasks',
  },
  health: {
    component: HealthMetricsView,
    catalogPage: createDomainCatalogPage('health'),
    label: 'Metrics',
    pluralLabel: 'Health',
    subtypeKey: 'health_type',
  },
  documents: {
    component: DocumentView,
    catalogPage: DocumentCatalogView,
    label: 'Document',
    pluralLabel: 'Documents',
  },
};

/**
 * Get the domain view registry entry for a given domain.
 * Falls back to GenericChunkTable + BaseCatalogView for unrecognized domains.
 */
export function getDomainView(domain: string): RegistryEntry {
  if (domain in registry) {
    return registry[domain as DomainType];
  }
  return {
    component: GenericChunkTableComponent,
    catalogPage: createDomainCatalogPage(domain),
    label: 'Chunks',
    pluralLabel: 'Sources',
  };
}
