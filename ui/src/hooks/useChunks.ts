import { useQuery } from '@tanstack/react-query';
import {
  fetchChunks,
  fetchChunk,
  fetchChunkProvenance,
  fetchSourceChunks,
  fetchVersionDiff,
} from '../api/client';
import type { ChunkQueryParams } from '../types/api';

export const useChunks = (params: ChunkQueryParams) =>
  useQuery({
    queryKey: ['chunks', params],
    queryFn: () => fetchChunks(params),
    staleTime: 10_000,
  });

export const useChunk = (hash: string, sourceId?: string) =>
  useQuery({
    queryKey: ['chunk', hash, sourceId],
    queryFn: () => fetchChunk(hash, sourceId),
    staleTime: 10_000,
  });

export const useChunkProvenance = (hash: string, sourceId?: string) =>
  useQuery({
    queryKey: ['chunk-provenance', hash, sourceId],
    queryFn: () => fetchChunkProvenance(hash, sourceId),
    staleTime: 10_000,
  });

export const useSourceChunks = (sourceId: string, version?: number, limit?: number, offset?: number, enabled: boolean = true) =>
  useQuery({
    queryKey: ['source-chunks', sourceId, version, limit, offset],
    queryFn: () => fetchSourceChunks(sourceId, version, limit, offset),
    staleTime: 10_000,
    enabled,
  });

export const useVersionDiff = (
  sourceId: string,
  fromVersion: number,
  toVersion: number
) =>
  useQuery({
    queryKey: ['version-diff', sourceId, fromVersion, toVersion],
    queryFn: () => fetchVersionDiff(sourceId, fromVersion, toVersion),
    staleTime: 10_000,
  });
