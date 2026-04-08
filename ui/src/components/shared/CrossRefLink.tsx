import { useState, type ReactNode } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { useChunk } from '../../hooks/useChunks';

interface CrossRefLinkProps {
  /** The hash of the referenced chunk */
  chunkHash: string;
}

/**
 * Single cross-reference link with eager chunk lookup.
 * Fetches chunk metadata on mount and navigates to its location when clicked.
 * Includes loading and error states with visual feedback.
 *
 * @example
 * <CrossRefLink chunkHash="abc123..." />
 */
export function CrossRefLink({ chunkHash }: CrossRefLinkProps): ReactNode {
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(false);

  // Fetch chunk data to get its source_id and domain
  // No source_id filter allows cross-source references to be resolved
  const { data: refChunk } = useChunk(chunkHash);

  const handleClick = (): void => {
    if (!refChunk) {
      setError(true);
      return;
    }

    setIsLoading(true);
    const refSourceId = refChunk.lineage.source_id;
    const refDomain = refChunk.lineage.domain;

    void navigate({
      to: '/browser/view/$domain/$sourceId',
      params: { domain: refDomain, sourceId: refSourceId },
    }).finally(() => {
      setIsLoading(false);
    });
  };

  if (!refChunk && !error) {
    // Still loading
    return (
      <span
        className="px-3 py-1 bg-gray-200 text-gray-700 text-xs rounded"
        title={chunkHash}
      >
        {chunkHash.substring(0, 8)}…
      </span>
    );
  }

  if (error || !refChunk) {
    return (
      <span
        className="px-3 py-1 bg-red-100 text-red-700 text-xs rounded cursor-not-allowed"
        title={`Failed to resolve: ${chunkHash}`}
      >
        {chunkHash.substring(0, 8)}… (broken)
      </span>
    );
  }

  return (
    <button
      onClick={handleClick}
      disabled={isLoading}
      className="px-3 py-1 bg-blue-100 hover:bg-blue-200 text-blue-700 text-xs rounded transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
      title={chunkHash}
    >
      {refChunk.lineage.domain}: {chunkHash.substring(0, 8)}…
    </button>
  );
}
