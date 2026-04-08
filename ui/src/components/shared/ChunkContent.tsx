import type { ReactNode } from 'react';
import type { ChunkResponse } from '../../types/api';
import { MarkdownContent } from './MarkdownContent';

interface ChunkContentProps {
  /** The chunk to render */
  chunk: ChunkResponse;
}

/**
 * Renders chunk content based on chunk_type.
 *
 * Handles three chunk types:
 * - `code`: Renders as a syntax-highlighted code block
 * - `table`: Parses and renders as a formatted HTML table
 * - default (prose): Renders as markdown
 *
 * @example
 * <ChunkContent chunk={chunk} />
 */
export function ChunkContent({ chunk }: ChunkContentProps): ReactNode {
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
