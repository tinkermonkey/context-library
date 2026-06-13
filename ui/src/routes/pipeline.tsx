import type { ReactNode } from 'react';
import { PageHeader, StatGrid, StatTile, Panel, Icon } from '@tinkermonkey/heimdall-ui';
import { useStats } from '../hooks/useStats';
import { useHealth } from '../hooks/useHealth';
import { useAdminAdapters } from '../hooks/useAdminAdapters';
import { getDomainColor } from '../lib/designTokens';
import { capitalize } from '../utils/formatters';

function formatNumber(n: number): string {
  return n.toLocaleString();
}

export default function PipelinePage(): ReactNode {
  const statsQuery = useStats();
  const healthQuery = useHealth(30_000);
  const adaptersQuery = useAdminAdapters(30_000);

  const stats = statsQuery.data;
  const health = healthQuery.data;
  const adapters = adaptersQuery.data?.adapters ?? [];

  const totalSources = stats?.total_sources ?? 0;
  const totalChunks = stats?.total_active_chunks ?? 0;
  const retiredChunks = stats?.retired_chunk_count ?? 0;
  const pendingInserts = stats?.sync_queue_pending_insert ?? 0;
  const pendingDeletes = stats?.sync_queue_pending_delete ?? 0;

  const healthyAdapters = adapters.filter((a) =>
    health?.helper?.collectors?.find((c) => c.name === a.adapter_id)?.healthy !== false
  ).length;

  return (
    <div className="flex flex-col h-full overflow-auto" style={{ background: 'rgb(var(--canvas-bg))' }}>
      <PageHeader
        eyebrow="System"
        title="Pipeline"
        subtitle="Ingestion pipeline status and sync queue"
      />

      <div className="flex flex-col gap-5 p-6">
        {/* ── Overview stats ── */}
        <StatGrid columns={4} className="shrink-0">
          <StatTile
            label="Total Sources"
            value={statsQuery.isLoading ? '—' : statsQuery.isError ? 'Error' : formatNumber(totalSources)}
          />
          <StatTile
            label="Active Chunks"
            value={statsQuery.isLoading ? '—' : statsQuery.isError ? 'Error' : formatNumber(totalChunks)}
          />
          <StatTile
            label="Retired Chunks"
            value={statsQuery.isLoading ? '—' : statsQuery.isError ? 'Error' : formatNumber(retiredChunks)}
          />
          <StatTile
            label="Active Adapters"
            value={adaptersQuery.isLoading ? '—' : adaptersQuery.isError ? 'Error' : `${healthyAdapters} / ${adapters.length}`}
          />
        </StatGrid>

        {/* ── Sync queue ── */}
        <Panel title="Sync Queue">
          {statsQuery.isError ? (
            <div className="flex items-center gap-2 py-2" style={{ color: 'rgb(var(--status-error))' }}>
              <Icon name="alert" size={16} />
              <span className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>Failed to load sync queue</span>
            </div>
          ) : (
            <div className="flex gap-6">
              <div className="flex flex-col gap-1">
                <span className="text-xs uppercase tracking-wide font-medium" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                  Pending Inserts
                </span>
                <span
                  className="text-2xl font-semibold font-mono"
                  style={{ color: pendingInserts > 0 ? 'rgb(var(--accent-primary))' : 'rgb(var(--canvas-fg-2))' }}
                >
                  {statsQuery.isLoading ? '—' : formatNumber(pendingInserts)}
                </span>
              </div>
              <div
                className="w-px shrink-0"
                style={{ background: 'rgb(var(--canvas-border))' }}
              />
              <div className="flex flex-col gap-1">
                <span className="text-xs uppercase tracking-wide font-medium" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                  Pending Deletes
                </span>
                <span
                  className="text-2xl font-semibold font-mono"
                  style={{ color: pendingDeletes > 0 ? 'rgb(var(--status-error))' : 'rgb(var(--canvas-fg-2))' }}
                >
                  {statsQuery.isLoading ? '—' : formatNumber(pendingDeletes)}
                </span>
              </div>
            </div>
          )}
        </Panel>

        {/* ── Domain breakdown ── */}
        {stats && stats.by_domain.length > 0 && (
          <Panel title="Domain Breakdown">
            <div className="flex flex-col gap-3">
              {[...stats.by_domain]
                .sort((a, b) => b.active_chunk_count - a.active_chunk_count)
                .map((d) => {
                  const color = getDomainColor(d.domain);
                  const max = Math.max(...stats.by_domain.map((x) => x.active_chunk_count), 1);
                  const pct = (d.active_chunk_count / max) * 100;
                  return (
                    <div key={d.domain} className="flex items-center gap-3">
                      <div
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ background: color }}
                      />
                      <span
                        className="text-xs w-24 shrink-0"
                        style={{ color: 'rgb(var(--canvas-fg-2))' }}
                      >
                        {capitalize(d.domain)}
                      </span>
                      <div
                        className="flex-1 rounded-full overflow-hidden"
                        style={{ height: 6, background: 'rgb(var(--canvas-surface))' }}
                      >
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{ width: `${pct}%`, background: color }}
                        />
                      </div>
                      <span className="text-xs font-mono w-16 text-right shrink-0" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                        {formatNumber(d.active_chunk_count)}
                      </span>
                      <span className="text-xs w-16 text-right shrink-0" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                        {formatNumber(d.source_count)} src
                      </span>
                    </div>
                  );
                })}
            </div>
          </Panel>
        )}

        {/* ── Storage health ── */}
        <Panel title="Storage">
          {healthQuery.isError ? (
            <div className="flex items-center gap-2 py-2" style={{ color: 'rgb(var(--status-error))' }}>
              <Icon name="alert" size={16} />
              <span className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>Failed to load storage health</span>
            </div>
          ) : (
            <div className="flex gap-6">
              <div className="flex items-center gap-2">
                <div
                  className="w-2 h-2 rounded-full"
                  style={{ background: health?.sqlite_ok ? 'rgb(var(--status-ok))' : 'rgb(var(--status-error))' }}
                />
                <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
                  SQLite · {health?.sqlite_ok ? 'ok' : healthQuery.isLoading ? '…' : 'error'}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-2 h-2 rounded-full"
                  style={{ background: health?.chromadb_ok ? 'rgb(var(--status-ok))' : 'rgb(var(--status-error))' }}
                />
                <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
                  ChromaDB · {health?.chromadb_ok ? 'ok' : healthQuery.isLoading ? '…' : 'error'}
                </span>
              </div>
              {health && (
                <span className="text-xs font-mono ml-auto" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                  {health.vector_count.toLocaleString()} vectors · {health.embedding_model}
                </span>
              )}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
