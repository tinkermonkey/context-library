import { useQuery } from '@tanstack/react-query';
import { fetchSources, fetchSource, fetchVersionHistory, fetchVersionDiff, fetchVersionDetail } from '../api/client';
import type { SourceQueryParams } from '../types/api';

export const useSources = (params: SourceQueryParams) =>
  useQuery({
    queryKey: ['sources', params],
    queryFn: () => fetchSources(params),
    staleTime: 10_000,
  });

export const useSource = (sourceId: string, enabled = true) =>
  useQuery({
    queryKey: ['source', sourceId],
    queryFn: () => fetchSource(sourceId),
    staleTime: 10_000,
    enabled: enabled && !!sourceId,
  });

export const useVersionHistory = (sourceId: string, enabled = true) =>
  useQuery({
    queryKey: ['version-history', sourceId],
    queryFn: () => fetchVersionHistory(sourceId),
    staleTime: 10_000,
    enabled: enabled && !!sourceId,
  });

export const useVersionDetail = (sourceId: string, version: number, enabled = true) =>
  useQuery({
    queryKey: ['version-detail', sourceId, version],
    queryFn: () => fetchVersionDetail(sourceId, version),
    staleTime: Infinity,
    enabled: enabled && !!sourceId && version > 0,
  });

export const useVersionDiff = (sourceId: string, fromVersion: number, toVersion: number, enabled = true) =>
  useQuery({
    queryKey: ['version-diff', sourceId, fromVersion, toVersion],
    queryFn: () => fetchVersionDiff(sourceId, fromVersion, toVersion),
    staleTime: 60_000,
    enabled: enabled && !!sourceId && fromVersion > 0 && toVersion > 0,
  });
