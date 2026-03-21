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
