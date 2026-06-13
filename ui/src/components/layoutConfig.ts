import type { IconName } from '@tinkermonkey/heimdall-ui';

const LIBRARY_NAV = [
  { id: '/', label: 'Overview', icon: 'dashboard' satisfies IconName },
  { id: '/search', label: 'Search', icon: 'search' satisfies IconName },
  { id: '/sources', label: 'Sources', icon: 'data' satisfies IconName },
] as const;

const DOMAIN_NAV = [
  { id: '/notes', label: 'Notes', icon: 'edit' satisfies IconName },
  { id: '/messages', label: 'Messages', icon: 'send' satisfies IconName },
  { id: '/events', label: 'Events', icon: 'calendar' satisfies IconName },
  { id: '/tasks', label: 'Tasks', icon: 'check' satisfies IconName },
  { id: '/health', label: 'Health', icon: 'heart' satisfies IconName },
  { id: '/documents', label: 'Documents', icon: 'file' satisfies IconName },
  { id: '/people', label: 'People', icon: 'user' satisfies IconName },
  { id: '/location', label: 'Location', icon: 'tag' satisfies IconName },
  { id: '/music', label: 'Music', icon: 'zap' satisfies IconName },
] as const;

const SYSTEM_NAV = [
  { id: '/pipeline', label: 'Pipeline', icon: 'pipeline' satisfies IconName },
  { id: '/adapters', label: 'Adapters', icon: 'data' satisfies IconName },
  { id: '/admin', label: 'Admin', icon: 'settings' satisfies IconName },
] as const;

export type ValidRoute =
  | typeof LIBRARY_NAV[number]['id']
  | typeof DOMAIN_NAV[number]['id']
  | typeof SYSTEM_NAV[number]['id']
  | '/sources/$sourceId'
  | '/chunks/$chunkHash';

export const LIBRARY_NAV_ITEMS = LIBRARY_NAV;
export const DOMAIN_NAV_ITEMS = DOMAIN_NAV;
export const SYSTEM_NAV_ITEMS = SYSTEM_NAV;

// Flat list of all navigable items for command palette and route validation
export const ALL_NAV_ITEMS = [...LIBRARY_NAV, ...DOMAIN_NAV, ...SYSTEM_NAV] as const;
