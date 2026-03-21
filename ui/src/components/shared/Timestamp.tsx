import type { ReactNode } from 'react';

interface TimestampProps {
  /** ISO 8601 timestamp string */
  value: string;
  /** Level of detail: 'date' for YYYY-MM-DD, 'datetime' for full ISO 8601 */
  granularity?: 'date' | 'datetime';
}

/**
 * Consistent ISO 8601 timestamp display across domain views.
 *
 * @example
 * <Timestamp value={isoString} granularity="date" />
 */
export function Timestamp({ value, granularity = 'datetime' }: TimestampProps): ReactNode {
  try {
    const date = new Date(value);
    if (isNaN(date.getTime())) {
      return <span className="text-gray-500">Invalid date</span>;
    }

    if (granularity === 'date') {
      // YYYY-MM-DD format
      return <span className="text-sm">{date.toISOString().split('T')[0]}</span>;
    }

    // 'datetime' - full ISO 8601 with time, but displayed in local format
    return <span className="text-sm">{date.toLocaleString()}</span>;
  } catch {
    return <span className="text-gray-500">Invalid date</span>;
  }
}
