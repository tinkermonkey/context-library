import type { ReactNode } from 'react';
import { useRouter, useRouterState } from '@tanstack/react-router';
import { Topbar, type IconName } from '@tinkermonkey/heimdall-ui';
import { Sidebar, type SidebarSection } from './Sidebar';
import { HealthIndicator } from './HealthIndicator';

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

interface NavigationItem {
  id: string;
  label: string;
  iconKey: string;
}

const PRIMARY_NAV: NavigationItem[] = [
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
];

const ADMIN_NAV: NavigationItem = {
  id: '/admin',
  label: 'Admin',
  iconKey: 'admin',
};

type ValidRoute = typeof PRIMARY_NAV[number]['id'] | typeof ADMIN_NAV['id'];

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

  const isActive = (itemId: string) => {
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
    router.navigate({ to: itemId as ValidRoute });
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

  return (
    <div className="flex h-screen" style={{ background: 'rgb(var(--canvas-bg))' }}>
      {/* Sidebar */}
      <Sidebar
        sections={sections}
        activeItemId={activeItemId}
        onSelectItem={handleSelectItem}
        appTitle="Context Library"
      />

      {/* Main content area */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Topbar */}
        <Topbar
          breadcrumbs={[{ label: title }]}
        >
          <div className="flex items-center gap-4 ml-auto">
            <HealthIndicator />
          </div>
        </Topbar>

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
      </div>
    </div>
  );
}
