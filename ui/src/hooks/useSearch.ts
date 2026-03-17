import { useQuery } from '@tanstack/react-query';
import { postQuery } from '../api/client';
import type { SearchPageSearch } from '../router';

export function useSearch(params: SearchPageSearch) {
  return useQuery({
    queryKey: ['search', params],
    queryFn: () =>
      postQuery({
        query: params.q!,
        top_k: params.top_k ?? 10,
        domain_filter: params.domain ?? null,
        source_filter: params.source_id ?? null,
        rerank: params.rerank ?? false,
      }),
    enabled: !!params.q,
    staleTime: 30_000,
  });
}
