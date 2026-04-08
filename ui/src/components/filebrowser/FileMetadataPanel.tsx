import type { ReactNode } from 'react';
import { useSourceChunks } from '../../hooks/useChunks';
import { MetadataField } from '../shared/MetadataField';
import { Timestamp } from '../shared/Timestamp';

interface FileMetadataPanelProps {
  /** The selected source ID, or null if no source is selected */
  selectedSourceId: string | null;
}

/**
 * Right panel component that displays metadata about the selected file.
 * Extracts metadata fields from domain_metadata on the fetched chunks:
 * - title: string
 * - document_type: string
 * - file_size_bytes: number
 * - modified_at: ISO 8601 timestamp string
 *
 * Renders only fields that are present in domain_metadata; omits absent fields entirely.
 *
 * @example
 * <FileMetadataPanel selectedSourceId="filesystem:///path/to/file.txt" />
 */
export function FileMetadataPanel({ selectedSourceId }: FileMetadataPanelProps): ReactNode {
  // Always call the hook at the top level (even if selectedSourceId is null)
  // The hook will be disabled when selectedSourceId is null
  const { data: chunksData } = useSourceChunks(selectedSourceId ?? '');

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

  const chunks = chunksData?.chunks ?? [];

  // Extract metadata from the first chunk (domain_metadata should be consistent across chunks for a source)
  const domainMetadata = chunks.length > 0 ? chunks[0].domain_metadata : null;

  if (!domainMetadata) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <div className="text-center">
          <p className="text-lg">No metadata available</p>
        </div>
      </div>
    );
  }

  // Extract metadata fields, only if they exist
  const title = domainMetadata.title;
  const documentType = domainMetadata.document_type;
  const fileSizeBytes = domainMetadata.file_size_bytes;
  const modifiedAt = domainMetadata.modified_at;

  return (
    <div className="space-y-4">
      {title !== undefined && title !== null && <MetadataField label="Title" value={title} />}
      {documentType !== undefined && documentType !== null && <MetadataField label="Type" value={documentType} />}
      {fileSizeBytes !== undefined && fileSizeBytes !== null && <MetadataField label="Size" value={formatBytes(fileSizeBytes as number)} />}
      {modifiedAt !== undefined && modifiedAt !== null && (
        <div className="flex justify-between items-start py-1">
          <span className="text-sm font-semibold text-gray-700">Modified:</span>
          <Timestamp value={modifiedAt as string} granularity="datetime" />
        </div>
      )}
    </div>
  );
}

/**
 * Format bytes into human-readable file size (e.g., "1.5 MB").
 */
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';

  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}
