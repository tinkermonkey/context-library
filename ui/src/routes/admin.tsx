import { useState, useMemo } from 'react';
import type { ReactNode } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { colors } from '../lib/designTokens';
import { useHealth } from '../hooks/useHealth';
import { useAdminAdapters } from '../hooks/useAdminAdapters';
import { useAdminConfig } from '../hooks/useAdminConfig';
import { useAdminLogs } from '../hooks/useAdminLogs';
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

const HEALTH_DOT: Record<AdapterHealth, string> = {
  healthy: colors.statusGreen,
  stale: colors.statusAmber,
  error: colors.statusRed,
  unknown: '#4B5563',
};

const STATUS_BADGE: Record<AdapterHealth, { bg: string; text: string; label: string }> = {
  healthy: { bg: '#052E16', text: colors.statusGreen, label: 'healthy' },
  stale:   { bg: '#1C1A00', text: colors.statusAmber, label: 'stale' },
  error:   { bg: '#2D1B1B', text: colors.statusRed,   label: 'error' },
  unknown: { bg: '#1A1A1A', text: '#4B5563',          label: 'unknown' },
};

// ── Stat Card ──────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  sub,
  subColor,
}: {
  label: string;
  value: string;
  sub: string;
  subColor?: string;
}): ReactNode {
  return (
    <div
      className="flex flex-col gap-1"
      style={{
        flex: 1,
        background: '#161616',
        borderRadius: 8,
        border: '1px solid #1E1E1E',
        padding: 14,
        minWidth: 0,
      }}
    >
      <span style={{ fontSize: 11, color: '#6B7280', fontFamily: 'Inter, sans-serif' }}>
        {label}
      </span>
      <span style={{ fontSize: 22, fontWeight: 700, color: '#FFFFFF', fontFamily: 'Inter, sans-serif' }}>
        {value}
      </span>
      <span style={{ fontSize: 11, color: subColor ?? '#4B5563', fontFamily: 'Inter, sans-serif' }}>
        {sub}
      </span>
    </div>
  );
}

// ── Adapter Row ────────────────────────────────────────────────────

function AdapterRow({
  adapter,
  health,
  onSync,
  onReset,
  syncingId,
}: {
  adapter: AdminAdapterStatus;
  health: AdapterHealth;
  onSync: (id: string) => void;
  onReset: (adapter: AdminAdapterStatus) => void;
  syncingId: string | null;
}): ReactNode {
  const dot = HEALTH_DOT[health];
  const badge = STATUS_BADGE[health];
  const isSyncing = syncingId === adapter.adapter_id;
  const lastRunColor = health === 'error' ? colors.statusRed : health === 'stale' ? colors.statusAmber : '#9CA3AF';
  const rowBg = health === 'error' ? '#1A0E0E' : 'transparent';

  return (
    <div
      className="flex items-stretch"
      style={{
        height: 44,
        background: rowBg,
        borderBottom: '1px solid #1A1A1A',
        width: '100%',
      }}
    >
      {/* Adapter name + dot */}
      <div
        className="flex items-center gap-2 shrink-0"
        style={{ width: 200, padding: '0 14px' }}
      >
        <div
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: dot,
            flexShrink: 0,
          }}
        />
        <span
          className="truncate"
          style={{ fontSize: 12, color: '#E5E7EB', fontFamily: 'Inter, sans-serif' }}
        >
          {adapter.adapter_id}
        </span>
      </div>

      {/* Domain */}
      <div
        className="flex items-center"
        style={{ width: 110, padding: '0 14px' }}
      >
        <span style={{ fontSize: 12, color: '#9CA3AF', fontFamily: 'Inter, sans-serif' }}>
          {adapter.domain}
        </span>
      </div>

      {/* Last run */}
      <div
        className="flex items-center"
        style={{ width: 160, padding: '0 14px' }}
      >
        <span style={{ fontSize: 12, color: lastRunColor, fontFamily: 'Inter, sans-serif' }}>
          {formatRelativeTime(adapter.last_run)}
        </span>
      </div>

      {/* Items */}
      <div
        className="flex items-center"
        style={{ width: 90, padding: '0 14px' }}
      >
        <span style={{ fontSize: 12, color: adapter.active_chunk_count > 0 ? '#9CA3AF' : '#4B5563', fontFamily: 'Inter, sans-serif' }}>
          {adapter.active_chunk_count > 0 ? adapter.active_chunk_count.toLocaleString() : '—'}
        </span>
      </div>

      {/* Status badge */}
      <div
        className="flex items-center"
        style={{ width: 110, padding: '0 14px' }}
      >
        <div
          style={{
            background: badge.bg,
            borderRadius: 10,
            padding: '2px 8px',
          }}
        >
          <span style={{ fontSize: 10, color: badge.text, fontFamily: 'Inter, sans-serif' }}>
            {badge.label}
          </span>
        </div>
      </div>

      {/* Actions */}
      <div
        className="flex items-center gap-2 flex-1"
        style={{ padding: '0 14px' }}
      >
        {/* Primary action */}
        <button
          onClick={() => onSync(adapter.adapter_id)}
          disabled={isSyncing}
          style={{
            background: health === 'error' ? '#2D1B1B' : health === 'stale' ? '#1C1A00' : '#1A1A1A',
            borderRadius: 4,
            padding: '4px 10px',
            border: 'none',
            cursor: isSyncing ? 'default' : 'pointer',
            opacity: isSyncing ? 0.6 : 1,
          }}
        >
          <span
            style={{
              fontSize: 11,
              color: health === 'error' ? colors.statusRed : health === 'stale' ? colors.statusAmber : '#9CA3AF',
              fontFamily: 'Inter, sans-serif',
            }}
          >
            {isSyncing ? 'Syncing…' : health === 'error' ? 'Retry' : health === 'stale' ? 'Force Sync' : 'Re-sync'}
          </span>
        </button>

        {/* Reset button */}
        <button
          onClick={() => onReset(adapter)}
          style={{
            background: '#1A1A1A',
            borderRadius: 4,
            padding: '4px 10px',
            border: 'none',
            cursor: 'pointer',
          }}
        >
          <span style={{ fontSize: 11, color: '#6B7280', fontFamily: 'Inter, sans-serif' }}>
            Reset
          </span>
        </button>
      </div>
    </div>
  );
}

// ── Config Row ─────────────────────────────────────────────────────

function ConfigRow({ label, value, masked }: { label: string; value: string; masked?: boolean }): ReactNode {
  return (
    <div
      className="flex items-center"
      style={{ borderBottom: '1px solid #1A1A1A', padding: '10px 14px', gap: 12 }}
    >
      <span
        style={{ width: 200, fontSize: 12, color: '#6B7280', fontFamily: 'Inter, sans-serif', flexShrink: 0 }}
      >
        {label}
      </span>
      <span
        style={{
          fontSize: 12,
          color: masked ? '#4B5563' : '#E5E7EB',
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
  const healthQuery = useHealth();
  const adminAdaptersQuery = useAdminAdapters();
  const adminConfigQuery = useAdminConfig();
  const [logsPage, setLogsPage] = useState(0);
  const logsLimit = 30;
  const logsQuery = useAdminLogs(logsLimit, logsPage * logsLimit);

  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [resetTarget, setResetTarget] = useState<AdminAdapterStatus | null>(null);
  const [syncFeedback, setSyncFeedback] = useState<{ id: string; ok: boolean; msg: string } | null>(null);

  const syncMutation = useMutation({
    mutationFn: (adapterId: string) => triggerAdapterSync(adapterId),
    onMutate: (adapterId) => {
      setSyncingId(adapterId);
      setSyncFeedback(null);
    },
    onSuccess: (data) => {
      setSyncingId(null);
      setSyncFeedback({ id: data.adapter_id, ok: data.triggered, msg: data.message });
      queryClient.invalidateQueries({ queryKey: ['admin-adapters'] });
      setTimeout(() => setSyncFeedback(null), 6000);
    },
    onError: (err, adapterId) => {
      setSyncingId(null);
      setSyncFeedback({
        id: adapterId,
        ok: false,
        msg: err instanceof Error ? err.message : 'Sync failed',
      });
      setTimeout(() => setSyncFeedback(null), 6000);
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

  const errorCount = Array.from(adapterHealthMap.values()).filter(h => h === 'error').length;
  const staleCount = Array.from(adapterHealthMap.values()).filter(h => h === 'stale').length;

  const totalChunks = adapters.reduce((s, a) => s + a.active_chunk_count, 0);
  const totalLogs = logsQuery.data?.total ?? 0;
  const totalLogPages = Math.ceil(totalLogs / logsLimit);

  return (
    <div
      className="flex flex-col h-full overflow-hidden"
      style={{ background: colors.bgBase }}
    >
      {/* ── Topbar ── */}
      <div
        className="flex items-center shrink-0 px-5"
        style={{
          height: 52,
          background: '#111111',
          borderBottom: '1px solid #1A1A1A',
          gap: 12,
        }}
      >
        <span
          className="flex-1 font-semibold"
          style={{ fontSize: 16, color: '#FFFFFF', fontFamily: 'Inter, sans-serif' }}
        >
          Admin
        </span>
        {health && (
          <div
            className="flex items-center"
            style={{
              background: isSystemHealthy ? '#052E16' : '#2D1B1B',
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
                background: isSystemHealthy ? colors.statusGreen : colors.statusRed,
                flexShrink: 0,
              }}
            />
            <span
              style={{
                fontSize: 12,
                color: isSystemHealthy ? colors.statusGreen : colors.statusRed,
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

        {/* ── Stat Cards ── */}
        <div className="flex gap-3">
          <StatCard
            label="SQLite DB"
            value={config ? formatBytes(config.db_size_bytes) : '—'}
            sub={totalChunks > 0 ? `${totalChunks.toLocaleString()} chunks` : 'No data'}
          />
          <StatCard
            label="ChromaDB"
            value={health ? `${(health.vector_count / 1000).toFixed(1)}K` : '—'}
            sub={health ? `${health.vector_count.toLocaleString()} vectors` : 'Loading…'}
          />
          <StatCard
            label="Adapters"
            value={adapters.length > 0 ? `${adapters.length} configured` : '—'}
            sub={
              errorCount > 0 || staleCount > 0
                ? `${errorCount > 0 ? `${errorCount} error${errorCount > 1 ? 's' : ''}` : ''}${errorCount > 0 && staleCount > 0 ? ' · ' : ''}${staleCount > 0 ? `${staleCount} stale` : ''}`
                : 'All healthy'
            }
            subColor={errorCount > 0 ? colors.statusRed : staleCount > 0 ? colors.statusAmber : '#4B5563'}
          />
          <StatCard
            label="Embedding Model"
            value={health ? health.embedding_model.replace(/^all-/, '').split('-').slice(0, 2).join('-') : '—'}
            sub={health ? `${health.embedding_model} · ${health.embedding_dimension}d` : 'Loading…'}
          />
        </div>

        {/* ── Adapter Status Table ── */}
        <div className="flex flex-col gap-2" style={{ flex: '0 0 auto' }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: '#FFFFFF', fontFamily: 'Inter, sans-serif' }}>
            Adapter Status
          </span>
          <div
            style={{
              background: '#161616',
              borderRadius: 8,
              border: '1px solid #1E1E1E',
              overflow: 'hidden',
            }}
          >
            {/* Header */}
            <div
              className="flex"
              style={{
                height: 36,
                background: '#111111',
                borderBottom: '1px solid #1A1A1A',
              }}
            >
              {[
                { label: 'ADAPTER', width: 200 },
                { label: 'DOMAIN', width: 110 },
                { label: 'LAST RUN', width: 160 },
                { label: 'ITEMS', width: 90 },
                { label: 'STATUS', width: 110 },
                { label: 'ACTIONS', width: undefined },
              ].map(col => (
                <div
                  key={col.label}
                  className="flex items-center"
                  style={{
                    width: col.width,
                    flex: col.width ? undefined : 1,
                    padding: '0 14px',
                  }}
                >
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: 700,
                      color: '#4B5563',
                      fontFamily: 'Inter, sans-serif',
                    }}
                  >
                    {col.label}
                  </span>
                </div>
              ))}
            </div>

            {/* Rows */}
            {adminAdaptersQuery.isLoading ? (
              <div className="flex flex-col">
                {[1, 2, 3].map(i => (
                  <div
                    key={i}
                    className="animate-pulse"
                    style={{ height: 44, borderBottom: '1px solid #1A1A1A' }}
                  />
                ))}
              </div>
            ) : adminAdaptersQuery.isError ? (
              <div
                className="flex items-center justify-center py-6"
                style={{ color: colors.statusRed, fontSize: 13 }}
              >
                Failed to load adapter status
              </div>
            ) : adapters.length === 0 ? (
              <div
                className="flex items-center justify-center py-8"
                style={{ color: '#4B5563', fontSize: 13 }}
              >
                No adapters registered
              </div>
            ) : (
              adapters.map(adapter => (
                <AdapterRow
                  key={adapter.adapter_id}
                  adapter={adapter}
                  health={adapterHealthMap.get(adapter.adapter_id) ?? 'unknown'}
                  onSync={id => syncMutation.mutate(id)}
                  onReset={setResetTarget}
                  syncingId={syncingId}
                />
              ))
            )}
          </div>

          {/* Sync feedback */}
          {syncFeedback && (
            <div
              style={{
                padding: '8px 12px',
                borderRadius: 6,
                background: syncFeedback.ok ? '#052E16' : '#1A0E0E',
                border: `1px solid ${syncFeedback.ok ? '#14532D' : '#3B1515'}`,
              }}
            >
              <span
                style={{
                  fontSize: 12,
                  color: syncFeedback.ok ? colors.statusGreen : colors.statusRed,
                  fontFamily: 'Inter, sans-serif',
                }}
              >
                {syncFeedback.id}: {syncFeedback.msg}
              </span>
            </div>
          )}
        </div>

        {/* ── System Configuration ── */}
        {config && (
          <div className="flex flex-col gap-2" style={{ flex: '0 0 auto' }}>
            <span
              style={{ fontSize: 13, fontWeight: 600, color: '#FFFFFF', fontFamily: 'Inter, sans-serif' }}
            >
              System Configuration
            </span>
            <div
              style={{
                background: '#161616',
                borderRadius: 8,
                border: '1px solid #1E1E1E',
                overflow: 'hidden',
              }}
            >
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
            </div>
          </div>
        )}

        {/* ── Sync Log ── */}
        <div className="flex flex-col gap-2" style={{ flex: '0 0 auto', paddingBottom: 16 }}>
          <div className="flex items-center gap-3">
            <span
              style={{ fontSize: 13, fontWeight: 600, color: '#FFFFFF', fontFamily: 'Inter, sans-serif' }}
            >
              Sync Log
            </span>
            {totalLogs > 0 && (
              <span style={{ fontSize: 11, color: '#4B5563', fontFamily: 'Inter, sans-serif' }}>
                {totalLogs.toLocaleString()} entries
              </span>
            )}
          </div>
          <div
            style={{
              background: '#161616',
              borderRadius: 8,
              border: '1px solid #1E1E1E',
              overflow: 'hidden',
            }}
          >
            {/* Log table header */}
            <div
              className="flex"
              style={{
                height: 32,
                background: '#111111',
                borderBottom: '1px solid #1A1A1A',
              }}
            >
              {['OPERATION', 'CHUNK HASH', 'TIMESTAMP'].map((label, i) => (
                <div
                  key={label}
                  className="flex items-center"
                  style={{
                    width: i === 0 ? 100 : i === 1 ? undefined : 180,
                    flex: i === 1 ? 1 : undefined,
                    padding: '0 14px',
                  }}
                >
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: 700,
                      color: '#4B5563',
                      fontFamily: 'Inter, sans-serif',
                    }}
                  >
                    {label}
                  </span>
                </div>
              ))}
            </div>

            {logsQuery.isLoading ? (
              <div className="flex flex-col">
                {[1, 2, 3].map(i => (
                  <div
                    key={i}
                    className="animate-pulse"
                    style={{ height: 36, borderBottom: '1px solid #1A1A1A' }}
                  />
                ))}
              </div>
            ) : logsQuery.isError ? (
              <div
                className="flex items-center justify-center py-5"
                style={{ color: colors.statusRed, fontSize: 13 }}
              >
                Failed to load sync log
              </div>
            ) : !logsQuery.data?.entries.length ? (
              <div
                className="flex items-center justify-center py-6"
                style={{ color: '#4B5563', fontSize: 13 }}
              >
                No sync log entries
              </div>
            ) : (
              logsQuery.data.entries.map(entry => (
                <div
                  key={entry.id}
                  className="flex items-center"
                  style={{ height: 36, borderBottom: '1px solid #1A1A1A' }}
                >
                  <div style={{ width: 100, padding: '0 14px' }}>
                    <span
                      style={{
                        fontSize: 11,
                        fontFamily: 'Inter, sans-serif',
                        color: entry.operation === 'insert' ? colors.statusGreen : colors.statusRed,
                        fontWeight: 600,
                      }}
                    >
                      {entry.operation.charAt(0).toUpperCase() + entry.operation.slice(1)}
                    </span>
                  </div>
                  <div style={{ flex: 1, padding: '0 14px', minWidth: 0 }}>
                    <span
                      className="block truncate"
                      style={{
                        fontSize: 11,
                        color: '#6B7280',
                        fontFamily: 'monospace',
                      }}
                    >
                      {entry.chunk_hash}
                    </span>
                  </div>
                  <div style={{ width: 180, padding: '0 14px' }}>
                    <span style={{ fontSize: 11, color: '#4B5563', fontFamily: 'Inter, sans-serif' }}>
                      {entry.synced_at
                        ? new Date(entry.synced_at).toLocaleString('en-US', {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })
                        : '—'}
                    </span>
                  </div>
                </div>
              ))
            )}

            {/* Pagination */}
            {totalLogPages > 1 && (
              <div
                className="flex items-center justify-between"
                style={{
                  padding: '8px 14px',
                  borderTop: '1px solid #1A1A1A',
                  background: '#111111',
                }}
              >
                <span style={{ fontSize: 11, color: '#4B5563', fontFamily: 'Inter, sans-serif' }}>
                  Page {logsPage + 1} of {totalLogPages}
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => setLogsPage(p => Math.max(0, p - 1))}
                    disabled={logsPage === 0}
                    style={{
                      padding: '3px 10px',
                      borderRadius: 4,
                      background: '#1A1A1A',
                      border: 'none',
                      cursor: logsPage === 0 ? 'default' : 'pointer',
                      opacity: logsPage === 0 ? 0.4 : 1,
                    }}
                  >
                    <span style={{ fontSize: 11, color: '#9CA3AF', fontFamily: 'Inter, sans-serif' }}>
                      Prev
                    </span>
                  </button>
                  <button
                    onClick={() => setLogsPage(p => Math.min(totalLogPages - 1, p + 1))}
                    disabled={logsPage >= totalLogPages - 1}
                    style={{
                      padding: '3px 10px',
                      borderRadius: 4,
                      background: '#1A1A1A',
                      border: 'none',
                      cursor: logsPage >= totalLogPages - 1 ? 'default' : 'pointer',
                      opacity: logsPage >= totalLogPages - 1 ? 0.4 : 1,
                    }}
                  >
                    <span style={{ fontSize: 11, color: '#9CA3AF', fontFamily: 'Inter, sans-serif' }}>
                      Next
                    </span>
                  </button>
                </div>
              </div>
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
