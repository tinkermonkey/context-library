import type { ReactNode } from 'react';

interface StatusBadgeProps {
  /** Status or lifecycle state (e.g., "open", "in-progress", "completed", "cancelled") */
  status: string | null | undefined;
}

/**
 * Visual indicator for lifecycle state.
 * Provides consistent styling for task/event status across domain views.
 *
 * @example
 * <StatusBadge status="in-progress" />
 */
export function StatusBadge({ status }: StatusBadgeProps): ReactNode {
  if (!status) {
    return <span className="text-gray-500">—</span>;
  }

  // Map statuses to Tailwind color classes
  const colorMap: Record<string, { bg: string; text: string }> = {
    open: { bg: 'bg-yellow-100', text: 'text-yellow-800' },
    'in-progress': { bg: 'bg-blue-100', text: 'text-blue-800' },
    'in_progress': { bg: 'bg-blue-100', text: 'text-blue-800' },
    completed: { bg: 'bg-green-100', text: 'text-green-800' },
    cancelled: { bg: 'bg-red-100', text: 'text-red-800' },
  };

  const colors = colorMap[status.toString().toLowerCase()] || { bg: 'bg-gray-100', text: 'text-gray-800' };

  return (
    <span className={`inline-block px-2 py-1 rounded text-xs font-semibold ${colors.bg} ${colors.text}`}>
      {status}
    </span>
  );
}
