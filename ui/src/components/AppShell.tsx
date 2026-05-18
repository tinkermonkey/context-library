import type { ReactNode } from 'react';
import { useRouter, useRouterState } from '@tanstack/react-router';
import { ShellLayout, type IconName } from '@tinkermonkey/heimdall-ui';
import { HealthIndicator } from './HealthIndicator';

interface NavItem {
  id: string;
  label: string;
  icon: IconName;
}

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

const PRIMARY_NAV = [
  { id: '/', label: 'Dashboard', icon: 'dashboard' },
  { id: '/search', label: 'Search', icon: 'search' },
  { id: '/notes', label: 'Notes', icon: 'component' },
  { id: '/messages', label: 'Messages', icon: 'component' },
  { id: '/events', label: 'Events', icon: 'calendar' },
  { id: '/tasks', label: 'Tasks', icon: 'check' },
  { id: '/health', label: 'Health', icon: 'heart' },
  { id: '/documents', label: 'Documents', icon: 'component' },
  { id: '/people', label: 'People', icon: 'user' },
  { id: '/location', label: 'Location', icon: 'component' },
  { id: '/music', label: 'Music', icon: 'component' },
] as const satisfies readonly NavItem[];

const ADMIN_NAV = { id: '/admin', label: 'Admin', icon: 'settings' } as const satisfies NavItem;

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

export function AppShell({ children }: { children: ReactNode }) {
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
      items: [...PRIMARY_NAV],
    },
    {
      title: 'Admin',
      items: [ADMIN_NAV],
    },
  ];

  const { title } = getPageMeta(path);

  return (
    <ShellLayout
      appTitle={{
        title: 'Context Library',
      }}
      sidebar={{
        sections,
        activeItemId,
        onSelectItem: handleSelectItem,
      }}
      topbar={{
        breadcrumbs: [{ label: title }],
        children: <HealthIndicator />,
      }}
    >
      {children}
    </ShellLayout>
  );
}
