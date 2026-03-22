import type { ReactNode } from 'react';
import { useEffect, useRef, useMemo, useState } from 'react';
import { useNavigate, useSearch } from '@tanstack/react-router';
import type { ChunkResponse } from '../types/api';
import type { DomainViewProps } from './registry';
import { eventsViewSearchSchema } from '../routes-config';
import { Timestamp } from '../components/shared/Timestamp';
import { formatDuration, formatDayHeader, formatWeekHeader, getISOWeekNumber } from '../utils/formatters';

/**
 * Event domain metadata structure.
 * Matches the backend EventMetadata model.
 */
interface EventMetadata {
  event_id: string;
  title: string;
  start_date: string | null; // ISO 8601 (date-only = all-day, datetime = timed)
  end_date: string | null; // ISO 8601
  duration_minutes: number | null;
  host: string | null;
  invitees: string[]; // serialized from tuple
  date_first_observed: string; // ISO 8601
  source_type: string;
}

/**
 * Cast domain_metadata to EventMetadata with safety checks.
 * Validates that required fields are present and have correct types.
 */
function extractEventMetadata(chunk: ChunkResponse): EventMetadata | null {
  if (!chunk.domain_metadata) return null;

  const meta = chunk.domain_metadata;

  // Validate required fields
  if (typeof meta.event_id !== 'string' || typeof meta.title !== 'string') {
    return null;
  }

  return {
    event_id: meta.event_id,
    title: meta.title,
    start_date: typeof meta.start_date === 'string' ? meta.start_date : null,
    end_date: typeof meta.end_date === 'string' ? meta.end_date : null,
    duration_minutes: typeof meta.duration_minutes === 'number' ? meta.duration_minutes : null,
    host: typeof meta.host === 'string' ? meta.host : null,
    invitees: Array.isArray(meta.invitees) ? meta.invitees : [],
    date_first_observed: typeof meta.date_first_observed === 'string' ? meta.date_first_observed : '',
    source_type: typeof meta.source_type === 'string' ? meta.source_type : '',
  };
}

/**
 * Check if a date string represents an all-day event.
 * All-day events have date-only format: YYYY-MM-DD (10 chars, no 'T')
 */
function isAllDay(isoString: string | null): boolean {
  if (!isoString) return false;
  return isoString.length === 10 && !isoString.includes('T');
}

/**
 * Compute duration in minutes from start_date and end_date ISO strings.
 * Returns null if either date is missing or invalid.
 */
function computeDurationFromDates(
  startDate: string | null,
  endDate: string | null
): number | null {
  if (!startDate || !endDate) return null;
  try {
    const start = new Date(startDate);
    const end = new Date(endDate);
    if (isNaN(start.getTime()) || isNaN(end.getTime())) return null;
    const minutes = Math.round((end.getTime() - start.getTime()) / (1000 * 60));
    return minutes > 0 ? minutes : null;
  } catch {
    return null;
  }
}

/**
 * Extract the date portion (YYYY-MM-DD) from an ISO 8601 string.
 */
function getDatePortion(isoString: string | null): string | null {
  if (!isoString) return null;
  return isoString.substring(0, 10);
}


/**
 * Get the ISO week key for a date in format: YYYY-W##
 * Example: "2026-W12"
 */
function getWeekKey(dateStr: string): string | null {
  try {
    const date = new Date(dateStr + 'T00:00:00Z');
    const weekNum = getISOWeekNumber(dateStr);
    const year = date.getUTCFullYear();
    return `${year}-W${String(weekNum).padStart(2, '0')}`;
  } catch {
    return null;
  }
}

/**
 * Get the first date of a week given a week key (YYYY-W##).
 * Returns ISO date string (YYYY-MM-DD).
 */
function getWeekStartDate(weekKey: string): string | null {
  try {
    const [yearStr, weekStr] = weekKey.split('-W');
    const year = parseInt(yearStr, 10);
    const week = parseInt(weekStr, 10);

    // Calculate Monday of the given ISO week
    const simple = new Date(Date.UTC(year, 0, 1 + (week - 1) * 7));
    const dow = simple.getUTCDay();
    const ISOweekStart = simple;
    if (dow <= 4) {
      ISOweekStart.setUTCDate(simple.getUTCDate() - simple.getUTCDay() + 1);
    } else {
      ISOweekStart.setUTCDate(simple.getUTCDate() + 8 - simple.getUTCDay());
    }

    const year1 = ISOweekStart.getUTCFullYear();
    const month1 = String(ISOweekStart.getUTCMonth() + 1).padStart(2, '0');
    const date1 = String(ISOweekStart.getUTCDate()).padStart(2, '0');
    return `${year1}-${month1}-${date1}`;
  } catch {
    return null;
  }
}

/**
 * Typed structure for grouped events (day or week).
 */
interface GroupedEvents {
  type: 'day' | 'week';
  key: string;
  label: string;
  chunks: ChunkResponse[];
}

/**
 * Group chunks by day or week, filtering by date range.
 * Returns a typed array of GroupedEvents objects.
 */
function groupEventsByGroupMode(
  chunks: ChunkResponse[],
  mode: 'day' | 'week',
  dateFrom?: string,
  dateTo?: string
): GroupedEvents[] {
  // Cache metadata to avoid redundant extraction during sort
  const metadataCache = new Map<ChunkResponse, EventMetadata | null>();

  // Parse date range
  let fromDate: Date | null = null;
  let toDate: Date | null = null;
  if (dateFrom) {
    fromDate = new Date(dateFrom + 'T00:00:00Z');
  }
  if (dateTo) {
    toDate = new Date(dateTo + 'T23:59:59Z');
  }

  // Group chunks by key (day or week)
  const grouped = new Map<string, ChunkResponse[]>();

  for (const chunk of chunks) {
    const metadata = extractEventMetadata(chunk);
    metadataCache.set(chunk, metadata);
    if (!metadata || !metadata.start_date) continue;

    const dateKey = getDatePortion(metadata.start_date);
    if (!dateKey) continue;

    // Apply date range filter
    const chunkDate = new Date(dateKey + 'T00:00:00Z');
    if (fromDate && chunkDate < fromDate) continue;
    if (toDate && chunkDate > toDate) continue;

    // Compute grouping key
    let groupKey = dateKey; // default to day
    if (mode === 'week') {
      const weekKey = getWeekKey(dateKey);
      if (!weekKey) continue;
      groupKey = weekKey;
    }

    if (!grouped.has(groupKey)) {
      grouped.set(groupKey, []);
    }
    grouped.get(groupKey)!.push(chunk);
  }

  // Sort chunks within each group by start_date (ascending)
  for (const groupChunks of grouped.values()) {
    groupChunks.sort((a, b) => {
      const aTime = metadataCache.get(a)?.start_date || '';
      const bTime = metadataCache.get(b)?.start_date || '';
      return aTime.localeCompare(bTime);
    });
  }

  // Convert to typed result array
  const result: GroupedEvents[] = Array.from(grouped.entries())
    .sort(([keyA], [keyB]) => keyA.localeCompare(keyB))
    .map(([key, groupChunks]) => {
      const label = mode === 'week'
        ? formatWeekHeader(getWeekStartDate(key) || '')
        : formatDayHeader(key);
      return { type: mode, key, label, chunks: groupChunks };
    });

  return result;
}

/**
 * Determine appropriate grouping mode based on date range span.
 * Returns 'week' for ranges >= 30 days, otherwise 'day'.
 */
function getAutoGroupMode(dateFrom?: string, dateTo?: string): 'day' | 'week' {
  if (!dateFrom || !dateTo) return 'day';

  try {
    const from = new Date(dateFrom + 'T00:00:00Z');
    const to = new Date(dateTo + 'T23:59:59Z');
    const diffDays = Math.ceil((to.getTime() - from.getTime()) / (1000 * 60 * 60 * 24));
    return diffDays >= 30 ? 'week' : 'day';
  } catch {
    return 'day';
  }
}

/**
 * Render a single event card.
 */
function EventCard({ chunk }: { chunk: ChunkResponse }): ReactNode {
  const metadata = extractEventMetadata(chunk);
  if (!metadata) return null;

  const allDay = isAllDay(metadata.start_date);
  // Use provided duration_minutes, fall back to computed duration, or null
  const durationMinutes =
    metadata.duration_minutes !== null
      ? metadata.duration_minutes
      : computeDurationFromDates(metadata.start_date, metadata.end_date);
  const duration = formatDuration(durationMinutes);

  return (
    <div className="border border-gray-200 rounded-lg p-4 mb-4 bg-white hover:shadow-md transition-shadow">
      {/* Event header */}
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="flex-1">
          <div className="flex items-baseline gap-2 mb-1">
            <h3 className="text-lg font-semibold text-gray-900">{metadata.title}</h3>
            {allDay && (
              <span className="text-xs font-semibold px-2 py-1 rounded bg-amber-100 text-amber-900">
                All Day
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Time range and duration */}
      {!allDay && metadata.start_date && (
        <div className="text-sm text-gray-700 mb-3">
          <Timestamp value={metadata.start_date} granularity="datetime" />
          {metadata.end_date && (
            <>
              {' – '}
              <Timestamp value={metadata.end_date} granularity="datetime" />
            </>
          )}
          {duration && <span className="text-gray-600 ml-2">({duration})</span>}
        </div>
      )}

      {/* Host */}
      {metadata.host && (
        <div className="text-sm text-gray-600 mb-2">
          <span className="text-gray-500">Host:</span> {metadata.host}
        </div>
      )}

      {/* Invitees */}
      {metadata.invitees.length > 0 && (
        <div className="text-sm text-gray-600">
          <span className="text-gray-500">Invitees:</span> {metadata.invitees.join(', ')}
        </div>
      )}
    </div>
  );
}

/**
 * Time-series (timeline) view for the events domain.
 *
 * Displays events in temporal order with day or week-based grouping and date-range filtering.
 *
 * Features:
 * - Events displayed in ascending start_date order
 * - Automatic grouping mode: week for 30+ day ranges, day otherwise
 * - Manual grouping override via groupBy URL parameter
 * - Day headers (e.g., 'Monday, January 15 2024') or week headers (e.g., 'Week 12: March 16 – March 22, 2026')
 * - All-day events visually distinguished with 'All Day' badge
 * - Timed events show start–end times and duration
 * - Per-event metadata: title, host, invitees
 * - Date-range filtering via dateFrom/dateTo URL params
 * - Shareable URLs with filters
 * - Empty state when no events match filter
 */
export function TimeSeriesView({ sourceId, chunks }: DomainViewProps): ReactNode {
  const navigate = useNavigate();
  const rawSearch = useSearch({ from: '/browser/view/$domain/$sourceId' });
  const search = eventsViewSearchSchema.parse(rawSearch);

  // Local state for inputs during editing (before "Apply Filter" is clicked)
  // Derived from URL params, but can be edited before applying
  const [pendingDateFrom, setPendingDateFrom] = useState<string>(search.dateFrom || '');
  const [pendingDateTo, setPendingDateTo] = useState<string>(search.dateTo || '');
  const prevSearchRef = useRef({ dateFrom: search.dateFrom, dateTo: search.dateTo });

  // Sync pending state when URL params change (e.g., browser back/forward)
  useEffect(() => {
    // Only update if the URL params actually changed (not on initial mount)
    if (
      prevSearchRef.current.dateFrom !== search.dateFrom ||
      prevSearchRef.current.dateTo !== search.dateTo
    ) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setPendingDateFrom(search.dateFrom || '');
      setPendingDateTo(search.dateTo || '');
      prevSearchRef.current = { dateFrom: search.dateFrom, dateTo: search.dateTo };
    }
  }, [search.dateFrom, search.dateTo]);

  // Determine grouping mode: explicit override or auto-detect based on date range
  const groupMode = search.groupBy || getAutoGroupMode(search.dateFrom, search.dateTo);
  const isAutoSelected = !search.groupBy;

  // Group events by day or week based on mode
  const groupedEvents = useMemo(
    () => groupEventsByGroupMode(chunks, groupMode, search.dateFrom, search.dateTo),
    [chunks, groupMode, search.dateFrom, search.dateTo]
  );

  // Handle date range filter application
  const handleApplyFilter = () => {
    navigate({
      to: '.',
      search: (prev: Record<string, unknown>) => ({
        ...prev,
        dateFrom: pendingDateFrom || undefined,
        dateTo: pendingDateTo || undefined,
      }),
    });
  };

  // Handle clear filter
  const handleClearFilter = () => {
    navigate({
      to: '.',
      search: (prev: Record<string, unknown>) => ({
        ...prev,
        dateFrom: undefined,
        dateTo: undefined,
      }),
    });
  };

  // Handle grouping mode change
  const handleGroupModeChange = (mode: 'day' | 'week') => {
    navigate({
      to: '.',
      search: (prev: Record<string, unknown>) => ({
        ...prev,
        groupBy: mode,
      }),
    });
  };

  return (
    <div className="max-w-4xl mx-auto">
      {/* Date range filter controls */}
      <div className="mb-8 p-6 border border-gray-200 rounded-lg bg-gray-50">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Filter by Date Range</h2>
        <div className="flex gap-4 items-end mb-4">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              From Date
            </label>
            <input
              type="date"
              value={pendingDateFrom}
              onChange={(e) => setPendingDateFrom(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              To Date
            </label>
            <input
              type="date"
              value={pendingDateTo}
              onChange={(e) => setPendingDateTo(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <button
            onClick={handleApplyFilter}
            className="px-6 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 transition-colors"
          >
            Apply Filter
          </button>
          {(search.dateFrom || search.dateTo) && (
            <button
              onClick={handleClearFilter}
              className="px-6 py-2 bg-gray-300 text-gray-900 text-sm font-medium rounded-md hover:bg-gray-400 transition-colors"
            >
              Clear Filter
            </button>
          )}
        </div>

        {/* Grouping mode indicator and toggle */}
        <div className="flex items-center gap-4 text-sm text-gray-600">
          <div>
            <span className="font-medium">Grouping:</span> {groupMode === 'week' ? 'By week' : 'By day'}
            {isAutoSelected && (
              <span className="text-gray-500 ml-2">(auto-selected)</span>
            )}
            {!isAutoSelected && (
              <span className="text-gray-500 ml-2">(manually selected)</span>
            )}
          </div>
          <div className="flex gap-2 border-l border-gray-300 pl-4">
            <button
              onClick={() => handleGroupModeChange('day')}
              className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                groupMode === 'day'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              Day
            </button>
            <button
              onClick={() => handleGroupModeChange('week')}
              className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                groupMode === 'week'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              Week
            </button>
          </div>
        </div>
      </div>

      {/* Events timeline */}
      {groupedEvents.length > 0 ? (
        <div>
          {groupedEvents.map((group) => (
            <div key={group.key} className="mb-8">
              {/* Day or week header */}
              <h2 className="text-xl font-bold text-gray-900 mb-4 pb-2 border-b-2 border-blue-200">
                {group.label}
              </h2>

              {/* Events for this day/week */}
              {group.chunks.map((chunk) => (
                <EventCard key={chunk.chunk_hash} chunk={chunk} />
              ))}
            </div>
          ))}
        </div>
      ) : (
        <div className="p-8 bg-blue-50 border border-blue-200 rounded-lg text-center">
          <p className="text-blue-900 font-semibold mb-2">No events found</p>
          <p className="text-blue-800 text-sm">
            {search.dateFrom || search.dateTo
              ? 'No events match the selected date range. Try adjusting your filters.'
              : 'No events available for this source.'}
          </p>
        </div>
      )}

      {/* View Raw Chunks link */}
      <div className="mt-8 pt-6 border-t border-gray-200">
        <button
          onClick={() =>
            navigate({
              to: '/browser',
              search: { table: 'chunks', source_id: sourceId },
            })
          }
          className="text-blue-600 hover:underline text-sm bg-none border-none cursor-pointer p-0"
        >
          View Raw Chunks
        </button>
      </div>
    </div>
  );
}
