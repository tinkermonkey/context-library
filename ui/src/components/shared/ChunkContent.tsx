import type { ReactNode } from 'react';
import type { ChunkResponse } from '../../types/api';
import { MarkdownContent } from './MarkdownContent';
import { ChunkTypeBadge } from './ChunkTypeBadge';
import { CrossRefLink } from './CrossRefLink';

interface ChunkContentProps {
  /** The chunk to render */
  chunk: ChunkResponse;
}

/**
 * Renders chunk content based on chunk_type.
 *
 * Handles three chunk types:
 * - `code`: Renders as a plain text code block
 * - `table_part`: Parses and renders as a formatted HTML table
 * - default (prose): Renders as markdown
 *
 * Includes type badge for all chunks and cross-reference links when present.
 *
 * @example
 * <ChunkContent chunk={chunk} />
 */
export function ChunkContent({ chunk }: ChunkContentProps): ReactNode {
  const { chunk_type, content, cross_refs } = chunk;

  // Render the main content based on chunk type
  let mainContent: ReactNode;

  switch (chunk_type) {
    case 'code':
      // Render plain text code block
      mainContent = (
        <pre className="bg-gray-900 text-gray-100 rounded p-4 overflow-x-auto my-3">
          <code className="font-mono text-sm whitespace-pre-wrap break-words">{content}</code>
        </pre>
      );
      break;

    case 'table_part':
      // Parse and render as HTML table
      mainContent = renderTable(content);
      break;

    default:
      // Standard prose - render as markdown
      mainContent = (
        <div className="prose prose-sm max-w-none">
          <MarkdownContent content={content} />
        </div>
      );
  }

  // Render cross-references if present
  const crossRefsElement = cross_refs && cross_refs.length > 0 ? (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mt-4">
      <h4 className="text-xs font-semibold text-blue-900 uppercase mb-2">Related Content</h4>
      <div className="flex flex-wrap gap-2">
        {cross_refs.map((chunkHash, idx) => (
          <CrossRefLink key={idx} chunkHash={chunkHash} />
        ))}
      </div>
    </div>
  ) : null;

  return (
    <div>
      <div className="mb-2">
        <ChunkTypeBadge type={chunk_type} />
      </div>
      {mainContent}
      {crossRefsElement}
    </div>
  );
}

/**
 * Parse markdown table and render as HTML table.
 * Simple table format: pipe-delimited rows with separator row.
 */
function renderTable(content: string): ReactNode {
  const lines = content.trim().split('\n');
  if (lines.length < 3) return <div>{content}</div>;

  // Check if this looks like a markdown table (separator row with dashes and pipes)
  const separatorMatch = lines[1]?.match(/^\|?[-\s|]+\|[-\s|]*\|?$/);
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
