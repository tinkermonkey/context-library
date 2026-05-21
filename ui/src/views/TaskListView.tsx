import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { StatusBadge } from '@tinkermonkey/heimdall-ui';
import type { ChunkResponse, TaskMetadata } from '../types/api';
import { extractTaskMetadata } from '../types/api';
import type { DomainViewProps } from './registryConfig';
import { tasksViewSearchSchema } from '../routes-config';
import { Timestamp } from '../components/shared/Timestamp';

/**
 * Map task status to Heimdall StatusBadge color.
 */
function statusToColor(status: string): 'emerald' | 'amber' | 'rose' | 'cyan' | 'violet' | 'neutral' {
  switch (status.toLowerCase()) {
    case 'completed':
      return 'emerald';
    case 'in-progress':
    case 'in_progress':
      return 'cyan';
    case 'open':
      return 'amber';
    case 'cancelled':
      return 'rose';
    default:
      return 'neutral';
  }
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
 * Get priority color based on priority level.
 * P1 uses --status-error, P3 uses --status-amber. P2 uses orange-500 (no direct token available).
 */
function getPriorityColor(priority: number | null): string {
  if (priority === null) return 'rgb(var(--canvas-fg-3))';
  if (priority === 1) return 'rgb(var(--status-error))';
  if (priority === 2) return 'rgb(249, 115, 22)';
  if (priority === 3) return 'rgb(var(--status-amber))';
  return 'rgb(var(--canvas-fg-2))';
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
    <div className="rounded-lg p-4 hover:shadow-md transition-shadow" style={{ border: `1px solid rgb(var(--canvas-border))`, background: 'rgb(var(--canvas-surface))' }}>
      {/* Title and Status Badge */}
      <div className="flex items-start justify-between mb-3 gap-2">
        <h3 className="text-base font-semibold flex-1" style={{ color: 'rgb(var(--canvas-fg-1))' }}>{metadata.title}</h3>
        <StatusBadge color={statusToColor(metadata.status)}>{metadata.status}</StatusBadge>
      </div>

      {/* Task Details Grid */}
      <div className="grid grid-cols-2 gap-3 text-sm">
        {/* Due Date */}
        <div>
          <span className="font-semibold" style={{ color: 'rgb(var(--canvas-fg-2))' }}>Due:</span>
          <div className="mt-1">
            {metadata.due_date ? (
              <Timestamp value={metadata.due_date} granularity="date" />
            ) : (
              <span style={{ color: 'rgb(var(--canvas-fg-3))' }}>—</span>
            )}
          </div>
        </div>

        {/* Priority */}
        <div>
          <span className="font-semibold" style={{ color: 'rgb(var(--canvas-fg-2))' }}>Priority:</span>
          <div className="mt-1 font-mono text-sm" style={{ color: getPriorityColor(metadata.priority) }}>
            {formatPriority(metadata.priority)}
          </div>
        </div>

        {/* Dependencies */}
        <div>
          <span className="font-semibold" style={{ color: 'rgb(var(--canvas-fg-2))' }}>Dependencies:</span>
          <div className="mt-1">
            {metadata.dependencies.length === 0 ? (
              <span style={{ color: 'rgb(var(--canvas-fg-3))' }}>—</span>
            ) : (
              <span style={{ color: 'rgb(var(--canvas-fg-2))' }}>{metadata.dependencies.length} task(s)</span>
            )}
          </div>
        </div>

        {/* Collaborators */}
        <div>
          <span className="font-semibold" style={{ color: 'rgb(var(--canvas-fg-2))' }}>Collaborators:</span>
          <div className="mt-1">
            {metadata.collaborators.length === 0 ? (
              <span style={{ color: 'rgb(var(--canvas-fg-3))' }}>—</span>
            ) : (
              <span style={{ color: 'rgb(var(--canvas-fg-2))' }}>{metadata.collaborators.length} person(s)</span>
            )}
          </div>
        </div>
      </div>

      {/* Task ID */}
      <div className="mt-3 pt-3" style={{ borderTop: `1px solid rgb(var(--canvas-border))` }}>
        <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>ID: {metadata.task_id}</span>
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
        <h2 className="text-xl font-bold capitalize" style={{ color: 'rgb(var(--canvas-fg-1))' }}>{status.replaceAll('-', ' ')}</h2>
        <span className="px-2 py-1 text-xs font-semibold rounded" style={{ background: 'rgb(var(--canvas-surface))', color: 'rgb(var(--canvas-fg-2))', border: `1px solid rgb(var(--canvas-border))` }}>
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
  const rawSearch = useSearch({ from: '/browser/view/$domain/$sourceId' });
  const search = tasksViewSearchSchema.parse(rawSearch);

  // Extract filter values from URL search params
  const statusFilter = search.status;
  const priorityFilter = search.priority;

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
      <div className="rounded-lg p-4" style={{ border: `1px solid rgb(var(--canvas-border))`, background: 'rgb(var(--canvas-surface))' }}>
        <div className="flex flex-col gap-4">
          {/* Title */}
          <h3 className="font-semibold" style={{ color: 'rgb(var(--canvas-fg-1))' }}>Filters</h3>

          {/* Filter Inputs */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Status Filter */}
            <div>
              <label htmlFor="status-filter" className="block text-sm font-medium mb-2" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
                Status
              </label>
              <select
                id="status-filter"
                value={pendingStatus}
                onChange={(e) => setPendingStatus(e.target.value)}
                className="w-full px-3 py-2 rounded-md shadow-sm focus:outline-none text-sm"
                style={{ border: `1px solid rgb(var(--canvas-border))`, background: 'rgb(var(--canvas-bg))', color: 'rgb(var(--canvas-fg-1))' }}
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
              <label htmlFor="priority-filter" className="block text-sm font-medium mb-2" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
                Priority
              </label>
              <select
                id="priority-filter"
                value={pendingPriority}
                onChange={(e) => setPendingPriority(e.target.value)}
                className="w-full px-3 py-2 rounded-md shadow-sm focus:outline-none text-sm"
                style={{ border: `1px solid rgb(var(--canvas-border))`, background: 'rgb(var(--canvas-bg))', color: 'rgb(var(--canvas-fg-1))' }}
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
              className="px-4 py-2 text-white text-sm font-medium rounded-md hover:opacity-90 transition-colors"
              style={{ background: 'rgb(var(--accent-primary))' }}
            >
              Apply Filters
            </button>
            {(statusFilter || priorityFilter) && (
              <button
                onClick={clearFilters}
                className="px-4 py-2 text-sm font-medium rounded-md hover:opacity-90 transition-colors"
                style={{ border: `1px solid rgb(var(--canvas-border))`, color: 'rgb(var(--canvas-fg-2))', background: 'transparent' }}
              >
                Clear Filters
              </button>
            )}
          </div>

          {/* Filter Summary */}
          <div className="text-xs pt-2" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
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
        <div className="rounded-lg p-8 text-center" style={{ background: `rgb(var(--status-amber) / 0.13)`, border: `1px solid rgb(var(--status-amber) / 0.3)` }}>
          <p className="text-sm" style={{ color: 'rgb(var(--status-amber))' }}>
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
