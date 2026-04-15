import { useQuery } from '@tanstack/react-query';
import { fetchAdminLogs } from '../api/client';

export const useAdminLogs = (limit = 50, offset = 0) =>
  useQuery({
    queryKey: ['admin-logs', limit, offset],
    queryFn: () => fetchAdminLogs(limit, offset),
    staleTime: 15_000,
    refetchInterval: 20_000,
  });
