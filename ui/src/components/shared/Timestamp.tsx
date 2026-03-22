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
  let dateString: string | null = null;
  let isInvalid = false;

  try {
    const date = new Date(value);
    if (isNaN(date.getTime())) {
      isInvalid = true;
    } else if (granularity === 'date') {
      // YYYY-MM-DD format
      dateString = date.toISOString().split('T')[0];
    } else {
      // 'datetime' - full ISO 8601 with time, but displayed in local format
      dateString = date.toLocaleString();
    }
  } catch {
    isInvalid = true;
  }

  if (isInvalid) {
    return <span className="text-gray-500">Invalid date</span>;
  }

  return <span className="text-sm">{dateString}</span>;
}
