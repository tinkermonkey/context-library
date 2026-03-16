import { useQuery } from '@tanstack/react-query';
import { fetchSources, fetchSource, fetchVersionHistory, fetchVersionDiff } from '../api/client';
import type { SourceQueryParams } from '../types/api';

export const useSources = (params: SourceQueryParams) =>
  useQuery({
    queryKey: ['sources', params],
    queryFn: () => fetchSources(params),
    staleTime: 10_000,
  });

export const useSource = (sourceId: string) =>
  useQuery({
    queryKey: ['source', sourceId],
    queryFn: () => fetchSource(sourceId),
    staleTime: 10_000,
  });

export const useVersionHistory = (sourceId: string) =>
  useQuery({
    queryKey: ['version-history', sourceId],
    queryFn: () => fetchVersionHistory(sourceId),
    staleTime: 10_000,
  });

export const useVersionDiff = (sourceId: string, fromVersion: number, toVersion: number) =>
  useQuery({
    queryKey: ['version-diff', sourceId, fromVersion, toVersion],
    queryFn: () => fetchVersionDiff(sourceId, fromVersion, toVersion),
    staleTime: 10_000,
    enabled: !!sourceId && fromVersion > 0 && toVersion > 0,
  });
