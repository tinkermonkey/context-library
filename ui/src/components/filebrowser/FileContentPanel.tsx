import type { ReactNode } from 'react';
import { Spinner } from 'flowbite-react';
import type { ChunkResponse } from '../../types/api';
import { ChunkContent } from '../shared/ChunkContent';
import { ChunkBoundary } from '../shared/ChunkBoundary';

interface FileContentPanelProps {
  /** The selected source ID, or null if no source is selected */
  selectedSourceId: string | null;
  /** Chunks for the selected source */
  chunks: ChunkResponse[] | undefined;
  /** Whether chunks are currently loading */
  isLoading: boolean;
  /** Whether an error occurred while loading chunks */
  isError: boolean;
  /** The error object if isError is true */
  error: Error | null;
}

/**
 * Center panel component that displays the full content of a selected file.
 * Renders chunks in ascending chunk_index order and displays them as a continuous document
 * using ChunkContent with ChunkBoundary separators.
 *
 * Chunks, loading state, and error state are managed by the parent component to avoid
 * duplicate data fetching when multiple panels need the same data.
 *
 * @example
 * <FileContentPanel selectedSourceId="filesystem:///path/to/file.txt" chunks={chunks} isLoading={isLoading} isError={isError} error={error} />
 */
export function FileContentPanel({ selectedSourceId, chunks, isLoading, isError, error }: FileContentPanelProps): ReactNode {
  // Show placeholder when no source is selected
  if (!selectedSourceId) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <div className="text-center">
          <p className="text-lg">No file selected</p>
          <p className="text-sm mt-2">Select a file from the browser to view its contents</p>
        </div>
      </div>
    );
  }

  // Show error state
  if (isError) {
    return (
      <div className="p-6 bg-red-50 border border-red-200 rounded">
        <p className="text-red-900 font-semibold">Failed to load file contents</p>
        <p className="text-red-800 text-sm mt-2">
          {error instanceof Error ? error.message : 'An unexpected error occurred'}
        </p>
      </div>
    );
  }

  // Show loading spinner while chunks are fetching
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <Spinner color="info" size="lg" />
          <p className="text-gray-600 mt-4">Loading file contents…</p>
        </div>
      </div>
    );
  }

  // Extract chunks from props
  const chunksToRender = chunks ?? [];

  // Show explicit empty-content message when source has zero chunks
  if (chunksToRender.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <div className="text-center">
          <p className="text-lg">This file has no content</p>
          <p className="text-sm mt-2">The selected source contains no chunks</p>
        </div>
      </div>
    );
  }

  // Sort chunks by chunk_index in ascending order
  const sortedChunks = [...chunksToRender].sort((a, b) => a.chunk_index - b.chunk_index);

  // Render chunks in order with boundaries between them
  return (
    <div className="prose prose-sm max-w-none">
      {sortedChunks.map((chunk, index) => (
        <div key={chunk.chunk_hash}>
          {index > 0 && <ChunkBoundary />}
          <ChunkContent chunk={chunk} />
        </div>
      ))}
    </div>
  );
}
