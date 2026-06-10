import type { IconName } from '@tinkermonkey/heimdall-ui';
import type { AdminAdapterStatus } from '../types/api';

export const DOMAIN_ORDER = [
  'notes', 'messages', 'events', 'tasks', 'health',
  'documents', 'people', 'location', 'music',
];

export const DOMAIN_LABELS: Record<string, string> = {
  notes: 'Notes', messages: 'Messages', events: 'Events', tasks: 'Tasks',
  health: 'Health', documents: 'Documents', people: 'People',
  location: 'Location', music: 'Music',
};

export const DOMAIN_ICONS: Record<string, IconName> = {
  notes: 'edit', messages: 'send', events: 'calendar', tasks: 'check',
  health: 'heart', documents: 'file', people: 'user',
  location: 'tag', music: 'palette',
};

export function formatRelativeTime(iso: string | null): string {
  if (!iso) return 'Never';
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const minutes = Math.floor(diff / 60_000);
    if (minutes < 2) return 'Just now';
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  } catch {
    return iso;
  }
}

export type AdapterHealth = 'healthy' | 'stale' | 'error' | 'unknown';

export function getAdapterHealth(adapter: AdminAdapterStatus, errorIds: Set<string>): AdapterHealth {
  if (errorIds.has(adapter.adapter_id)) return 'error';
  if (!adapter.last_run) return 'unknown';
  if (Date.now() - new Date(adapter.last_run).getTime() > 24 * 60 * 60 * 1000) return 'stale';
  return 'healthy';
}

export type BadgeColor = 'emerald' | 'amber' | 'rose' | 'neutral';

export function healthToBadgeColor(h: AdapterHealth): BadgeColor {
  if (h === 'healthy') return 'emerald';
  if (h === 'stale') return 'amber';
  if (h === 'error') return 'rose';
  return 'neutral';
}
