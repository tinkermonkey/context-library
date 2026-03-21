import { useNavigate } from '@tanstack/react-router';
import type { ReactNode } from 'react';
import { useMemo } from 'react';
import type { ChunkResponse } from '../types/api';
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
 * Parse context header breadcrumb.
 * Handles two formats:
 * 1. Notes domain: "# H1 > ## H2 > ### H3" (hierarchical markdown headings)
 * 2. Documents domain: "{title} — {document_type}" (title-based context)
 * Returns array of heading levels and text pairs.
 */
function parseContextHeaderHierarchy(contextHeader: string | null): Array<{ level: number; text: string }> {
  if (!contextHeader) return [];

  // Try parsing notes domain format: "# H1 > ## H2 > ### H3"
  const parts = contextHeader.split(' > ');
  const hierarchicalHeadings = parts
    .map((part) => {
      const match = part.match(/^(#+)\s+(.*)$/);
      if (!match) return null;
      return {
        level: match[1].length,
        text: match[2],
      };
    })
    .filter((item) => item !== null) as Array<{ level: number; text: string }>;

  if (hierarchicalHeadings.length > 0) {
    return hierarchicalHeadings;
  }

  // Fallback to documents domain format: "{title} — {document_type}"
  // Extract title (part before dash) and treat as h1
  const titleMatch = contextHeader.match(/^([^—-]+)/);
  if (titleMatch) {
    return [
      {
        level: 1,
        text: titleMatch[1].trim(),
      },
    ];
  }

  return [];
}

/**
 * Hierarchical heading entry for TOC generation.
 */
interface HeadingEntry {
  level: number;
  text: string;
  chunkIndex: number;
}

/**
 * Extract headings from chunks to build a table of contents.
 * For documents, we use context_header since documents don't have heading_level metadata.
 */
function buildTableOfContents(chunks: ChunkResponse[]): HeadingEntry[] {
  const headings: HeadingEntry[] = [];

  chunks.forEach((chunk) => {
    const hierarchy = parseContextHeaderHierarchy(chunk.context_header);
    if (hierarchy.length > 0) {
      // Use the most specific (last) heading in the hierarchy
      const lastHeading = hierarchy[hierarchy.length - 1];
      headings.push({
        level: lastHeading.level,
        text: lastHeading.text,
        chunkIndex: chunk.chunk_index,
      });
    }
  });

  return headings;
}

/**
 * Render table of contents as a hierarchical list.
 */
function TableOfContents({ headings }: { headings: HeadingEntry[] }): ReactNode {
  if (headings.length === 0) return null;

  // Dynamically calculate minimum level present in headings
  const minLevelInData = Math.min(...headings.map((h) => h.level));

  const renderHeadings = (items: HeadingEntry[], minLevel: number = minLevelInData, startIndex: number = 0): ReactNode => {
    const filtered = items.slice(startIndex).filter((h) => h.level === minLevel);
    if (filtered.length === 0) return null;

    return (
      <ul className={`${minLevel === minLevelInData ? 'list-none' : 'list-disc ml-4'} space-y-1`}>
        {filtered.map((heading) => {
          const headingIndexInSlice = items.slice(startIndex).findIndex((h) => h === heading);
          const headingIndexInFull = startIndex + headingIndexInSlice;

          const nextSameLevelIndex = items.findIndex(
            (h, idx) => idx > headingIndexInFull && h.level === minLevel
          );
          const sectionEndIndex = nextSameLevelIndex === -1 ? items.length : nextSameLevelIndex;

          const hasChildren = items.some(
            (h, idx) => idx > headingIndexInFull && idx < sectionEndIndex && h.level === minLevel + 1
          );

          return (
            <li key={`${heading.level}-${heading.chunkIndex}`} className="text-sm text-blue-600">
              <a href={`#chunk-${heading.chunkIndex}`} className="hover:underline">
                {heading.text}
              </a>
              {hasChildren && renderHeadings(items.slice(headingIndexInFull + 1, sectionEndIndex), minLevel + 1, 0)}
            </li>
          );
        })}
      </ul>
    );
  };

  return (
    <nav className="bg-white rounded-lg border border-gray-200 p-4">
      <h3 className="text-sm font-semibold text-gray-900 mb-3">Contents</h3>
      {renderHeadings(headings, minLevelInData)}
    </nav>
  );
}

/**
 * Render cross-reference links for a chunk.
 * Each cross-ref button displays the source ID (truncated) for differentiation.
 *
 * NOTE: Domain is currently hardcoded to 'documents' as the cross_refs data model
 * does not include domain context. If cross-domain references are needed in the future,
 * the cross_refs format should be updated to include domain information.
 */
function CrossReferences({
  crossRefs,
}: {
  crossRefs: string[];
}): ReactNode {
  const navigate = useNavigate({ from: '/browser/view/$domain/$sourceId' });

  if (!crossRefs || crossRefs.length === 0) return null;

  const handleCrossRefClick = (refSourceId: string): void => {
    void navigate({
      to: '/browser/view/$domain/$sourceId',
      // TODO: Update when cross_refs includes domain information
      params: { domain: 'documents', sourceId: refSourceId },
    });
  };

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mt-4">
      <h4 className="text-xs font-semibold text-blue-900 uppercase mb-2">Related Documents</h4>
      <div className="flex flex-wrap gap-2">
        {crossRefs.map((refSourceId, idx) => {
          // Truncate source ID to first 8 characters for display
          const displayId = refSourceId.substring(0, 8);
          return (
            <button
              key={idx}
              onClick={() => handleCrossRefClick(refSourceId)}
              className="px-3 py-1 bg-blue-100 hover:bg-blue-200 text-blue-700 text-xs rounded transition-colors cursor-pointer"
              title={refSourceId}
            >
              View {displayId}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Document Detail View Component.
 *
 * Displays content from the documents domain (filesystem files and music library items)
 * as a detailed view with:
 * - Document metadata (type, author, tags, file size, modified date)
 * - Table of contents with hierarchical navigation
 * - Chronological chunk display with boundaries
 * - Cross-reference navigation to related documents
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

  // Build table of contents from chunks
  const tableOfContents = useMemo(() => buildTableOfContents(chunks), [chunks]);

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

      {/* Table of Contents */}
      {tableOfContents.length > 0 && <TableOfContents headings={tableOfContents} />}

      {/* Document Content */}
      <div className="space-y-4">
        {chunks.length === 0 ? (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-6 text-center">
            <p className="text-sm text-gray-600">No content available for this document.</p>
          </div>
        ) : (
          chunks.map((chunk, index) => (
            <div key={chunk.chunk_hash} id={`chunk-${chunk.chunk_index}`} className="bg-white rounded-lg border border-gray-200 p-4">
              {/* Context header breadcrumb */}
              {chunk.context_header && (
                <div className="text-xs text-gray-500 mb-3 font-mono">
                  {chunk.context_header}
                </div>
              )}

              <ChunkBoundary label={`Chunk ${index + 1}`} />
              <div className="mt-4 prose prose-sm max-w-none">
                <MarkdownContent content={chunk.content} />
              </div>

              {/* Cross-references */}
              <CrossReferences crossRefs={chunk.cross_refs} />

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
