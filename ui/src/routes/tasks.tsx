import { useNavigate, useSearch } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  CheckCircleIcon,
  XMarkIcon,
  CalendarIcon,
  TagIcon,
  UserGroupIcon,
  ClockIcon,
  FlagIcon,
  AdjustmentsHorizontalIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import { fetchChunks } from '../api/client';
import { colors, getDomainColor } from '../lib/designTokens';
import type { ChunkResponse } from '../types/api';

const taskColor = getDomainColor('tasks'); // #F97316

// ── Types ──────────────────────────────────────────────────────────

interface TaskMeta {
  task_id: string;
  // Mirrors TaskMetadata.ALLOWED_STATUSES: 'open' | 'in-progress' | 'completed' | 'cancelled'
  status: string;
  title: string;
  due_date: string | null;
  // 1=Urgent, 2=High, 3=Medium, 4=Low; null if not set
  priority: number | null;
  // Python tuples serialize to JSON arrays via Pydantic model_dump()
  dependencies: string[];
  collaborators: string[];
  date_first_observed: string;
  source_type: string;
}

function extractTaskMeta(chunk: ChunkResponse): TaskMeta | null {
  const dm = chunk.domain_metadata;
  if (!dm) {
    console.warn('[TasksView] chunk missing domain_metadata:', chunk.chunk_hash);
    return null;
  }
  return {
    task_id: typeof dm.task_id === 'string' ? dm.task_id : chunk.chunk_hash,
    status: typeof dm.status === 'string' ? dm.status : 'open',
    title: typeof dm.title === 'string' ? dm.title : 'Untitled Task',
    due_date: typeof dm.due_date === 'string' ? dm.due_date : null,
    priority: typeof dm.priority === 'number' ? dm.priority : null,
    dependencies: Array.isArray(dm.dependencies) ? (dm.dependencies as string[]) : [],
    collaborators: Array.isArray(dm.collaborators) ? (dm.collaborators as string[]) : [],
    date_first_observed: typeof dm.date_first_observed === 'string' ? dm.date_first_observed : '',
    source_type: typeof dm.source_type === 'string' ? dm.source_type : 'unknown',
  };
}

// ── Status helpers ─────────────────────────────────────────────────

type DisplayStatus = 'active' | 'urgent' | 'in-progress' | 'done' | 'cancelled';

function resolveDisplayStatus(meta: TaskMeta): DisplayStatus {
  if (meta.status === 'completed') return 'done';
  if (meta.status === 'cancelled') return 'cancelled';
  if (meta.status === 'in-progress') return 'in-progress';
  // open + priority=1 is the "urgent" display tier
  if (meta.priority === 1) return 'urgent';
  return 'active';
}

const STATUS_CONFIG: Record<DisplayStatus, {
  label: string;
  badgeBg: string;
  badgeText: string;
  dotFill: string | null;
  dotStroke: string;
}> = {
  active:        { label: 'Active',      badgeBg: '#1F2937', badgeText: '#6B7280', dotFill: null,      dotStroke: '#6366F1' },
  urgent:        { label: 'Urgent',      badgeBg: '#2D1B1B', badgeText: '#EF4444', dotFill: null,      dotStroke: '#EF4444' },
  'in-progress': { label: 'In Progress', badgeBg: '#1C1A00', badgeText: '#F59E0B', dotFill: null,      dotStroke: '#F59E0B' },
  done:          { label: 'Done',        badgeBg: '#052E16', badgeText: '#22C55E', dotFill: '#22C55E', dotStroke: '#22C55E' },
  cancelled:     { label: 'Cancelled',   badgeBg: '#1F2937', badgeText: '#4B5563', dotFill: null,      dotStroke: '#4B5563' },
};

const PRIORITY_LABELS: Record<number, string> = { 1: 'Urgent', 2: 'High', 3: 'Medium', 4: 'Low' };

// ── Date helpers ───────────────────────────────────────────────────

function parseIsoDate(iso: string | null): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return isNaN(d.getTime()) ? null : d;
}

function todayMidnight(): Date {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

function endOfWeek(d: Date): Date {
  const sun = new Date(d);
  sun.setDate(sun.getDate() - sun.getDay() + 6);
  sun.setHours(23, 59, 59, 999);
  return sun;
}

type DueDateClass = 'overdue' | 'today' | 'this-week' | 'future' | 'none';

function dueDateClass(dueIso: string | null): DueDateClass {
  if (!dueIso) return 'none';
  const due = parseIsoDate(dueIso);
  if (!due) return 'none';
  const now = todayMidnight();
  due.setHours(0, 0, 0, 0);
  if (due < now) return 'overdue';
  if (due.getTime() === now.getTime()) return 'today';
  if (due <= endOfWeek(now)) return 'this-week';
  return 'future';
}

function dueDateColor(cls: DueDateClass): string {
  if (cls === 'overdue' || cls === 'today') return colors.statusRed;
  if (cls === 'this-week') return colors.statusAmber;
  return colors.textDim;
}

function formatDueLabel(dueIso: string | null, ds: DisplayStatus): string {
  const isDone = ds === 'done' || ds === 'cancelled';
  if (!dueIso) return isDone ? '' : 'No due date';
  const due = parseIsoDate(dueIso);
  if (!due) return isDone ? '' : 'No due date';
  const shortDate = due.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  if (isDone) return `Due ${shortDate}`;
  const cls = dueDateClass(dueIso);
  if (cls === 'overdue') return `Overdue · ${shortDate}`;
  if (cls === 'today') return 'Due today';
  return `Due ${shortDate}`;
}

function formatFullDate(iso: string | null): string {
  if (!iso) return '—';
  const d = parseIsoDate(iso);
  if (!d) return '—';
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'long', day: 'numeric', year: 'numeric' });
}

// ── Source label ───────────────────────────────────────────────────

function sourceLabel(sourceType: string): string {
  const map: Record<string, string> = {
    apple_reminders: 'Reminders',
    caldav: 'CalDAV Tasks',
    caldav_tasks: 'CalDAV Tasks',
    obsidian_tasks: 'Obsidian Tasks',
    obsidian: 'Obsidian Tasks',
  };
  return (
    map[sourceType.toLowerCase()] ??
    sourceType.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  );
}

// ── Sort tasks ─────────────────────────────────────────────────────

function sortTasks(tasks: Array<{ chunk: ChunkResponse; meta: TaskMeta }>): typeof tasks {
  return [...tasks].sort((a, b) => {
    const dsA = resolveDisplayStatus(a.meta);
    const dsB = resolveDisplayStatus(b.meta);

    // Done/cancelled always last
    const isInactiveA = dsA === 'done' || dsA === 'cancelled';
    const isInactiveB = dsB === 'done' || dsB === 'cancelled';
    if (isInactiveA !== isInactiveB) return isInactiveA ? 1 : -1;

    // Overdue/today before future
    const clsA = dueDateClass(a.meta.due_date);
    const clsB = dueDateClass(b.meta.due_date);
    const overdueA = clsA === 'overdue' || clsA === 'today';
    const overdueB = clsB === 'overdue' || clsB === 'today';
    if (overdueA !== overdueB) return overdueA ? -1 : 1;

    // Urgent before other active statuses
    if (dsA === 'urgent' && dsB !== 'urgent') return -1;
    if (dsB === 'urgent' && dsA !== 'urgent') return 1;

    // By due date ascending; no due date sorts to end
    if (a.meta.due_date && b.meta.due_date) return a.meta.due_date.localeCompare(b.meta.due_date);
    if (a.meta.due_date) return -1;
    if (b.meta.due_date) return 1;
    return 0;
  });
}

// ── Filter tab ─────────────────────────────────────────────────────

// "active" covers open+in-progress statuses regardless of priority.
// Urgency (priority=1) is surfaced via badge within the active tab, not a separate filter.
type FilterTab = 'all' | 'active' | 'completed';

function matchesTab(meta: TaskMeta, tab: FilterTab): boolean {
  if (tab === 'all') return true;
  if (tab === 'active') return meta.status === 'open' || meta.status === 'in-progress';
  return meta.status === 'completed' || meta.status === 'cancelled';
}

// ── Task row ───────────────────────────────────────────────────────

function TaskRow({
  chunk,
  meta,
  isSelected,
  onClick,
}: {
  chunk: ChunkResponse;
  meta: TaskMeta;
  isSelected: boolean;
  onClick: () => void;
}): ReactNode {
  const ds = resolveDisplayStatus(meta);
  const cfg = STATUS_CONFIG[ds];
  const isDone = ds === 'done' || ds === 'cancelled';
  const dueLabel = formatDueLabel(meta.due_date, ds);
  const dueCls = isDone ? 'none' as DueDateClass : dueDateClass(meta.due_date);
  const dueColor = isDone ? colors.textDim : dueDateColor(dueCls);

  return (
    <button
      onClick={onClick}
      title={meta.title}
      className="flex items-center gap-3 w-full text-left transition-colors"
      style={{
        height: 48,
        padding: '0 14px',
        borderRadius: 6,
        flexShrink: 0,
        background: isSelected ? `${taskColor}12` : '#161616',
        border: `1px solid ${isSelected ? taskColor + '40' : colors.border}`,
      }}
    >
      {/* Status dot */}
      <div
        style={{
          width: 18,
          height: 18,
          borderRadius: '50%',
          flexShrink: 0,
          background: cfg.dotFill ?? 'transparent',
          border: `2px solid ${cfg.dotStroke}`,
        }}
      />

      {/* Info */}
      <div className="flex flex-col gap-0.5 flex-1 min-w-0">
        <span
          className="truncate"
          style={{ fontSize: 13, fontWeight: 500, color: isDone ? colors.textDim : '#E5E7EB' }}
        >
          {meta.title}
        </span>
        <div className="flex items-center gap-1.5 min-w-0">
          {dueLabel && (
            <span className="shrink-0" style={{ fontSize: 11, color: dueColor }}>{dueLabel}</span>
          )}
          <span className="truncate" style={{ fontSize: 11, color: '#4B5563' }}>
            {dueLabel ? '· ' : ''}{sourceLabel(meta.source_type)}
          </span>
        </div>
      </div>

      {/* Status badge */}
      <div style={{ borderRadius: 10, padding: '2px 8px', background: cfg.badgeBg, flexShrink: 0 }}>
        <span style={{ fontSize: 10, color: cfg.badgeText }}>{cfg.label}</span>
      </div>
    </button>
  );
}

// ── Detail panel ───────────────────────────────────────────────────

function DetailPanel({
  chunk,
  meta,
  onClose,
}: {
  chunk: ChunkResponse;
  meta: TaskMeta;
  onClose: () => void;
}): ReactNode {
  const ds = resolveDisplayStatus(meta);
  const cfg = STATUS_CONFIG[ds];
  const isDone = ds === 'done' || ds === 'cancelled';
  const dueCls = isDone ? 'none' as DueDateClass : dueDateClass(meta.due_date);
  const dueColor = isDone ? colors.textDim : dueDateColor(dueCls);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div
        className="flex items-start gap-3 px-4 py-3 shrink-0"
        style={{ borderBottom: `1px solid ${colors.border}` }}
      >
        <div
          style={{
            width: 18,
            height: 18,
            borderRadius: '50%',
            flexShrink: 0,
            marginTop: 3,
            background: cfg.dotFill ?? 'transparent',
            border: `2px solid ${cfg.dotStroke}`,
          }}
        />
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold leading-snug" style={{ color: colors.textPrimary }}>
            {meta.title}
          </h3>
          <div
            className="mt-1 inline-flex"
            style={{ borderRadius: 10, padding: '2px 8px', background: cfg.badgeBg }}
          >
            <span style={{ fontSize: 10, color: cfg.badgeText }}>{cfg.label}</span>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-0.5 rounded transition-opacity hover:opacity-75 shrink-0"
          style={{ color: colors.textDim }}
          aria-label="Close detail panel"
        >
          <XMarkIcon className="w-4 h-4" />
        </button>
      </div>

      {/* Metadata */}
      <div
        className="px-4 py-3 flex flex-col gap-2.5 shrink-0"
        style={{ borderBottom: `1px solid ${colors.border}` }}
      >
        {/* Due date */}
        <div className="flex items-center gap-2">
          <CalendarIcon className="w-3.5 h-3.5 shrink-0" style={{ color: colors.textDim }} />
          <span style={{ fontSize: 12, color: meta.due_date ? dueColor : colors.textDim }}>
            {meta.due_date ? formatFullDate(meta.due_date) : 'No due date'}
          </span>
        </div>

        {/* Priority */}
        {meta.priority != null && (
          <div className="flex items-center gap-2">
            <FlagIcon className="w-3.5 h-3.5 shrink-0" style={{ color: colors.textDim }} />
            <span style={{ fontSize: 12, color: colors.textMuted }}>
              {PRIORITY_LABELS[meta.priority] ?? `Priority ${meta.priority}`}
            </span>
          </div>
        )}

        {/* Source */}
        <div className="flex items-center gap-2">
          <TagIcon className="w-3.5 h-3.5 shrink-0" style={{ color: colors.textDim }} />
          <span style={{ fontSize: 12, color: colors.textMuted }}>{sourceLabel(meta.source_type)}</span>
        </div>

        {/* Collaborators */}
        {meta.collaborators.length > 0 && (
          <div className="flex items-start gap-2">
            <UserGroupIcon className="w-3.5 h-3.5 shrink-0 mt-0.5" style={{ color: colors.textDim }} />
            <span style={{ fontSize: 12, color: colors.textMuted }}>
              {meta.collaborators.join(', ')}
            </span>
          </div>
        )}

        {/* Created */}
        {meta.date_first_observed && (
          <div className="flex items-center gap-2">
            <ClockIcon className="w-3.5 h-3.5 shrink-0" style={{ color: colors.textDim }} />
            <span style={{ fontSize: 12, color: colors.textDim }}>
              Created {formatFullDate(meta.date_first_observed)}
            </span>
          </div>
        )}
      </div>

      {/* Notes / content */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {chunk.content ? (
          <pre
            className="whitespace-pre-wrap font-sans"
            style={{ fontSize: 13, color: colors.textMuted, lineHeight: '1.6' }}
          >
            {chunk.content}
          </pre>
        ) : (
          <p style={{ fontSize: 13, color: colors.textDim }}>No notes.</p>
        )}
      </div>
    </div>
  );
}

// ── Empty state ────────────────────────────────────────────────────

function EmptyState({ filtered }: { filtered: boolean }): ReactNode {
  return (
    <div className="flex flex-col items-center justify-center flex-1 gap-4">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 64, height: 64, background: `${taskColor}20` }}
      >
        <CheckCircleIcon className="w-8 h-8" style={{ color: taskColor }} />
      </div>
      <div className="text-center">
        <p className="text-sm font-medium mb-1" style={{ color: colors.textMuted }}>
          {filtered ? 'No matching tasks' : 'No tasks found'}
        </p>
        <p style={{ fontSize: 12, color: colors.textDim }}>
          {filtered
            ? 'Try a different filter or source.'
            : 'Connect Apple Reminders or a CalDAV source to see tasks here.'}
        </p>
      </div>
    </div>
  );
}

// ── Error state ────────────────────────────────────────────────────

function ErrorState(): ReactNode {
  return (
    <div className="flex flex-col items-center justify-center flex-1 gap-4">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 64, height: 64, background: `${colors.statusRed}20` }}
      >
        <ExclamationTriangleIcon className="w-8 h-8" style={{ color: colors.statusRed }} />
      </div>
      <div className="text-center">
        <p className="text-sm font-medium mb-1" style={{ color: colors.textMuted }}>
          Failed to load tasks
        </p>
        <p style={{ fontSize: 12, color: colors.textDim }}>
          Check that the context-library server is running.
        </p>
      </div>
    </div>
  );
}

// ── TasksPage ──────────────────────────────────────────────────────

export default function TasksPage(): ReactNode {
  const navigate = useNavigate();
  const search = useSearch({ from: '/tasks' });

  // filterTab and selectedHash are URL-persisted for deep-linking and back-nav consistency
  const filterTab: FilterTab = (['all', 'active', 'completed'].includes(search.status ?? '')
    ? (search.status as FilterTab)
    : 'all');
  const selectedHash = search.selectedHash ?? null;

  // Source filter is local state — source types are data-driven and not meaningful as share URLs
  const [sourceFilter, setSourceFilter] = useState<string>('all');
  const [showSourceMenu, setShowSourceMenu] = useState(false);

  function setFilterTab(tab: FilterTab): void {
    void navigate({
      to: '/tasks',
      search: (prev: Record<string, unknown>) => ({
        ...prev,
        status: tab === 'all' ? undefined : tab,
        selectedHash: undefined,
      }),
    });
  }

  function toggleSelectedHash(hash: string): void {
    void navigate({
      to: '/tasks',
      search: (prev: Record<string, unknown>) => ({
        ...prev,
        selectedHash: hash === selectedHash ? undefined : hash,
      }),
    });
  }

  function clearSelectedHash(): void {
    void navigate({
      to: '/tasks',
      search: (prev: Record<string, unknown>) => ({ ...prev, selectedHash: undefined }),
    });
  }

  const { data, isLoading, isError } = useQuery({
    queryKey: ['chunks', { domain: 'tasks', limit: 2000 }],
    queryFn: () => fetchChunks({ domain: 'tasks', limit: 2000 }),
    staleTime: 30_000,
  });

  const allChunks = data?.chunks ?? [];

  const allTasks = useMemo(() => {
    const result: Array<{ chunk: ChunkResponse; meta: TaskMeta }> = [];
    for (const chunk of allChunks) {
      const meta = extractTaskMeta(chunk);
      if (meta) result.push({ chunk, meta });
    }
    return result;
  }, [allChunks]);

  const sourcesAvailable = useMemo(() => {
    const set = new Set<string>();
    for (const { meta } of allTasks) set.add(meta.source_type);
    return Array.from(set).sort();
  }, [allTasks]);

  const visibleTasks = useMemo(() => {
    let tasks = allTasks.filter(({ meta }) => matchesTab(meta, filterTab));
    if (sourceFilter !== 'all') {
      tasks = tasks.filter(({ meta }) => meta.source_type === sourceFilter);
    }
    return sortTasks(tasks);
  }, [allTasks, filterTab, sourceFilter]);

  const selectedItem = useMemo(
    () => (selectedHash ? (visibleTasks.find(t => t.chunk.chunk_hash === selectedHash) ?? null) : null),
    [visibleTasks, selectedHash],
  );

  const countAll = allTasks.length;
  const countActive = useMemo(() => allTasks.filter(t => matchesTab(t.meta, 'active')).length, [allTasks]);
  const countCompleted = useMemo(() => allTasks.filter(t => matchesTab(t.meta, 'completed')).length, [allTasks]);

  const isFiltered = filterTab !== 'all' || sourceFilter !== 'all';

  const tabs: Array<{ key: FilterTab; label: string }> = [
    { key: 'all',       label: 'All' },
    { key: 'active',    label: 'Active' },
    { key: 'completed', label: 'Completed' },
  ];

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: colors.bgBase }}>

      {/* ── Top bar ── */}
      <div
        className="flex items-center gap-3 px-5 shrink-0"
        style={{ height: 52, borderBottom: `1px solid #1A1A1A`, background: '#111111' }}
      >
        <span className="flex-1" style={{ fontSize: 16, fontWeight: 600, color: '#FFFFFF' }}>
          Tasks
        </span>

        {!isLoading && !isError && (
          <div style={{ borderRadius: 10, padding: '3px 10px', background: '#1F2937' }}>
            <span style={{ fontSize: 11, color: '#6B7280' }}>
              {countAll.toLocaleString()} task{countAll !== 1 ? 's' : ''}
            </span>
          </div>
        )}

        {/* View toggle — List active; Kanban is future work */}
        <div
          className="flex items-center"
          style={{ height: 32, borderRadius: 6, background: '#1A1A1A', border: '1px solid #2D2D2D', padding: 2 }}
        >
          <div style={{ borderRadius: 5, background: '#312E81', padding: '6px 14px' }}>
            <span style={{ fontSize: 12, color: '#A5B4FC' }}>List</span>
          </div>
          <div style={{ padding: '6px 14px' }}>
            <span style={{ fontSize: 12, color: '#6B7280' }}>Kanban</span>
          </div>
        </div>
      </div>

      {/* ── Filter row ── */}
      <div
        className="flex items-center gap-2 px-5 shrink-0"
        style={{ height: 40, borderBottom: `1px solid #1A1A1A`, background: '#0D0D0D' }}
      >
        {tabs.map(tab => {
          const isActive = filterTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setFilterTab(tab.key)}
              style={{
                borderRadius: 4,
                padding: '4px 10px',
                background: isActive ? '#312E81' : 'transparent',
                fontSize: 12,
                color: isActive ? '#A5B4FC' : '#6B7280',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              {tab.label}
            </button>
          );
        })}

        <div className="flex-1" />

        {/* Source filter dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowSourceMenu(v => !v)}
            className="flex items-center gap-1.5"
            style={{
              borderRadius: 4,
              padding: '4px 10px',
              background: sourceFilter !== 'all' ? `${taskColor}22` : colors.bgElevated,
              fontSize: 12,
              color: sourceFilter !== 'all' ? taskColor : colors.textMuted,
              border: 'none',
              cursor: 'pointer',
            }}
          >
            <AdjustmentsHorizontalIcon className="w-3 h-3" />
            {sourceFilter === 'all' ? 'All Sources' : sourceLabel(sourceFilter)}
          </button>

          {showSourceMenu && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setShowSourceMenu(false)} />
              <div
                className="absolute right-0 top-full mt-1 z-20 py-1"
                style={{
                  minWidth: 160,
                  borderRadius: 6,
                  background: colors.bgElevated,
                  border: `1px solid ${colors.border}`,
                  boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
                }}
              >
                {[
                  { value: 'all', label: 'All Sources' },
                  ...sourcesAvailable.map(s => ({ value: s, label: sourceLabel(s) })),
                ].map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => {
                      setSourceFilter(opt.value);
                      setShowSourceMenu(false);
                      clearSelectedHash();
                    }}
                    className="w-full text-left px-3 py-1.5"
                    style={{
                      fontSize: 12,
                      color: sourceFilter === opt.value ? taskColor : colors.textMuted,
                      background: sourceFilter === opt.value ? `${taskColor}18` : 'transparent',
                    }}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* ── Body ── */}
      {isLoading ? (
        <div className="flex flex-1 items-center justify-center">
          <div
            className="w-6 h-6 rounded-full border-2 animate-spin"
            style={{ borderColor: `${taskColor} transparent transparent transparent` }}
          />
        </div>
      ) : isError ? (
        <ErrorState />
      ) : visibleTasks.length === 0 ? (
        <EmptyState filtered={isFiltered} />
      ) : (
        <div className="flex flex-1 overflow-hidden">
          {/* Task list */}
          <div className="flex-1 flex flex-col overflow-y-auto gap-1.5 p-3">
            {visibleTasks.map(({ chunk, meta }) => (
              <TaskRow
                key={chunk.chunk_hash}
                chunk={chunk}
                meta={meta}
                isSelected={chunk.chunk_hash === selectedHash}
                onClick={() => toggleSelectedHash(chunk.chunk_hash)}
              />
            ))}
          </div>

          {/* Detail panel */}
          {selectedItem && (
            <div
              className="w-80 shrink-0 flex flex-col overflow-hidden"
              style={{ borderLeft: `1px solid ${colors.border}`, background: colors.bgSurface }}
            >
              <DetailPanel
                chunk={selectedItem.chunk}
                meta={selectedItem.meta}
                onClose={clearSelectedHash}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
