import { useQuery } from '@tanstack/react-query';
import { fetchAdminConfig } from '../api/client';

export const useAdminConfig = () =>
  useQuery({
    queryKey: ['admin-config'],
    queryFn: fetchAdminConfig,
    staleTime: 60_000,
  });
