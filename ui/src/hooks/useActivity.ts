import { useQuery } from '@tanstack/react-query';
import type { ActivityEvent } from '@tinkermonkey/heimdall-ui';
import { fetchActivityFeed } from '../api/client';
import { capitalize } from '../utils/formatters';

export const useActivity = (limit = 20) =>
  useQuery({
    queryKey: ['activity'],
    queryFn: async (): Promise<ActivityEvent[]> => {
      const resp = await fetchActivityFeed(limit);
      return resp.events.map((e) => ({
        id: e.identifier,
        type: 'run' as const,
        subject: e.entity_name,
        timestamp: e.timestamp,
        kind: e.tags[0],
        kindLabel: capitalize(e.tags[0] ?? ''),
        meta: e.tags[1],
      }));
    },
    staleTime: 15_000,
    refetchInterval: 15_000,
  });
