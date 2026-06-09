import type { ReactNode } from 'react';
import { useRouter, useRouterState } from '@tanstack/react-router';
import { ShellLayout, type IconName } from '@tinkermonkey/heimdall-ui';
import { HealthIndicator } from './HealthIndicator';
import { CommandPaletteWrapper } from './CommandPaletteWrapper';
import { useAdminAdapters } from '../hooks/useAdminAdapters';
import { useHealth } from '../hooks/useHealth';
import { ICON_MAP, PRIMARY_NAV_ITEMS, ADMIN_NAV_ITEM, resolveHeimdallIcon, type ValidRoute } from './layoutConfig';

interface SidebarItem {
  id: string;
  label: string;
  icon?: IconName;
  count?: number;
}

interface SidebarSection {
  title: string;
  items: SidebarItem[];
}

const VALID_ROUTES = new Set<ValidRoute>([
  ...PRIMARY_NAV_ITEMS.map((item) => item.id),
  ADMIN_NAV_ITEM.id,
]);

function isValidRoute(value: string): value is ValidRoute {
  return VALID_ROUTES.has(value as ValidRoute);
}

interface PageMeta {
  title: string;
  subtitle: string;
}

const PAGE_META: Record<string, PageMeta> = {
  '/': { title: 'Dashboard', subtitle: 'System overview and activity' },
  '/search': { title: 'Search', subtitle: 'Semantic search across your knowledge base' },
  '/notes': { title: 'Notes', subtitle: 'Browse notes from Obsidian and Apple Notes' },
  '/messages': { title: 'Messages', subtitle: 'iMessage conversation history' },
  '/events': { title: 'Events', subtitle: 'Calendar events from all sources' },
  '/tasks': { title: 'Tasks', subtitle: 'To-dos from Reminders and CalDAV' },
  '/health': { title: 'Health', subtitle: 'Health metrics from Oura Ring and Apple Health' },
  '/documents': { title: 'Documents', subtitle: 'Ingested filesystem documents' },
  '/people': { title: 'People', subtitle: 'Contacts and their connections' },
  '/location': { title: 'Location', subtitle: 'Place visits and location history' },
  '/music': { title: 'Music', subtitle: 'Apple Music library and listening history' },
  '/admin': { title: 'Admin', subtitle: 'System administration and adapter management' },
  '/browser': { title: 'Data Browser', subtitle: 'Explore raw documents and chunks' },
  '/browser/files': { title: 'File Browser', subtitle: 'Navigate ingested filesystem content' },
};

function getPageMeta(pathname: string): PageMeta {
  if (PAGE_META[pathname]) return PAGE_META[pathname];
  for (const [prefix, meta] of Object.entries(PAGE_META)) {
    if (prefix !== '/' && pathname.startsWith(prefix)) return meta;
  }
  return { title: 'Context Library', subtitle: '' };
}

export function Layout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { location } = useRouterState();
  const path = location.pathname;
  const { data: adaptersData } = useAdminAdapters(120_000);
  const { data: healthData } = useHealth(120_000);

  const isActive = (itemId: string): boolean => {
    if (itemId === '/') return path === '/';
    return path === itemId || path.startsWith(itemId + '/');
  };

  const activeItemId = (() => {
    if (path === '/') return '/';
    for (const item of [...PRIMARY_NAV_ITEMS, ADMIN_NAV_ITEM]) {
      if (isActive(item.id)) return item.id;
    }
    return undefined;
  })();

  const handleSelectItem = (itemId: string) => {
    if (!isValidRoute(itemId)) {
      console.error(`Invalid route: ${itemId}`);
      return;
    }
    router.navigate({ to: itemId });
  };

  const sections: SidebarSection[] = [
    {
      title: 'Primary',
      items: PRIMARY_NAV_ITEMS.map((item) => ({
        id: item.id,
        label: item.label,
        icon: resolveHeimdallIcon(ICON_MAP[item.iconKey]),
      })),
    },
    {
      title: 'Admin',
      items: [
        {
          id: ADMIN_NAV_ITEM.id,
          label: ADMIN_NAV_ITEM.label,
          icon: resolveHeimdallIcon(ICON_MAP[ADMIN_NAV_ITEM.iconKey]),
        },
      ],
    },
  ];

  const { title, subtitle } = getPageMeta(path);

  // Format last sync timestamp
  const lastSyncTimestamp = (() => {
    if (!healthData?.helper?.watermark) return 'Never';
    const date = new Date(healthData.helper.watermark);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  })();

  // Count active adapters
  const activeAdapterCount = adaptersData?.adapters.length || 0;

  // Statusbar left content
  const statusbarLeft = (
    <div className="text-xs" style={{ color: 'rgb(var(--shell-fg-3))' }}>
      Last sync: {lastSyncTimestamp}
    </div>
  );

  // Statusbar right content
  const statusbarRight = (
    <div className="text-xs" style={{ color: 'rgb(var(--shell-fg-3))' }}>
      {activeAdapterCount} adapter{activeAdapterCount !== 1 ? 's' : ''}
    </div>
  );

  return (
    <div style={{ background: 'rgb(var(--canvas-bg))', height: '100vh' }}>
      <CommandPaletteWrapper primaryNav={PRIMARY_NAV_ITEMS} adminNav={ADMIN_NAV_ITEM} />
      <ShellLayout
        appTitle={{ title: 'Context Library' }}
        sidebar={{
          sections,
          activeItemId,
          onSelectItem: handleSelectItem,
        }}
        topbar={{
          breadcrumbs: [{ label: title }],
          children: (
            <div className="flex items-center gap-4 ml-auto">
              <HealthIndicator />
            </div>
          ),
        }}
        statusbar={{
          left: statusbarLeft,
          right: statusbarRight,
        }}
      >
      {/* Subtitle */}
      {subtitle && (
        <div
          className="px-6 py-3 text-sm border-b"
          style={{
            color: 'rgb(var(--shell-fg-2))',
            borderColor: 'rgb(var(--shell-border))',
          }}
        >
          {subtitle}
        </div>
      )}

        {/* Content */}
        <div className="flex-1 overflow-auto">
          {children}
        </div>
      </ShellLayout>
    </div>
  );
}
