import type { ReactNode } from 'react';
import type { ChunkResponse } from '../../types/api';
import { useSource } from '../../hooks/useSources';
import { MetadataField } from '../shared/MetadataField';
import { Timestamp } from '../shared/Timestamp';

interface FileMetadataPanelProps {
  /** The selected source ID, or null if no source is selected */
  selectedSourceId: string | null;
  /** Chunks for the selected source (optional; if provided, chunk-level metadata will be displayed) */
  chunks: ChunkResponse[] | undefined;
  /** Whether chunks are currently loading */
  isLoading: boolean;
  /** Whether an error occurred while loading chunks */
  isError: boolean;
}

/**
 * Right panel component that displays metadata about the selected file.
 * Fetches and displays both source-level metadata (from useSource hook) and chunk-level metadata
 * (from domain_metadata on the first chunk).
 *
 * Source-level metadata includes:
 * - chunk_count: Total number of chunks for this source
 * - created_at, updated_at, last_fetched_at: Source timestamps
 *
 * Chunk-level metadata (from domain_metadata) includes:
 * - title, document_type, file_size_bytes, created_at, modified_at, author, tags
 * - Domain-specific fields (music, YouTube)
 *
 * Renders only fields that are present; omits absent fields entirely.
 *
 * @example
 * <FileMetadataPanel selectedSourceId="filesystem:///path/to/file.txt" chunks={chunks} isLoading={isLoading} isError={isError} />
 */
export function FileMetadataPanel({ selectedSourceId, chunks, isLoading, isError }: FileMetadataPanelProps): ReactNode {
  // Fetch source-level metadata
  const {
    data: sourceData,
    isLoading: isSourceLoading,
    isError: isSourceError,
  } = useSource(selectedSourceId ?? '');
  const source = sourceData && selectedSourceId ? sourceData : null;
  // Show placeholder when no source is selected
  if (!selectedSourceId) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <div className="text-center">
          <p className="text-lg">No file selected</p>
          <p className="text-sm mt-2">Select a file to view its metadata</p>
        </div>
      </div>
    );
  }

  // Show loading state while source metadata is being fetched
  if (isSourceLoading || isLoading) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <div className="text-center">
          <p className="text-sm">Loading metadata…</p>
        </div>
      </div>
    );
  }

  // Show error state
  if (isError || isSourceError) {
    return (
      <div className="flex items-center justify-center h-full bg-red-50">
        <div className="text-center">
          <p className="text-lg font-semibold text-red-700 mb-2">Failed to load metadata</p>
          <p className="text-sm text-red-600">Please try selecting a different file</p>
        </div>
      </div>
    );
  }

  // Return error state if source not found
  if (!source) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <div className="text-center">
          <p className="text-lg">Source not found</p>
        </div>
      </div>
    );
  }

  const chunksToRender = chunks ?? [];

  // Extract chunk-level metadata from the first chunk's domain_metadata
  const domainMetadata = chunksToRender.length > 0 ? chunksToRender[0].domain_metadata : null;

  // Extract metadata fields from chunk-level domain_metadata, only if they exist
  const title = domainMetadata?.title;
  const documentType = domainMetadata?.document_type;
  const fileSizeBytes = domainMetadata?.file_size_bytes;
  const createdAt = domainMetadata?.created_at;
  const modifiedAt = domainMetadata?.modified_at;
  const author = domainMetadata?.author;
  const tags = Array.isArray(domainMetadata?.tags) ? domainMetadata.tags : [];

  return (
    <div className="space-y-6">
      {/* Source-level metadata section */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-gray-700 border-b pb-2">Source</h3>
        {source.display_name && <MetadataField label="Name" value={source.display_name} />}
        {source.chunk_count !== undefined && source.chunk_count !== null && (
          <MetadataField label="Chunks" value={source.chunk_count.toString()} />
        )}
        {source.created_at && typeof source.created_at === 'string' && (
          <div className="flex justify-between items-start py-1">
            <span className="text-sm font-semibold text-gray-700">Created:</span>
            <Timestamp value={source.created_at} granularity="datetime" />
          </div>
        )}
        {source.updated_at && typeof source.updated_at === 'string' && (
          <div className="flex justify-between items-start py-1">
            <span className="text-sm font-semibold text-gray-700">Updated:</span>
            <Timestamp value={source.updated_at} granularity="datetime" />
          </div>
        )}
        {source.last_fetched_at && typeof source.last_fetched_at === 'string' && (
          <div className="flex justify-between items-start py-1">
            <span className="text-sm font-semibold text-gray-700">Last Fetched:</span>
            <Timestamp value={source.last_fetched_at} granularity="datetime" />
          </div>
        )}
      </div>

      {/* Chunk-level metadata section (from domain_metadata) */}
      {domainMetadata && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-gray-700 border-b pb-2">Document</h3>
          {title !== undefined && title !== null && <MetadataField label="Title" value={title} />}
          {documentType !== undefined && documentType !== null && (
            <MetadataField label="Type" value={documentType} />
          )}
          {author !== undefined && author !== null && <MetadataField label="Author" value={author} />}
          {fileSizeBytes !== undefined && fileSizeBytes !== null && typeof fileSizeBytes === 'number' && (
            <MetadataField label="Size" value={formatBytes(fileSizeBytes)} />
          )}
          {createdAt !== undefined && createdAt !== null && typeof createdAt === 'string' && (
            <div className="flex justify-between items-start py-1">
              <span className="text-sm font-semibold text-gray-700">Created:</span>
              <Timestamp value={createdAt} granularity="datetime" />
            </div>
          )}
          {modifiedAt !== undefined && modifiedAt !== null && typeof modifiedAt === 'string' && (
            <div className="flex justify-between items-start py-1">
              <span className="text-sm font-semibold text-gray-700">Modified:</span>
              <Timestamp value={modifiedAt} granularity="datetime" />
            </div>
          )}
          {tags.length > 0 && (
            <div className="py-1">
              <span className="text-sm font-semibold text-gray-700 block mb-1">Tags:</span>
              <div className="flex flex-wrap gap-1">
                {tags.map((tag) => (
                  <span key={tag} className="inline-block px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded">
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Format bytes into human-readable file size (e.g., "1.5 MB").
 * Handles edge cases: negative numbers, zero, and values beyond GB.
 */
function formatBytes(bytes: number): string {
  if (bytes < 0) return '0 B';
  if (bytes === 0) return '0 B';

  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), sizes.length - 1);

  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}
