import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearch } from '@tanstack/react-router';
import type { ChunkResponse } from '../types/api';
import type { DomainViewProps } from './registry';
import { Timestamp } from '../components/shared/Timestamp';
import { StatusBadge } from '../components/shared/StatusBadge';

/**
 * Task domain metadata structure.
 * Matches the backend TaskMetadata model.
 */
interface TaskMetadata {
  task_id: string;
  status: string; // 'open' | 'completed' | 'cancelled' | 'in-progress'
  title: string;
  due_date: string | null; // ISO 8601
  priority: number | null; // 1-4 (1 = highest)
  dependencies: string[]; // serialized from tuple, task_id references
  collaborators: string[]; // serialized from tuple
  date_first_observed: string; // ISO 8601
  source_type: string;
}

/**
 * Cast domain_metadata to TaskMetadata with safety checks.
 * Validates that required fields are present and have correct types.
 */
function extractTaskMetadata(chunk: ChunkResponse): TaskMetadata | null {
  if (!chunk.domain_metadata) return null;

  const meta = chunk.domain_metadata;

  // Validate required fields
  if (typeof meta.task_id !== 'string' || typeof meta.status !== 'string' || typeof meta.title !== 'string') {
    return null;
  }

  return {
    task_id: meta.task_id,
    status: meta.status,
    title: meta.title,
    due_date: typeof meta.due_date === 'string' ? meta.due_date : null,
    priority: typeof meta.priority === 'number' ? meta.priority : null,
    dependencies: Array.isArray(meta.dependencies) ? meta.dependencies : [],
    collaborators: Array.isArray(meta.collaborators) ? meta.collaborators : [],
    date_first_observed: typeof meta.date_first_observed === 'string' ? meta.date_first_observed : '',
    source_type: typeof meta.source_type === 'string' ? meta.source_type : '',
  };
}

/**
 * Format priority number to display text.
 * Priority 1 = highest urgency.
 */
function formatPriority(priority: number | null): string {
  if (priority === null) {
    return 'No priority';
  }
  return `P${priority}`;
}

/**
 * Get priority color class based on priority level.
 */
function getPriorityColor(priority: number | null): string {
  if (priority === null) return 'text-gray-500';
  if (priority === 1) return 'text-red-600 font-semibold';
  if (priority === 2) return 'text-orange-600 font-semibold';
  if (priority === 3) return 'text-yellow-600';
  return 'text-gray-600';
}

/**
 * Status display order.
 */
const STATUS_ORDER = ['in-progress', 'open', 'completed', 'cancelled'];

/**
 * Get the index of a status in the display order.
 */
function getStatusIndex(status: string): number {
  const index = STATUS_ORDER.indexOf(status.toLowerCase());
  return index !== -1 ? index : STATUS_ORDER.length;
}

/**
 * Group tasks by status and sort within each group by priority and due date.
 * Returns a Map with status keys in display order.
 */
function groupAndSortTasks(
  chunks: ChunkResponse[],
  statusFilter?: string,
  priorityFilter?: number
): Map<string, ChunkResponse[]> {
  const grouped = new Map<string, ChunkResponse[]>();
  // Cache metadata to avoid redundant extraction during sort
  const metadataCache = new Map<ChunkResponse, TaskMetadata | null>();

  // Process each chunk and extract metadata
  for (const chunk of chunks) {
    const metadata = extractTaskMetadata(chunk);
    metadataCache.set(chunk, metadata);

    if (!metadata) continue;

    // Apply filters
    if (statusFilter && metadata.status !== statusFilter) continue;
    if (priorityFilter != null && metadata.priority !== priorityFilter) continue;

    const status = metadata.status;
    if (!grouped.has(status)) {
      grouped.set(status, []);
    }
    grouped.get(status)!.push(chunk);
  }

  // Sort chunks within each status group
  // Primary: priority ascending (1 = highest, shown first)
  // Secondary: due_date ascending (null dates come last)
  for (const statusChunks of grouped.values()) {
    statusChunks.sort((a, b) => {
      const aMeta = metadataCache.get(a);
      const bMeta = metadataCache.get(b);

      if (!aMeta || !bMeta) return 0;

      // Sort by priority ascending (1 is highest, so comes first)
      if (aMeta.priority !== bMeta.priority) {
        const aPrio = aMeta.priority ?? Infinity;
        const bPrio = bMeta.priority ?? Infinity;
        return aPrio - bPrio;
      }

      // Secondary sort: by due_date ascending
      // null due dates sort to end
      if (aMeta.due_date === null && bMeta.due_date === null) return 0;
      if (aMeta.due_date === null) return 1;
      if (bMeta.due_date === null) return -1;
      return aMeta.due_date.localeCompare(bMeta.due_date);
    });
  }

  // Return sorted by status display order
  const sorted = new Map(
    Array.from(grouped.entries()).sort(([statusA], [statusB]) => {
      const indexA = getStatusIndex(statusA);
      const indexB = getStatusIndex(statusB);
      return indexA - indexB;
    })
  );

  return sorted;
}

/**
 * Render a single task card.
 */
function TaskCard({ chunk }: { chunk: ChunkResponse }): ReactNode {
  const metadata = extractTaskMetadata(chunk);
  if (!metadata) return null;

  return (
    <div className="border border-gray-200 rounded-lg p-4 bg-white hover:shadow-md transition-shadow">
      {/* Title and Status Badge */}
      <div className="flex items-start justify-between mb-3 gap-2">
        <h3 className="text-base font-semibold text-gray-900 flex-1">{metadata.title}</h3>
        <StatusBadge status={metadata.status} />
      </div>

      {/* Task Details Grid */}
      <div className="grid grid-cols-2 gap-3 text-sm">
        {/* Due Date */}
        <div>
          <span className="font-semibold text-gray-700">Due:</span>
          <div className="mt-1">
            {metadata.due_date ? (
              <Timestamp value={metadata.due_date} granularity="date" />
            ) : (
              <span className="text-gray-400">—</span>
            )}
          </div>
        </div>

        {/* Priority */}
        <div>
          <span className="font-semibold text-gray-700">Priority:</span>
          <div className={`mt-1 font-mono text-sm ${getPriorityColor(metadata.priority)}`}>
            {formatPriority(metadata.priority)}
          </div>
        </div>

        {/* Dependencies */}
        <div>
          <span className="font-semibold text-gray-700">Dependencies:</span>
          <div className="mt-1">
            {metadata.dependencies.length === 0 ? (
              <span className="text-gray-400">—</span>
            ) : (
              <span className="text-gray-600">{metadata.dependencies.length} task(s)</span>
            )}
          </div>
        </div>

        {/* Collaborators */}
        <div>
          <span className="font-semibold text-gray-700">Collaborators:</span>
          <div className="mt-1">
            {metadata.collaborators.length === 0 ? (
              <span className="text-gray-400">—</span>
            ) : (
              <span className="text-gray-600">{metadata.collaborators.length} person(s)</span>
            )}
          </div>
        </div>
      </div>

      {/* Task ID */}
      <div className="mt-3 pt-3 border-t border-gray-100">
        <span className="text-xs text-gray-500">ID: {metadata.task_id}</span>
      </div>
    </div>
  );
}

/**
 * Render a status group section.
 */
function TaskGroup({
  status,
  chunks,
}: {
  status: string;
  chunks: ChunkResponse[];
}): ReactNode {
  return (
    <div className="mb-8">
      {/* Group Header */}
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-xl font-bold text-gray-900 capitalize">{status.replaceAll('-', ' ')}</h2>
        <span className="px-2 py-1 text-xs font-semibold bg-gray-100 text-gray-700 rounded">
          {chunks.length}
        </span>
      </div>

      {/* Task Cards Grid */}
      <div className="grid grid-cols-1 gap-3">
        {chunks.map((chunk) => (
          <TaskCard key={chunk.chunk_hash} chunk={chunk} />
        ))}
      </div>
    </div>
  );
}

/**
 * Task List View Component.
 *
 * Displays tasks grouped by lifecycle status with sortable within-group ordering.
 * Supports filtering by status and priority via URL search parameters.
 */
export function TaskListView({ chunks }: DomainViewProps): ReactNode {
  const navigate = useNavigate({ from: '/browser/view/$domain/$sourceId' });
  const search = useSearch({ from: '/browser/view/$domain/$sourceId' });

  // Extract filter values from URL search params
  const statusFilter = (search as { status?: string }).status;
  const priorityFilter = (search as { priority?: number }).priority;

  // Local state for filter controls (UI-only, not source of truth)
  const [pendingStatus, setPendingStatus] = useState<string>(statusFilter || '');
  const [pendingPriority, setPendingPriority] = useState<string>(priorityFilter?.toString() || '');

  // Sync pending state with URL params on route change (external nav)
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPendingStatus(statusFilter || '');
    setPendingPriority(priorityFilter?.toString() || '');
  }, [statusFilter, priorityFilter]);

  // Apply filters and group/sort tasks using URL params as source of truth
  const groupedTasks = useMemo(() => {
    const parsedPriority = statusFilter || priorityFilter ? (priorityFilter ?? undefined) : undefined;
    return groupAndSortTasks(chunks, statusFilter, parsedPriority);
  }, [chunks, statusFilter, priorityFilter]);

  /**
   * Apply filters by updating URL search params.
   */
  const applyFilters = (): void => {
    void navigate({
      to: '.',
      search: (prev: Record<string, unknown>) => ({
        ...prev,
        status: pendingStatus || undefined,
        priority: pendingPriority ? parseInt(pendingPriority, 10) : undefined,
      }),
    });
  };

  /**
   * Clear all filters.
   */
  const clearFilters = (): void => {
    setPendingStatus('');
    setPendingPriority('');
    void navigate({
      to: '.',
      search: (prev: Record<string, unknown>) => ({
        ...prev,
        status: undefined,
        priority: undefined,
      }),
    });
  };

  // Calculate total task count
  const totalTasks = chunks.filter((chunk) => extractTaskMetadata(chunk) !== null).length;
  const filteredTasks = Array.from(groupedTasks.values()).reduce((sum, group) => sum + group.length, 0);

  return (
    <div className="space-y-6">
      {/* Filter Controls */}
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <div className="flex flex-col gap-4">
          {/* Title */}
          <h3 className="font-semibold text-gray-900">Filters</h3>

          {/* Filter Inputs */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Status Filter */}
            <div>
              <label htmlFor="status-filter" className="block text-sm font-medium text-gray-700 mb-2">
                Status
              </label>
              <select
                id="status-filter"
                value={pendingStatus}
                onChange={(e) => setPendingStatus(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
              >
                <option value="">All statuses</option>
                <option value="open">Open</option>
                <option value="in-progress">In Progress</option>
                <option value="completed">Completed</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </div>

            {/* Priority Filter */}
            <div>
              <label htmlFor="priority-filter" className="block text-sm font-medium text-gray-700 mb-2">
                Priority
              </label>
              <select
                id="priority-filter"
                value={pendingPriority}
                onChange={(e) => setPendingPriority(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
              >
                <option value="">All priorities</option>
                <option value="1">P1 (Highest)</option>
                <option value="2">P2 (High)</option>
                <option value="3">P3 (Medium)</option>
                <option value="4">P4 (Low)</option>
              </select>
            </div>
          </div>

          {/* Filter Actions */}
          <div className="flex gap-2 pt-2">
            <button
              onClick={applyFilters}
              className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 transition-colors"
            >
              Apply Filters
            </button>
            {(statusFilter || priorityFilter) && (
              <button
                onClick={clearFilters}
                className="px-4 py-2 border border-gray-300 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50 transition-colors"
              >
                Clear Filters
              </button>
            )}
          </div>

          {/* Filter Summary */}
          <div className="text-xs text-gray-600 pt-2">
            Showing {filteredTasks} of {totalTasks} task(s)
            {(statusFilter || priorityFilter) && (
              <span className="font-semibold">
                {' '}
                — filtered by {statusFilter && `status: ${statusFilter.replaceAll('-', ' ')}`}
                {statusFilter && priorityFilter && ' and '}
                {priorityFilter && `priority: P${priorityFilter}`}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Empty State */}
      {groupedTasks.size === 0 ? (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-8 text-center">
          <p className="text-sm text-yellow-800">
            {filteredTasks === 0 && totalTasks > 0
              ? 'No tasks match the selected filters.'
              : 'No tasks found for this source.'}
          </p>
        </div>
      ) : (
        /* Task Groups */
        <div>
          {Array.from(groupedTasks.entries()).map(([status, statusChunks]) => (
            <TaskGroup key={status} status={status} chunks={statusChunks} />
          ))}
        </div>
      )}
    </div>
  );
}
