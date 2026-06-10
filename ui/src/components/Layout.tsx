import { type ReactNode, useState, useRef, useEffect } from 'react';
import { useRouter, useRouterState } from '@tanstack/react-router';
import { useQueryClient } from '@tanstack/react-query';
import { ShellLayout, Avatar, Chip, Icon, type IconName, type StatusbarItem } from '@tinkermonkey/heimdall-ui';
import { CommandPaletteWrapper } from './CommandPaletteWrapper';
import { useStats } from '../hooks/useStats';
import { useHealth } from '../hooks/useHealth';
import { useAdminAdapters } from '../hooks/useAdminAdapters';
import {
  LIBRARY_NAV_ITEMS,
  DOMAIN_NAV_ITEMS,
  SYSTEM_NAV_ITEMS,
  ALL_NAV_ITEMS,
  type ValidRoute,
} from './layoutConfig';

const APP_VERSION = '1.0.0';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? '/api' : '');

const VALID_ROUTES = new Set<ValidRoute>(ALL_NAV_ITEMS.map((item) => item.id));

function isValidRoute(value: string): value is ValidRoute {
  return VALID_ROUTES.has(value as ValidRoute);
}

// ── macOS-style window dots ────────────────────────────────────────

function WindowDots() {
  return (
    <div className="flex items-center gap-1.5 pl-3">
      <div className="w-3 h-3 rounded-full" style={{ background: '#FF5F57' }} />
      <div className="w-3 h-3 rounded-full" style={{ background: '#FFBD2E' }} />
      <div className="w-3 h-3 rounded-full" style={{ background: '#28C840' }} />
    </div>
  );
}

// ── Branch indicator ───────────────────────────────────────────────

function BranchIndicator() {
  return (
    <div className="flex items-center gap-1" style={{ color: 'rgb(var(--shell-fg-3))' }}>
      <Icon name="gitBranch" size={12} />
      <span className="text-xs font-mono">main</span>
    </div>
  );
}

// ── Sync button ────────────────────────────────────────────────────

function SyncButton({ onSync }: { onSync: () => void }) {
  return (
    <button
      onClick={onSync}
      title="Refresh data"
      className="flex items-center justify-center rounded px-2 py-1 transition-colors"
      style={{ color: 'rgb(var(--shell-fg-3))' }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.color = 'rgb(var(--shell-fg-1))'; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.color = 'rgb(var(--shell-fg-3))'; }}
    >
      <Icon name="reload" size={14} />
    </button>
  );
}

// ── Workspace chip ─────────────────────────────────────────────────

function WorkspaceChip({ url }: { url: string }) {
  const label = url || 'local';
  return (
    <Chip className="font-mono text-xs shrink-0" style={{ maxWidth: 200 }}>
      {label}
    </Chip>
  );
}

// ── Environment status chips ───────────────────────────────────────

function EnvStatusChips({
  chromaOk,
  sqliteOk,
}: {
  chromaOk: boolean | null;
  sqliteOk: boolean | null;
}) {
  const tone = (ok: boolean | null) =>
    ok === null ? 'rgb(var(--shell-fg-3))' : ok ? 'rgb(var(--status-ok))' : 'rgb(var(--status-error))';

  return (
    <div className="flex items-center gap-2 ml-auto">
      <span className="text-xs font-mono" style={{ color: tone(sqliteOk) }}>
        sqlite · {sqliteOk === null ? '…' : sqliteOk ? 'ok' : 'err'}
      </span>
      <span style={{ color: 'rgb(var(--shell-fg-3))' }}>·</span>
      <span className="text-xs font-mono" style={{ color: tone(chromaOk) }}>
        chroma · {chromaOk === null ? '…' : chromaOk ? 'ok' : 'err'}
      </span>
    </div>
  );
}

// ── Notification button ────────────────────────────────────────────

function NotificationButton() {
  return (
    <button
      title="Notifications"
      aria-label="Notifications"
      className="flex items-center justify-center rounded px-2 py-1 transition-colors"
      style={{ color: 'rgb(var(--shell-fg-3))' }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.color = 'rgb(var(--shell-fg-1))'; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.color = 'rgb(var(--shell-fg-3))'; }}
    >
      <Icon name="bell" size={16} />
    </button>
  );
}

// ── Workspace footer ───────────────────────────────────────────────

function WorkspaceFooter() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      {open && (
        <div
          style={{
            position: 'absolute',
            bottom: '100%',
            left: 0,
            right: 0,
            marginBottom: 4,
            background: 'rgb(var(--canvas-card))',
            border: '1px solid rgb(var(--canvas-border))',
            borderRadius: 6,
            padding: '4px 0',
            zIndex: 100,
            boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
          }}
        >
          <div style={{ padding: '8px 12px 6px', borderBottom: '1px solid rgb(var(--canvas-border))' }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: 'rgb(var(--canvas-fg-3))', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Workspace
            </span>
          </div>
          <button
            type="button"
            className="flex items-center gap-2 w-full px-3 py-1.5 text-xs transition-colors"
            style={{ color: 'rgb(var(--shell-fg-2))' }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgb(var(--canvas-hover))'; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
            onClick={() => setOpen(false)}
          >
            <Icon name="settings" size={13} />
            Settings
          </button>
        </div>
      )}
      <button
        type="button"
        className="flex items-center gap-2 w-full px-2 py-2 transition-colors"
        style={{ color: 'rgb(var(--shell-fg-2))' }}
        onClick={() => setOpen(!open)}
        onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgb(var(--canvas-hover))'; }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
        aria-expanded={open}
        aria-haspopup="true"
      >
        <Avatar name="Context Library" size="xs" decorative />
        <span className="flex-1 text-xs text-left truncate" style={{ color: 'rgb(var(--shell-fg-1))' }}>
          Context Library
        </span>
        <Icon name={open ? 'chevronUp' : 'chevronDown'} size={12} />
      </button>
    </div>
  );
}

// ── Layout ─────────────────────────────────────────────────────────

export function Layout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { location } = useRouterState();
  const path = location.pathname;

  const { data: statsData } = useStats();
  const { data: healthData } = useHealth(120_000);
  const { data: adaptersData } = useAdminAdapters(120_000);

  // ── Active item detection ────────────────────────────────────────

  const isActive = (itemId: string): boolean => {
    if (itemId === '/') return path === '/';
    return path === itemId || path.startsWith(itemId + '/');
  };

  const activeItemId = (() => {
    if (path === '/') return '/';
    for (const item of ALL_NAV_ITEMS) {
      if (isActive(item.id)) return item.id;
    }
    return undefined;
  })();

  const handleSelectItem = (itemId: string) => {
    if (!isValidRoute(itemId)) {
      console.error(`Invalid route: ${itemId}`);
      return;
    }
    // itemId is validated as a concrete registered route by isValidRoute
    router.navigate({ to: itemId as string });
  };

  // ── Stats for count badges ────────────────────────────────────────

  const domainCountMap = Object.fromEntries(
    (statsData?.by_domain ?? []).map((d) => [d.domain, d.active_chunk_count])
  );
  const totalSources = statsData?.total_sources ?? 0;
  const totalChunks = statsData?.total_active_chunks ?? 0;

  // ── Sidebar sections ──────────────────────────────────────────────

  const sections = [
    {
      title: 'Library',
      items: LIBRARY_NAV_ITEMS.map((item) => ({
        id: item.id,
        label: item.label,
        icon: item.icon as IconName,
        count: item.id === '/sources' ? (totalSources || undefined) : undefined,
      })),
    },
    {
      title: 'Domains',
      items: DOMAIN_NAV_ITEMS.map((item) => {
        const domain = item.id.slice(1); // strip leading '/'
        const count = domainCountMap[domain];
        return {
          id: item.id,
          label: item.label,
          icon: item.icon as IconName,
          count: count || undefined,
        };
      }),
    },
    {
      title: 'System',
      items: SYSTEM_NAV_ITEMS.map((item) => ({
        id: item.id,
        label: item.label,
        icon: item.icon as IconName,
      })),
    },
  ];

  // ── Health state ──────────────────────────────────────────────────

  const helperOk = !healthData?.helper || healthData.helper.reachable;
  const isHealthy =
    healthData?.sqlite_ok === true &&
    healthData?.chromadb_ok === true &&
    helperOk;

  const healthTone: 'emerald' | 'amber' | 'rose' | 'neutral' = (() => {
    if (!healthData) return 'neutral';
    if (isHealthy) return 'emerald';
    if (healthData.sqlite_ok === false && healthData.chromadb_ok === false) return 'rose';
    return 'amber';
  })();

  // ── Titlebar ──────────────────────────────────────────────────────

  const titlebar = {
    left: <WindowDots />,
    center: <BranchIndicator />,
    right: <SyncButton onSync={() => queryClient.invalidateQueries()} />,
  };

  // ── Topbar content ────────────────────────────────────────────────

  const topbarLeadingContent = <WorkspaceChip url={API_BASE} />;

  const topbarChildren = (
    <div className="flex items-center gap-1">
      <EnvStatusChips
        chromaOk={healthData?.chromadb_ok ?? null}
        sqliteOk={healthData?.sqlite_ok ?? null}
      />
      <NotificationButton />
    </div>
  );

  // ── Statusbar items ───────────────────────────────────────────────

  const adapterCount = adaptersData?.adapters.length ?? 0;
  const embeddingModel = healthData?.embedding_model ?? '—';

  const statusbarLeft: StatusbarItem[] = [
    { kind: 'pulse', tone: healthTone, label: 'daemon' },
    { kind: 'divider' },
    { kind: 'icon', icon: 'data', label: `${adapterCount} adapter${adapterCount !== 1 ? 's' : ''}` },
    { kind: 'divider' },
    { kind: 'icon', icon: 'folder', label: `${totalSources.toLocaleString()} sources` },
    { kind: 'divider' },
    { kind: 'icon', icon: 'component', label: `${totalChunks.toLocaleString()} chunks` },
  ];

  const statusbarRight: StatusbarItem[] = [
    { kind: 'icon', icon: 'schema', label: embeddingModel, mono: true },
    { kind: 'divider' },
    { kind: 'icon', icon: 'info', label: `v${APP_VERSION}`, mono: true },
  ];

  return (
    <div style={{ background: 'rgb(var(--canvas-bg))', height: '100vh' }}>
      <CommandPaletteWrapper />
      <ShellLayout
        appTitle={{ title: 'Context Library' }}
        titlebar={titlebar}
        sidebar={{
          sections,
          activeItemId,
          onSelectItem: handleSelectItem,
          footer: <WorkspaceFooter />,
        }}
        topbar={{
          leadingContent: topbarLeadingContent,
          children: topbarChildren,
        }}
        statusbar={{
          left: statusbarLeft,
          right: statusbarRight,
        }}
      >
        <div className="flex-1 overflow-auto">
          {children}
        </div>
      </ShellLayout>
    </div>
  );
}
