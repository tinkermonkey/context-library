import { useNavigate, useSearch } from '@tanstack/react-router';
import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import type { ChunkResponse } from '../types/api';
import type { DomainViewProps } from './registry';
import { MarkdownContent } from '../components/shared/MarkdownContent';
import { ChunkBoundary } from '../components/shared/ChunkBoundary';
import { Timestamp } from '../components/shared/Timestamp';
import { MetadataField } from '../components/shared/MetadataField';
import { useChunk } from '../hooks/useChunks';

/**
 * Notes domain metadata structure.
 */
interface NoteMetadata {
  heading_level: number;
  tags?: string[];
  aliases?: string[];
  wikilinks?: string[];
  backlinks?: string[];
}

/**
 * Document domain metadata structure.
 */
interface DocumentMetadata {
  document_type: string;
  author: string | null;
  tags: string[];
  file_size: number | null;
  modified_date: string | null;
}

/**
 * Hierarchical heading entry for TOC generation.
 */
interface HeadingNode {
  label: string;    // heading text without # prefix
  level: number;    // 1, 2, or 3
  chunkIndex: number;  // first chunk under this heading
  anchor: string;   // URL-safe slug for scroll targeting
}

/**
 * Detect which domain this view is rendering.
 */
function detectDomain(chunks: ChunkResponse[]): 'notes' | 'documents' | 'unknown' {
  if (chunks.length === 0) return 'unknown';

  // Check for notes-specific metadata (heading_level)
  const hasHeadingLevel = chunks.some((c) => {
    const meta = c.domain_metadata as Record<string, unknown> | null;
    return meta && typeof meta.heading_level === 'number';
  });

  if (hasHeadingLevel) return 'notes';

  // Check for documents-specific metadata (document_type, file_size, etc.)
  const hasDocumentMetadata = chunks.some((c) => {
    const meta = c.domain_metadata as Record<string, unknown> | null;
    return meta && (typeof meta.document_type === 'string' || typeof meta.file_size === 'number');
  });

  if (hasDocumentMetadata) return 'documents';

  return 'unknown';
}

/**
 * Extract notes metadata from domain_metadata with safety checks.
 */
function extractNoteMetadata(domainMetadata: Record<string, unknown> | null): NoteMetadata | null {
  if (!domainMetadata) return null;

  return {
    heading_level: typeof domainMetadata.heading_level === 'number' ? domainMetadata.heading_level : 0,
    tags: Array.isArray(domainMetadata.tags) ? (domainMetadata.tags as string[]) : undefined,
    aliases: Array.isArray(domainMetadata.aliases) ? (domainMetadata.aliases as string[]) : undefined,
    wikilinks: Array.isArray(domainMetadata.wikilinks) ? (domainMetadata.wikilinks as string[]) : undefined,
    backlinks: Array.isArray(domainMetadata.backlinks) ? (domainMetadata.backlinks as string[]) : undefined,
  };
}

/**
 * Extract document metadata from domain_metadata with safety checks.
 */
function extractDocumentMetadata(domainMetadata: Record<string, unknown>): DocumentMetadata {
  let tags: string[] = [];
  if (Array.isArray(domainMetadata.tags)) {
    tags = domainMetadata.tags.every((item) => typeof item === 'string')
      ? (domainMetadata.tags as string[])
      : [];
  }

  return {
    document_type: typeof domainMetadata.document_type === 'string' ? domainMetadata.document_type : 'unknown',
    author: typeof domainMetadata.author === 'string' ? domainMetadata.author : null,
    tags,
    file_size: typeof domainMetadata.file_size === 'number' ? domainMetadata.file_size : null,
    modified_date: typeof domainMetadata.modified_date === 'string' ? domainMetadata.modified_date : null,
  };
}

/**
 * Parse context header breadcrumb (format: "# H1 > ## H2 > ### H3").
 * Returns the last heading and its level.
 */
function parseContextHeaderBreadcrumb(contextHeader: string | null): { text: string; level: number } | null {
  if (!contextHeader) return null;

  const parts = contextHeader.split(' > ');
  if (parts.length === 0) return null;

  const lastPart = parts[parts.length - 1];
  const match = lastPart.match(/^(#+)\s+(.*)$/);

  if (match) {
    return {
      level: match[1].length,
      text: match[2],
    };
  }

  return null;
}

/**
 * Create a URL-safe anchor slug from heading text.
 */
function createAnchor(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .slice(0, 50);
}

/**
 * Extract headings from chunks to build a table of contents.
 * Deduplicates only consecutive identical headings (not global duplicates).
 */
function buildTableOfContents(chunks: ChunkResponse[]): HeadingNode[] {
  const headings: HeadingNode[] = [];
  let lastHeadingText: string | null = null;

  chunks.forEach((chunk) => {
    const parsed = parseContextHeaderBreadcrumb(chunk.context_header);
    if (parsed) {
      // Deduplicate consecutive identical headings
      if (parsed.text !== lastHeadingText) {
        headings.push({
          label: parsed.text,
          level: parsed.level,
          chunkIndex: chunk.chunk_index,
          anchor: createAnchor(parsed.text),
        });
        lastHeadingText = parsed.text;
      }
    }
  });

  return headings;
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
 * Parse markdown table and render as HTML table.
 * Simple table format: pipe-delimited rows with separator row.
 */
function renderTable(content: string): ReactNode {
  const lines = content.trim().split('\n');
  if (lines.length < 3) return <div>{content}</div>;

  // Check if this looks like a markdown table (separator row with dashes and pipes)
  const separatorMatch = lines[1]?.match(/^\|?[\s|-]+\|[\s|-]*\|?$/);
  if (!separatorMatch) {
    return <div>{content}</div>;
  }

  const parseRow = (line: string): string[] => {
    return line
      .split('|')
      .map((cell) => cell.trim())
      .filter((cell) => cell.length > 0);
  };

  const headerCells = parseRow(lines[0]);
  const bodyRows = lines.slice(2).map(parseRow);

  return (
    <div className="overflow-x-auto my-3">
      <table className="border-collapse w-full text-sm">
        <thead>
          <tr>
            {headerCells.map((cell, idx) => (
              <th key={idx} className="border border-gray-300 bg-gray-100 px-3 py-2 text-left font-semibold">
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {bodyRows.map((row, rowIdx) => (
            <tr key={rowIdx}>
              {row.map((cell, cellIdx) => (
                <td key={cellIdx} className="border border-gray-300 px-3 py-2">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Render chunk content based on chunk_type.
 */
function renderChunkContent(chunk: ChunkResponse): ReactNode {
  const { chunk_type, content } = chunk;

  switch (chunk_type) {
    case 'code':
      // Render code block with syntax highlighting via monospace
      return (
        <pre className="bg-gray-900 text-gray-100 rounded p-4 overflow-x-auto my-3">
          <code className="font-mono text-sm whitespace-pre-wrap break-words">{content}</code>
        </pre>
      );

    case 'table':
      // Parse and render as HTML table
      return renderTable(content);

    default:
      // Standard prose - render as markdown
      return (
        <div className="prose prose-sm max-w-none">
          <MarkdownContent content={content} />
        </div>
      );
  }
}

/**
 * Render table of contents as a hierarchical list.
 */
function TableOfContents({ headings }: { headings: HeadingNode[] }): ReactNode {
  const navigate = useNavigate({ from: '/browser/view/$domain/$sourceId' });

  if (headings.length === 0) return null;

  const handleTocClick = (anchor: string, chunkIndex: number): void => {
    // Update URL with section parameter, preserving other search params
    void navigate({
      search: (prev) => ({ ...prev, section: anchor }),
      replace: false,
    });

    // Scroll to the chunk element
    const element = document.getElementById(`chunk-${chunkIndex}`);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  };

  const renderHeadings = (items: HeadingNode[], minLevel: number): ReactNode => {
    const filtered = items.filter((h) => h.level === minLevel);
    if (filtered.length === 0) return null;

    return (
      <ul className={`${minLevel === 1 ? 'list-none' : 'list-disc'} space-y-1`}>
        {filtered.map((heading) => {
          // Find child headings
          const headingIdx = items.indexOf(heading);
          const nextSameLevelIdx = items.findIndex(
            (h, idx) => idx > headingIdx && h.level === minLevel
          );
          const sectionEnd = nextSameLevelIdx === -1 ? items.length : nextSameLevelIdx;

          const hasChildren = items.some(
            (h, idx) => idx > headingIdx && idx < sectionEnd && h.level === minLevel + 1
          );

          return (
            <li key={`${heading.anchor}`} className="text-sm text-blue-600" style={{ paddingLeft: `${(heading.level - 1) * 16}px` }}>
              <button
                onClick={() => handleTocClick(heading.anchor, heading.chunkIndex)}
                className="hover:underline bg-none border-none cursor-pointer text-blue-600 p-0"
              >
                {heading.label}
              </button>
              {hasChildren && renderHeadings(items.slice(headingIdx + 1, sectionEnd), minLevel + 1)}
            </li>
          );
        })}
      </ul>
    );
  };

  const minLevel = Math.min(...headings.map((h) => h.level));

  return (
    <nav className="bg-white rounded-lg border border-gray-200 p-4 sticky top-6">
      <h3 className="text-sm font-semibold text-gray-900 mb-3">Contents</h3>
      {renderHeadings(headings, minLevel)}
    </nav>
  );
}

/**
 * Render metadata tags, aliases, and backlinks for notes.
 */
function NoteMetadataSection({
  metadata,
}: {
  metadata: NoteMetadata | null;
}): ReactNode {
  if (!metadata) return null;

  const hasTags = metadata.tags && metadata.tags.length > 0;
  const hasAliases = metadata.aliases && metadata.aliases.length > 0;
  const hasBacklinks = metadata.backlinks && metadata.backlinks.length > 0;

  if (!hasTags && !hasAliases && !hasBacklinks) return null;

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-3">
      {hasTags && (
        <div>
          <span className="text-xs font-semibold text-gray-600 uppercase">Tags</span>
          <div className="mt-2 flex flex-wrap gap-2">
            {metadata.tags!.map((tag) => (
              <span key={tag} className="px-2 py-1 bg-blue-50 text-blue-700 text-xs rounded">
                {tag}
              </span>
            ))}
          </div>
        </div>
      )}

      {hasAliases && (
        <div>
          <span className="text-xs font-semibold text-gray-600 uppercase">Aliases</span>
          <div className="mt-2 flex flex-wrap gap-2">
            {metadata.aliases!.map((alias) => (
              <span key={alias} className="px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded">
                {alias}
              </span>
            ))}
          </div>
        </div>
      )}

      {hasBacklinks && (
        <div>
          <span className="text-xs font-semibold text-gray-600 uppercase">Backlinks</span>
          <div className="mt-2 flex flex-wrap gap-2">
            {metadata.backlinks!.map((link) => (
              <span key={link} className="px-2 py-1 bg-green-50 text-green-700 text-xs rounded">
                {link}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Render document metadata header for documents domain.
 */
function DocumentMetadataHeader({
  metadata,
}: {
  metadata: DocumentMetadata | null;
}): ReactNode {
  if (!metadata) return null;

  const formattedSize = metadata.file_size !== null ? formatFileSize(metadata.file_size) : null;
  const formattedDate = metadata.modified_date ? (
    <Timestamp value={metadata.modified_date} granularity="date" />
  ) : null;

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-3">
      <MetadataField label="Type" value={metadata.document_type} />
      <MetadataField label="Author" value={metadata.author} />
      <MetadataField label="Size" value={formattedSize} />
      <MetadataField label="Modified" value={formattedDate} />

      {metadata.tags.length > 0 && (
        <div>
          <span className="text-xs font-semibold text-gray-600 uppercase block mb-2">Tags</span>
          <div className="flex flex-wrap gap-2">
            {metadata.tags.map((tag) => (
              <span key={tag} className="px-2 py-1 bg-blue-50 text-blue-700 text-xs rounded">
                {tag}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Single cross-reference link with lazy chunk lookup.
 */
function CrossRefLink({
  chunkHash,
}: {
  chunkHash: string;
}): ReactNode {
  const navigate = useNavigate({ from: '/browser/view/$domain/$sourceId' });
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

/**
 * Render cross-reference links for a chunk.
 * Cross-refs are chunk hashes that reference other chunks (possibly in other sources).
 */
function CrossReferences({
  crossRefs,
}: {
  crossRefs: string[];
}): ReactNode {
  if (!crossRefs || crossRefs.length === 0) return null;

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mt-4">
      <h4 className="text-xs font-semibold text-blue-900 uppercase mb-2">Related Content</h4>
      <div className="flex flex-wrap gap-2">
        {crossRefs.map((chunkHash, idx) => (
          <CrossRefLink key={idx} chunkHash={chunkHash} />
        ))}
      </div>
    </div>
  );
}

/**
 * Render a single chunk with heading hierarchy and context.
 */
function DocumentChunk({ chunk }: { chunk: ChunkResponse }): ReactNode {
  return (
    <div key={chunk.chunk_hash} id={`chunk-${chunk.chunk_index}`} className="bg-white rounded-lg border border-gray-200 p-4">
      {/* Breadcrumb context header */}
      {chunk.context_header && (
        <div className="text-xs text-gray-500 mb-3 font-mono">
          {chunk.context_header}
        </div>
      )}

      {/* Chunk content */}
      {renderChunkContent(chunk)}

      {/* Cross-references */}
      <CrossReferences crossRefs={chunk.cross_refs} />
    </div>
  );
}

/**
 * Document View Component.
 *
 * Unified view for both notes and documents domains with:
 * - Automatic domain detection
 * - TOC sidebar derived from context_header breadcrumbs
 * - Chunk-type-aware rendering (prose, code, tables)
 * - Cross-reference navigation
 * - URL state management for scroll position
 *
 * Handles:
 * - Notes domain: heading hierarchy, tags, aliases, backlinks
 * - Documents domain: file metadata, document type, author info
 *
 * Features:
 * - Chunks displayed in chunk_index order
 * - TOC entries are clickable and scroll to first chunk under that heading
 * - Section URL parameter encodes active TOC section for bookmarking
 * - When no chunks have context_header, renders without TOC panel
 * - Code blocks render with syntax highlighting support
 * - Tables render as formatted HTML, not raw markdown
 */
export function DocumentView({ chunks }: DomainViewProps): ReactNode {
  const domain = detectDomain(chunks);

  // Get current section from URL
  const search = useSearch({ from: '/browser/view/$domain/$sourceId' }) as { section?: string };

  // Sort chunks by chunk_index
  const sortedChunks = useMemo(() => {
    return [...chunks].sort((a, b) => a.chunk_index - b.chunk_index);
  }, [chunks]);

  // Build table of contents
  const tableOfContents = useMemo(() => buildTableOfContents(sortedChunks), [sortedChunks]);

  // Extract domain-specific metadata
  const firstChunk = sortedChunks[0];
  const noteMetadata = domain === 'notes' && firstChunk?.domain_metadata
    ? extractNoteMetadata(firstChunk.domain_metadata as Record<string, unknown> | null)
    : null;

  const documentMetadata = domain === 'documents' && firstChunk?.domain_metadata
    ? extractDocumentMetadata(firstChunk.domain_metadata as Record<string, unknown>)
    : null;

  // Handle scroll to section on mount and when section changes
  useEffect(() => {
    if (!search.section || tableOfContents.length === 0) {
      return;
    }

    const headingNode = tableOfContents.find((h) => h.anchor === search.section);
    if (!headingNode) {
      return;
    }

    const element = document.getElementById(`chunk-${headingNode.chunkIndex}`);
    if (element) {
      // Use requestAnimationFrame to ensure element is rendered
      requestAnimationFrame(() => {
        element.scrollIntoView({ behavior: 'smooth' });
      });
    }
  }, [search.section, tableOfContents]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
      {/* TOC Sidebar - only render if we have headings */}
      {tableOfContents.length > 0 && (
        <div className="lg:col-span-1">
          <TableOfContents headings={tableOfContents} />
        </div>
      )}

      {/* Main Content */}
      <div className={tableOfContents.length > 0 ? 'lg:col-span-3' : 'lg:col-span-4'}>
        <div className="space-y-6">
          {/* Notes metadata section */}
          {domain === 'notes' && <NoteMetadataSection metadata={noteMetadata} />}

          {/* Documents metadata header */}
          {domain === 'documents' && <DocumentMetadataHeader metadata={documentMetadata} />}

          {/* Document content */}
          <div className="space-y-4">
            {sortedChunks.length === 0 ? (
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-6 text-center">
                <p className="text-sm text-gray-600">No content available.</p>
              </div>
            ) : (
              sortedChunks.map((chunk, index) => (
                <div key={chunk.chunk_hash}>
                  <DocumentChunk chunk={chunk} />
                  {index < sortedChunks.length - 1 && <ChunkBoundary />}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
