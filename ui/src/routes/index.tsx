import { useMemo } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  StatTile,
  StatGrid,
  Panel,
  PageHeader,
  ActivityTimeline,
  PipelineCard,
  MetricRow,
  QuickAccessGrid,
  Icon,
} from '@tinkermonkey/heimdall-ui';
import { useStats } from '../hooks/useStats';
import { useAdapterStats } from '../hooks/useAdapterStats';
import { useHealth } from '../hooks/useHealth';
import { useAdminConfig } from '../hooks/useAdminConfig';
import { useAdminLogs } from '../hooks/useAdminLogs';
import { useActivity } from '../hooks/useActivity';
import { usePipelineStatus } from '../hooks/usePipelineStatus';
import { DomainTile } from '../components/DomainTile';
import { DOMAIN_NAMES } from '../lib/designTokens';
import { capitalize } from '../utils/formatters';

// ── Constants ─────────────────────────────────────────────────────

const domainTileRoutes: Record<string, string> = {
  notes: '/notes', messages: '/messages', events: '/events', tasks: '/tasks',
  health: '/health', documents: '/documents', people: '/people', location: '/location',
  music: '/music',
};

// ── Helpers ───────────────────────────────────────────────────────

function formatNumber(n: number): string {
  return n.toLocaleString();
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

// ── Dashboard page ────────────────────────────────────────────────

export default function DashboardPage() {
  const navigate = useNavigate();

  const stats = useStats();
  const adapterStats = useAdapterStats();
  const health = useHealth();
  const adminConfig = useAdminConfig();
  const adminLogs = useAdminLogs(1);
  const activity = useActivity(25);
  const pipelineStatus = usePipelineStatus();

  // Group adapter stats by domain for DomainTile grid
  const domainData = useMemo(() => {
    if (!adapterStats.data) return {} as Record<string, { source_count: number; active_chunk_count: number; adapters: string[] }>;
    const byDomain: Record<string, { source_count: number; active_chunk_count: number; adapters: string[] }> = {};
    for (const a of adapterStats.data.adapters) {
      if (!byDomain[a.domain]) {
        byDomain[a.domain] = { source_count: 0, active_chunk_count: 0, adapters: [] };
      }
      byDomain[a.domain].source_count += a.source_count;
      byDomain[a.domain].active_chunk_count += a.active_chunk_count;
      byDomain[a.domain].adapters.push(a.adapter_id);
    }
    return byDomain;
  }, [adapterStats.data]);

  const totalSources = stats.data?.total_sources ?? 0;
  const totalChunks = stats.data?.total_active_chunks ?? 0;
  const vectorCount = health.data?.vector_count ?? 0;
  const embeddingDim = health.data?.embedding_dimension ?? 0;
  const versionTotal = adminLogs.data?.total ?? 0;
  const dbSizeBytes = adminConfig.data?.db_size_bytes ?? 0;
  const pendingInserts = stats.data?.sync_queue_pending_insert ?? 0;
  const pendingDeletes = stats.data?.sync_queue_pending_delete ?? 0;
  const pendingTotal = pendingInserts + pendingDeletes;

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader
        eyebrow="Context Library"
        title="Overview"
        subtitle="System overview and activity"
      />
      <div className="flex flex-col gap-5 p-6 flex-1 overflow-auto">

        {/* Stat tiles */}
        <StatGrid columns={4} className="shrink-0">
          <StatTile
            label="Sources"
            value={stats.isLoading ? '—' : stats.isError ? 'Error' : formatNumber(totalSources)}
            icon="data"
          />
          <StatTile
            label="Active Chunks"
            value={stats.isLoading ? '—' : stats.isError ? 'Error' : formatNumber(totalChunks)}
            icon="component"
          />
          <StatTile
            label="Embeddings"
            value={health.isLoading ? '—' : health.isError ? 'Error' : formatNumber(vectorCount)}
            meta={embeddingDim > 0 ? `dim: ${embeddingDim}` : undefined}
            icon="zap"
          />
          <StatTile
            label="Versions"
            value={adminLogs.isLoading ? '—' : adminLogs.isError ? 'Error' : formatNumber(versionTotal)}
            icon="gitBranch"
          />
        </StatGrid>

        {/* Domain tiles grid */}
        <Panel title="Domains">
          <div className="grid grid-cols-3 gap-3">
            {DOMAIN_NAMES.map((domain) => (
              <DomainTile
                key={domain}
                domain={domain}
                name={capitalize(domain)}
                recordCount={domainData[domain]?.source_count ?? 0}
                adapterCount={domainData[domain]?.adapters.length ?? 0}
                chunkCount={domainData[domain]?.active_chunk_count ?? 0}
                adapters={domainData[domain]?.adapters ?? []}
                onClick={() => navigate({ to: domainTileRoutes[domain] as string })}
              />
            ))}
          </div>
        </Panel>

        {/* Two-column: left (pipeline + storage), right (activity + quick actions) */}
        <div className="flex gap-4">

          {/* Left column */}
          <div className="flex-1 flex flex-col gap-4 min-w-0">

            {/* Active pipelines */}
            <Panel title="Active Pipelines">
              {pipelineStatus.isLoading ? (
                <div className="flex items-center justify-center py-8">
                  <div
                    className="w-5 h-5 rounded-full border-2 border-t-transparent animate-spin"
                    style={{ borderColor: 'rgb(var(--accent-primary)) transparent transparent transparent' }}
                  />
                </div>
              ) : pipelineStatus.isError ? (
                <div className="flex flex-col items-center justify-center py-8 gap-2">
                  <span style={{ color: 'rgb(var(--status-error))' }}>
                    <Icon name="alert" size={20} />
                  </span>
                  <span className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                    Failed to load pipeline status
                  </span>
                </div>
              ) : pipelineStatus.data && pipelineStatus.data.length > 0 ? (
                <div className="flex flex-col gap-3">
                  {pipelineStatus.data.map((pipeline) => (
                    <PipelineCard key={pipeline.id} pipeline={pipeline} />
                  ))}
                </div>
              ) : (
                <div className="flex items-center justify-center py-8">
                  <span className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                    No active pipelines
                  </span>
                </div>
              )}
            </Panel>

            {/* Storage panel */}
            <Panel title="Storage">
              <div className="flex flex-col gap-1">
                <MetricRow
                  label="SQLite"
                  value={formatBytes(dbSizeBytes)}
                  percent={Math.min(100, (dbSizeBytes / (5 * 1024 * 1024 * 1024)) * 100)}
                  color="emerald"
                />
                <MetricRow
                  label="ChromaDB"
                  value={formatNumber(vectorCount)}
                  unit="vectors"
                  percent={Math.min(100, (vectorCount / 1_000_000) * 100)}
                  color="cyan"
                />
                <MetricRow
                  label="Sync Queue"
                  value={formatNumber(pendingTotal)}
                  unit="pending"
                  percent={Math.min(100, (pendingTotal / 100) * 100)}
                  color={pendingTotal > 0 ? 'amber' : 'emerald'}
                />
              </div>
            </Panel>
          </div>

          {/* Right column */}
          <div className="w-80 shrink-0 flex flex-col gap-4">

            {/* Recent ingests activity timeline */}
            <Panel title="Recent Ingests">
              {activity.isError ? (
                <div className="flex flex-col items-center justify-center py-8 gap-2">
                  <span style={{ color: 'rgb(var(--status-error))' }}>
                    <Icon name="alert" size={20} />
                  </span>
                  <span className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                    Failed to load activity
                  </span>
                </div>
              ) : (
                <ActivityTimeline
                  events={activity.data ?? []}
                  emptyState="No recent activity"
                />
              )}
            </Panel>

            {/* Quick actions */}
            <Panel title="Quick Actions">
              <QuickAccessGrid
                tiles={[
                  { id: 'search', icon: 'search', title: 'Search', description: 'Semantic search across all content' },
                  { id: 'sources', icon: 'data', title: 'Sources', description: 'Browse ingested sources' },
                  { id: 'pipeline', icon: 'pipeline', title: 'Pipeline', description: 'View adapter sync status' },
                  { id: 'admin', icon: 'settings', title: 'Admin', description: 'Manage configuration' },
                ]}
                onAction={(id) => {
                  const routes: Record<string, string> = {
                    search: '/search',
                    sources: '/sources',
                    pipeline: '/pipeline',
                    admin: '/admin',
                  };
                  if (routes[id]) navigate({ to: routes[id] as string });
                }}
                columns={2}
              />
            </Panel>
          </div>
        </div>
      </div>
    </div>
  );
}
