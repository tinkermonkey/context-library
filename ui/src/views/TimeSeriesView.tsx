import type { ReactNode } from 'react';
import { useMemo, useState } from 'react';
import { useNavigate, useSearch } from '@tanstack/react-router';
import type { ChunkResponse } from '../types/api';
import type { DomainViewProps } from './registry';
import { Timestamp } from '../components/shared/Timestamp';

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
 * Format duration in minutes to a human-readable string.
 * Returns '1h 30m' format, or null if no duration available.
 */
function formatDuration(durationMinutes: number | null): string | null {
  if (durationMinutes === null) return null;
  const hours = Math.floor(durationMinutes / 60);
  const minutes = durationMinutes % 60;
  if (hours > 0 && minutes > 0) {
    return `${hours}h ${minutes}m`;
  } else if (hours > 0) {
    return `${hours}h`;
  } else {
    return `${minutes}m`;
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
 * Format a date string as a human-readable day header.
 * Example: 'Monday, January 15 2024'
 */
function formatDayHeader(dateStr: string): string {
  try {
    const date = new Date(dateStr + 'T00:00:00Z');
    const formatter = new Intl.DateTimeFormat('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
    return formatter.format(date);
  } catch {
    return dateStr;
  }
}

/**
 * Group chunks by day, filtering by date range.
 * Returns a Map with date keys (YYYY-MM-DD) in chronological order.
 */
function groupEventsByDay(
  chunks: ChunkResponse[],
  dateFrom?: string,
  dateTo?: string
): Map<string, ChunkResponse[]> {
  const grouped = new Map<string, ChunkResponse[]>();

  // Parse date range
  let fromDate: Date | null = null;
  let toDate: Date | null = null;
  if (dateFrom) {
    fromDate = new Date(dateFrom + 'T00:00:00Z');
  }
  if (dateTo) {
    toDate = new Date(dateTo + 'T23:59:59Z');
  }

  // Process each chunk
  for (const chunk of chunks) {
    const metadata = extractEventMetadata(chunk);
    if (!metadata || !metadata.start_date) continue;

    const dateKey = getDatePortion(metadata.start_date);
    if (!dateKey) continue;

    // Apply date range filter
    const chunkDate = new Date(dateKey + 'T00:00:00Z');
    if (fromDate && chunkDate < fromDate) continue;
    if (toDate && chunkDate > toDate) continue;

    if (!grouped.has(dateKey)) {
      grouped.set(dateKey, []);
    }
    grouped.get(dateKey)!.push(chunk);
  }

  // Sort chunks within each day by start_date (ascending)
  for (const dayChunks of grouped.values()) {
    dayChunks.sort((a, b) => {
      const aTime = extractEventMetadata(a)?.start_date || '';
      const bTime = extractEventMetadata(b)?.start_date || '';
      return aTime.localeCompare(bTime);
    });
  }

  // Return sorted by date keys (chronologically)
  const sorted = new Map(
    Array.from(grouped.entries()).sort(([keyA], [keyB]) => keyA.localeCompare(keyB))
  );

  return sorted;
}

/**
 * Render a single event card.
 */
function EventCard({ chunk }: { chunk: ChunkResponse }): ReactNode {
  const metadata = extractEventMetadata(chunk);
  if (!metadata) return null;

  const allDay = isAllDay(metadata.start_date);
  const duration = metadata.duration_minutes
    ? formatDuration(metadata.duration_minutes)
    : null;

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
      {!allDay && metadata.start_date && metadata.end_date && (
        <div className="text-sm text-gray-700 mb-3">
          <Timestamp value={metadata.start_date} granularity="datetime" /> –{' '}
          <Timestamp value={metadata.end_date} granularity="datetime" />
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
 * Displays events in temporal order with day-based grouping and date-range filtering.
 *
 * Features:
 * - Events displayed in ascending start_date order
 * - Events grouped under day headers (e.g., 'Monday, January 15 2024')
 * - All-day events visually distinguished with 'All Day' badge
 * - Timed events show start–end times and duration
 * - Per-event metadata: title, host, invitees
 * - Date-range filtering via dateFrom/dateTo URL params
 * - Shareable URLs with filters
 * - Empty state when no events match filter
 */
export function TimeSeriesView({ sourceId, chunks }: DomainViewProps): ReactNode {
  const navigate = useNavigate();
  const search = useSearch({ from: '/browser/view/$domain/$sourceId' }) as {
    dateFrom?: string;
    dateTo?: string;
  };

  const [dateFromInput, setDateFromInput] = useState<string>(search.dateFrom || '');
  const [dateToInput, setDateToInput] = useState<string>(search.dateTo || '');

  // Group events by day with filtering
  const groupedEvents = useMemo(
    () => groupEventsByDay(chunks, search.dateFrom, search.dateTo),
    [chunks, search.dateFrom, search.dateTo]
  );

  // Handle date range filter application
  const handleApplyFilter = () => {
    navigate({
      search: (prev) => ({
        ...prev,
        dateFrom: dateFromInput || undefined,
        dateTo: dateToInput || undefined,
      }),
    });
  };

  // Handle clear filter
  const handleClearFilter = () => {
    setDateFromInput('');
    setDateToInput('');
    navigate({
      search: (prev) => ({
        ...prev,
        dateFrom: undefined,
        dateTo: undefined,
      }),
    });
  };

  return (
    <div className="max-w-4xl mx-auto">
      {/* Date range filter controls */}
      <div className="mb-8 p-6 border border-gray-200 rounded-lg bg-gray-50">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Filter by Date Range</h2>
        <div className="flex gap-4 items-end">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              From Date
            </label>
            <input
              type="date"
              value={dateFromInput}
              onChange={(e) => setDateFromInput(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              To Date
            </label>
            <input
              type="date"
              value={dateToInput}
              onChange={(e) => setDateToInput(e.target.value)}
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
      </div>

      {/* Events timeline */}
      {groupedEvents.size > 0 ? (
        <div>
          {Array.from(groupedEvents.entries()).map(([dateKey, dayChunks]) => (
            <div key={dateKey} className="mb-8">
              {/* Day header */}
              <h2 className="text-xl font-bold text-gray-900 mb-4 pb-2 border-b-2 border-blue-200">
                {formatDayHeader(dateKey)}
              </h2>

              {/* Events for this day */}
              {dayChunks.map((chunk) => (
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
