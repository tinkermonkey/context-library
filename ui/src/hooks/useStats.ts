import { useQuery } from '@tanstack/react-query';
import { fetchStats } from '../api/client';

export const useStats = () =>
  useQuery({
    queryKey: ['stats'],
    queryFn: fetchStats,
    staleTime: 30_000,
  });
