import { useState, useMemo } from 'react';
import type { ReactNode } from 'react';
import { useParams } from '@tanstack/react-router';
import {
  PageHeader,
  VersionPill,
  LineageRail,
  VersionTimeline,
  LogStream,
} from '@tinkermonkey/heimdall-ui';
import type { LineageNode, VersionEntry, LogEntry } from '@tinkermonkey/heimdall-ui';
import { KVGrid } from '../components/KVGrid';
import { SegmentedControl } from '../components/SegmentedControl';
import { useChunk, useChunkVersionChain } from '../hooks/useChunks';
import { useAdminLogs } from '../hooks/useAdminLogs';
import { capitalize } from '../utils/formatters';

const ADMIN_LOGS_LIMIT = 200;

type CenterView = 'context' | 'content' | 'embedding';

function SectionHeading({ children }: { children: ReactNode }) {
  return (
    <h2
      className="text-xs font-medium uppercase tracking-wider mb-3"
      style={{ color: 'rgb(var(--canvas-fg-3))' }}
    >
      {children}
    </h2>
  );
}

export default function ChunkInspectorPage(): ReactNode {
  const { chunkHash } = useParams({ from: '/chunks/$chunkHash' });
  const [centerView, setCenterView] = useState<CenterView>('context');

  const chunkQuery = useChunk(chunkHash);

  const chunk = chunkQuery.data;
  const sourceId = chunk?.lineage.source_id ?? '';

  const versionChainQuery = useChunkVersionChain(chunkHash, sourceId, !!sourceId);
  const logsQuery = useAdminLogs(ADMIN_LOGS_LIMIT);

  const lineageNodes: LineageNode[] = useMemo(() => {
    if (!chunk) return [];
    const nodes: LineageNode[] = [
      { icon: 'component', label: chunk.lineage.adapter_id },
      { icon: 'schema', label: `Normalize: ${chunk.lineage.normalizer_version}` },
      { icon: 'gitBranch', label: `Source v${chunk.lineage.source_version_id}` },
      { icon: 'file', label: chunk.chunk_type },
    ];
    if (chunk.context_header) {
      const heading = chunk.context_header.split('\n')[0].slice(0, 50);
      nodes.push({ icon: 'tag', label: heading });
    }
    nodes.push({ icon: 'zap', label: chunk.lineage.embedding_model_id });
    nodes.push({ icon: 'hardDrive', label: 'ChromaDB + SQLite' });
    return nodes;
  }, [chunk]);

  const kvRows = useMemo(() => {
    if (!chunk) return [];
    return [
      { key: 'Domain', value: capitalize(chunk.lineage.domain) },
      { key: 'Source', value: <code style={{ fontFamily: 'monospace', fontSize: 12 }}>{chunk.lineage.source_id}</code> },
      { key: 'Adapter', value: chunk.lineage.adapter_id },
      { key: 'Content Hash', value: <code style={{ fontFamily: 'monospace', fontSize: 12 }}>{chunk.chunk_hash.substring(0, 24)}…</code> },
      { key: 'Chunk Type', value: chunk.chunk_type },
      { key: 'Embedding Model', value: chunk.lineage.embedding_model_id },
    ];
  }, [chunk]);

  const timelineEntries: VersionEntry[] = useMemo(() => {
    const chain = versionChainQuery.data?.chain ?? [];
    return chain.map((item, index) => {
      const isHead = item.chunk_hash === chunkHash || index === chain.length - 1;
      const baseHeadline = item.context_header
        ? item.context_header.split('\n')[0].slice(0, 60)
        : item.chunk_type;
      const scoreLabel =
        item.similarity_to_head != null && !isHead
          ? ` · ${(item.similarity_to_head * 100).toFixed(1)}% similar`
          : '';
      return {
        id: item.chunk_hash,
        label: item.chunk_hash.substring(0, 12),
        headline: `${baseHeadline}${scoreLabel}`,
        timestamp: item.fetch_timestamp ?? '',
        head: isHead,
      };
    });
  }, [versionChainQuery.data, chunkHash]);

  const logEntries: LogEntry[] = useMemo(() => {
    const entries = logsQuery.data?.entries ?? [];
    return entries
      .filter((e) => e.chunk_hash === chunkHash)
      .map((e) => ({
        id: String(e.id),
        timestamp: e.synced_at ?? new Date().toISOString(),
        level: 'INFO' as const,
        message: e.operation,
        op: e.operation,
        target: e.chunk_hash.substring(0, 12),
      }));
  }, [logsQuery.data, chunkHash]);

  const logsMayBeTruncated =
    !logsQuery.isLoading &&
    (logsQuery.data?.total ?? 0) > ADMIN_LOGS_LIMIT;

  const isLoading = chunkQuery.isLoading;

  if (isLoading) {
    return (
      <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
        <PageHeader eyebrow="Chunks" title="Chunk Inspector" />
        <div className="flex-1 flex items-center justify-center">
          <span className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>Loading…</span>
        </div>
      </div>
    );
  }

  if (chunkQuery.isError || !chunk) {
    return (
      <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
        <PageHeader eyebrow="Chunks" title="Chunk Inspector" />
        <div className="flex-1 flex items-center justify-center">
          <span className="text-sm" style={{ color: 'rgb(var(--status-error))' }}>
            Failed to load chunk
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
      <PageHeader
        eyebrow="Chunks"
        title={chunkHash.substring(0, 24)}
        idChip={chunkHash.substring(0, 16)}
        subtitle={`${capitalize(chunk.lineage.domain)} · ${chunk.chunk_type}`}
        actions={<VersionPill>v{chunk.lineage.source_version_id}</VersionPill>}
      />

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        {/* Provenance Chain */}
        <section>
          <SectionHeading>Provenance</SectionHeading>
          <LineageRail nodes={lineageNodes} wrap aria-label="Chunk provenance chain" />
        </section>

        {/* Metadata */}
        <section>
          <SectionHeading>Metadata</SectionHeading>
          <KVGrid rows={kvRows} keyWidth={140} />
        </section>

        {/* Content viewer */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <SectionHeading>Content</SectionHeading>
            <SegmentedControl
              value={centerView}
              onChange={(v) => setCenterView(v as CenterView)}
              options={[
                { value: 'context', label: 'Context' },
                { value: 'content', label: 'Content' },
                { value: 'embedding', label: 'Embedding' },
              ]}
            />
          </div>

          <div
            className="rounded p-4"
            style={{
              background: 'rgb(var(--canvas-surface))',
              border: `1px solid rgb(var(--canvas-border))`,
              minHeight: 120,
            }}
          >
            {centerView === 'context' && (
              chunk.context_header ? (
                <pre
                  className="text-sm whitespace-pre-wrap"
                  style={{ color: 'rgb(var(--canvas-fg-1))', fontFamily: 'monospace' }}
                >
                  {chunk.context_header}
                </pre>
              ) : (
                <span className="text-sm italic" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                  No context header
                </span>
              )
            )}

            {centerView === 'content' && (
              <pre
                className="text-sm whitespace-pre-wrap"
                style={{ color: 'rgb(var(--canvas-fg-1))', fontFamily: 'monospace' }}
              >
                {chunk.content}
              </pre>
            )}

            {centerView === 'embedding' && (
              <div className="space-y-2 text-sm">
                <div style={{ color: 'rgb(var(--canvas-fg-2))' }}>
                  <span style={{ color: 'rgb(var(--canvas-fg-3))' }}>Model: </span>
                  <code style={{ fontFamily: 'monospace' }}>{chunk.lineage.embedding_model_id}</code>
                </div>
                <div style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                  <span style={{ color: 'rgb(var(--canvas-fg-3))' }}>Normalizer: </span>
                  <code style={{ fontFamily: 'monospace' }}>{chunk.lineage.normalizer_version}</code>
                </div>
                <div className="text-xs italic" style={{ color: 'rgb(var(--canvas-fg-4, var(--canvas-fg-3)))' }}>
                  Embedding vector is not exposed via the API
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Chunk Version Chain */}
        <section>
          <SectionHeading>Version Chain</SectionHeading>
          {!sourceId ? (
            <span className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
              Waiting for source ID…
            </span>
          ) : versionChainQuery.isLoading ? (
            <span className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>Loading…</span>
          ) : versionChainQuery.isError ? (
            <span className="text-sm" style={{ color: 'rgb(var(--status-error))' }}>
              Failed to load version chain
            </span>
          ) : (
            <VersionTimeline
              entries={timelineEntries}
              order="newest-first"
              emptyState="No version chain data"
            />
          )}
        </section>

        {/* Sync Log */}
        <section>
          <SectionHeading>Sync Log</SectionHeading>
          {logsMayBeTruncated && (
            <p
              className="text-xs mb-2 italic"
              style={{ color: 'rgb(var(--status-warning, var(--canvas-fg-3)))' }}
            >
              The log has {logsQuery.data!.total} entries; only the most recent {ADMIN_LOGS_LIMIT} were
              fetched. Entries for this chunk may be missing.
            </p>
          )}
          {logsQuery.isLoading ? (
            <span className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>Loading…</span>
          ) : logEntries.length === 0 ? (
            <span className="text-sm italic" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
              No sync log entries found for this chunk
            </span>
          ) : (
            <LogStream entries={logEntries} showOps maxRows={50} />
          )}
        </section>
      </div>
    </div>
  );
}
