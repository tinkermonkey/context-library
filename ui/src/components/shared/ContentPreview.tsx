import { useState, type ReactNode } from 'react';
import { MarkdownContent } from './MarkdownContent';

interface ContentPreviewProps {
  /** Content text to display (markdown or plain text) */
  content: string;
  /** Optional maximum characters to show before expanding (default: 200) */
  maxLength?: number;
  /** Optional label for expand/collapse button (default: "Read More") */
  expandLabel?: string;
  /** Optional label for collapse button (default: "Read Less") */
  collapseLabel?: string;
}

/**
 * Renders content with expand/collapse capability.
 * Shows truncated content with a "Read More" button if content exceeds maxLength.
 *
 * Features:
 * - Automatically truncates long content
 * - Renders markdown formatting
 * - Smooth expand/collapse toggle
 * - Customizable character limit and button labels
 *
 * @example
 * <ContentPreview content={chunkContent} maxLength={150} />
 */
export function ContentPreview({
  content,
  maxLength = 200,
  expandLabel = 'Read More',
  collapseLabel = 'Read Less',
}: ContentPreviewProps): ReactNode {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!content) {
    return <div className="text-gray-500">No content</div>;
  }

  const shouldTruncate = content.length > maxLength;
  const displayContent = isExpanded ? content : content.substring(0, maxLength);

  return (
    <div>
      <div className="text-sm text-gray-700">
        <MarkdownContent content={displayContent} />
      </div>

      {shouldTruncate && (
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="mt-2 text-sm text-blue-600 hover:text-blue-800 font-medium transition-colors bg-none border-none cursor-pointer p-0"
        >
          {isExpanded ? collapseLabel : expandLabel}
        </button>
      )}
    </div>
  );
}
