import { useState, useMemo } from 'react';
import type { ReactNode } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  StatTile,
  StatGrid,
  StatusBadge,
  Chip,
  Select,
  PageHeader,
  Panel,
  LogStream,
  TextInput,
  NumberInput,
} from '@tinkermonkey/heimdall-ui';
import type { LogEntry } from '@tinkermonkey/heimdall-ui';

import { useHealth } from '../hooks/useHealth';
import { useAdminAdapters } from '../hooks/useAdminAdapters';
import { useAdminConfig } from '../hooks/useAdminConfig';
import { useAdminLogs } from '../hooks/useAdminLogs';
import { useToast } from '../hooks/useToast';
import { triggerAdapterSync } from '../api/client';
import { ResetAdapterDialog } from '../components/ResetAdapterDialog';
import { ConfigTile } from '../components/ConfigTile';
import type { AdminAdapterStatus } from '../types/api';
import {
  DOMAIN_ORDER,
  DOMAIN_LABELS,
  DOMAIN_ICONS,
  formatRelativeTime,
  getAdapterHealth,
  healthToBadgeColor,
} from '../utils/adapterHelpers';
import type { AdapterHealth } from '../utils/adapterHelpers';

// ── Utilities ──────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function domainColor(domain: string): string {
  return `rgb(var(--domain-${domain}, var(--canvas-fg-3)))`;
}

// ── AdminPage ──────────────────────────────────────────────────────

export default function AdminPage(): ReactNode {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const healthQuery = useHealth();
  const adminAdaptersQuery = useAdminAdapters();
  const adminConfigQuery = useAdminConfig();
  const logsQuery = useAdminLogs(100, 0);

  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [resetTarget, setResetTarget] = useState<AdminAdapterStatus | null>(null);

  const syncMutation = useMutation({
    mutationFn: (adapterId: string) => triggerAdapterSync(adapterId),
    onMutate: (adapterId) => {
      setSyncingId(adapterId);
    },
    onSuccess: (data) => {
      setSyncingId(null);
      showToast({
        title: data.triggered ? 'Sync started' : 'Sync already in progress',
        subtitle: `Adapter: ${data.adapter_id}`,
        variant: data.triggered ? 'success' : 'warning',
        duration: 3000,
      });
      queryClient.invalidateQueries({ queryKey: ['admin-adapters'] });
    },
    onError: (err) => {
      setSyncingId(null);
      showToast({
        title: 'Sync failed',
        subtitle: err instanceof Error ? err.message : 'Unknown error',
        variant: 'error',
        duration: 4000,
      });
    },
  });

  const errorAdapterIds = useMemo((): Set<string> => {
    const s = new Set<string>();
    const collectors = healthQuery.data?.helper?.collectors ?? [];
    for (const c of collectors) {
      if (c.healthy === false) s.add(c.name);
    }
    return s;
  }, [healthQuery.data]);

  const health = healthQuery.data;
  const isSystemHealthy =
    health?.sqlite_ok !== false &&
    health?.chromadb_ok !== false &&
    health?.status !== 'degraded';

  const adapters = adminAdaptersQuery.data?.adapters ?? [];
  const config = adminConfigQuery.data;

  const adapterHealthMap = useMemo(() => {
    const m = new Map<string, AdapterHealth>();
    for (const a of adapters) {
      m.set(a.adapter_id, getAdapterHealth(a, errorAdapterIds));
    }
    return m;
  }, [adapters, errorAdapterIds]);

  const adapterHealthCounts = useMemo(() => {
    let errorCount = 0;
    let staleCount = 0;
    for (const h of adapterHealthMap.values()) {
      if (h === 'error') errorCount++;
      if (h === 'stale') staleCount++;
    }
    return { errorCount, staleCount };
  }, [adapterHealthMap]);

  const totalChunkCount = useMemo(
    () => adapters.reduce((sum, a) => sum + (a.active_chunk_count ?? 0), 0),
    [adapters],
  );

  // Group adapters by domain in sidebar order
  const adaptersByDomain = useMemo(() => {
    const grouped = new Map<string, AdminAdapterStatus[]>();
    for (const a of adapters) {
      const list = grouped.get(a.domain) ?? [];
      list.push(a);
      grouped.set(a.domain, list);
    }
    // Collect unknown domains
    const knownDomains = new Set(DOMAIN_ORDER);
    const unknownDomains = [...grouped.keys()].filter((d) => !knownDomains.has(d));
    return [...DOMAIN_ORDER, ...unknownDomains]
      .filter((d) => grouped.has(d))
      .map((d) => ({ domain: d, adapters: grouped.get(d)! }));
  }, [adapters]);

  // Map sync log entries to LogEntry format for LogStream
  const logEntries: LogEntry[] = useMemo(() => {
    const entries = logsQuery.data?.entries ?? [];
    return entries.map((e) => ({
      id: String(e.id),
      timestamp: e.synced_at ?? '—',
      level: 'INFO' as const,
      message: `${e.operation}: ${e.chunk_hash.substring(0, 16)}…`,
      op: e.operation,
      target: e.chunk_hash.substring(0, 12),
    }));
  }, [logsQuery.data]);

  return (
    <div
      className="flex flex-col h-full overflow-hidden"
      style={{ background: 'rgb(var(--canvas-bg))' }}
    >
      <PageHeader
        eyebrow="System"
        title="Admin"
        subtitle="System administration and adapter management"
        actions={
          healthQuery.isError ? (
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full" style={{ background: 'rgb(var(--status-error))' }} />
              <span className="text-xs" style={{ color: 'rgb(var(--status-error))' }}>Health check failed</span>
            </div>
          ) : health ? (
            <div className="flex items-center gap-1.5">
              <div
                className="w-1.5 h-1.5 rounded-full"
                style={{ background: isSystemHealthy ? 'rgb(var(--status-ok))' : 'rgb(var(--status-error))' }}
              />
              <span className="text-xs" style={{ color: isSystemHealthy ? 'rgb(var(--status-ok))' : 'rgb(var(--status-error))' }}>
                {isSystemHealthy ? 'System Healthy' : 'System Degraded'}
              </span>
            </div>
          ) : null
        }
      />

      <div className="flex-1 overflow-y-auto" style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 20 }}>

        {/* ── Stat Grid ── */}
        <StatGrid columns={4} className="shrink-0">
          <StatTile
            label="SQLite DB"
            value={config ? formatBytes(config.db_size_bytes) : '—'}
          />
          <StatTile
            label="Total Chunks"
            value={totalChunkCount > 0 ? totalChunkCount.toLocaleString() : '—'}
            delta={
              adapterHealthCounts.staleCount > 0
                ? { value: adapterHealthCounts.staleCount, direction: 'down', label: 'stale' }
                : undefined
            }
          />
          <StatTile
            label="Adapters"
            value={adapters.length > 0 ? `${adapters.length}` : '—'}
            delta={
              adapters.length > 0 && adapterHealthCounts.errorCount > 0
                ? { value: adapterHealthCounts.errorCount, direction: 'down', label: 'errors' }
                : undefined
            }
          />
          <StatTile
            label="Embedding Dimension"
            value={health ? `${health.embedding_dimension}d` : '—'}
          />
        </StatGrid>

        {/* ── Adapter Cards grouped by domain ── */}
        <div className="flex flex-col gap-4">
          <span style={{ fontSize: 13, fontWeight: 600, color: 'rgb(var(--shell-fg-1))', fontFamily: 'Inter, sans-serif' }}>
            Adapters
          </span>

          {adminAdaptersQuery.isLoading ? (
            <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-36 rounded-md animate-pulse"
                  style={{ background: 'rgb(var(--canvas-card))', border: `1px solid rgb(var(--canvas-border))` }}
                />
              ))}
            </div>
          ) : adminAdaptersQuery.isError ? (
            <div
              style={{
                padding: '24px',
                textAlign: 'center',
                color: 'rgb(var(--status-error))',
                fontSize: 13,
                background: 'rgb(var(--canvas-card))',
                borderRadius: 8,
                border: `1px solid rgb(var(--canvas-border))`,
              }}
            >
              Failed to load adapter status
            </div>
          ) : adapters.length === 0 ? (
            <div
              style={{
                padding: '32px',
                textAlign: 'center',
                color: 'rgb(var(--canvas-fg-4))',
                fontSize: 13,
                background: 'rgb(var(--canvas-card))',
                borderRadius: 8,
                border: `1px solid rgb(var(--canvas-border))`,
              }}
            >
              No adapters registered
            </div>
          ) : (
            <div className="flex flex-col gap-5">
              {adaptersByDomain.map(({ domain, adapters: domainAdapters }) => {
                const color = domainColor(domain);
                const label = DOMAIN_LABELS[domain] ?? domain;
                return (
                  <div key={domain} className="flex flex-col gap-2">
                    {/* Domain section header */}
                    <div className="flex items-center gap-2">
                      <span
                        style={{
                          width: 7,
                          height: 7,
                          borderRadius: 2,
                          background: color,
                          display: 'inline-block',
                          flexShrink: 0,
                        }}
                      />
                      <span
                        style={{
                          fontSize: 11,
                          fontWeight: 700,
                          letterSpacing: '0.06em',
                          textTransform: 'uppercase',
                          color: 'rgb(var(--canvas-fg-3))',
                        }}
                      >
                        {label}
                      </span>
                    </div>

                    {/* Adapter cards grid */}
                    <div
                      className="grid gap-3"
                      style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}
                    >
                      {domainAdapters.map((adapter) => {
                        const adapterHealth = adapterHealthMap.get(adapter.adapter_id) ?? 'unknown';
                        const isSyncing = syncingId === adapter.adapter_id;
                        return (
                          <ConfigTile
                            key={adapter.adapter_id}
                            icon={DOMAIN_ICONS[domain] ?? 'component'}
                            title={adapter.adapter_id}
                            domainColor={color}
                            stats={[
                              { label: 'Sources', value: adapter.source_count.toLocaleString() },
                              { label: 'Last Poll', value: formatRelativeTime(adapter.last_run) },
                            ]}
                            actions={[
                              {
                                label: isSyncing ? 'Syncing…' : 'Re-poll',
                                variant: adapterHealth === 'error' ? 'danger' : 'ghost',
                                onClick: () => syncMutation.mutate(adapter.adapter_id),
                                disabled: isSyncing,
                              },
                              {
                                label: 'Reset',
                                variant: 'ghost',
                                onClick: () => setResetTarget(adapter),
                              },
                            ]}
                          >
                            <div
                              style={{
                                padding: '8px 12px',
                                display: 'flex',
                                gap: 6,
                                flexWrap: 'wrap',
                                alignItems: 'center',
                              }}
                            >
                              <Chip form="id-tag">{adapter.adapter_type}</Chip>
                              <StatusBadge color={healthToBadgeColor(adapterHealth)}>
                                {adapterHealth}
                              </StatusBadge>
                            </div>
                          </ConfigTile>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* ── Pipeline Configuration ── */}
        <Panel title="Pipeline Configuration">
          {adminConfigQuery.isLoading ? (
            <div className="flex flex-col gap-2">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-9 rounded animate-pulse"
                  style={{ background: 'rgb(var(--canvas-border))' }}
                />
              ))}
            </div>
          ) : adminConfigQuery.isError ? (
            <div style={{ color: 'rgb(var(--status-error))', fontSize: 13 }}>
              Failed to load configuration
            </div>
          ) : config ? (
            <div className="flex flex-col gap-4">
              <div className="grid gap-4" style={{ gridTemplateColumns: '1fr 1fr' }}>
                <div className="flex flex-col gap-1.5">
                  <label style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'rgb(var(--canvas-fg-3))' }}>
                    Embedding Model
                  </label>
                  <TextInput
                    value={config.embedding_model}
                    readOnly
                    mono
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'rgb(var(--canvas-fg-3))' }}>
                    Embedding Dimension
                  </label>
                  <NumberInput
                    value={health?.embedding_dimension ?? ''}
                    readOnly
                    mono
                  />
                </div>
              </div>
              <div className="grid gap-4" style={{ gridTemplateColumns: '1fr 1fr' }}>
                <div className="flex flex-col gap-1.5">
                  <label style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'rgb(var(--canvas-fg-3))' }}>
                    Reranker Model
                  </label>
                  <Select
                    value={config.enable_reranker ? config.reranker_model : '__disabled__'}
                    onChange={() => {}}
                    disabled
                  >
                    <Select.Item value="__disabled__">Disabled</Select.Item>
                    <Select.Item value={config.reranker_model}>{config.reranker_model}</Select.Item>
                  </Select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <label style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'rgb(var(--canvas-fg-3))' }}>
                    SQLite Path
                  </label>
                  <TextInput
                    value={config.sqlite_db_path}
                    readOnly
                    mono
                  />
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <label style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'rgb(var(--canvas-fg-3))' }}>
                  ChromaDB Path
                </label>
                <TextInput
                  value={config.chromadb_path}
                  readOnly
                  mono
                />
              </div>
            </div>
          ) : null}
        </Panel>

        {/* ── LogStream ── */}
        <Panel
          title="Pipeline Log"
          subtitle={logsQuery.data ? `${logsQuery.data.total.toLocaleString()} entries` : undefined}
          noPadding
        >
          <LogStream
            entries={logEntries}
            follow={false}
            showOps
            style={{ minHeight: 200, maxHeight: 320 }}
          />
        </Panel>

      </div>

      {/* ── Reset Adapter Dialog ── */}
      {resetTarget && (
        <ResetAdapterDialog
          adapterId={resetTarget.adapter_id}
          adapterName={resetTarget.adapter_id}
          isOpen={true}
          onClose={() => {
            setResetTarget(null);
            queryClient.invalidateQueries({ queryKey: ['admin-adapters'] });
          }}
        />
      )}
    </div>
  );
}
