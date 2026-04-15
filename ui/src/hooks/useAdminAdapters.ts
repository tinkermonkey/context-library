import { useQuery } from '@tanstack/react-query';
import { fetchAdminAdapters } from '../api/client';

export const useAdminAdapters = () =>
  useQuery({
    queryKey: ['admin-adapters'],
    queryFn: fetchAdminAdapters,
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
