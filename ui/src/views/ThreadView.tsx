import type { ReactNode } from 'react';
import { useMemo } from 'react';
import { useNavigate, useSearch } from '@tanstack/react-router';
import type { ChunkResponse } from '../types/api';
import type { DomainViewProps } from './registry';
import { messagesViewSearchSchema } from '../routes-config';
import { Timestamp } from '../components/shared/Timestamp';
import { MarkdownContent } from '../components/shared/MarkdownContent';
import { ChunkBoundary } from '../components/shared/ChunkBoundary';

/**
 * Message domain metadata structure.
 * Matches the backend MessageMetadata model.
 */
interface MessageMetadata {
  thread_id: string;
  message_id: string;
  sender: string;
  recipients: string[];
  timestamp: string; // ISO 8601
  in_reply_to: string | null;
  subject: string | null;
  is_thread_root: boolean;
}

/**
 * Message node in the reply tree, with children.
 */
interface MessageNode {
  chunk: ChunkResponse;
  metadata: MessageMetadata;
  children: MessageNode[];
}

/**
 * Cast domain_metadata to MessageMetadata with safety checks.
 * Validates that required fields are present and have correct types.
 */
function extractMessageMetadata(chunk: ChunkResponse): MessageMetadata | null {
  if (!chunk.domain_metadata) return null;

  const meta = chunk.domain_metadata;

  // Validate required fields
  if (
    typeof meta.message_id !== 'string' ||
    typeof meta.sender !== 'string' ||
    typeof meta.timestamp !== 'string'
  ) {
    return null;
  }

  return {
    thread_id: typeof meta.thread_id === 'string' ? meta.thread_id : '',
    message_id: meta.message_id,
    sender: meta.sender,
    recipients: Array.isArray(meta.recipients) ? meta.recipients : [],
    timestamp: meta.timestamp,
    in_reply_to: typeof meta.in_reply_to === 'string' ? meta.in_reply_to : null,
    subject: typeof meta.subject === 'string' ? meta.subject : null,
    is_thread_root: Boolean(meta.is_thread_root),
  };
}

/**
 * Build a reply tree from chunks using in_reply_to relationships.
 *
 * Algorithm:
 * 1. Find the root: chunk where is_thread_root === true; fallback to chunk with lowest chunk_index
 * 2. Build a Map<message_id, chunk> for O(1) lookup
 * 3. Build reply tree: for each chunk, if in_reply_to is set and exists in the map, attach as child
 *    Otherwise, attach as child of root (graceful fallback for missing parents)
 * 4. Return root node with children tree
 * 5. If no metadata, return null (graceful degradation)
 */
function buildReplyTree(chunks: ChunkResponse[]): MessageNode | null {
  const chunksByMetadata: Array<[ChunkResponse, MessageMetadata]> = chunks
    .map((chunk) => [chunk, extractMessageMetadata(chunk)])
    .filter(([, meta]) => meta !== null) as Array<[ChunkResponse, MessageMetadata]>;

  if (chunksByMetadata.length === 0) return null;

  // Find root: is_thread_root or lowest chunk_index
  let root = chunksByMetadata[0];
  let minChunkIndex = chunksByMetadata[0][0].chunk_index;

  for (const entry of chunksByMetadata) {
    if (entry[1].is_thread_root) {
      root = entry;
      break;
    }
    // Track the entry with lowest chunk_index as fallback
    if (entry[0].chunk_index < minChunkIndex) {
      minChunkIndex = entry[0].chunk_index;
      root = entry;
    }
  }

  // Build map for O(1) lookup
  const messageMap = new Map<string, [ChunkResponse, MessageMetadata]>(
    chunksByMetadata.map(([chunk, meta]) => [meta.message_id, [chunk, meta]])
  );

  // Build tree: create node for each chunk
  const nodeMap = new Map<string, MessageNode>();
  for (const [chunk, meta] of chunksByMetadata) {
    nodeMap.set(meta.message_id, {
      chunk,
      metadata: meta,
      children: [],
    });
  }

  // Attach children using in_reply_to
  // Messages with missing parents are attached to root (graceful fallback)
  const rootNode = nodeMap.get(root[1].message_id);
  if (!rootNode) return null;

  for (const [, meta] of chunksByMetadata) {
    // Skip the root itself
    if (meta.message_id === root[1].message_id) continue;

    const childNode = nodeMap.get(meta.message_id);
    if (!childNode) continue;

    if (meta.in_reply_to && messageMap.has(meta.in_reply_to)) {
      // Attach to parent
      const parentNode = nodeMap.get(meta.in_reply_to);
      if (parentNode) {
        parentNode.children.push(childNode);
      }
    } else {
      // No parent (or parent missing) - attach to root
      rootNode.children.push(childNode);
    }
  }

  // Sort children by timestamp (ascending)
  const sortChildren = (node: MessageNode) => {
    node.children.sort((a, b) => {
      const aTime = new Date(a.metadata.timestamp).getTime();
      const bTime = new Date(b.metadata.timestamp).getTime();
      return aTime - bTime;
    });
    for (const child of node.children) {
      sortChildren(child);
    }
  };

  sortChildren(rootNode);
  return rootNode;
}

/**
 * Render a single message card.
 */
function MessageCard({
  node,
  depth,
  isRoot,
}: {
  node: MessageNode;
  depth: number;
  isRoot: boolean;
}): ReactNode {
  const { metadata, chunk } = node;
  const indentPx = depth * 24;

  return (
    <div style={{ paddingLeft: `${indentPx}px` }} className="mb-4">
      <div
        className={`border rounded-lg overflow-hidden ${
          isRoot
            ? 'border-blue-300 bg-blue-50 shadow-md'
            : 'border-gray-200 bg-white shadow-sm'
        }`}
      >
        {/* Message header */}
        <div className={`px-4 py-3 ${isRoot ? 'bg-blue-100' : 'bg-gray-50'}`}>
          <div className="flex items-baseline justify-between mb-2">
            <div className="flex items-baseline gap-2">
              <span className="font-semibold text-gray-900">{metadata.sender}</span>
              {isRoot && (
                <span className="text-xs font-semibold px-2 py-1 rounded bg-blue-200 text-blue-900">
                  Root
                </span>
              )}
            </div>
            <Timestamp value={metadata.timestamp} granularity="datetime" />
          </div>

          {/* Recipients */}
          {metadata.recipients.length > 0 && (
            <div className="text-sm text-gray-600 mb-2">
              <span className="text-gray-500">to:</span> {metadata.recipients.join(', ')}
            </div>
          )}

          {/* Subject */}
          {metadata.subject && (
            <div className="text-sm font-medium text-gray-700 mb-2">
              <span className="text-gray-500">Subject:</span> {metadata.subject}
            </div>
          )}

          {/* Divider */}
          <div className="border-t border-gray-300 mt-2" />
        </div>

        {/* Message body */}
        <div className="px-4 py-3">
          <MarkdownContent content={chunk.content} />
        </div>
      </div>

      {/* Render children */}
      {node.children.length > 0 && (
        <div className="mt-4">
          {node.children.map((child) => (
            <div key={child.metadata.message_id}>
              <ChunkBoundary />
              <MessageCard node={child} depth={depth + 1} isRoot={false} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Thread view component for the messages domain.
 *
 * Displays a conversation-style thread with nested reply hierarchy,
 * derived from domain_metadata relationships.
 *
 * Features:
 * - Root message displayed at top with distinct styling
 * - Replies indented under parent based on in_reply_to relationships
 * - Supports arbitrarily nested reply chains
 * - Graceful fallback for missing message IDs
 * - Shows sender, recipients, subject, timestamp, and rendered body
 * - 'View Raw Chunks' link back to browser chunk table
 */
export function ThreadView({ sourceId, chunks }: DomainViewProps): ReactNode {
  const navigate = useNavigate();
  const rawSearch = useSearch({ from: '/browser/view/$domain/$sourceId' });
  const search = messagesViewSearchSchema.parse(rawSearch);

  // Filter chunks by thread_id if specified in URL params
  const filteredChunks = useMemo(() => {
    if (!search.thread_id) {
      return chunks;
    }
    return chunks.filter((chunk) => {
      const metadata = extractMessageMetadata(chunk);
      return metadata?.thread_id === search.thread_id;
    });
  }, [chunks, search.thread_id]);

  const rootNode = useMemo(() => buildReplyTree(filteredChunks), [filteredChunks]);

  return (
    <div className="max-w-4xl mx-auto">
      {rootNode ? (
        <div>
          {/* Thread root */}
          <MessageCard node={rootNode} depth={0} isRoot={true} />

          {/* View Raw Chunks link */}
          <div className="mt-8 pt-6 border-t border-gray-200">
            <button
              onClick={() =>
                navigate({
                  to: '/browser',
                  search: { table: 'chunks', source_id: sourceId },
                })
              }
              className="text-blue-600 hover:underline text-sm bg-none border-none cursor-pointer p-0"
            >
              View Raw Chunks
            </button>
          </div>
        </div>
      ) : (
        <div className="p-6 bg-yellow-50 border border-yellow-200 rounded">
          <p className="text-yellow-900">
            No message metadata found in chunks. Unable to display thread view.
          </p>
        </div>
      )}
    </div>
  );
}
