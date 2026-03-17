import { useQuery } from '@tanstack/react-query';
import { fetchAdapters } from '../api/client';

export const useAdapters = () =>
  useQuery({
    queryKey: ['adapters'],
    queryFn: fetchAdapters,
    staleTime: 30_000,
  });
