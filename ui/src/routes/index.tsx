import { useNavigate } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import type { IconName } from '@tinkermonkey/heimdall-ui';
import { StatTile, StatGrid, Panel, Chip, Icon, PageHeader } from '@tinkermonkey/heimdall-ui';
import {
  DocumentTextIcon,
  MapPinIcon,
  MusicalNoteIcon,
} from '@heroicons/react/24/outline';
import { useStats } from '../hooks/useStats';
import { useAdapterStats } from '../hooks/useAdapterStats';
import { useHealth } from '../hooks/useHealth';
import { fetchSources } from '../api/client';
import { getDomainColor, getDomainColorWithAlpha } from '../lib/designTokens';
import type { SourceSummary } from '../types/api';
import { type ValidRoute } from '../components/layoutConfig';
import { capitalize } from '../utils/formatters';

// ── Helpers ──────────────────────────────────────────────────────

function timeAgo(isoString: string | null | undefined): string {
  if (!isoString) return 'Never';
  const diff = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
  if (diff < 5) return 'just now';
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function formatNumber(n: number): string {
  return n.toLocaleString();
}

// ── Domain config ─────────────────────────────────────────────────

type IconType = IconName | React.ComponentType<{ className?: string }>;

interface DomainConfig {
  label: string;
  to: ValidRoute;
  icon: IconType;
}

const DOMAIN_CONFIG = {
  notes:     { label: 'Notes',     to: '/notes',     icon: 'component' as const },
  messages:  { label: 'Messages',  to: '/messages',  icon: 'info' as const },
  events:    { label: 'Events',    to: '/events',    icon: 'calendar' as const },
  tasks:     { label: 'Tasks',     to: '/tasks',     icon: 'check' as const },
  health:    { label: 'Health',    to: '/health',    icon: 'heart' as const },
  documents: { label: 'Documents', to: '/documents', icon: DocumentTextIcon },
  people:    { label: 'People',    to: '/people',    icon: 'user' as const },
  location:  { label: 'Location',  to: '/location',  icon: MapPinIcon },
  music:     { label: 'Music',     to: '/music',     icon: MusicalNoteIcon },
} as const satisfies Record<string, DomainConfig>;

// ── Sub-components ────────────────────────────────────────────────

function DomainBreakdownSkeleton() {
  return (
    <Panel title="Domain Breakdown">
      <div className="flex flex-col gap-3">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="flex items-center gap-3">
            <div className="w-20 h-3 rounded animate-pulse shrink-0" style={{ background: 'rgb(var(--canvas-bg-2))' }} />
            <div className="flex-1 h-1.5 rounded-full animate-pulse" style={{ background: 'rgb(var(--canvas-bg-2))' }} />
            <div className="w-12 h-3 rounded animate-pulse shrink-0" style={{ background: 'rgb(var(--canvas-bg-2))' }} />
          </div>
        ))}
      </div>
    </Panel>
  );
}

function DomainBreakdownError() {
  return (
    <Panel title="Domain Breakdown">
      <div className="flex items-center justify-center py-8">
        <span className="text-sm" style={{ color: 'rgb(var(--accent-error))' }}>
          Error loading domain breakdown
        </span>
      </div>
    </Panel>
  );
}

interface DomainBreakdownProps {
  data: { domain: string; active_chunk_count: number }[];
}

function DomainBreakdown({ data }: DomainBreakdownProps) {
  const max = Math.max(...data.map((d) => d.active_chunk_count), 1);
  const sorted = [...data].sort((a, b) => b.active_chunk_count - a.active_chunk_count);

  return (
    <Panel title="Domain Breakdown">
      <div className="flex flex-col gap-3">
        {sorted.map((d) => {
          const color = getDomainColor(d.domain);
          const pct = (d.active_chunk_count / max) * 100;
          return (
            <div key={d.domain} className="flex items-center gap-3">
              <span
                className="text-xs w-20 shrink-0 text-right"
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
              <span
                className="text-xs w-12 shrink-0 text-right"
                style={{ color: 'rgb(var(--canvas-fg-3))' }}
              >
                {formatNumber(d.active_chunk_count)}
              </span>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

interface ActivityFeedProps {
  sources: SourceSummary[];
  isLoading: boolean;
  isRefetching: boolean;
  isError: boolean;
}

function ActivityFeed({ sources, isLoading, isRefetching, isError }: ActivityFeedProps) {
  return (
    <Panel title="Recent Activity">
      {isRefetching && (
        <div className="absolute top-4 right-4">
          <span style={{ color: 'rgb(var(--canvas-fg-3))' }}>
            <Icon name="reload" size={14} className="animate-spin" />
          </span>
        </div>
      )}

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {[...Array(5)].map((_, i) => (
            <div
              key={i}
              className="h-12 rounded-lg animate-pulse"
              style={{ background: 'rgb(var(--canvas-bg-2))' }}
            />
          ))}
        </div>
      ) : isError ? (
        <div className="flex items-center justify-center py-8">
          <span className="text-sm" style={{ color: 'rgb(var(--accent-error))' }}>
            Error loading activity
          </span>
        </div>
      ) : sources.length === 0 ? (
        <div className="flex items-center justify-center py-8">
          <span className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
            No activity yet
          </span>
        </div>
      ) : (
        <div className="flex flex-col overflow-y-auto">
          {sources.map((s) => {
            const color = getDomainColor(s.domain);
            return (
              <div
                key={s.source_id}
                className="flex items-start gap-3 py-2.5 border-b last:border-b-0"
                style={{ borderColor: 'rgb(var(--canvas-border))' }}
              >
                {/* Domain color dot */}
                <div
                  className="w-2 h-2 rounded-full mt-1.5 shrink-0"
                  style={{ background: color }}
                />
                <div className="flex flex-col gap-0.5 flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span
                      className="text-xs font-medium truncate max-w-[140px]"
                      style={{ color: 'rgb(var(--canvas-fg-1))' }}
                    >
                      {s.adapter_id}
                    </span>
                    <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>→</span>
                    <Chip
                      className="text-xs font-medium"
                      style={{ color, background: getDomainColorWithAlpha(s.domain, '20'), border: 'none' }}
                    >
                      {capitalize(s.domain)}
                    </Chip>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                      {formatNumber(s.chunk_count)} chunk{s.chunk_count !== 1 ? 's' : ''}
                    </span>
                    {s.display_name && (
                      <>
                        <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>·</span>
                        <span
                          className="text-xs truncate max-w-[120px]"
                          style={{ color: 'rgb(var(--canvas-fg-3))' }}
                        >
                          {s.display_name}
                        </span>
                      </>
                    )}
                  </div>
                </div>
                <span
                  className="text-xs shrink-0 mt-0.5"
                  style={{ color: 'rgb(var(--canvas-fg-3))' }}
                >
                  {timeAgo(s.updated_at)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}

function DomainIcon({ icon }: { icon: IconType }) {
  if (typeof icon === 'string') {
    return <Icon name={icon} size={16} />;
  }
  const Component = icon;
  return <Component className="w-4 h-4" />;
}

interface QuickLaunchTilesProps {
  domainCounts: Record<string, number>;
  onNavigate: (to: ValidRoute) => void;
}

function QuickLaunchTiles({ domainCounts, onNavigate }: QuickLaunchTilesProps) {
  return (
    <Panel title="Quick Launch">
      <div className="grid grid-cols-3 gap-2">
        {Object.entries(DOMAIN_CONFIG).map(([domain, cfg]) => {
          const color = getDomainColor(domain);
          const count = domainCounts[domain] ?? 0;

          return (
            <button
              key={domain}
              onClick={() => onNavigate(cfg.to)}
              className="flex flex-col items-center gap-1.5 rounded-lg p-3 transition-colors text-center group"
              style={{ background: 'rgb(var(--canvas-surface))', border: `1px solid rgb(var(--canvas-border))` }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.borderColor = color;
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.borderColor = 'rgb(var(--canvas-border))';
              }}
            >
              <div
                className="flex items-center justify-center rounded-lg w-8 h-8"
                style={{ background: getDomainColorWithAlpha(domain, '1A'), color }}
              >
                <DomainIcon icon={cfg.icon} />
              </div>
              <span className="text-xs font-medium leading-tight" style={{ color: 'rgb(var(--canvas-fg-1))' }}>
                {cfg.label}
              </span>
              {count > 0 && (
                <span className="text-[10px]" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                  {formatNumber(count)}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </Panel>
  );
}

// ── Search bar ────────────────────────────────────────────────────

function SearchBar({ onSearch }: { onSearch: () => void }) {
  return (
    <button
      onClick={onSearch}
      className="flex items-center gap-2 w-full rounded-lg px-4 h-10 text-left transition-colors"
      style={{
        background: 'rgb(var(--canvas-surface))',
        border: `1px solid rgb(var(--canvas-border))`,
        color: 'rgb(var(--canvas-fg-3))',
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLElement).style.borderColor = 'rgb(var(--accent-primary))';
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLElement).style.borderColor = 'rgb(var(--canvas-border))';
      }}
    >
      <Icon name="search" size={16} className="shrink-0" />
      <span className="text-sm">Search across all your knowledge…</span>
      <kbd
        className="ml-auto text-[10px] rounded px-1.5 py-0.5"
        style={{ background: 'rgb(var(--canvas-surface))', color: 'rgb(var(--canvas-fg-3))' }}
      >
        /
      </kbd>
    </button>
  );
}

// ── Dashboard page ────────────────────────────────────────────────

export default function DashboardPage() {
  const navigate = useNavigate();

  const stats = useStats();
  const adapterStats = useAdapterStats();
  const health = useHealth();

  // Activity feed: fetch 20 most recently updated sources via server-side sort
  const activityQuery = useQuery({
    queryKey: ['dashboard-activity'],
    queryFn: () => fetchSources({ limit: 20, sort_by: 'updated_at', order: 'desc' }),
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  // Derive values
  const totalDocs = stats.data?.total_sources ?? 0;
  const totalChunks = stats.data?.total_active_chunks ?? 0;
  const adapterCount = adapterStats.data?.adapters.length ?? 0;
  const domainData = stats.data?.by_domain ?? [];

  // Activity feed: already sorted by updated_at desc from the server
  const recentSources = activityQuery.data?.sources ?? [];
  const lastSync = recentSources[0]?.updated_at ?? null;

  // Domain counts map for quick launch — memoized to avoid object reconstruction every render
  const domainCounts = useMemo(
    () => Object.fromEntries(domainData.map((d) => [d.domain, d.active_chunk_count])),
    [domainData]
  );

  const handleDomainNavigate = (to: ValidRoute) => {
    navigate({ to: to as string });
  };

  const handleSearch = () => {
    navigate({ to: '/search' });
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader
        eyebrow="Context Library"
        title="Overview"
        subtitle="System overview and activity"
      />
      <div className="flex flex-col gap-5 p-6 flex-1 overflow-auto">
      {/* Search bar */}
      <SearchBar onSearch={handleSearch} />

      {/* Stat tiles grid */}
      <StatGrid columns={4} className="shrink-0">
        <StatTile
          label="Total Documents"
          value={stats.isError ? 'Error loading' : stats.isLoading ? '—' : formatNumber(totalDocs)}
        />
        <StatTile
          label="Total Chunks"
          value={stats.isError ? 'Error loading' : stats.isLoading ? '—' : formatNumber(totalChunks)}
        />
        <StatTile
          label="Active Adapters"
          value={adapterStats.isError ? 'Error loading' : adapterStats.isLoading ? '—' : formatNumber(adapterCount)}
        />
        <StatTile
          label="Last Sync"
          value={health.isError || activityQuery.isError ? 'Error loading' : lastSync ? timeAgo(lastSync) : (health.isLoading || activityQuery.isLoading ? '—' : 'No data')}
        />
      </StatGrid>

      {/* Main content: Domain Breakdown + Activity Feed */}
      <div className="flex gap-4 flex-1 min-h-0">
        {/* Left column */}
        <div className="flex flex-col gap-4 w-[55%] shrink-0 min-h-0">
          {stats.isLoading ? (
            <DomainBreakdownSkeleton />
          ) : stats.isError ? (
            <DomainBreakdownError />
          ) : domainData.length > 0 ? (
            <DomainBreakdown data={domainData} />
          ) : null}
          <QuickLaunchTiles
            domainCounts={domainCounts}
            onNavigate={handleDomainNavigate}
          />
        </div>

        {/* Right column: Activity Feed */}
        <div className="flex-1 min-h-0 overflow-y-auto">
          <ActivityFeed
            sources={recentSources}
            isLoading={activityQuery.isLoading}
            isRefetching={activityQuery.isRefetching}
            isError={activityQuery.isError}
          />
        </div>
      </div>
      </div>
    </div>
  );
}

