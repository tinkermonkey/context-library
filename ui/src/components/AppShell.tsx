import type { ReactNode } from 'react';
import { useRouter, useRouterState } from '@tanstack/react-router';
import {
  HomeIcon,
  MagnifyingGlassIcon,
  DocumentTextIcon,
  ChatBubbleLeftIcon,
  CalendarIcon,
  CheckCircleIcon,
  HeartIcon,
  FolderIcon,
  UsersIcon,
  MapPinIcon,
  MusicalNoteIcon,
  Cog6ToothIcon,
} from '@heroicons/react/24/outline';
import { HealthIndicator } from './HealthIndicator';
import { NavigationSidebar } from './NavigationSidebar';
import type { NavItem, NavigationSection } from './NavigationSidebar';

const PRIMARY_NAV = [
  { id: '/', label: 'Dashboard', icon: HomeIcon },
  { id: '/search', label: 'Search', icon: MagnifyingGlassIcon },
  { id: '/notes', label: 'Notes', icon: DocumentTextIcon },
  { id: '/messages', label: 'Messages', icon: ChatBubbleLeftIcon },
  { id: '/events', label: 'Events', icon: CalendarIcon },
  { id: '/tasks', label: 'Tasks', icon: CheckCircleIcon },
  { id: '/health', label: 'Health', icon: HeartIcon },
  { id: '/documents', label: 'Documents', icon: FolderIcon },
  { id: '/people', label: 'People', icon: UsersIcon },
  { id: '/location', label: 'Location', icon: MapPinIcon },
  { id: '/music', label: 'Music', icon: MusicalNoteIcon },
] as const satisfies readonly NavItem[];

const ADMIN_NAV = { id: '/admin', label: 'Admin', icon: Cog6ToothIcon } as const satisfies NavItem;

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

  const sections: NavigationSection[] = [
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
    <div
      className="flex h-screen"
      style={{ background: 'rgb(var(--canvas-bg))' }}
    >
      {/* Sidebar */}
      <NavigationSidebar
        sections={sections}
        activeItemId={activeItemId}
        onSelectItem={handleSelectItem}
      />

      {/* Main content area */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Top bar */}
        <div
          className="flex items-center justify-between h-14 px-6 border-b"
          style={{
            borderColor: 'rgb(var(--shell-border))',
            background: 'rgb(var(--shell-surface))',
          }}
        >
          <div className="flex flex-col flex-1 min-w-0">
            <span
              style={{ color: 'rgb(var(--shell-fg-1))' }}
              className="font-semibold text-sm leading-tight"
            >
              {title}
            </span>
          </div>
          <div className="flex items-center gap-4 ml-auto">
            <HealthIndicator />
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto">
          {children}
        </div>
      </div>
    </div>
  );
}
