/**
 * Shared formatting utilities used across domain views.
 */

/**
 * Format duration in minutes to a human-readable string.
 * Returns null if duration is null or 0.
 *
 * @example
 * formatDuration(90) => "1h 30m"
 * formatDuration(60) => "1h"
 * formatDuration(45) => "45m"
 */
export function formatDuration(durationMinutes: number | null): string | null {
  if (durationMinutes === null || durationMinutes === 0) return null;
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
 * Format a date string as a human-readable day header.
 * Converts ISO date (YYYY-MM-DD) to localized format.
 *
 * @example
 * formatDayHeader('2026-03-21') => "Saturday, March 21 2026"
 */
export function formatDayHeader(dateStr: string): string {
  try {
    const date = new Date(dateStr + 'T00:00:00Z');
    const formatter = new Intl.DateTimeFormat('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      timeZone: 'UTC',
    });
    return formatter.format(date);
  } catch {
    return dateStr;
  }
}

/**
 * Get the ISO week number for a date.
 * Week 1 is the first week with a Thursday in the year (ISO 8601).
 *
 * @example
 * getISOWeekNumber('2026-03-21') => 12
 */
export function getISOWeekNumber(dateStr: string): number {
  try {
    const date = new Date(dateStr + 'T00:00:00Z');
    // Create a copy to avoid mutating the original
    const d = new Date(date);
    d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    const weekNum = Math.ceil((((d.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
    return weekNum;
  } catch {
    return 0;
  }
}

/**
 * Format a week header with date range.
 * Shows the start and end dates of the ISO week.
 *
 * @example
 * formatWeekHeader('2026-03-21') => "Week 12: March 16 – March 22, 2026"
 */
export function formatWeekHeader(dateStr: string): string {
  try {
    const date = new Date(dateStr + 'T00:00:00Z');
    const weekNum = getISOWeekNumber(dateStr);

    // Calculate Monday (start of week)
    const d = new Date(date);
    const day = d.getUTCDay();
    const diff = d.getUTCDate() - day + (day === 0 ? -6 : 1);
    const monday = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), diff));

    // Calculate Sunday (end of week)
    const sunday = new Date(monday);
    sunday.setUTCDate(sunday.getUTCDate() + 6);

    const dateFormatter = new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      timeZone: 'UTC',
    });

    const yearFormatter = new Intl.DateTimeFormat('en-US', {
      year: 'numeric',
      timeZone: 'UTC',
    });

    const mondayStr = dateFormatter.format(monday);
    const sundayStr = dateFormatter.format(sunday);
    const year = yearFormatter.format(sunday);

    return `Week ${weekNum}: ${mondayStr} – ${sundayStr}, ${year}`;
  } catch {
    return dateStr;
  }
}
