/**
 * Placeholder domain view components for Phase 2-5 implementation.
 * Exported to a separate non-component file to satisfy react-refresh/only-export-components.
 */

import type { ComponentType } from 'react';
import type { DomainViewProps } from './registry';

export const DocumentView: ComponentType<DomainViewProps> = () => (
  <div className="p-4 bg-blue-50 border border-blue-200 rounded">
    <p className="text-sm text-blue-900">Document view not yet available</p>
  </div>
);

export const TimeSeriesView: ComponentType<DomainViewProps> = () => (
  <div className="p-4 bg-blue-50 border border-blue-200 rounded">
    <p className="text-sm text-blue-900">Timeline view not yet available</p>
  </div>
);

export const TaskListView: ComponentType<DomainViewProps> = () => (
  <div className="p-4 bg-blue-50 border border-blue-200 rounded">
    <p className="text-sm text-blue-900">Task list view not yet available</p>
  </div>
);

// Note: HealthMetricsView has been moved to its own file (HealthMetricsView.tsx)
// This placeholder is kept for backwards compatibility but should not be used
export const HealthMetricsView: ComponentType<DomainViewProps> = () => (
  <div className="p-4 bg-blue-50 border border-blue-200 rounded">
    <p className="text-sm text-blue-900">Health metrics view - component moved to HealthMetricsView.tsx</p>
  </div>
);

export const DocumentCatalogView: ComponentType<DomainViewProps> = () => (
  <div className="p-4 bg-blue-50 border border-blue-200 rounded">
    <p className="text-sm text-blue-900">Document catalog view not yet available</p>
  </div>
);
