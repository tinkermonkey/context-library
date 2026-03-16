import { useMutation } from '@tanstack/react-query';
import { postQuery } from '../api/client';
import type { QueryRequest } from '../types/api';

export const useSearch = () =>
  useMutation({
    mutationFn: (request: QueryRequest) => postQuery(request),
  });
