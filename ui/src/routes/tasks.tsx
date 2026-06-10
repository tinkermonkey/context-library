import { useNavigate, useSearch } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useCallback } from 'react';
import type { ReactNode } from 'react';
import { fetchChunks } from '../api/client';
import { Icon, PageHeader, KanbanBoard, VersionTimeline, VersionPill } from '@tinkermonkey/heimdall-ui';
import type { KanbanCard, KanbanColumn, VersionEntry } from '@tinkermonkey/heimdall-ui';
import { FilterDropdown } from '../components/FilterDropdown';
import { useVersionHistory } from '../hooks/useSources';
import { getDomainColor, getDomainColorWithAlpha } from '../lib/designTokens';
import type { ChunkResponse, TaskMetadata } from '../types/api';
import { extractTaskMetadata } from '../types/api';

const taskColor = getDomainColor('tasks');

// ── Types ──────────────────────────────────────────────────────────

type TaskMeta = TaskMetadata;

// ── Status helpers ─────────────────────────────────────────────────

type DisplayStatus = 'active' | 'urgent' | 'in-progress' | 'done' | 'cancelled';

function resolveDisplayStatus(meta: TaskMeta): DisplayStatus {
  if (meta.status === 'completed') return 'done';
  if (meta.status === 'cancelled') return 'cancelled';
  if (meta.status === 'in-progress') return 'in-progress';
  if (meta.priority === 1) return 'urgent';
  return 'active';
}

// ── Kanban column assignment ───────────────────────────────────────

const KANBAN_COLUMNS: KanbanColumn[] = [
  { id: 'open',        title: 'Open',        statusColor: 'cyan' },
  { id: 'in-progress', title: 'In Progress',  statusColor: 'amber' },
  { id: 'blocked',     title: 'Blocked',      statusColor: 'rose' },
  { id: 'done',        title: 'Done',         statusColor: 'emerald' },
];

function taskColumnId(meta: TaskMeta): string {
  if (meta.status === 'completed' || meta.status === 'cancelled') return 'done';
  if (meta.status === 'in-progress') return 'in-progress';
  if (meta.dependencies.length > 0) return 'blocked';
  return 'open';
}

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
  if (cls === 'overdue' || cls === 'today') return 'rgb(var(--status-error))';
  if (cls === 'this-week') return 'rgb(var(--status-amber))';
  return 'rgb(var(--canvas-fg-3))';
}

function formatDueLabel(dueIso: string | null): string {
  if (!dueIso) return '';
  const due = parseIsoDate(dueIso);
  if (!due) return '';
  const shortDate = due.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
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
    apple_reminders:  'Reminders',
    caldav:           'CalDAV Tasks',
    caldav_tasks:     'CalDAV Tasks',
    obsidian_tasks:   'Obsidian Tasks',
    obsidian:         'Obsidian Tasks',
  };
  return (
    map[sourceType.toLowerCase()] ??
    sourceType.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  );
}

// ── KanbanCard builder ─────────────────────────────────────────────

function toKanbanCard(chunk: ChunkResponse, meta: TaskMeta): KanbanCard {
  return {
    id:       chunk.chunk_hash,
    columnId: taskColumnId(meta),
    title:    meta.title,
    context:  chunk.context_header ?? undefined,
    version:  `v${chunk.lineage.source_version_id}`,
    dueDate:  meta.due_date ?? undefined,
    badges:   [sourceLabel(meta.source_type)],
    blocked:  meta.dependencies.length > 0 ? meta.dependencies.join(', ') : undefined,
    done:     meta.status === 'completed' || meta.status === 'cancelled',
  };
}

// ── Custom task card renderer ──────────────────────────────────────

function TaskCard({
  chunk,
  meta,
  isSelected,
}: {
  chunk: ChunkResponse;
  meta: TaskMeta;
  isSelected: boolean;
}): ReactNode {
  const ds = resolveDisplayStatus(meta);
  const isDone = ds === 'done' || ds === 'cancelled';
  const dueLabel = formatDueLabel(meta.due_date);
  const dueCls = isDone ? 'none' as DueDateClass : dueDateClass(meta.due_date);
  const dueColor = isDone ? 'rgb(var(--canvas-fg-3))' : dueDateColor(dueCls);
  const isBlocked = meta.dependencies.length > 0 && meta.status !== 'completed' && meta.status !== 'cancelled';
  const notesExcerpt = chunk.content.slice(0, 120).replace(/\n/g, ' ');

  return (
    <div
      style={{
        padding: '10px 12px',
        borderRadius: 6,
        background: isSelected ? getDomainColorWithAlpha('tasks', '12') : 'rgb(var(--canvas-bg))',
        border: `1px solid ${isSelected ? getDomainColorWithAlpha('tasks', '40') : 'rgb(var(--canvas-border))'}`,
        cursor: 'pointer',
        userSelect: 'none',
      }}
    >
      {/* Top row: checkbox + context label + version pill */}
      <div className="flex items-center gap-1.5 mb-1.5">
        <div
          style={{
            width: 14,
            height: 14,
            borderRadius: '50%',
            flexShrink: 0,
            background: isDone ? 'rgb(var(--status-ok))' : 'transparent',
            border: `2px solid ${isDone ? 'rgb(var(--status-ok))' : 'rgb(var(--canvas-fg-3))'}`,
          }}
        />
        {chunk.context_header && (
          <span className="truncate flex-1" style={{ fontSize: 10, color: 'rgb(var(--canvas-fg-3))' }}>
            {chunk.context_header}
          </span>
        )}
        <VersionPill style={{ fontSize: 9, flexShrink: 0 }}>
          v{chunk.lineage.source_version_id}
        </VersionPill>
      </div>

      {/* Title */}
      <div
        className="leading-snug mb-1"
        style={{
          fontSize: 13,
          fontWeight: 500,
          color: isDone ? 'rgb(var(--canvas-fg-3))' : 'rgb(var(--canvas-fg-1))',
          textDecoration: isDone ? 'line-through' : 'none',
        }}
      >
        {meta.title}
      </div>

      {/* Notes excerpt */}
      {notesExcerpt && (
        <div
          className="mb-1.5 line-clamp-2"
          style={{ fontSize: 11, color: 'rgb(var(--canvas-fg-3))', lineHeight: 1.4 }}
        >
          {notesExcerpt}
          {chunk.content.length > 120 ? '…' : ''}
        </div>
      )}

      {/* Bottom row: blocked indicator + due date + source adapter */}
      <div className="flex items-center gap-1.5 flex-wrap">
        {isBlocked && (
          <span
            className="flex items-center gap-0.5"
            style={{ fontSize: 10, color: 'rgb(var(--status-error))' }}
          >
            <Icon name="lock" size={10} />
            Blocked
          </span>
        )}
        {dueLabel && (
          <span style={{ fontSize: 10, color: dueColor }}>{dueLabel}</span>
        )}
        <span
          className="ml-auto"
          style={{
            fontSize: 10,
            color: 'rgb(var(--canvas-fg-3))',
            background: 'rgb(var(--canvas-surface))',
            borderRadius: 4,
            padding: '1px 5px',
          }}
        >
          {sourceLabel(meta.source_type)}
        </span>
      </div>
    </div>
  );
}

// ── Task detail pane with VersionTimeline ──────────────────────────

function TaskDetailPane({
  chunk,
  meta,
  onClose,
}: {
  chunk: ChunkResponse;
  meta: TaskMeta;
  onClose: () => void;
}): ReactNode {
  const sourceId = chunk.lineage.source_id;
  const historyQuery = useVersionHistory(sourceId);
  const ds = resolveDisplayStatus(meta);
  const isDone = ds === 'done' || ds === 'cancelled';

  const timelineEntries: VersionEntry[] = useMemo(() => {
    const entries: VersionEntry[] = [];

    if (meta.date_first_observed) {
      entries.push({
        id:        'created',
        label:     'First observed',
        headline:  meta.title,
        timestamp: meta.date_first_observed,
        transition: { from: '', to: 'open' },
      });
    }

    for (const v of historyQuery.data?.versions ?? []) {
      const isCurrent = v.version === chunk.lineage.source_version_id;
      entries.push({
        id:        String(v.version),
        label:     `v${v.version}`,
        timestamp: v.fetch_timestamp,
        head:      isCurrent,
        stats: {
          added:   v.added_chunks,
          removed: v.removed_chunks,
          kept:    v.unchanged_chunks,
        },
        ...(isCurrent ? { transition: { from: 'open', to: meta.status } } : {}),
      });
    }

    return entries;
  }, [meta, historyQuery.data, chunk.lineage.source_version_id]);

  const dueCls = isDone ? 'none' as DueDateClass : dueDateClass(meta.due_date);
  const dueColor = isDone ? 'rgb(var(--canvas-fg-3))' : dueDateColor(dueCls);

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-surface))' }}>
      {/* Header */}
      <div
        className="flex items-start gap-3 px-4 py-3 shrink-0"
        style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}
      >
        <div
          style={{
            width: 16,
            height: 16,
            borderRadius: '50%',
            flexShrink: 0,
            marginTop: 3,
            background: isDone ? 'rgb(var(--status-ok))' : 'transparent',
            border: `2px solid ${isDone ? 'rgb(var(--status-ok))' : taskColor}`,
          }}
        />
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold leading-snug" style={{ color: 'rgb(var(--canvas-fg-1))' }}>
            {meta.title}
          </h3>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <VersionPill>v{chunk.lineage.source_version_id}</VersionPill>
            <span
              style={{
                fontSize: 10,
                borderRadius: 8,
                padding: '2px 7px',
                background: isDone ? 'rgb(var(--status-ok) / 0.13)' : getDomainColorWithAlpha('tasks', '18'),
                color: isDone ? 'rgb(var(--status-ok))' : taskColor,
              }}
            >
              {ds.charAt(0).toUpperCase() + ds.slice(1)}
            </span>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-0.5 rounded transition-opacity hover:opacity-75 shrink-0"
          style={{ color: 'rgb(var(--canvas-fg-3))' }}
          aria-label="Close detail panel"
        >
          <Icon name="x" size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Metadata */}
        <div
          className="px-4 py-3 flex flex-col gap-2 shrink-0"
          style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}
        >
          <div className="flex items-center gap-2">
            <Icon name="calendar" size={13} style={{ color: 'rgb(var(--canvas-fg-3))' }} />
            <span style={{ fontSize: 12, color: meta.due_date ? dueColor : 'rgb(var(--canvas-fg-3))' }}>
              {meta.due_date ? formatFullDate(meta.due_date) : 'No due date'}
            </span>
          </div>
          {meta.priority != null && (
            <div className="flex items-center gap-2">
              <Icon name="alert" size={13} style={{ color: 'rgb(var(--canvas-fg-3))' }} />
              <span style={{ fontSize: 12, color: 'rgb(var(--canvas-fg-2))' }}>
                Priority {meta.priority}
              </span>
            </div>
          )}
          <div className="flex items-center gap-2">
            <Icon name="filter" size={13} style={{ color: 'rgb(var(--canvas-fg-3))' }} />
            <span style={{ fontSize: 12, color: 'rgb(var(--canvas-fg-2))' }}>{sourceLabel(meta.source_type)}</span>
          </div>
          {meta.dependencies.length > 0 && (
            <div className="flex items-start gap-2">
              <Icon name="lock" size={13} style={{ color: 'rgb(var(--status-error))', marginTop: 1 }} />
              <span style={{ fontSize: 12, color: 'rgb(var(--canvas-fg-2))' }}>
                Blocked by: {meta.dependencies.join(', ')}
              </span>
            </div>
          )}
        </div>

        {/* Notes content */}
        {chunk.content && (
          <div className="px-4 py-3" style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}>
            <div
              className="text-xs font-medium uppercase tracking-wider mb-2"
              style={{ color: 'rgb(var(--canvas-fg-3))' }}
            >
              Notes
            </div>
            <pre
              className="whitespace-pre-wrap font-sans"
              style={{ fontSize: 12, color: 'rgb(var(--canvas-fg-2))', lineHeight: '1.6' }}
            >
              {chunk.content}
            </pre>
          </div>
        )}

        {/* Version timeline */}
        <div className="px-4 py-3">
          <div
            className="text-xs font-medium uppercase tracking-wider mb-2"
            style={{ color: 'rgb(var(--canvas-fg-3))' }}
          >
            State Transitions
          </div>
          <VersionTimeline
            entries={timelineEntries}
            order="newest-first"
            emptyState="No history available"
          />
        </div>
      </div>
    </div>
  );
}

// ── Filter helpers ─────────────────────────────────────────────────

type DueDateFilter = 'all' | 'overdue' | 'today' | 'this-week';

function matchesDueDateFilter(meta: TaskMeta, filter: DueDateFilter): boolean {
  if (filter === 'all') return true;
  const cls = dueDateClass(meta.due_date);
  if (filter === 'overdue') return cls === 'overdue';
  if (filter === 'today') return cls === 'today';
  if (filter === 'this-week') return cls === 'this-week' || cls === 'today';
  return true;
}

// ── Empty state ────────────────────────────────────────────────────

function EmptyState({ filtered }: { filtered: boolean }): ReactNode {
  return (
    <div className="flex flex-col items-center justify-center flex-1 gap-4">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 64, height: 64, background: getDomainColorWithAlpha('tasks', '20') }}
      >
        <span style={{ color: taskColor }}>
          <Icon name="check" size={32} />
        </span>
      </div>
      <div className="text-center">
        <p className="text-sm font-medium mb-1" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
          {filtered ? 'No matching tasks' : 'No tasks found'}
        </p>
        <p style={{ fontSize: 12, color: 'rgb(var(--canvas-fg-3))' }}>
          {filtered
            ? 'Try a different filter.'
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
        style={{ width: 64, height: 64, background: `rgb(var(--status-error) / 0.13)` }}
      >
        <span style={{ color: 'rgb(var(--status-error))' }}>
          <Icon name="alert" size={32} />
        </span>
      </div>
      <div className="text-center">
        <p className="text-sm font-medium mb-1" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
          Failed to load tasks
        </p>
        <p style={{ fontSize: 12, color: 'rgb(var(--canvas-fg-3))' }}>
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

  const selectedHash = search.selectedHash ?? null;

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

  const allChunks = useMemo(() => data?.chunks ?? [], [data]);

  const allTasks = useMemo(() => {
    const result: Array<{ chunk: ChunkResponse; meta: TaskMeta }> = [];
    for (const chunk of allChunks) {
      const meta = extractTaskMetadata(chunk);
      if (meta) result.push({ chunk, meta });
    }
    return result;
  }, [allChunks]);

  // Build lookup map for renderCard access
  const taskMap = useMemo(() => {
    const m = new Map<string, { chunk: ChunkResponse; meta: TaskMeta }>();
    for (const item of allTasks) m.set(item.chunk.chunk_hash, item);
    return m;
  }, [allTasks]);

  const sourcesAvailable = useMemo(() => {
    const set = new Set<string>();
    for (const { meta } of allTasks) set.add(meta.source_type);
    return Array.from(set).sort();
  }, [allTasks]);

  // FilterDropdown state
  const activeSourceFilters = useMemo(() => (search.sources as string[] | undefined) ?? [], [search.sources]);
  const activeStateFilters = useMemo(() => (search.states as string[] | undefined) ?? [], [search.states]);
  const activeDueDateFilter: DueDateFilter = (search.dueDate as DueDateFilter | undefined) ?? 'all';

  function setSourceFilters(values: string[]): void {
    void navigate({
      to: '/tasks',
      search: (prev: Record<string, unknown>) => ({
        ...prev,
        sources: values.length > 0 ? values : undefined,
        selectedHash: undefined,
      }),
    });
  }

  function setStateFilters(values: string[]): void {
    void navigate({
      to: '/tasks',
      search: (prev: Record<string, unknown>) => ({
        ...prev,
        states: values.length > 0 ? values : undefined,
        selectedHash: undefined,
      }),
    });
  }

  function setDueDateFilter(values: string[]): void {
    const val = values[0] as DueDateFilter ?? 'all';
    void navigate({
      to: '/tasks',
      search: (prev: Record<string, unknown>) => ({
        ...prev,
        dueDate: val === 'all' ? undefined : val,
        selectedHash: undefined,
      }),
    });
  }

  const filteredTasks = useMemo(() => {
    return allTasks.filter(({ meta }) => {
      if (activeSourceFilters.length > 0 && !activeSourceFilters.includes(meta.source_type)) return false;
      if (activeStateFilters.length > 0 && !activeStateFilters.includes(meta.status)) return false;
      if (!matchesDueDateFilter(meta, activeDueDateFilter)) return false;
      return true;
    });
  }, [allTasks, activeSourceFilters, activeStateFilters, activeDueDateFilter]);

  const kanbanCards: KanbanCard[] = useMemo(
    () => filteredTasks.map(({ chunk, meta }) => toKanbanCard(chunk, meta)),
    [filteredTasks],
  );

  const selectedItem = useMemo(
    () => (selectedHash ? (taskMap.get(selectedHash) ?? null) : null),
    [taskMap, selectedHash],
  );

  const countAll = allTasks.length;
  const isFiltered = activeSourceFilters.length > 0 || activeStateFilters.length > 0 || activeDueDateFilter !== 'all';

  const renderCard = useCallback((card: KanbanCard, isSelected: boolean): ReactNode => {
    const item = taskMap.get(card.id);
    if (!item) return null;
    return <TaskCard chunk={item.chunk} meta={item.meta} isSelected={isSelected} />;
  }, [taskMap]);

  const sourceFilterSummary = activeSourceFilters.length > 0
    ? `${activeSourceFilters.length} selected`
    : 'All';
  const stateFilterSummary = activeStateFilters.length > 0
    ? `${activeStateFilters.length} selected`
    : 'All';
  const dueDateFilterSummary: Record<DueDateFilter, string> = {
    all: 'All', overdue: 'Overdue', today: 'Today', 'this-week': 'This week',
  };

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
      <PageHeader
        eyebrow="Domains"
        title="Tasks"
        subtitle="To-dos from Reminders and CalDAV"
      />

      {/* ── Toolbar ── */}
      <div
        className="flex items-center gap-3 px-5 shrink-0"
        style={{ height: 48, borderBottom: `1px solid rgb(var(--canvas-border))`, background: 'rgb(var(--canvas-surface))' }}
      >
        {!isLoading && !isError && (
          <div style={{ borderRadius: 10, padding: '3px 10px', background: 'rgb(var(--canvas-bg))' }}>
            <span style={{ fontSize: 11, color: 'rgb(var(--canvas-fg-2))' }}>
              {countAll.toLocaleString()} task{countAll !== 1 ? 's' : ''}
            </span>
          </div>
        )}

        <div className="flex-1" />

        <FilterDropdown
          mode="checkbox"
          value={activeSourceFilters}
          onChange={setSourceFilters}
        >
          <FilterDropdown.Trigger label="Source" summary={sourceFilterSummary} />
          <FilterDropdown.Panel>
            <FilterDropdown.Section title="Source adapter">
              {sourcesAvailable.map(s => (
                <FilterDropdown.Checkbox key={s} value={s} label={sourceLabel(s)} />
              ))}
            </FilterDropdown.Section>
          </FilterDropdown.Panel>
        </FilterDropdown>

        <FilterDropdown
          mode="checkbox"
          value={activeStateFilters}
          onChange={setStateFilters}
        >
          <FilterDropdown.Trigger label="State" summary={stateFilterSummary} />
          <FilterDropdown.Panel>
            <FilterDropdown.Section title="Task status">
              <FilterDropdown.Checkbox value="open"        label="Open" />
              <FilterDropdown.Checkbox value="in-progress" label="In Progress" />
              <FilterDropdown.Checkbox value="completed"   label="Completed" />
              <FilterDropdown.Checkbox value="cancelled"   label="Cancelled" />
            </FilterDropdown.Section>
          </FilterDropdown.Panel>
        </FilterDropdown>

        <FilterDropdown
          mode="radio"
          value={activeDueDateFilter !== 'all' ? [activeDueDateFilter] : []}
          onChange={setDueDateFilter}
        >
          <FilterDropdown.Trigger label="Due" summary={dueDateFilterSummary[activeDueDateFilter]} />
          <FilterDropdown.Panel>
            <FilterDropdown.Section title="Due date">
              <FilterDropdown.Radio value="all"       label="All dates" />
              <FilterDropdown.Radio value="overdue"   label="Overdue" />
              <FilterDropdown.Radio value="today"     label="Due today" />
              <FilterDropdown.Radio value="this-week" label="This week" />
            </FilterDropdown.Section>
          </FilterDropdown.Panel>
        </FilterDropdown>
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
      ) : filteredTasks.length === 0 ? (
        <EmptyState filtered={isFiltered} />
      ) : (
        <div className="flex flex-1 min-h-0 overflow-hidden">
          {/* Kanban board */}
          <div className="flex-1 overflow-hidden">
            <KanbanBoard
              columns={KANBAN_COLUMNS}
              cards={kanbanCards}
              selectedId={selectedHash ?? undefined}
              onSelectCard={toggleSelectedHash}
              onMoveCard={() => {
                // Tasks are read-only from external sources; moves are no-ops
              }}
              renderCard={renderCard}
              style={{ height: '100%' }}
            />
          </div>

          {/* Detail panel */}
          {selectedItem && (
            <div
              className="w-80 shrink-0 flex flex-col overflow-hidden"
              style={{ borderLeft: `1px solid rgb(var(--canvas-border))` }}
            >
              <TaskDetailPane
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
