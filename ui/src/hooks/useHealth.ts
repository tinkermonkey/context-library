import { useQuery } from '@tanstack/react-query';
import { fetchHealth } from '../api/client';

export const useHealth = () =>
  useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    staleTime: 0,
    refetchInterval: 60_000,
  });
