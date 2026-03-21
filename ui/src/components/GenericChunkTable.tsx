import { useMemo, useState } from 'react';
import type { ChunkResponse } from '../types/api';

interface GenericChunkTableProps {
  chunks: ChunkResponse[];
}

/**
 * Generic fallback component for rendering chunks as a table.
 * Used for domains without a specialized view implementation.
 *
 * This component displays chunks in a table format with basic metadata display
 * and an expanded detail panel for the selected chunk.
 */
export function GenericChunkTable({
  chunks,
}: GenericChunkTableProps) {
  const [selectedChunkHash, setSelectedChunkHash] = useState<string | null>(null);

  const selectedChunk = useMemo(
    () => chunks.find((c) => c.chunk_hash === selectedChunkHash),
    [chunks, selectedChunkHash]
  );

  return (
    <div className="space-y-6">
      {/* Chunks Table */}
      <div className="bg-white rounded border border-gray-200 overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="text-left px-4 py-3 font-semibold text-sm text-gray-700">Hash</th>
              <th className="text-left px-4 py-3 font-semibold text-sm text-gray-700">Index</th>
              <th className="text-left px-4 py-3 font-semibold text-sm text-gray-700">Content</th>
              <th className="text-left px-4 py-3 font-semibold text-sm text-gray-700">Type</th>
              <th className="text-left px-4 py-3 font-semibold text-sm text-gray-700">Version</th>
            </tr>
          </thead>
          <tbody>
            {chunks.length === 0 ? (
              <tr>
                <td colSpan={5} className="text-center py-8 text-gray-500">
                  No chunks available
                </td>
              </tr>
            ) : (
              chunks.map((chunk) => (
                <tr
                  key={chunk.chunk_hash}
                  onClick={() => setSelectedChunkHash(chunk.chunk_hash)}
                  className={`border-b border-gray-200 hover:bg-gray-50 cursor-pointer ${
                    selectedChunkHash === chunk.chunk_hash ? 'bg-blue-50' : ''
                  }`}
                >
                  <td className="px-4 py-3 text-xs">
                    <code>{chunk.chunk_hash.substring(0, 12)}…</code>
                  </td>
                  <td className="px-4 py-3 text-sm">{chunk.chunk_index}</td>
                  <td className="px-4 py-3 text-sm text-gray-700 line-clamp-2">
                    {chunk.content.substring(0, 200)}
                    {chunk.content.length > 200 ? '…' : ''}
                  </td>
                  <td className="px-4 py-3">
                    <span className="inline-block px-2 py-1 bg-gray-100 text-gray-800 rounded text-xs">
                      {chunk.chunk_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    v{chunk.lineage.source_version_id || '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Detail Panel */}
      {selectedChunk && (
        <ChunkDetailPanel chunk={selectedChunk} />
      )}
    </div>
  );
}

/**
 * Detail panel for displaying comprehensive chunk information.
 */
function ChunkDetailPanel({ chunk }: { chunk: ChunkResponse }) {
  return (
    <div className="space-y-6 bg-white rounded border border-gray-200 p-6">
      <div>
        <h3 className="text-lg font-semibold mb-2">Chunk Details</h3>
        <p className="text-sm text-gray-600 mb-4">Hash: {chunk.chunk_hash}</p>
      </div>

      {/* Full Content */}
      <div>
        <h4 className="font-semibold text-sm mb-2">Content</h4>
        <pre className="bg-gray-100 p-3 rounded text-xs overflow-auto max-h-40 whitespace-pre-wrap break-words">
          {chunk.content}
        </pre>
      </div>

      {/* Context Header */}
      {chunk.context_header && (
        <div>
          <h4 className="font-semibold text-sm mb-2">Context Header</h4>
          <pre className="bg-gray-100 p-3 rounded text-xs overflow-auto">
            {chunk.context_header}
          </pre>
        </div>
      )}

      {/* Chunk Type and Index */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <span className="text-sm font-semibold">Chunk Type:</span>
          <span className="block text-sm text-gray-600">{chunk.chunk_type}</span>
        </div>
        <div>
          <span className="text-sm font-semibold">Chunk Index:</span>
          <span className="block text-sm text-gray-600">{chunk.chunk_index}</span>
        </div>
      </div>

      {/* Domain Metadata */}
      {chunk.domain_metadata && (
        <div>
          <h4 className="font-semibold text-sm mb-2">Domain Metadata</h4>
          <pre className="bg-gray-100 p-3 rounded text-xs overflow-auto max-h-32">
            {JSON.stringify(chunk.domain_metadata, null, 2)}
          </pre>
        </div>
      )}

      {/* Cross References */}
      {chunk.cross_refs && chunk.cross_refs.length > 0 && (
        <div>
          <h4 className="font-semibold text-sm mb-2">Cross References</h4>
          <div className="space-y-1">
            {chunk.cross_refs.map((ref, i) => (
              <code key={i} className="block text-xs text-gray-600 break-all">
                {ref}
              </code>
            ))}
          </div>
        </div>
      )}

      {/* Lineage */}
      {chunk.lineage && (
        <div>
          <h4 className="font-semibold text-sm mb-2">Lineage</h4>
          <div className="space-y-1 text-sm">
            <div>
              <span className="font-semibold">Source ID:</span>
              <code className="ml-2 text-xs">{chunk.lineage.source_id}</code>
            </div>
            <div>
              <span className="font-semibold">Domain:</span>
              <span className="ml-2">{chunk.lineage.domain}</span>
            </div>
            <div>
              <span className="font-semibold">Adapter:</span>
              <span className="ml-2">{chunk.lineage.adapter_id}</span>
            </div>
            <div>
              <span className="font-semibold">Version:</span>
              <span className="ml-2">v{chunk.lineage.source_version_id}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
