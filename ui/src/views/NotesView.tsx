import type { ReactNode } from 'react';
import { useMemo } from 'react';
import type { ChunkResponse } from '../types/api';
import type { DomainViewProps } from './registry';
import { MarkdownContent } from '../components/shared/MarkdownContent';
import { ChunkBoundary } from '../components/shared/ChunkBoundary';

/**
 * Notes domain metadata structure.
 * Matches the backend NotesDomain model.
 */
interface NoteMetadata {
  heading_level: number;
  tags?: string[];
  aliases?: string[];
  wikilinks?: string[];
  backlinks?: string[];
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
 * Parse context header breadcrumb (format: "# H1 > ## H2 > ### H3").
 * Returns the last heading text (most specific).
 */
function parseContextHeaderBreadcrumb(contextHeader: string | null): string | null {
  if (!contextHeader) return null;

  const parts = contextHeader.split(' > ');
  if (parts.length === 0) return null;

  const lastPart = parts[parts.length - 1];
  // Remove leading hashes and space
  const match = lastPart.match(/^#+\s+(.*)$/);
  return match ? match[1] : lastPart;
}

/**
 * Extract headings from chunks to build a table of contents.
 */
function buildTableOfContents(chunks: ChunkResponse[]): HeadingEntry[] {
  const headings: HeadingEntry[] = [];

  chunks.forEach((chunk) => {
    const meta = extractNoteMetadata(chunk.domain_metadata);
    if (meta && meta.heading_level > 0) {
      // Extract heading text from context header if available
      const headingText = parseContextHeaderBreadcrumb(chunk.context_header);
      if (headingText) {
        headings.push({
          level: meta.heading_level,
          text: headingText,
          chunkIndex: chunk.chunk_index,
        });
      }
    }
  });

  return headings;
}

/**
 * Render table of contents as a hierarchical list.
 */
function TableOfContents({ headings }: { headings: HeadingEntry[] }): ReactNode {
  if (headings.length === 0) return null;

  const renderHeadings = (items: HeadingEntry[], minLevel: number = 1): ReactNode => {
    const filtered = items.filter((h) => h.level === minLevel);
    if (filtered.length === 0) return null;

    return (
      <ul className={`${minLevel === 1 ? 'list-none' : 'list-disc ml-4'} space-y-1`}>
        {filtered.map((heading) => (
          <li key={`${heading.level}-${heading.chunkIndex}`} className="text-sm text-blue-600">
            <a href={`#chunk-${heading.chunkIndex}`} className="hover:underline">
              {heading.text}
            </a>
            {items.some((h) => h.level === minLevel + 1 && items.indexOf(h) > items.indexOf(heading)) &&
              renderHeadings(items, minLevel + 1)}
          </li>
        ))}
      </ul>
    );
  };

  return (
    <nav className="bg-white rounded-lg border border-gray-200 p-4">
      <h3 className="text-sm font-semibold text-gray-900 mb-3">Contents</h3>
      {renderHeadings(headings)}
    </nav>
  );
}

/**
 * Render metadata tags, aliases, and backlinks.
 */
function MetadataSection({
  metadata,
  chunks,
}: {
  metadata: NoteMetadata | null;
  chunks: ChunkResponse[];
}): ReactNode {
  if (!metadata) return null;

  // Check if any metadata is present
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
 * Render a single chunk with heading hierarchy and context.
 */
function NoteChunk({ chunk, index, totalChunks }: { chunk: ChunkResponse; index: number; totalChunks: number }): ReactNode {
  const metadata = extractNoteMetadata(chunk.domain_metadata);
  const breadcrumb = parseContextHeaderBreadcrumb(chunk.context_header);

  // Determine visual indentation based on heading level
  const indentClass = {
    1: 'ml-0',
    2: 'ml-4',
    3: 'ml-8',
    4: 'ml-12',
    5: 'ml-16',
    6: 'ml-20',
  }[metadata?.heading_level ?? 0] || 'ml-0';

  return (
    <div key={chunk.chunk_hash} id={`chunk-${chunk.chunk_index}`} className={`bg-white rounded-lg border border-gray-200 p-4 ${indentClass}`}>
      {/* Breadcrumb context header */}
      {chunk.context_header && (
        <div className="text-xs text-gray-500 mb-3 font-mono">
          {chunk.context_header}
        </div>
      )}

      {/* Chunk content */}
      <div className="prose prose-sm max-w-none">
        <MarkdownContent content={chunk.content} />
      </div>

      {/* Visual separator between chunks */}
      {index < totalChunks - 1 && <div className="mt-6 border-t border-gray-200" />}
    </div>
  );
}

/**
 * Notes View Component.
 *
 * Displays notes content with hierarchical heading structure,
 * table of contents navigation, and rich metadata.
 *
 * Features:
 * - Hierarchical display based on heading levels from domain_metadata
 * - Table of contents with clickable links to chunks
 * - Context header breadcrumbs for location in note hierarchy
 * - Metadata display: tags, aliases, backlinks/wikilinks
 * - Proper chunk ordering via chunk_index
 * - Visual indentation showing heading hierarchy
 *
 * The backend NotesDomain provides:
 * - heading_level in domain_metadata for each heading chunk
 * - context_header as "# H1 > ## H2 > ### H3" breadcrumbs
 * - tags, aliases, wikilinks, backlinks in domain_metadata
 */
export function NotesView({ chunks }: DomainViewProps): ReactNode {
  // Sort chunks by chunk_index to ensure proper order
  const sortedChunks = useMemo(() => {
    return [...chunks].sort((a, b) => a.chunk_index - b.chunk_index);
  }, [chunks]);

  // Build table of contents from headings
  const tableOfContents = useMemo(() => buildTableOfContents(sortedChunks), [sortedChunks]);

  // Extract metadata from first chunk (common to all chunks in a note)
  const firstChunk = sortedChunks[0];
  const noteMetadata = firstChunk ? extractNoteMetadata(firstChunk.domain_metadata) : null;

  return (
    <div className="space-y-6">
      {/* Table of Contents */}
      {tableOfContents.length > 0 && <TableOfContents headings={tableOfContents} />}

      {/* Note Metadata */}
      <MetadataSection metadata={noteMetadata} chunks={sortedChunks} />

      {/* Note Content */}
      <div className="space-y-4">
        {sortedChunks.length === 0 ? (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-6 text-center">
            <p className="text-sm text-gray-600">No content available for this note.</p>
          </div>
        ) : (
          sortedChunks.map((chunk, index) => (
            <div key={chunk.chunk_hash}>
              <NoteChunk chunk={chunk} index={index} totalChunks={sortedChunks.length} />
              {index < sortedChunks.length - 1 && <ChunkBoundary />}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
