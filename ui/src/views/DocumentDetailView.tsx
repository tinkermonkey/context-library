import type { ReactNode } from 'react';
import type { DomainViewProps } from './registry';
import { MarkdownContent } from '../components/shared/MarkdownContent';
import { ChunkBoundary } from '../components/shared/ChunkBoundary';
import { Timestamp } from '../components/shared/Timestamp';

/**
 * Document domain metadata structure.
 * Matches the backend DocumentMetadata model.
 */
interface DocumentMetadata {
  document_type: string;
  author: string | null;
  tags: string[];
  file_size: number | null;
  modified_date: string | null;
}

/**
 * Cast domain_metadata to DocumentMetadata with safety checks.
 */
function extractDocumentMetadata(domainMetadata: Record<string, unknown>): DocumentMetadata {
  return {
    document_type: typeof domainMetadata.document_type === 'string' ? domainMetadata.document_type : 'unknown',
    author: typeof domainMetadata.author === 'string' ? domainMetadata.author : null,
    tags: Array.isArray(domainMetadata.tags) ? (domainMetadata.tags as string[]) : [],
    file_size: typeof domainMetadata.file_size === 'number' ? domainMetadata.file_size : null,
    modified_date: typeof domainMetadata.modified_date === 'string' ? domainMetadata.modified_date : null,
  };
}

/**
 * Format file size in human-readable form.
 */
function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

/**
 * Document Detail View Component.
 *
 * Displays content from the documents domain (filesystem files and music library items)
 * as a detailed view with:
 * - Document metadata (type, author, tags, file size, modified date)
 * - Chronological chunk display with boundaries
 * - Markdown rendering for text content
 *
 * Handles both filesystem documents (PDFs, Markdown, text) and music library items.
 */
export function DocumentDetailView(props: DomainViewProps): ReactNode {
  const { chunks } = props;

  // Extract document metadata from first chunk if available
  const firstChunk = chunks[0];
  const documentMetadata = firstChunk?.domain_metadata
    ? extractDocumentMetadata(firstChunk.domain_metadata as Record<string, unknown>)
    : null;

  return (
    <div className="space-y-6">
      {/* Document Metadata Header */}
      {documentMetadata && (
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Document Type */}
            <div>
              <span className="text-xs font-semibold text-gray-600 uppercase">Type</span>
              <p className="mt-1 text-sm text-gray-900">{documentMetadata.document_type}</p>
            </div>

            {/* Author */}
            {documentMetadata.author && (
              <div>
                <span className="text-xs font-semibold text-gray-600 uppercase">Author</span>
                <p className="mt-1 text-sm text-gray-900">{documentMetadata.author}</p>
              </div>
            )}

            {/* File Size */}
            {documentMetadata.file_size !== null && (
              <div>
                <span className="text-xs font-semibold text-gray-600 uppercase">Size</span>
                <p className="mt-1 text-sm text-gray-900">{formatFileSize(documentMetadata.file_size)}</p>
              </div>
            )}

            {/* Modified Date */}
            {documentMetadata.modified_date && (
              <div>
                <span className="text-xs font-semibold text-gray-600 uppercase">Modified</span>
                <p className="mt-1 text-sm text-gray-900">
                  <Timestamp value={documentMetadata.modified_date} granularity="date" />
                </p>
              </div>
            )}

            {/* Tags */}
            {documentMetadata.tags.length > 0 && (
              <div className="md:col-span-2">
                <span className="text-xs font-semibold text-gray-600 uppercase">Tags</span>
                <div className="mt-2 flex flex-wrap gap-2">
                  {documentMetadata.tags.map((tag) => (
                    <span key={tag} className="px-2 py-1 bg-blue-50 text-blue-700 text-xs rounded">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Document Content */}
      <div className="space-y-4">
        {chunks.length === 0 ? (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-6 text-center">
            <p className="text-sm text-gray-600">No content available for this document.</p>
          </div>
        ) : (
          chunks.map((chunk, index) => (
            <div key={chunk.chunk_hash} className="bg-white rounded-lg border border-gray-200 p-4">
              <ChunkBoundary label={`Chunk ${index + 1}`} />
              <div className="mt-4 prose prose-sm max-w-none">
                <MarkdownContent content={chunk.content} />
              </div>
              {index < chunks.length - 1 && (
                <div className="mt-6 border-t border-gray-200" />
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
