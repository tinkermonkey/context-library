import { useQuery } from '@tanstack/react-query';
import type { ActivityEvent } from '@tinkermonkey/heimdall-ui';
import { fetchSources } from '../api/client';
import { capitalize } from '../utils/formatters';

export const useActivity = (limit = 20) =>
  useQuery({
    queryKey: ['activity', limit],
    queryFn: async (): Promise<ActivityEvent[]> => {
      const resp = await fetchSources({ limit, sort_by: 'updated_at', order: 'desc' });
      return resp.sources.map((s) => ({
        id: s.source_id,
        type: 'update' as const,
        subject: s.display_name ?? s.adapter_id,
        timestamp: s.updated_at,
        kind: s.domain,
        kindLabel: capitalize(s.domain),
        meta: `${s.chunk_count.toLocaleString()} chunks`,
      }));
    },
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
