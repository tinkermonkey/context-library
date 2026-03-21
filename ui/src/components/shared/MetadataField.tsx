import type { ReactNode } from 'react';

interface MetadataFieldProps {
  /** Label for the metadata field */
  label: string;
  /** Value to display (handles null/undefined gracefully) */
  value: unknown;
}

/**
 * Key-value pair display for metadata.
 * Handles null and undefined values gracefully.
 *
 * @example
 * <MetadataField label="Priority" value={task.priority} />
 */
export function MetadataField({ label, value }: MetadataFieldProps): ReactNode {
  const displayValue = formatValue(value);

  return (
    <div className="flex justify-between items-start py-1">
      <span className="text-sm font-semibold text-gray-700">{label}:</span>
      <span className="text-sm text-gray-600">{displayValue}</span>
    </div>
  );
}

/**
 * Format a value for display.
 * Handles null, undefined, booleans, arrays, objects, and primitives.
 */
function formatValue(value: unknown): ReactNode {
  if (value === null || value === undefined) {
    return <span className="text-gray-400">—</span>;
  }

  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }

  if (typeof value === 'object') {
    if (Array.isArray(value)) {
      return value.length === 0 ? '(empty)' : `[${value.length} items]`;
    }
    return '(object)';
  }

  return String(value);
}
