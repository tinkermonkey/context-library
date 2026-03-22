import type { ReactNode } from 'react';

interface ChunkBoundaryProps {
  /** Optional label or identifier for this boundary */
  label?: string | null;
}

/**
 * Subtle horizontal visual separator between assembled chunks.
 * Used in document and thread views to separate distinct content units.
 *
 * @example
 * <ChunkBoundary />
 * <ChunkBoundary label="Message 2" />
 */
export function ChunkBoundary({ label }: ChunkBoundaryProps): ReactNode {
  if (label) {
    return (
      <div className="flex items-center gap-2 my-4">
        <div className="flex-1 border-t border-gray-200" />
        <span className="text-xs text-gray-400 px-2">{label}</span>
        <div className="flex-1 border-t border-gray-200" />
      </div>
    );
  }

  return <div className="border-t border-gray-200 my-4" />;
}
