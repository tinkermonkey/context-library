import type { ReactNode } from 'react';
import { useRouter, useRouterState } from '@tanstack/react-router';
import { ShellLayout, type IconName } from '@tinkermonkey/heimdall-ui';
import { HealthIndicator } from './HealthIndicator';
import { CommandPaletteWrapper } from './CommandPaletteWrapper';
import { useAdminAdapters } from '../hooks/useAdminAdapters';
import { useHealth } from '../hooks/useHealth';

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

// Icon mapping from Heroicons to Heimdall IconName
const ICON_MAP: Record<string, IconName> = {
  dashboard: 'dashboard',
  search: 'search',
  notes: 'component',
  messages: 'info',
  events: 'calendar',
  tasks: 'check',
  health: 'heart',
  documents: 'table',
  people: 'user',
  location: 'link',
  music: 'palette',
  admin: 'settings',
};

const PRIMARY_NAV = [
  { id: '/', label: 'Dashboard', iconKey: 'dashboard' },
  { id: '/search', label: 'Search', iconKey: 'search' },
  { id: '/notes', label: 'Notes', iconKey: 'notes' },
  { id: '/messages', label: 'Messages', iconKey: 'messages' },
  { id: '/events', label: 'Events', iconKey: 'events' },
  { id: '/tasks', label: 'Tasks', iconKey: 'tasks' },
  { id: '/health', label: 'Health', iconKey: 'health' },
  { id: '/documents', label: 'Documents', iconKey: 'documents' },
  { id: '/people', label: 'People', iconKey: 'people' },
  { id: '/location', label: 'Location', iconKey: 'location' },
  { id: '/music', label: 'Music', iconKey: 'music' },
] as const;

const ADMIN_NAV = {
  id: '/admin' as const,
  label: 'Admin',
  iconKey: 'admin',
} as const;

export type ValidRoute = typeof PRIMARY_NAV[number]['id'] | typeof ADMIN_NAV['id'];

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
  const { data: adaptersData } = useAdminAdapters();
  const { data: healthData } = useHealth();

  const isActive = (itemId: string): itemId is ValidRoute => {
    if (itemId === '/') return path === '/';
    return path === itemId || path.startsWith(itemId + '/');
  };

  const activeItemId = (() => {
    if (path === '/') return '/';
    for (const item of [...PRIMARY_NAV, ADMIN_NAV]) {
      if (isActive(item.id)) return item.id;
    }
    return undefined;
  })();

  const handleSelectItem = (itemId: string) => {
    if (isActive(itemId)) {
      router.navigate({ to: itemId });
    }
  };

  const sections: SidebarSection[] = [
    {
      title: 'Primary',
      items: PRIMARY_NAV.map((item) => ({
        id: item.id,
        label: item.label,
        icon: ICON_MAP[item.iconKey] as IconName,
      })),
    },
    {
      title: 'Admin',
      items: [
        {
          id: ADMIN_NAV.id,
          label: ADMIN_NAV.label,
          icon: ICON_MAP[ADMIN_NAV.iconKey] as IconName,
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

  // Create statusbar content
  const statusbarContent = (
    <div className="flex items-center gap-4 text-xs" style={{ color: 'rgb(var(--shell-fg-3))' }}>
      <div>Last sync: {lastSyncTimestamp}</div>
      <div>{activeAdapterCount} adapter{activeAdapterCount !== 1 ? 's' : ''}</div>
    </div>
  );

  return (
    <div style={{ background: 'rgb(var(--canvas-bg))', height: '100vh' }}>
      <CommandPaletteWrapper primaryNav={PRIMARY_NAV} adminNav={ADMIN_NAV} />
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
          left: statusbarContent,
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
