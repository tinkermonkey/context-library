import type { ReactNode } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { useChunk } from '../../hooks/useChunks';

interface CrossRefLinkProps {
  /** The hash of the referenced chunk */
  chunkHash: string;
}

/**
 * Single cross-reference link with lazy chunk lookup.
 * Fetches chunk metadata and navigates to its location when clicked.
 *
 * @example
 * <CrossRefLink chunkHash="abc123..." />
 */
export function CrossRefLink({ chunkHash }: CrossRefLinkProps): ReactNode {
  const navigate = useNavigate();

  // Fetch chunk data to get its source_id and domain
  // No source_id filter allows cross-source references to be resolved
  const { data: refChunk, isError } = useChunk(chunkHash);

  const handleClick = (): void => {
    if (!refChunk) {
      return;
    }

    const refSourceId = refChunk.lineage.source_id;
    const refDomain = refChunk.lineage.domain;

    void navigate({
      to: '/browser/view/$domain/$sourceId',
      params: { domain: refDomain, sourceId: refSourceId },
    });
  };

  if (!refChunk && !isError) {
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

  if (isError || !refChunk) {
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
      className="px-3 py-1 bg-blue-100 hover:bg-blue-200 text-blue-700 text-xs rounded transition-colors cursor-pointer"
      title={chunkHash}
    >
      {refChunk.lineage.domain}: {chunkHash.substring(0, 8)}…
    </button>
  );
}
