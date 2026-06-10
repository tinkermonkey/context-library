import { useQuery } from '@tanstack/react-query';
import type { ActivityEvent, ActivityEventType } from '@tinkermonkey/heimdall-ui';
import { fetchActivityFeed } from '../api/client';
import { capitalize } from '../utils/formatters';

const EVENT_TYPE_MAP: Record<string, ActivityEventType> = {
  ingested: 'run',
  created: 'create',
  updated: 'update',
  deleted: 'delete',
};

const toActivityEventType = (eventType: string): ActivityEventType =>
  EVENT_TYPE_MAP[eventType] ?? 'run';

export const useActivity = (limit = 20) =>
  useQuery({
    queryKey: ['activity'],
    queryFn: async (): Promise<ActivityEvent[]> => {
      const resp = await fetchActivityFeed(limit);
      return resp.events.map((e) => ({
        id: e.identifier,
        type: toActivityEventType(e.event_type),
        subject: e.entity_name,
        timestamp: e.timestamp,
        kind: e.tags[0] ?? undefined,
        kindLabel: capitalize(e.tags[0] ?? ''),
        meta: e.tags[1] ?? undefined,
      }));
    },
    staleTime: 15_000,
    refetchInterval: 15_000,
  });
