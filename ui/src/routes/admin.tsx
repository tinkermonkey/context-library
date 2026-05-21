import { useState, useMemo } from 'react';
import type { ReactNode } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { StatTile, StatGrid, Table, Button, StatusBadge, Badge, Select } from '@tinkermonkey/heimdall-ui';

import { useHealth } from '../hooks/useHealth';
import { useAdminAdapters } from '../hooks/useAdminAdapters';
import { useAdminConfig } from '../hooks/useAdminConfig';
import { useAdminLogs } from '../hooks/useAdminLogs';
import { useToast } from '../hooks/useToast';
import { triggerAdapterSync } from '../api/client';
import { ResetAdapterDialog } from '../components/ResetAdapterDialog';
import type { AdminAdapterStatus } from '../types/api';

// ── Utilities ──────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatRelativeTime(iso: string | null): string {
  if (!iso) return 'Never';
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const minutes = Math.floor(diff / 60_000);
    if (minutes < 2) return 'Just now';
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  } catch {
    return iso;
  }
}

type AdapterHealth = 'healthy' | 'stale' | 'error' | 'unknown';

function getAdapterHealth(
  adapter: AdminAdapterStatus,
  errorAdapterIds: Set<string>,
): AdapterHealth {
  if (errorAdapterIds.has(adapter.adapter_id)) return 'error';
  if (!adapter.last_run) return 'unknown';
  const ageMs = Date.now() - new Date(adapter.last_run).getTime();
  if (ageMs > 24 * 60 * 60 * 1000) return 'stale';
  return 'healthy';
}

type BadgeColor = 'emerald' | 'amber' | 'rose' | 'neutral';

function healthToBadgeColor(health: AdapterHealth): BadgeColor {
  switch (health) {
    case 'healthy': return 'emerald';
    case 'stale': return 'amber';
    case 'error': return 'rose';
    case 'unknown': return 'neutral';
  }
}

function getSyncButtonLabel(health: AdapterHealth, isSyncing: boolean): string {
  if (isSyncing) return 'Syncing…';
  switch (health) {
    case 'error': return 'Retry';
    case 'stale': return 'Force Sync';
    default: return 'Re-sync';
  }
}

function ConfigRow({ label, value, masked }: { label: string; value: string; masked?: boolean }): ReactNode {
  return (
    <div
      className="flex items-center"
      style={{
        borderBottom: `1px solid rgb(var(--shell-border))`,
        padding: '10px 14px',
        gap: 12,
      }}
    >
      <span
        style={{
          width: 200,
          fontSize: 12,
          color: 'rgb(var(--shell-fg-3))',
          fontFamily: 'Inter, sans-serif',
          flexShrink: 0,
        }}
      >
        {label}
      </span>
      <span
        style={{
          fontSize: 12,
          color: masked ? 'rgb(var(--shell-fg-4))' : 'rgb(var(--shell-fg-1))',
          fontFamily: masked ? 'Inter, sans-serif' : 'monospace',
          letterSpacing: masked ? 1 : 0,
        }}
      >
        {masked ? '••••••' : value}
      </span>
    </div>
  );
}

// ── AdminPage ──────────────────────────────────────────────────────

export default function AdminPage(): ReactNode {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const healthQuery = useHealth();
  const adminAdaptersQuery = useAdminAdapters();
  const adminConfigQuery = useAdminConfig();
  const [logsPage, setLogsPage] = useState(0);
  const [logsLimit, setLogsLimit] = useState(30);
  const logsQuery = useAdminLogs(logsLimit, logsPage * logsLimit);

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

  // Build set of adapter IDs that have errors from helper health
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
    for (const health of adapterHealthMap.values()) {
      if (health === 'error') errorCount++;
      if (health === 'stale') staleCount++;
    }
    return { errorCount, staleCount };
  }, [adapterHealthMap]);

  const totalChunkCount = useMemo(() => {
    return adapters.reduce((sum, adapter) => sum + (adapter.active_chunk_count ?? 0), 0);
  }, [adapters]);

  const totalLogs = logsQuery.data?.total ?? 0;
  const totalLogPages = Math.ceil(totalLogs / logsLimit);

  return (
    <div
      className="flex flex-col h-full overflow-hidden"
      style={{ background: 'rgb(var(--canvas-bg))' }}
    >
      {/* ── Topbar ── */}
      <div
        className="flex items-center shrink-0 px-5"
        style={{
          height: 52,
          background: 'rgb(var(--shell-bg-2))',
          borderBottom: `1px solid rgb(var(--shell-border))`,
          gap: 12,
        }}
      >
        <span
          className="flex-1 font-semibold"
          style={{ fontSize: 16, color: 'rgb(var(--shell-fg-1))', fontFamily: 'Inter, sans-serif' }}
        >
          Admin
        </span>
        {healthQuery.isError ? (
          <div
            className="flex items-center"
            style={{
              background: 'rgb(var(--status-error) / 0.08)',
              borderRadius: 6,
              padding: '5px 12px',
              gap: 6,
            }}
          >
            <div
              style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: 'rgb(var(--status-error))',
                flexShrink: 0,
              }}
            />
            <span
              style={{
                fontSize: 12,
                color: 'rgb(var(--status-error))',
                fontFamily: 'Inter, sans-serif',
              }}
            >
              Health check failed
            </span>
          </div>
        ) : health && (
          <div
            className="flex items-center"
            style={{
              background: isSystemHealthy ? 'rgb(var(--status-ok) / 0.08)' : 'rgb(var(--status-error) / 0.08)',
              borderRadius: 6,
              padding: '5px 12px',
              gap: 6,
            }}
          >
            <div
              style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: isSystemHealthy ? 'rgb(var(--status-ok))' : 'rgb(var(--status-error))',
                flexShrink: 0,
              }}
            />
            <span
              style={{
                fontSize: 12,
                color: isSystemHealthy ? 'rgb(var(--status-ok))' : 'rgb(var(--status-error))',
                fontFamily: 'Inter, sans-serif',
              }}
            >
              {isSystemHealthy ? 'System Healthy' : 'System Degraded'}
            </span>
          </div>
        )}
      </div>

      {/* ── Scrollable body ── */}
      <div className="flex-1 overflow-y-auto" style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 16 }}>

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

        {/* ── Adapter Status Table ── */}
        <div className="flex flex-col gap-2" style={{ flex: '0 0 auto' }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'rgb(var(--shell-fg-1))', fontFamily: 'Inter, sans-serif' }}>
            Adapter Status
          </span>
          {adminAdaptersQuery.isLoading ? (
            <div
              style={{
                background: 'rgb(var(--shell-surface))',
                borderRadius: 8,
                border: `1px solid rgb(var(--shell-border))`,
                padding: '16px',
              }}
            >
              <div className="flex flex-col gap-2">
                {[1, 2, 3].map(i => (
                  <div
                    key={i}
                    className="h-10 rounded animate-pulse"
                    style={{ background: 'rgb(var(--shell-border))' }}
                  />
                ))}
              </div>
            </div>
          ) : adminAdaptersQuery.isError ? (
            <div
              style={{
                background: 'rgb(var(--shell-surface))',
                borderRadius: 8,
                border: `1px solid rgb(var(--shell-border))`,
                padding: '24px',
                textAlign: 'center',
                color: 'rgb(var(--status-error))',
                fontSize: 13,
              }}
            >
              Failed to load adapter status
            </div>
          ) : adapters.length === 0 ? (
            <div
              style={{
                background: 'rgb(var(--shell-surface))',
                borderRadius: 8,
                border: `1px solid rgb(var(--shell-border))`,
                padding: '32px',
                textAlign: 'center',
                color: 'rgb(var(--shell-fg-4))',
                fontSize: 13,
              }}
            >
              No adapters registered
            </div>
          ) : (
            <div
              style={{
                background: 'rgb(var(--shell-surface))',
                borderRadius: 8,
                border: `1px solid rgb(var(--shell-border))`,
                overflow: 'hidden',
              }}
            >
              <Table<AdminAdapterStatus & { health: AdapterHealth; _actions: string }>
                data={adapters.map(adapter => ({
                  ...adapter,
                  health: adapterHealthMap.get(adapter.adapter_id) ?? 'unknown',
                  _actions: '',
                }))}
                rowKey="adapter_id"
                columns={[
                  {
                    key: 'adapter_id',
                    label: 'ADAPTER',
                    width: '200px',
                    render: (value, row) => (
                      <div className="flex items-center gap-2">
                        <Badge color={healthToBadgeColor(row.health)} pulse />
                        <span className="truncate">{String(value)}</span>
                      </div>
                    ),
                  },
                  {
                    key: 'domain',
                    label: 'DOMAIN',
                    width: '110px',
                    render: (value) => <span>{String(value)}</span>,
                  },
                  {
                    key: 'last_run',
                    label: 'LAST RUN',
                    width: '160px',
                    render: (value, row) => (
                      <span
                        style={{
                          color:
                            row.health === 'error'
                              ? 'rgb(var(--status-error))'
                              : row.health === 'stale'
                                ? 'rgb(var(--status-amber))'
                                : 'rgb(var(--shell-fg-2))',
                        }}
                      >
                        {formatRelativeTime(value as string | null)}
                      </span>
                    ),
                  },
                  {
                    key: 'active_chunk_count',
                    label: 'ITEMS',
                    width: '90px',
                    render: (value) => {
                      const count = value as number;
                      return (
                        <span style={{ color: count > 0 ? 'rgb(var(--shell-fg-2))' : 'rgb(var(--shell-fg-4))' }}>
                          {count > 0 ? count.toLocaleString() : '—'}
                        </span>
                      );
                    },
                  },
                  {
                    key: 'health',
                    label: 'STATUS',
                    width: '110px',
                    render: (value) => <StatusBadge color={healthToBadgeColor(value as AdapterHealth)}>{String(value)}</StatusBadge>,
                  },
                  {
                    key: '_actions',
                    label: 'ACTIONS',
                    render: (_, row) => (
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant={row.health === 'error' ? 'danger' : 'secondary'}
                          onClick={() => syncMutation.mutate(row.adapter_id)}
                          disabled={syncingId === row.adapter_id}
                        >
                          {getSyncButtonLabel(row.health, syncingId === row.adapter_id)}
                        </Button>
                        <Button size="sm" variant="secondary" onClick={() => setResetTarget(row)}>
                          Reset
                        </Button>
                      </div>
                    ),
                  },
                ]}
              />
            </div>
          )}
        </div>

        {/* ── System Configuration ── */}
        <div className="flex flex-col gap-2" style={{ flex: '0 0 auto' }}>
          <span
            style={{ fontSize: 13, fontWeight: 600, color: 'rgb(var(--shell-fg-1))', fontFamily: 'Inter, sans-serif' }}
          >
            System Configuration
          </span>
          <div
            style={{
              background: 'rgb(var(--shell-surface))',
              borderRadius: 8,
              border: `1px solid rgb(var(--shell-border))`,
              overflow: 'hidden',
            }}
          >
            {adminConfigQuery.isLoading ? (
              <div className="flex flex-col gap-1 p-4">
                {[1, 2, 3].map(i => (
                  <div
                    key={i}
                    className="h-8 rounded animate-pulse"
                    style={{ background: 'rgb(var(--shell-border))' }}
                  />
                ))}
              </div>
            ) : adminConfigQuery.isError ? (
              <div
                style={{
                  padding: '24px',
                  textAlign: 'center',
                  color: 'rgb(var(--status-error))',
                  fontSize: 13,
                }}
              >
                Failed to load system configuration
              </div>
            ) : config ? (
              <>
                <ConfigRow label="Embedding Model" value={config.embedding_model} />
                <ConfigRow label="Reranker" value={config.enable_reranker ? config.reranker_model : 'Disabled'} />
                <ConfigRow label="SQLite Path" value={config.sqlite_db_path} />
                <ConfigRow label="ChromaDB Path" value={config.chromadb_path} />
                <ConfigRow label="Webhook Secret" value="••••••" masked />
                <ConfigRow label="Helper Service" value={config.helper_url_set ? 'Configured' : 'Not configured'} />
                <ConfigRow label="Oura Adapter" value={config.helper_oura_enabled ? 'Enabled' : 'Disabled'} />
                <ConfigRow label="Filesystem Adapter" value={config.helper_filesystem_enabled ? 'Enabled' : 'Disabled'} />
                <ConfigRow
                  label="YouTube Adapters"
                  value={config.youtube_enabled ? 'Enabled' : 'Disabled'}
                />
              </>
            ) : null}
          </div>
        </div>

        {/* ── Sync Log ── */}
        <div className="flex flex-col gap-2" style={{ flex: '0 0 auto', paddingBottom: 16 }}>
          <div className="flex items-center gap-3">
            <span
              style={{ fontSize: 13, fontWeight: 600, color: 'rgb(var(--shell-fg-1))', fontFamily: 'Inter, sans-serif' }}
            >
              Sync Log
            </span>
            {totalLogs > 0 && (
              <span style={{ fontSize: 11, color: 'rgb(var(--shell-fg-4))', fontFamily: 'Inter, sans-serif' }}>
                {totalLogs.toLocaleString()} entries
              </span>
            )}
          </div>
          <div
            style={{
              background: 'rgb(var(--shell-surface))',
              borderRadius: 8,
              border: `1px solid rgb(var(--shell-border))`,
              overflow: 'hidden',
            }}
          >
            {logsQuery.isLoading ? (
              <div className="flex flex-col gap-1 p-4">
                {[1, 2, 3].map(i => (
                  <div
                    key={i}
                    className="h-8 rounded animate-pulse"
                    style={{ background: 'rgb(var(--shell-border))' }}
                  />
                ))}
              </div>
            ) : logsQuery.isError ? (
              <div
                style={{
                  padding: '20px',
                  textAlign: 'center',
                  color: 'rgb(var(--status-error))',
                  fontSize: 13,
                }}
              >
                Failed to load sync log
              </div>
            ) : !logsQuery.data?.entries.length ? (
              <div
                style={{
                  padding: '24px',
                  textAlign: 'center',
                  color: 'rgb(var(--shell-fg-4))',
                  fontSize: 13,
                }}
              >
                No sync log entries
              </div>
            ) : (
              <>
                <Table
                  data={logsQuery.data.entries}
                  rowKey="id"
                  columns={[
                    {
                      key: 'operation',
                      label: 'OPERATION',
                      width: '100px',
                      render: (value) => (
                        <span
                          style={{
                            color: value === 'insert' ? 'rgb(var(--status-ok))' : 'rgb(var(--status-error))',
                            fontWeight: 600,
                          }}
                        >
                          {String(value).charAt(0).toUpperCase() + String(value).slice(1)}
                        </span>
                      ),
                    },
                    {
                      key: 'chunk_hash',
                      label: 'CHUNK HASH',
                      render: (value) => (
                        <span
                          className="block truncate"
                          style={{
                            color: 'rgb(var(--shell-fg-3))',
                            fontFamily: 'monospace',
                            fontSize: '11px',
                          }}
                        >
                          {value}
                        </span>
                      ),
                    },
                    {
                      key: 'synced_at',
                      label: 'TIMESTAMP',
                      width: '180px',
                      render: (value) => (
                        <span style={{ color: 'rgb(var(--shell-fg-4))', fontSize: '11px' }}>
                          {value
                            ? new Date(value as string).toLocaleString('en-US', {
                                month: 'short',
                                day: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                              })
                            : '—'}
                        </span>
                      ),
                    },
                  ]}
                />
                {totalLogPages > 1 && (
                  <div
                    className="flex items-center justify-between"
                    style={{
                      padding: '8px 14px',
                      borderTop: `1px solid rgb(var(--shell-border))`,
                      background: 'rgb(var(--shell-bg-2))',
                    }}
                  >
                    <div className="flex items-center gap-3">
                      <span style={{ fontSize: 11, color: 'rgb(var(--shell-fg-4))', fontFamily: 'Inter, sans-serif' }}>
                        Page {logsPage + 1} of {totalLogPages}
                      </span>
                      <div className="flex items-center gap-2">
                        <label style={{ fontSize: 11, color: 'rgb(var(--shell-fg-4))', fontFamily: 'Inter, sans-serif' }}>
                          Per page:
                        </label>
                        <Select
                          value={String(logsLimit)}
                          onChange={(e) => {
                            setLogsLimit(parseInt(e.target.value, 10));
                            setLogsPage(0);
                          }}
                          style={{ fontSize: 11 }}
                        >
                          <option value="10">10</option>
                          <option value="20">20</option>
                          <option value="30">30</option>
                          <option value="50">50</option>
                        </Select>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => setLogsPage(p => Math.max(0, p - 1))}
                        disabled={logsPage === 0}
                      >
                        Prev
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => setLogsPage(p => Math.min(totalLogPages - 1, p + 1))}
                        disabled={logsPage >= totalLogPages - 1}
                      >
                        Next
                      </Button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
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

