import type { ReactNode } from 'react';
import { Spinner } from 'flowbite-react';
import { useSourceChunks } from '../../hooks/useChunks';
import { ChunkContent } from '../shared/ChunkContent';
import { ChunkBoundary } from '../shared/ChunkBoundary';

interface FileContentPanelProps {
  /** The selected source ID, or null if no source is selected */
  selectedSourceId: string | null;
}

/**
 * Center panel component that displays the full content of a selected file.
 * Fetches chunks from the selected source, renders them in ascending chunk_index order,
 * and displays them as a continuous document using ChunkContent with ChunkBoundary separators.
 *
 * @example
 * <FileContentPanel selectedSourceId="filesystem:///path/to/file.txt" />
 */
export function FileContentPanel({ selectedSourceId }: FileContentPanelProps): ReactNode {
  // Always call the hook at the top level (even if selectedSourceId is null)
  // The hook will be disabled when selectedSourceId is null
  const { data: chunksData, isLoading, isError, error } = useSourceChunks(
    selectedSourceId ?? ''
  );

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

  // Extract chunks from response
  const chunks = chunksData?.chunks ?? [];

  // Show explicit empty-content message when source has zero chunks
  if (chunks.length === 0) {
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
  const sortedChunks = [...chunks].sort((a, b) => a.chunk_index - b.chunk_index);

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
