import type { IconName } from '@tinkermonkey/heimdall-ui';

const LIBRARY_NAV = [
  { id: '/', label: 'Overview', iconKey: 'dashboard' },
  { id: '/search', label: 'Search', iconKey: 'search' },
  { id: '/sources', label: 'Sources', iconKey: 'data' },
] as const;

const DOMAIN_NAV = [
  { id: '/notes', label: 'Notes', iconKey: 'edit' },
  { id: '/messages', label: 'Messages', iconKey: 'send' },
  { id: '/events', label: 'Events', iconKey: 'calendar' },
  { id: '/tasks', label: 'Tasks', iconKey: 'check' },
  { id: '/health', label: 'Health', iconKey: 'heart' },
  { id: '/documents', label: 'Documents', iconKey: 'file' },
  { id: '/people', label: 'People', iconKey: 'user' },
  { id: '/location', label: 'Location', iconKey: 'star' },
  { id: '/music', label: 'Music', iconKey: 'zap' },
] as const;

const SYSTEM_NAV = [
  { id: '/pipeline', label: 'Pipeline', iconKey: 'pipeline' },
  { id: '/admin', label: 'Admin', iconKey: 'settings' },
] as const;

export type ValidRoute =
  | typeof LIBRARY_NAV[number]['id']
  | typeof DOMAIN_NAV[number]['id']
  | typeof SYSTEM_NAV[number]['id']
  | '/sources/$sourceId'
  | '/chunks/$chunkHash';

export const ICON_MAP: Record<string, IconName> = {
  dashboard: 'dashboard',
  search: 'search',
  data: 'data',
  edit: 'edit',
  send: 'send',
  calendar: 'calendar',
  check: 'check',
  heart: 'heart',
  file: 'file',
  user: 'user',
  star: 'star',
  zap: 'zap',
  pipeline: 'pipeline',
  settings: 'settings',
};

export const LIBRARY_NAV_ITEMS = LIBRARY_NAV;
export const DOMAIN_NAV_ITEMS = DOMAIN_NAV;
export const SYSTEM_NAV_ITEMS = SYSTEM_NAV;

// Flat list of all navigable items for command palette and route validation
export const ALL_NAV_ITEMS = [...LIBRARY_NAV, ...DOMAIN_NAV, ...SYSTEM_NAV] as const;
