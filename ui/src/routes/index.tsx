import { useNavigate } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import {
  DocumentTextIcon,
  CircleStackIcon,
  ServerStackIcon,
  ClockIcon,
  MagnifyingGlassIcon,
  ChatBubbleLeftIcon,
  CalendarIcon,
  CheckCircleIcon,
  HeartIcon,
  FolderIcon,
  UsersIcon,
  MapPinIcon,
  MusicalNoteIcon,
  ExclamationTriangleIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';
import { useMemo } from 'react';
import type { ComponentType, SVGProps } from 'react';
import { useStats } from '../hooks/useStats';
import { useAdapterStats } from '../hooks/useAdapterStats';
import { useHealth } from '../hooks/useHealth';
import { fetchSources } from '../api/client';
import { getDomainColor, colors } from '../lib/designTokens';
import type { SourceSummary } from '../types/api';

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

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// ── Domain config ─────────────────────────────────────────────────

interface DomainConfig {
  label: string;
  to: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

const DOMAIN_CONFIG: Record<string, DomainConfig> = {
  notes:     { label: 'Notes',     to: '/notes',     icon: DocumentTextIcon },
  messages:  { label: 'Messages',  to: '/messages',  icon: ChatBubbleLeftIcon },
  events:    { label: 'Events',    to: '/events',    icon: CalendarIcon },
  tasks:     { label: 'Tasks',     to: '/tasks',     icon: CheckCircleIcon },
  health:    { label: 'Health',    to: '/health',    icon: HeartIcon },
  documents: { label: 'Documents', to: '/documents', icon: FolderIcon },
  people:    { label: 'People',    to: '/people',    icon: UsersIcon },
  location:  { label: 'Location',  to: '/location',  icon: MapPinIcon },
  music:     { label: 'Music',     to: '/music',     icon: MusicalNoteIcon },
};

// ── Sub-components ────────────────────────────────────────────────

interface StatCardProps {
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  value: string;
  label: string;
  sub?: string;
  subColor?: string;
}

function StatCard({ icon: Icon, value, label, sub, subColor }: StatCardProps) {
  return (
    <div
      className="flex flex-col gap-2 rounded-xl p-5 flex-1"
      style={{ background: colors.bgSurface, border: `1px solid ${colors.border}` }}
    >
      <div className="flex items-center gap-2">
        <Icon className="w-4 h-4 shrink-0" style={{ color: colors.textDim }} />
        <span className="text-xs" style={{ color: colors.textDim }}>{label}</span>
      </div>
      <span className="text-3xl font-bold tracking-tight" style={{ color: colors.textPrimary }}>
        {value}
      </span>
      {sub && (
        <span className="text-xs" style={{ color: subColor ?? colors.textMuted }}>
          {sub}
        </span>
      )}
    </div>
  );
}

function DomainBreakdownSkeleton() {
  return (
    <div
      className="rounded-xl p-5 flex flex-col gap-4"
      style={{ background: colors.bgSurface, border: `1px solid ${colors.border}` }}
    >
      <div className="h-4 w-32 rounded animate-pulse" style={{ background: colors.bgElevated }} />
      <div className="flex flex-col gap-3">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="flex items-center gap-3">
            <div className="w-20 h-3 rounded animate-pulse shrink-0" style={{ background: colors.bgElevated }} />
            <div className="flex-1 h-1.5 rounded-full animate-pulse" style={{ background: colors.bgElevated }} />
            <div className="w-12 h-3 rounded animate-pulse shrink-0" style={{ background: colors.bgElevated }} />
          </div>
        ))}
      </div>
    </div>
  );
}

interface DomainBreakdownProps {
  data: { domain: string; active_chunk_count: number }[];
}

function DomainBreakdown({ data }: DomainBreakdownProps) {
  const max = Math.max(...data.map((d) => d.active_chunk_count), 1);
  const sorted = [...data].sort((a, b) => b.active_chunk_count - a.active_chunk_count);

  return (
    <div
      className="rounded-xl p-5 flex flex-col gap-4"
      style={{ background: colors.bgSurface, border: `1px solid ${colors.border}` }}
    >
      <span className="text-sm font-semibold" style={{ color: colors.textPrimary }}>
        Domain Breakdown
      </span>
      <div className="flex flex-col gap-3">
        {sorted.map((d) => {
          const color = getDomainColor(d.domain);
          const pct = (d.active_chunk_count / max) * 100;
          return (
            <div key={d.domain} className="flex items-center gap-3">
              <span
                className="text-xs w-20 shrink-0 text-right"
                style={{ color: colors.textMuted }}
              >
                {capitalize(d.domain)}
              </span>
              <div
                className="flex-1 rounded-full overflow-hidden"
                style={{ height: 6, background: colors.bgElevated }}
              >
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{ width: `${pct}%`, background: color }}
                />
              </div>
              <span
                className="text-xs w-12 shrink-0 text-right"
                style={{ color: colors.textDim }}
              >
                {formatNumber(d.active_chunk_count)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface ActivityFeedProps {
  sources: SourceSummary[];
  isLoading: boolean;
  isRefetching: boolean;
}

function ActivityFeed({ sources, isLoading, isRefetching }: ActivityFeedProps) {
  return (
    <div
      className="rounded-xl p-5 flex flex-col gap-4 min-h-0"
      style={{ background: colors.bgSurface, border: `1px solid ${colors.border}` }}
    >
      <div className="flex items-center justify-between shrink-0">
        <span className="text-sm font-semibold" style={{ color: colors.textPrimary }}>
          Recent Activity
        </span>
        {isRefetching && (
          <ArrowPathIcon className="w-3.5 h-3.5 animate-spin" style={{ color: colors.textDim }} />
        )}
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {[...Array(5)].map((_, i) => (
            <div
              key={i}
              className="h-12 rounded-lg animate-pulse"
              style={{ background: colors.bgElevated }}
            />
          ))}
        </div>
      ) : sources.length === 0 ? (
        <div className="flex items-center justify-center py-8">
          <span className="text-sm" style={{ color: colors.textDim }}>
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
                style={{ borderColor: colors.border }}
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
                      style={{ color: colors.textPrimary }}
                    >
                      {s.adapter_id}
                    </span>
                    <span className="text-xs" style={{ color: colors.textDim }}>→</span>
                    <span className="text-xs font-medium" style={{ color }}>
                      {capitalize(s.domain)}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs" style={{ color: colors.textDim }}>
                      {formatNumber(s.chunk_count)} chunk{s.chunk_count !== 1 ? 's' : ''}
                    </span>
                    {s.display_name && (
                      <>
                        <span className="text-xs" style={{ color: colors.textDim }}>·</span>
                        <span
                          className="text-xs truncate max-w-[120px]"
                          style={{ color: colors.textDim }}
                        >
                          {s.display_name}
                        </span>
                      </>
                    )}
                  </div>
                </div>
                <span
                  className="text-xs shrink-0 mt-0.5"
                  style={{ color: colors.textDim }}
                >
                  {timeAgo(s.updated_at)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

interface QuickLaunchTilesProps {
  domainCounts: Record<string, number>;
  onNavigate: (to: string) => void;
}

function QuickLaunchTiles({ domainCounts, onNavigate }: QuickLaunchTilesProps) {
  return (
    <div
      className="rounded-xl p-5 flex flex-col gap-4"
      style={{ background: colors.bgSurface, border: `1px solid ${colors.border}` }}
    >
      <span className="text-sm font-semibold" style={{ color: colors.textPrimary }}>
        Quick Launch
      </span>
      <div className="grid grid-cols-3 gap-2">
        {Object.entries(DOMAIN_CONFIG).map(([domain, cfg]) => {
          const color = getDomainColor(domain);
          const count = domainCounts[domain] ?? 0;
          const Icon = cfg.icon;
          return (
            <button
              key={domain}
              onClick={() => onNavigate(cfg.to)}
              className="flex flex-col items-center gap-1.5 rounded-lg p-3 transition-colors text-center group"
              style={{ background: colors.bgElevated, border: `1px solid ${colors.border}` }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.borderColor = color;
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.borderColor = colors.border;
              }}
            >
              <div
                className="flex items-center justify-center rounded-lg w-8 h-8"
                style={{ background: `${color}1A` }}
              >
                <Icon className="w-4 h-4" style={{ color }} />
              </div>
              <span className="text-xs font-medium leading-tight" style={{ color: colors.textPrimary }}>
                {cfg.label}
              </span>
              {count > 0 && (
                <span className="text-[10px]" style={{ color: colors.textDim }}>
                  {formatNumber(count)}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── Search bar ────────────────────────────────────────────────────

function SearchBar({ onSearch }: { onSearch: () => void }) {
  return (
    <button
      onClick={onSearch}
      className="flex items-center gap-2 w-full rounded-lg px-4 h-10 text-left transition-colors"
      style={{
        background: colors.bgSurface,
        border: `1px solid ${colors.border}`,
        color: colors.textDim,
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLElement).style.borderColor = colors.accent;
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLElement).style.borderColor = colors.border;
      }}
    >
      <MagnifyingGlassIcon className="w-4 h-4 shrink-0" />
      <span className="text-sm">Search across all your knowledge…</span>
      <kbd
        className="ml-auto text-[10px] rounded px-1.5 py-0.5"
        style={{ background: colors.bgElevated, color: colors.textDim }}
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

  // Activity feed: fetch recent sources, sorted by updated_at desc
  const activityQuery = useQuery({
    queryKey: ['dashboard-activity'],
    queryFn: () => fetchSources({ limit: 100 }),
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  // Derive values
  const totalDocs = stats.data?.total_sources ?? 0;
  const totalChunks = stats.data?.total_active_chunks ?? 0;
  const adapterCount = adapterStats.data?.adapters.length ?? 0;
  const domainData = stats.data?.by_domain ?? [];

  // Activity feed: sort by updated_at desc, take 20 — memoized to avoid re-sort every render
  const { recentSources, lastSync } = useMemo(() => {
    const sorted = [...(activityQuery.data?.sources ?? [])].sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    );
    return { recentSources: sorted.slice(0, 20), lastSync: sorted[0]?.updated_at ?? null };
  }, [activityQuery.data]);

  // Health status — explicit boolean checks so undefined (loading) doesn't read as unhealthy
  const systemOk = health.data?.sqlite_ok === true && health.data?.chromadb_ok === true;
  const collectors = health.data?.helper?.collectors ?? [];
  const healthyCount = collectors.filter((c) => c.healthy === true).length;
  const errorCount = collectors.filter((c) => c.healthy === false).length;

  // Last Sync card derived display values — extracted to avoid nested ternaries in JSX
  // Show warning icon once health has responded and system is not OK (covers both unhealthy + error states)
  const lastSyncIcon = !health.isLoading && !systemOk ? ExclamationTriangleIcon : ClockIcon;
  const lastSyncSub = health.isLoading
    ? undefined
    : systemOk
      ? 'system healthy'
      : 'check connectivity';
  const lastSyncSubColor = systemOk ? colors.statusGreen : colors.statusAmber;

  // Active adapters subtitle
  let adapterSub = '';
  if (collectors.length > 0) {
    adapterSub = `${healthyCount} healthy`;
    if (errorCount > 0) adapterSub += ` · ${errorCount} error`;
  }

  // Domain counts map for quick launch — memoized to avoid object reconstruction every render
  const domainCounts = useMemo(
    () => Object.fromEntries(domainData.map((d) => [d.domain, d.active_chunk_count])),
    [domainData]
  );

  const handleDomainNavigate = (to: string) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    navigate({ to: to as any });
  };

  const handleSearch = () => {
    navigate({ to: '/search' });
  };

  return (
    <div className="flex flex-col gap-5 p-6 h-full min-h-0">
      {/* Search bar */}
      <SearchBar onSearch={handleSearch} />

      {/* Stat cards */}
      <div className="flex gap-4 shrink-0">
        <StatCard
          icon={DocumentTextIcon}
          value={stats.isLoading ? '—' : formatNumber(totalDocs)}
          label="Total Documents"
          sub={stats.isError ? 'Error loading' : undefined}
          subColor={colors.statusRed}
        />
        <StatCard
          icon={CircleStackIcon}
          value={stats.isLoading ? '—' : formatNumber(totalChunks)}
          label="Total Chunks"
          sub={
            stats.data
              ? `${formatNumber(stats.data.sync_queue_pending_insert + stats.data.sync_queue_pending_delete)} pending sync`
              : undefined
          }
        />
        <StatCard
          icon={ServerStackIcon}
          value={adapterStats.isLoading ? '—' : formatNumber(adapterCount)}
          label="Active Adapters"
          sub={adapterSub || undefined}
          subColor={errorCount > 0 ? colors.statusAmber : colors.statusGreen}
        />
        <StatCard
          icon={lastSyncIcon}
          value={lastSync ? timeAgo(lastSync) : (health.isLoading || activityQuery.isLoading ? '—' : 'No data')}
          label="Last Sync"
          sub={lastSyncSub}
          subColor={lastSyncSubColor}
        />
      </div>

      {/* Main content: Domain Breakdown + Activity Feed */}
      <div className="flex gap-4 flex-1 min-h-0">
        {/* Left column */}
        <div className="flex flex-col gap-4 w-[55%] shrink-0 min-h-0">
          {stats.isLoading ? (
            <DomainBreakdownSkeleton />
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
          />
        </div>
      </div>
    </div>
  );
}
