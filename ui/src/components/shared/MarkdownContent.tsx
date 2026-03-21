import { useMemo, type ReactNode } from 'react';

interface MarkdownContentProps {
  /** Markdown text content */
  content: string;
}

/**
 * Renders markdown content as formatted HTML.
 *
 * Uses a simple markdown parser for common patterns.
 * For code blocks and tables, applies appropriate styling.
 *
 * Note: This is a simplified markdown renderer that handles the most common
 * patterns used in domain views. For full markdown support, consider adding
 * a library like react-markdown.
 *
 * @example
 * <MarkdownContent content={markdownText} />
 */
export function MarkdownContent({ content }: MarkdownContentProps): ReactNode {
  const parsed = useMemo(() => {
    if (!content) {
      return <div className="text-gray-500">No content</div>;
    }

    return parseMarkdownContent(content);
  }, [content]);

  return parsed;
}

/**
 * Parse markdown content into React elements.
 * Extracted as a pure function to enable memoization.
 */
function parseMarkdownContent(content: string): ReactNode {
  // Parse markdown and convert to HTML-like structure
  const lines = content.split('\n');
  const elements: ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trimStart();

    // Heading levels (# ## ###)
    const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const text = headingMatch[2];
      const className = {
        1: 'text-2xl font-bold',
        2: 'text-xl font-bold',
        3: 'text-lg font-bold',
        4: 'text-base font-bold',
        5: 'text-sm font-bold',
        6: 'text-xs font-bold',
      }[level] || 'text-base font-bold';

      elements.push(
        <div key={`h${i}`} className={`mt-3 mb-2 ${className}`}>
          {text}
        </div>
      );
      i++;
      continue;
    }

    // Code block (```)
    if (trimmed.startsWith('```')) {
      const codeBlockLines: string[] = [];
      // Language identifier is parsed but not currently used for syntax highlighting
      // To add syntax highlighting, integrate a library like highlight.js or prism
      i++;

      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeBlockLines.push(lines[i]);
        i++;
      }

      elements.push(
        <pre
          key={`code${i}`}
          className="bg-gray-100 border border-gray-300 rounded p-3 overflow-x-auto my-2"
        >
          <code className="text-xs font-mono text-gray-800">
            {codeBlockLines.join('\n')}
          </code>
        </pre>
      );

      if (i < lines.length && lines[i].trim().startsWith('```')) {
        i++;
      }
      continue;
    }

    // Empty line - add spacing
    if (trimmed === '') {
      elements.push(<div key={`empty${i}`} className="h-2" />);
      i++;
      continue;
    }

    // List items (- or *)
    if (trimmed.match(/^[-*]\s+/)) {
      const listItems: string[] = [];

      while (i < lines.length) {
        const itemLine = lines[i].trimStart();
        const markerMatch = itemLine.match(/^[-*]\s+/);
        if (!markerMatch) break;
        listItems.push(itemLine.slice(markerMatch[0].length));
        i++;
      }

      elements.push(
        <ul key={`list${i}`} className="list-disc list-inside my-2 space-y-1">
          {listItems.map((item, idx) => (
            <li key={idx} className="text-sm text-gray-700">
              {item}
            </li>
          ))}
        </ul>
      );
      continue;
    }

    // Regular paragraph
    elements.push(
      <p key={`p${i}`} className="text-sm text-gray-700 my-1 leading-relaxed">
        {formatInlineMarkdown(line)}
      </p>
    );
    i++;
  }

  return <div className="prose prose-sm max-w-none">{elements}</div>;
}

/**
 * Format inline markdown patterns (bold, italic, links, code).
 */
function formatInlineMarkdown(text: string): ReactNode {
  if (!text) return text;

  const parts: ReactNode[] = [];
  let lastIdx = 0;

  // Simple regex to match **bold**, *italic*, `code`, and [text](url)
  const pattern = /\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`|\[(.+?)\]\((.+?)\)/g;
  let match;

  while ((match = pattern.exec(text)) !== null) {
    // Add text before match
    if (match.index > lastIdx) {
      parts.push(text.substring(lastIdx, match.index));
    }

    // Handle matched pattern
    if (match[1]) {
      // **bold**
      parts.push(
        <strong key={`bold${match.index}`} className="font-semibold">
          {match[1]}
        </strong>
      );
    } else if (match[2]) {
      // *italic*
      parts.push(
        <em key={`italic${match.index}`} className="italic">
          {match[2]}
        </em>
      );
    } else if (match[3]) {
      // `code`
      parts.push(
        <code key={`code${match.index}`} className="bg-gray-100 px-1 py-0.5 rounded text-xs font-mono">
          {match[3]}
        </code>
      );
    } else if (match[4] && match[5]) {
      // [text](url)
      parts.push(
        <a
          key={`link${match.index}`}
          href={match[5]}
          className="text-blue-600 hover:underline"
          target="_blank"
          rel="noopener noreferrer"
        >
          {match[4]}
        </a>
      );
    }

    lastIdx = pattern.lastIndex;
  }

  // Add remaining text
  if (lastIdx < text.length) {
    parts.push(text.substring(lastIdx));
  }

  return parts.length > 0 ? parts : text;
}
