import type { ReactNode } from 'react';

interface ChunkTypeBadgeProps {
  /** Chunk type string (e.g., "message", "note", "event", "task", "health_metric", "document") */
  type: string;
}

/**
 * Color-coded badge for chunk types.
 * Provides consistent visual identification of content type across all views.
 *
 * @example
 * <ChunkTypeBadge type="message" />
 */
export function ChunkTypeBadge({ type }: ChunkTypeBadgeProps): ReactNode {
  // Map chunk types to Tailwind color classes
  const colorMap: Record<string, { bg: string; text: string }> = {
    message: { bg: 'bg-blue-100', text: 'text-blue-800' },
    note: { bg: 'bg-purple-100', text: 'text-purple-800' },
    event: { bg: 'bg-green-100', text: 'text-green-800' },
    task: { bg: 'bg-orange-100', text: 'text-orange-800' },
    health_metric: { bg: 'bg-red-100', text: 'text-red-800' },
    document: { bg: 'bg-cyan-100', text: 'text-cyan-800' },
  };

  const colors = colorMap[type.toLowerCase()] || { bg: 'bg-gray-100', text: 'text-gray-800' };

  return (
    <span className={`inline-block px-2 py-1 rounded text-xs font-semibold ${colors.bg} ${colors.text}`}>
      {type}
    </span>
  );
}
