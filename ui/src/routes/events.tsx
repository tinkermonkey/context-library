import { useNavigate, useSearch } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { MapPinIcon } from '@heroicons/react/24/outline';
import { Calendar, MiniCalendar, Icon, PageHeader } from '@tinkermonkey/heimdall-ui';
import type { CalendarEvent, CalendarView } from '@tinkermonkey/heimdall-ui';
import { SegmentedControl } from '../components/SegmentedControl';
import { FilterDropdown } from '../components/FilterDropdown';
import { fetchChunks } from '../api/client';
import { getDomainColor, getDomainColorWithAlpha } from '../lib/designTokens';
import type { ChunkResponse } from '../types/api';

const evtColor = getDomainColor('events');

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
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) & 0x7fffffff;
  return FALLBACK_PALETTE[h % FALLBACK_PALETTE.length];
}

// ── Date helpers ───────────────────────────────────────────────────

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

// ── Agenda event row ───────────────────────────────────────────────

function AgendaEventRow({ meta }: { meta: EventMeta }): ReactNode {
  const color = sourceColor(meta.source_type, meta.calendar_name);
  const timeStr = formatTimeRange(meta.start_date, meta.end_date);
  const allDay = isAllDay(meta.start_date, meta.end_date);

  return (
    <div
      className="flex items-start gap-3 px-4 py-3"
      style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}
    >
      <div
        className="shrink-0 rounded-full"
        style={{ width: 3, alignSelf: 'stretch', background: color, minHeight: 16 }}
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <span className="text-sm font-medium truncate" style={{ color: 'rgb(var(--canvas-fg-1))' }}>
            {meta.title}
          </span>
          <span
            className="shrink-0 rounded"
            style={{ background: `${color}22`, color, fontSize: 10, padding: '2px 6px' }}
          >
            {meta.calendar_name ?? meta.source_type}
          </span>
        </div>
        <div className="mt-0.5 flex items-center gap-3 flex-wrap">
          {!allDay && timeStr && (
            <span style={{ fontSize: 12, color: 'rgb(var(--canvas-fg-3))' }}>{timeStr}</span>
          )}
          {allDay && (
            <span style={{ fontSize: 12, color: 'rgb(var(--canvas-fg-3))' }}>All day</span>
          )}
          {meta.location && (
            <span className="flex items-center gap-1" style={{ fontSize: 12, color: 'rgb(var(--canvas-fg-3))' }}>
              <MapPinIcon className="w-3 h-3" />
              {meta.location}
            </span>
          )}
          {meta.invitees.length > 0 && (
            <span className="flex items-center gap-1" style={{ fontSize: 12, color: 'rgb(var(--canvas-fg-3))' }}>
              <Icon name="user" size={12} />
              {meta.invitees.length} {meta.invitees.length === 1 ? 'attendee' : 'attendees'}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Day agenda panel ───────────────────────────────────────────────

interface EventEntry {
  chunk: ChunkResponse;
  meta: EventMeta;
}

type EventMap = Map<string, EventEntry[]>;

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

function DayAgendaPanel({
  dateKey,
  events,
}: {
  dateKey: string;
  events: EventEntry[];
}): ReactNode {
  const date = new Date(dateKey + 'T12:00:00');

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="px-4 py-3 shrink-0" style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}>
        <h3 className="text-sm font-semibold" style={{ color: 'rgb(var(--canvas-fg-1))' }}>
          {formatDayHeading(date)}
        </h3>
        <p style={{ fontSize: 12, color: 'rgb(var(--canvas-fg-3))', marginTop: 2 }}>
          {events.length} {events.length === 1 ? 'event' : 'events'}
        </p>
      </div>
      <div className="flex-1 overflow-y-auto">
        {events.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 gap-2">
            <p style={{ fontSize: 13, color: 'rgb(var(--canvas-fg-3))' }}>No events</p>
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

// ── Custom event renderer ──────────────────────────────────────────

function renderCalendarEvent(event: CalendarEvent, calendarColor?: string): ReactNode {
  const color = calendarColor ?? evtColor;
  // Extract source adapter label from calendarId
  const adapterLabel = event.calendarId.replace(/_/g, ' ');
  // Format time from startDate
  let timeStr = '';
  if (event.startDate) {
    const d = typeof event.startDate === 'string' ? parseIsoDate(event.startDate) : event.startDate;
    if (d) {
      timeStr = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
    }
  }
  return (
    <div
      className="flex items-center gap-1 overflow-hidden w-full"
      style={{ fontSize: 11, color, padding: '1px 4px' }}
    >
      <span
        className="shrink-0 rounded-full"
        style={{ width: 6, height: 6, background: color, flexShrink: 0 }}
      />
      <span className="truncate font-medium flex-1">{event.title}</span>
      {timeStr && (
        <span className="shrink-0 opacity-70" style={{ fontSize: 9 }}>{timeStr}</span>
      )}
      <span
        className="shrink-0 rounded"
        style={{
          background: `${color}22`,
          color,
          fontSize: 9,
          padding: '1px 4px',
          maxWidth: 60,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {adapterLabel}
      </span>
    </div>
  );
}

// ── EmptyState ─────────────────────────────────────────────────────

function EmptyState(): ReactNode {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 64, height: 64, background: getDomainColorWithAlpha('events', '20') }}
      >
        <span style={{ color: evtColor }}>
          <Icon name="calendar" size={32} />
        </span>
      </div>
      <div className="text-center">
        <p className="text-sm font-medium mb-1" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
          No calendar events found
        </p>
        <p style={{ fontSize: 12, color: 'rgb(var(--canvas-fg-3))' }}>
          Connect a CalDAV or Apple Calendar source to see events here.
        </p>
      </div>
    </div>
  );
}

function ErrorState(): ReactNode {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 64, height: 64, background: 'rgb(var(--status-error) / 0.13)' }}
      >
        <span style={{ color: 'rgb(var(--status-error))' }}>
          <Icon name="alert" size={32} />
        </span>
      </div>
      <div className="text-center">
        <p className="text-sm font-medium mb-1" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
          Failed to load events
        </p>
        <p style={{ fontSize: 12, color: 'rgb(var(--canvas-fg-3))' }}>
          There was a problem fetching your calendar events. Please try again.
        </p>
      </div>
    </div>
  );
}

// ── EventsPage ─────────────────────────────────────────────────────

const VIEW_OPTIONS = [
  { value: 'month', label: 'Month' },
  { value: 'week', label: 'Week' },
  { value: 'day', label: 'Day' },
];

export default function EventsPage(): ReactNode {
  const navigate = useNavigate();
  const search = useSearch({ from: '/events' });

  const [viewMode, setViewMode] = useState<CalendarView>('month');
  const [focusedDate, setFocusedDate] = useState<Date>(() => new Date());
  const [sourceFilter, setSourceFilter] = useState<string[]>([]);

  const today = new Date();
  const todayKey = isoDateKey(today);
  const selectedDateKey = search.dateFrom ?? todayKey;
  const selectedDate = useMemo(
    () => new Date(selectedDateKey + 'T12:00:00'),
    [selectedDateKey],
  );

  function selectDate(date: Date): void {
    const key = isoDateKey(date);
    setFocusedDate(date);
    void navigate({
      to: '/events',
      search: (prev: Record<string, unknown>) => ({ ...prev, dateFrom: key }),
    });
  }

  function handleMiniCalendarSelect(date: Date): void {
    selectDate(date);
  }

  const { data, isLoading, isError } = useQuery({
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

  // Convert chunks to CalendarEvent format for the Calendar component
  const allCalendarEvents = useMemo<CalendarEvent[]>(() => {
    return allChunks.flatMap(chunk => {
      const meta = extractEventMeta(chunk);
      if (!meta || !meta.start_date) return [];
      return [{
        id: chunk.chunk_hash,
        title: meta.title,
        calendarId: meta.source_type,
        startDate: meta.start_date,
        endDate: meta.end_date ?? undefined,
      }];
    });
  }, [allChunks]);

  // Available source types for filtering
  const sourceTypes = useMemo(() => {
    const types = new Set<string>();
    for (const chunk of allChunks) {
      const meta = extractEventMeta(chunk);
      if (meta) types.add(meta.source_type);
    }
    return Array.from(types).sort();
  }, [allChunks]);

  // Filtered calendar events
  const calendarEvents = useMemo(() => {
    if (sourceFilter.length === 0) return allCalendarEvents;
    return allCalendarEvents.filter(e => sourceFilter.includes(e.calendarId));
  }, [allCalendarEvents, sourceFilter]);

  // Markers for MiniCalendar — all dates that have events
  const eventMarkers = useMemo(() => {
    const seen = new Set<string>();
    for (const chunk of allChunks) {
      const meta = extractEventMeta(chunk);
      if (meta?.start_date) {
        const d = parseIsoDate(meta.start_date);
        if (d) seen.add(isoDateKey(d));
      }
    }
    return Array.from(seen).map(k => new Date(k + 'T12:00:00'));
  }, [allChunks]);

  const hasEvents = allChunks.length > 0;

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
      <PageHeader
        eyebrow="Domains"
        title="Events"
        subtitle="Calendar events from all sources"
      />

      {/* ── Toolbar ── */}
      <div
        className="flex items-center gap-3 px-4 py-2 shrink-0"
        style={{ borderBottom: `1px solid rgb(var(--canvas-border))`, background: 'rgb(var(--canvas-surface))' }}
      >
        <SegmentedControl
          value={viewMode}
          onChange={v => setViewMode(v as CalendarView)}
          options={VIEW_OPTIONS}
        />

        <div className="flex-1" />

        <FilterDropdown
          mode="checkbox"
          value={sourceFilter}
          onChange={setSourceFilter}
        >
          <FilterDropdown.Trigger
            label="Source"
            summary={sourceFilter.length === 0 ? 'All' : `${sourceFilter.length} selected`}
          />
          <FilterDropdown.Panel>
            <FilterDropdown.Section title="Calendar source">
              {sourceTypes.map(type => (
                <FilterDropdown.Checkbox
                  key={type}
                  value={type}
                  label={type.replace(/_/g, ' ')}
                />
              ))}
            </FilterDropdown.Section>
          </FilterDropdown.Panel>
        </FilterDropdown>
      </div>

      {/* ── Body ── */}
      {isLoading ? (
        <div className="flex flex-1 items-center justify-center">
          <div
            className="w-6 h-6 rounded-full border-2 animate-spin"
            style={{ borderColor: `${evtColor} transparent transparent transparent` }}
          />
        </div>
      ) : isError ? (
        <ErrorState />
      ) : !hasEvents ? (
        <EmptyState />
      ) : (
        <div className="flex flex-1 overflow-hidden">
          {/* Left: MiniCalendar + source legend */}
          <div
            className="shrink-0 flex flex-col overflow-y-auto"
            style={{ width: 220, borderRight: `1px solid rgb(var(--canvas-border))`, background: 'rgb(var(--canvas-surface))' }}
          >
            <MiniCalendar
              focusedDate={focusedDate}
              selectedDate={selectedDate}
              markers={eventMarkers}
              onSelect={handleMiniCalendarSelect}
            />

            {/* Source color legend */}
            {sourceTypes.length > 0 && (
              <div className="px-3 py-3 flex flex-col gap-2">
                <span
                  className="text-[10px] font-semibold uppercase tracking-wider"
                  style={{ color: 'rgb(var(--canvas-fg-3))' }}
                >
                  Calendars
                </span>
                {sourceTypes.map(type => {
                  const color = sourceColor(type, null);
                  return (
                    <div key={type} className="flex items-center gap-2">
                      <span
                        className="shrink-0 rounded-full"
                        style={{ width: 8, height: 8, background: color }}
                      />
                      <span
                        className="text-xs truncate"
                        style={{ color: 'rgb(var(--canvas-fg-2))' }}
                      >
                        {type.replace(/_/g, ' ')}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Main: Calendar */}
          <div className="flex-1 overflow-hidden">
            <Calendar
              view={viewMode}
              focusedDate={focusedDate}
              selectedDate={selectedDate}
              events={calendarEvents}
              calendarColors={SOURCE_PALETTE}
              onChangeView={v => setViewMode(v)}
              onNavigate={setFocusedDate}
              onSelectDate={selectDate}
              renderEvent={renderCalendarEvent}
              style={{ height: '100%' }}
            />
          </div>

          {/* Right: Day agenda panel */}
          <div
            className="w-72 shrink-0 flex flex-col overflow-hidden"
            style={{ borderLeft: `1px solid rgb(var(--canvas-border))`, background: 'rgb(var(--canvas-surface))' }}
          >
            <DayAgendaPanel dateKey={selectedDateKey} events={selectedDayEvents} />
          </div>
        </div>
      )}
    </div>
  );
}
