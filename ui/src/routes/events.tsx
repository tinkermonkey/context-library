import { useNavigate, useSearch } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  CalendarIcon,
  MapPinIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline';
import { fetchChunks } from '../api/client';
import { colors, getDomainColor } from '../lib/designTokens';
import type { ChunkResponse } from '../types/api';

const evtColor = getDomainColor('events'); // #F59E0B

// ── Types ──────────────────────────────────────────────────────────

interface EventMeta {
  event_id: string;
  title: string;
  start_date: string | null;
  end_date: string | null;
  duration_minutes: number | null;
  host: string | null;
  invitees: string[];
  source_type: string;
  calendar_name: string | null;
  location: string | null;
}

function extractEventMeta(chunk: ChunkResponse): EventMeta | null {
  const dm = chunk.domain_metadata;
  if (!dm) return null;
  return {
    event_id: typeof dm.event_id === 'string' ? dm.event_id : chunk.chunk_hash,
    title: typeof dm.title === 'string' ? dm.title : 'Untitled Event',
    start_date: typeof dm.start_date === 'string' ? dm.start_date : null,
    end_date: typeof dm.end_date === 'string' ? dm.end_date : null,
    duration_minutes: typeof dm.duration_minutes === 'number' ? dm.duration_minutes : null,
    host: typeof dm.host === 'string' ? dm.host : null,
    invitees: Array.isArray(dm.invitees) ? (dm.invitees as string[]) : [],
    source_type: typeof dm.source_type === 'string' ? dm.source_type : 'calendar',
    calendar_name: typeof dm.calendar_name === 'string' ? dm.calendar_name : null,
    location: typeof dm.location === 'string' ? dm.location : null,
  };
}

// ── Calendar colors by source type ────────────────────────────────

const SOURCE_PALETTE: Record<string, string> = {
  google_calendar: '#4285F4',
  caldav: '#6366F1',
  apple_calendar: '#EC4899',
  ical: '#22C55E',
  work: '#F59E0B',
  personal: '#A855F7',
  shared: '#14B8A6',
};

const FALLBACK_PALETTE = [
  '#6366F1', '#A855F7', '#EC4899', '#F43F5E',
  '#F97316', '#F59E0B', '#22C55E', '#14B8A6',
  '#06B6D4', '#3B82F6',
];

function sourceColor(sourceType: string, calendarName: string | null): string {
  const key = (calendarName ?? sourceType).toLowerCase();
  if (SOURCE_PALETTE[key]) return SOURCE_PALETTE[key];
  if (SOURCE_PALETTE[sourceType]) return SOURCE_PALETTE[sourceType];
  // Deterministic fallback
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) & 0x7fffffff;
  return FALLBACK_PALETTE[h % FALLBACK_PALETTE.length];
}

// ── Date helpers ───────────────────────────────────────────────────

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function isoDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function parseIsoDate(iso: string): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return isNaN(d.getTime()) ? null : d;
}

function formatTimeRange(start: string | null, end: string | null): string {
  if (!start) return '';
  const s = parseIsoDate(start);
  if (!s) return '';
  const fmt = (d: Date) =>
    d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
  if (!end) return fmt(s);
  const e = parseIsoDate(end);
  if (!e) return fmt(s);
  return `${fmt(s)} – ${fmt(e)}`;
}

function formatDayHeading(date: Date): string {
  const today = new Date();
  const isToday =
    date.getFullYear() === today.getFullYear() &&
    date.getMonth() === today.getMonth() &&
    date.getDate() === today.getDate();
  const base = date.toLocaleDateString('en-US', { month: 'long', day: 'numeric' });
  return isToday ? `${base} — Today` : base;
}

function isAllDay(start: string | null, end: string | null): boolean {
  if (!start) return true;
  const s = parseIsoDate(start);
  if (!s) return true;
  if (s.getHours() === 0 && s.getMinutes() === 0) {
    if (!end) return true;
    const e = parseIsoDate(end);
    if (e && e.getTime() - s.getTime() >= 23 * 3600 * 1000) return true;
  }
  return false;
}

// ── Build month grid ───────────────────────────────────────────────

interface CalendarWeek {
  days: Date[];
}

function buildMonthGrid(year: number, month: number): CalendarWeek[] {
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const gridStart = new Date(firstDay);
  gridStart.setDate(gridStart.getDate() - gridStart.getDay());

  const weeks: CalendarWeek[] = [];
  const cursor = new Date(gridStart);
  while (cursor <= lastDay || weeks.length < 1) {
    const days: Date[] = [];
    for (let i = 0; i < 7; i++) {
      days.push(new Date(cursor));
      cursor.setDate(cursor.getDate() + 1);
    }
    weeks.push({ days });
    if (cursor > lastDay && weeks.length >= 4) break;
  }
  return weeks;
}

// ── Event map (by date key) ────────────────────────────────────────

type EventMap = Map<string, Array<{ chunk: ChunkResponse; meta: EventMeta }>>;

function buildEventMap(chunks: ChunkResponse[]): EventMap {
  const map: EventMap = new Map();
  for (const chunk of chunks) {
    const meta = extractEventMeta(chunk);
    if (!meta || !meta.start_date) continue;
    const d = parseIsoDate(meta.start_date);
    if (!d) continue;
    const key = isoDateKey(d);
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push({ chunk, meta });
  }
  for (const [, events] of map) {
    events.sort((a, b) => {
      const ta = a.meta.start_date ?? '';
      const tb = b.meta.start_date ?? '';
      return ta.localeCompare(tb);
    });
  }
  return map;
}

// ── Event chip ─────────────────────────────────────────────────────

function EventChip({ meta }: { meta: EventMeta }): ReactNode {
  const color = sourceColor(meta.source_type, meta.calendar_name);
  return (
    <div
      className="truncate"
      style={{
        background: `${color}28`,
        color,
        borderLeft: `2px solid ${color}`,
        borderRadius: 3,
        padding: '1px 4px',
        lineHeight: '1.4',
        fontSize: '10px',
        maxWidth: '100%',
      }}
      title={meta.title}
    >
      {meta.title}
    </div>
  );
}

// ── Day cell ───────────────────────────────────────────────────────

function DayCell({
  date,
  events,
  isCurrentMonth,
  isToday,
  isSelected,
  onClick,
}: {
  date: Date;
  events: Array<{ chunk: ChunkResponse; meta: EventMeta }>;
  isCurrentMonth: boolean;
  isToday: boolean;
  isSelected: boolean;
  onClick: () => void;
}): ReactNode {
  const MAX_CHIPS = 3;
  const overflow = events.length - MAX_CHIPS;

  return (
    <button
      onClick={onClick}
      className="text-left flex flex-col gap-0.5 p-1 transition-colors w-full"
      style={{
        minHeight: 72,
        borderTop: `1px solid ${colors.border}`,
        background: isSelected ? `${evtColor}12` : 'transparent',
        opacity: isCurrentMonth ? 1 : 0.35,
      }}
    >
      <div className="flex items-center justify-start mb-0.5 px-0.5">
        {isToday ? (
          <span
            className="flex items-center justify-center rounded-full font-semibold"
            style={{
              width: 22,
              height: 22,
              background: colors.accent,
              color: '#fff',
              fontSize: 12,
              lineHeight: 1,
            }}
          >
            {date.getDate()}
          </span>
        ) : (
          <span
            style={{
              fontSize: 12,
              fontWeight: 500,
              color: isSelected ? evtColor : isCurrentMonth ? colors.textMuted : colors.textDim,
            }}
          >
            {date.getDate()}
          </span>
        )}
      </div>
      <div className="flex flex-col gap-0.5 w-full overflow-hidden">
        {events.slice(0, MAX_CHIPS).map(({ meta, chunk }) => (
          <EventChip key={chunk.chunk_hash} meta={meta} />
        ))}
        {overflow > 0 && (
          <span style={{ color: colors.textDim, fontSize: 10, paddingLeft: 4 }}>
            +{overflow} more
          </span>
        )}
      </div>
    </button>
  );
}

// ── Month view ─────────────────────────────────────────────────────

function MonthView({
  year,
  month,
  eventMap,
  selectedDateKey,
  onSelectDate,
}: {
  year: number;
  month: number;
  eventMap: EventMap;
  selectedDateKey: string | null;
  onSelectDate: (key: string) => void;
}): ReactNode {
  const today = new Date();
  const todayKey = isoDateKey(today);
  const weeks = buildMonthGrid(year, month);

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <div className="grid grid-cols-7 shrink-0">
        {WEEKDAYS.map(d => (
          <div
            key={d}
            className="text-center py-2"
            style={{
              fontSize: 11,
              fontWeight: 500,
              color: colors.textDim,
              borderBottom: `1px solid ${colors.border}`,
            }}
          >
            {d.toUpperCase()}
          </div>
        ))}
      </div>
      <div className="flex flex-col flex-1 overflow-hidden">
        {weeks.map((week, wi) => (
          <div key={wi} className="grid grid-cols-7 flex-1">
            {week.days.map(date => {
              const key = isoDateKey(date);
              return (
                <DayCell
                  key={key}
                  date={date}
                  events={eventMap.get(key) ?? []}
                  isCurrentMonth={date.getMonth() === month}
                  isToday={key === todayKey}
                  isSelected={key === selectedDateKey}
                  onClick={() => onSelectDate(key)}
                />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Week view ──────────────────────────────────────────────────────

function WeekView({
  year,
  month,
  eventMap,
  selectedDateKey,
  onSelectDate,
}: {
  year: number;
  month: number;
  eventMap: EventMap;
  selectedDateKey: string | null;
  onSelectDate: (key: string) => void;
}): ReactNode {
  const today = new Date();
  const todayKey = isoDateKey(today);
  const anchor = new Date(year, month, 1);
  const weekStart = new Date(anchor);
  weekStart.setDate(weekStart.getDate() - weekStart.getDay());

  const days: Date[] = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + i);
    days.push(d);
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <div className="grid grid-cols-7 shrink-0">
        {days.map(date => {
          const key = isoDateKey(date);
          const isToday = key === todayKey;
          const isCurrentMonth = date.getMonth() === month;
          return (
            <div
              key={key}
              className="text-center py-2"
              style={{ borderBottom: `1px solid ${colors.border}` }}
            >
              <span style={{ fontSize: 11, fontWeight: 500, color: colors.textDim, display: 'block' }}>
                {WEEKDAYS[date.getDay()].toUpperCase()}
              </span>
              {isToday ? (
                <span
                  className="inline-flex items-center justify-center rounded-full font-semibold mx-auto"
                  style={{ width: 28, height: 28, background: colors.accent, color: '#fff', fontSize: 13 }}
                >
                  {date.getDate()}
                </span>
              ) : (
                <span style={{ fontSize: 13, fontWeight: 500, color: isCurrentMonth ? colors.textMuted : colors.textDim }}>
                  {date.getDate()}
                </span>
              )}
            </div>
          );
        })}
      </div>
      <div className="grid grid-cols-7 flex-1 overflow-y-auto">
        {days.map(date => {
          const key = isoDateKey(date);
          const dayEvents = eventMap.get(key) ?? [];
          const isSelected = key === selectedDateKey;
          return (
            <button
              key={key}
              onClick={() => onSelectDate(key)}
              className="flex flex-col gap-0.5 p-1.5 text-left transition-colors overflow-hidden"
              style={{
                borderRight: `1px solid ${colors.border}`,
                borderTop: `1px solid ${colors.border}`,
                background: isSelected ? `${evtColor}12` : 'transparent',
              }}
            >
              {dayEvents.map(({ chunk, meta }) => (
                <EventChip key={chunk.chunk_hash} meta={meta} />
              ))}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── Agenda event row ───────────────────────────────────────────────

function AgendaEventRow({ meta }: { meta: EventMeta }): ReactNode {
  const color = sourceColor(meta.source_type, meta.calendar_name);
  const timeStr = formatTimeRange(meta.start_date, meta.end_date);
  const allDay = isAllDay(meta.start_date, meta.end_date);

  return (
    <div
      className="flex items-start gap-3 px-4 py-3"
      style={{ borderBottom: `1px solid ${colors.border}` }}
    >
      <div
        className="shrink-0 rounded-full"
        style={{ width: 3, alignSelf: 'stretch', background: color, minHeight: 16 }}
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <span className="text-sm font-medium truncate" style={{ color: colors.textPrimary }}>
            {meta.title}
          </span>
          <span
            className="shrink-0 rounded"
            style={{
              background: `${color}22`,
              color,
              fontSize: 10,
              padding: '2px 6px',
            }}
          >
            {meta.calendar_name ?? meta.source_type}
          </span>
        </div>
        <div className="mt-0.5 flex items-center gap-3 flex-wrap">
          {!allDay && timeStr && (
            <span style={{ fontSize: 12, color: colors.textDim }}>{timeStr}</span>
          )}
          {allDay && (
            <span style={{ fontSize: 12, color: colors.textDim }}>All day</span>
          )}
          {meta.location && (
            <span className="flex items-center gap-1" style={{ fontSize: 12, color: colors.textDim }}>
              <MapPinIcon className="w-3 h-3" />
              {meta.location}
            </span>
          )}
          {meta.invitees.length > 0 && (
            <span className="flex items-center gap-1" style={{ fontSize: 12, color: colors.textDim }}>
              <UserGroupIcon className="w-3 h-3" />
              {meta.invitees.length} {meta.invitees.length === 1 ? 'attendee' : 'attendees'}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Agenda full view ───────────────────────────────────────────────

function AgendaFullView({ eventMap }: { eventMap: EventMap }): ReactNode {
  const today = new Date();
  const days = Array.from(eventMap.entries())
    .filter(([, events]) => events.length > 0)
    .sort(([a], [b]) => a.localeCompare(b));

  if (days.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center flex-1 gap-3">
        <CalendarIcon className="w-8 h-8" style={{ color: colors.textDim }} />
        <p className="text-sm" style={{ color: colors.textDim }}>No events found</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      {days.map(([key, events]) => {
        const date = new Date(key + 'T12:00:00');
        const isToday = isoDateKey(today) === key;
        return (
          <div key={key}>
            <div
              className="px-4 py-2 sticky top-0"
              style={{ background: colors.bgSurface, borderBottom: `1px solid ${colors.border}` }}
            >
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: isToday ? evtColor : colors.textMuted,
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                }}
              >
                {date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
                {isToday && ' — Today'}
              </span>
            </div>
            {events.map(({ chunk, meta }) => (
              <AgendaEventRow key={chunk.chunk_hash} meta={meta} />
            ))}
          </div>
        );
      })}
    </div>
  );
}

// ── Day agenda panel ───────────────────────────────────────────────

function DayAgendaPanel({
  dateKey,
  events,
}: {
  dateKey: string;
  events: Array<{ chunk: ChunkResponse; meta: EventMeta }>;
}): ReactNode {
  const date = new Date(dateKey + 'T12:00:00');

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="px-4 py-3 shrink-0" style={{ borderBottom: `1px solid ${colors.border}` }}>
        <h3 className="text-sm font-semibold" style={{ color: colors.textPrimary }}>
          {formatDayHeading(date)}
        </h3>
        <p style={{ fontSize: 12, color: colors.textDim, marginTop: 2 }}>
          {events.length} {events.length === 1 ? 'event' : 'events'}
        </p>
      </div>
      <div className="flex-1 overflow-y-auto">
        {events.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 gap-2">
            <p style={{ fontSize: 13, color: colors.textDim }}>No events</p>
          </div>
        ) : (
          events.map(({ chunk, meta }) => (
            <AgendaEventRow key={chunk.chunk_hash} meta={meta} />
          ))
        )}
      </div>
    </div>
  );
}

// ── View type ──────────────────────────────────────────────────────

type ViewMode = 'month' | 'week' | 'agenda';

// ── EmptyState ─────────────────────────────────────────────────────

function EmptyState(): ReactNode {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 64, height: 64, background: `${evtColor}20` }}
      >
        <CalendarIcon className="w-8 h-8" style={{ color: evtColor }} />
      </div>
      <div className="text-center">
        <p className="text-sm font-medium mb-1" style={{ color: colors.textMuted }}>
          No calendar events found
        </p>
        <p style={{ fontSize: 12, color: colors.textDim }}>
          Connect a CalDAV or Apple Calendar source to see events here.
        </p>
      </div>
    </div>
  );
}

// ── EventsPage ─────────────────────────────────────────────────────

export default function EventsPage(): ReactNode {
  const navigate = useNavigate();
  const search = useSearch({ from: '/events' });

  const [viewMode, setViewMode] = useState<ViewMode>('month');

  const today = new Date();
  const [displayYear, setDisplayYear] = useState(today.getFullYear());
  const [displayMonth, setDisplayMonth] = useState(today.getMonth());

  const todayKey = isoDateKey(today);
  const selectedDateKey = search.dateFrom ?? todayKey;

  function selectDate(key: string): void {
    void navigate({ to: '/events', search: (prev: Record<string, unknown>) => ({ ...prev, dateFrom: key }) });
  }

  const { data, isLoading } = useQuery({
    queryKey: ['chunks', { domain: 'events', limit: 2000 }],
    queryFn: () => fetchChunks({ domain: 'events', limit: 2000 }),
    staleTime: 30_000,
  });

  const allChunks = data?.chunks ?? [];
  const eventMap = useMemo(() => buildEventMap(allChunks), [allChunks]);
  const selectedDayEvents = useMemo(
    () => eventMap.get(selectedDateKey) ?? [],
    [eventMap, selectedDateKey],
  );

  function prevMonth(): void {
    if (displayMonth === 0) {
      setDisplayYear(y => y - 1);
      setDisplayMonth(11);
    } else {
      setDisplayMonth(m => m - 1);
    }
  }

  function nextMonth(): void {
    if (displayMonth === 11) {
      setDisplayYear(y => y + 1);
      setDisplayMonth(0);
    } else {
      setDisplayMonth(m => m + 1);
    }
  }

  function goToToday(): void {
    setDisplayYear(today.getFullYear());
    setDisplayMonth(today.getMonth());
    selectDate(todayKey);
  }

  const hasEvents = allChunks.length > 0;

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: colors.bgBase }}>
      {/* ── Toolbar ── */}
      <div
        className="flex items-center gap-3 px-4 py-2 shrink-0"
        style={{ borderBottom: `1px solid ${colors.border}`, background: colors.bgSurface }}
      >
        {/* View toggle */}
        <div
          className="flex items-center rounded-lg gap-0.5"
          style={{ background: colors.bgElevated, padding: 2 }}
        >
          {(['month', 'week', 'agenda'] as ViewMode[]).map(mode => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              className="px-3 py-1 rounded-md transition-colors"
              style={{
                fontSize: 12,
                fontWeight: 500,
                background: viewMode === mode ? colors.bgSurface : 'transparent',
                color: viewMode === mode ? colors.textPrimary : colors.textDim,
                boxShadow: viewMode === mode ? '0 1px 2px rgba(0,0,0,0.3)' : 'none',
              }}
            >
              {mode.charAt(0).toUpperCase() + mode.slice(1)}
            </button>
          ))}
        </div>

        <div className="flex-1" />

        {/* Today button */}
        <button
          onClick={goToToday}
          className="px-3 py-1 rounded-md transition-opacity hover:opacity-75"
          style={{
            fontSize: 12,
            fontWeight: 500,
            background: colors.bgElevated,
            color: colors.textMuted,
            border: `1px solid ${colors.border}`,
          }}
        >
          Today
        </button>

        {/* Month navigation */}
        <div className="flex items-center gap-1">
          <button
            onClick={prevMonth}
            className="p-1 rounded transition-opacity hover:opacity-75"
            style={{ color: colors.textMuted }}
          >
            <ChevronLeftIcon className="w-4 h-4" />
          </button>
          <span
            className="text-center"
            style={{ fontSize: 13, fontWeight: 600, color: colors.textPrimary, minWidth: 110 }}
          >
            {MONTHS[displayMonth]} {displayYear}
          </span>
          <button
            onClick={nextMonth}
            className="p-1 rounded transition-opacity hover:opacity-75"
            style={{ color: colors.textMuted }}
          >
            <ChevronRightIcon className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* ── Body ── */}
      {isLoading ? (
        <div className="flex flex-1 items-center justify-center">
          <div
            className="w-6 h-6 rounded-full border-2 animate-spin"
            style={{ borderColor: `${evtColor} transparent transparent transparent` }}
          />
        </div>
      ) : !hasEvents ? (
        <EmptyState />
      ) : viewMode === 'agenda' ? (
        <AgendaFullView eventMap={eventMap} />
      ) : (
        <div className="flex flex-1 overflow-hidden">
          {/* Main calendar area */}
          <div className="flex flex-col flex-1 overflow-hidden">
            {viewMode === 'month' ? (
              <MonthView
                year={displayYear}
                month={displayMonth}
                eventMap={eventMap}
                selectedDateKey={selectedDateKey}
                onSelectDate={selectDate}
              />
            ) : (
              <WeekView
                year={displayYear}
                month={displayMonth}
                eventMap={eventMap}
                selectedDateKey={selectedDateKey}
                onSelectDate={selectDate}
              />
            )}
          </div>

          {/* Right day agenda panel */}
          <div
            className="w-72 shrink-0 flex flex-col overflow-hidden"
            style={{ borderLeft: `1px solid ${colors.border}`, background: colors.bgSurface }}
          >
            <DayAgendaPanel dateKey={selectedDateKey} events={selectedDayEvents} />
          </div>
        </div>
      )}
    </div>
  );
}
