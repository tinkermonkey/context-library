import { useQuery } from '@tanstack/react-query';
import type { Pipeline, FlowNode } from '@tinkermonkey/heimdall-ui';
import { fetchAdminAdapters } from '../api/client';

const PIPELINE_FLOW: FlowNode[] = [
  { id: 'fetch', name: 'fetch', label: 'Fetch', icon: 'download' },
  { id: 'normalize', name: 'normalize', label: 'Normalize', icon: 'component' },
  { id: 'diff', name: 'diff', label: 'Diff', icon: 'gitBranch' },
  { id: 'chunk', name: 'chunk', label: 'Chunk', icon: 'layout' },
  { id: 'embed', name: 'embed', label: 'Embed', icon: 'zap' },
  { id: 'store', name: 'store', label: 'Store', icon: 'hardDrive' },
];

export const usePipelineStatus = () =>
  useQuery({
    queryKey: ['pipeline-status'],
    queryFn: async (): Promise<Pipeline[]> => {
      const resp = await fetchAdminAdapters();
      return resp.adapters
        .filter((a) => a.last_run !== null)
        .map((a) => ({
          id: a.adapter_id,
          name: a.adapter_id,
          status: 'success' as const,
          flow: PIPELINE_FLOW,
          recent: {
            ingested: a.source_count,
            created: a.active_chunk_count,
            updated: 0,
            errors: 0,
          },
          tags: [a.domain],
          lastRun: a.last_run ?? undefined,
        }));
    },
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
