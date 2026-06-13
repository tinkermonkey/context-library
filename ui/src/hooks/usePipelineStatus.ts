import { useQuery } from '@tanstack/react-query';
import type { Pipeline, FlowNode } from '@tinkermonkey/heimdall-ui';
import { fetchAdminPipelines } from '../api/client';

const PIPELINE_FLOW: FlowNode[] = [
  { id: 'fetch', name: 'fetch', label: 'Fetch', icon: 'download' },
  { id: 'chunk', name: 'chunk', label: 'Chunk', icon: 'layout' },
  { id: 'diff', name: 'diff', label: 'Diff', icon: 'gitBranch' },
  { id: 'embed', name: 'embed', label: 'Embed', icon: 'zap' },
  { id: 'store', name: 'store', label: 'Store', icon: 'hardDrive' },
];

export const usePipelineStatus = () =>
  useQuery({
    queryKey: ['pipeline-status'],
    queryFn: async (): Promise<Pipeline[]> => {
      const resp = await fetchAdminPipelines();
      return resp.runs.map((r) => ({
        id: r.run_id,
        name: r.adapter_id,
        status: 'running' as const,
        flow: PIPELINE_FLOW.map((node) => ({
          ...node,
          color: node.id === r.current_step ? 'amber' : undefined,
        })),
        recent: {
          ingested: r.ingested,
          created: r.created,
          updated: 'N/A',
          errors: r.errors,
        },
        tags: [r.adapter_id],
        lastRun: r.started_at,
      }));
    },
    staleTime: 10_000,
    refetchInterval: 10_000,
  });
