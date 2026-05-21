import { useQuery } from '@tanstack/react-query';
import { fetchHealth } from '../api/client';

export const useHealth = (refetchInterval: number = 60_000) =>
  useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    staleTime: 0,
    refetchInterval,
  });
