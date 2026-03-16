import { useQuery } from '@tanstack/react-query';
import { fetchAdapterStats } from '../api/client';

export const useAdapterStats = () =>
  useQuery({
    queryKey: ['adapter-stats'],
    queryFn: fetchAdapterStats,
    staleTime: 30_000,
  });
