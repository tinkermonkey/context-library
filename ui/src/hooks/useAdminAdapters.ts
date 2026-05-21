import { useQuery } from '@tanstack/react-query';
import { fetchAdminAdapters } from '../api/client';

export const useAdminAdapters = (refetchInterval: number = 30_000) =>
  useQuery({
    queryKey: ['admin-adapters'],
    queryFn: fetchAdminAdapters,
    staleTime: 15_000,
    refetchInterval,
  });
