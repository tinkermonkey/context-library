import type { ComponentType, SVGProps } from 'react';
import type { IconName } from '@tinkermonkey/heimdall-ui';
import {
  ChatBubbleLeftRightIcon,
  MapPinIcon,
  MusicalNoteIcon,
} from '@heroicons/react/24/outline';

export type NavIconValue = IconName | ComponentType<SVGProps<SVGSVGElement>>;

/** Returns the heimdall IconName if the value is a string, otherwise undefined. */
export function resolveHeimdallIcon(value: NavIconValue | undefined): IconName | undefined {
  return typeof value === 'string' ? value : undefined;
}

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
  id: '/admin',
  label: 'Admin',
  iconKey: 'admin',
} as const;

export type ValidRoute = typeof PRIMARY_NAV[number]['id'] | typeof ADMIN_NAV['id'];

export const ICON_MAP: Record<string, NavIconValue> = {
  dashboard: 'dashboard',
  search: 'search',
  notes: 'edit',
  messages: ChatBubbleLeftRightIcon,
  events: 'calendar',
  tasks: 'check',
  health: 'heart',
  documents: 'file',
  people: 'user',
  location: MapPinIcon,
  music: MusicalNoteIcon,
  admin: 'settings',
};

export const PRIMARY_NAV_ITEMS = PRIMARY_NAV;
export const ADMIN_NAV_ITEM = ADMIN_NAV;
