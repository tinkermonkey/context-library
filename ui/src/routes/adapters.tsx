import { useState, useMemo } from 'react';
import type { ReactNode } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  PageHeader,
  StatGrid,
  StatTile,
  Chip,
  StatusBadge,
} from '@tinkermonkey/heimdall-ui';

import { useAdminAdapters } from '../hooks/useAdminAdapters';
import { useHealth } from '../hooks/useHealth';
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

export default function AdaptersPage(): ReactNode {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const healthQuery = useHealth(30_000);
  const adaptersQuery = useAdminAdapters(30_000);

  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [resetTarget, setResetTarget] = useState<AdminAdapterStatus | null>(null);

  const syncMutation = useMutation({
    mutationFn: (id: string) => triggerAdapterSync(id),
    onMutate: (id) => setSyncingId(id),
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
    for (const c of healthQuery.data?.helper?.collectors ?? []) {
      if (c.healthy === false) s.add(c.name);
    }
    return s;
  }, [healthQuery.data]);

  const adapters = adaptersQuery.data?.adapters ?? [];

  const adapterHealthMap = useMemo(() => {
    const m = new Map<string, AdapterHealth>();
    for (const a of adapters) m.set(a.adapter_id, getAdapterHealth(a, errorAdapterIds));
    return m;
  }, [adapters, errorAdapterIds]);

  const errorCount = useMemo(
    () => [...adapterHealthMap.values()].filter((h) => h === 'error').length,
    [adapterHealthMap],
  );

  const healthyCount = useMemo(
    () => [...adapterHealthMap.values()].filter((h) => h === 'healthy').length,
    [adapterHealthMap],
  );

  const adaptersByDomain = useMemo(() => {
    const grouped = new Map<string, AdminAdapterStatus[]>();
    for (const a of adapters) {
      const list = grouped.get(a.domain) ?? [];
      list.push(a);
      grouped.set(a.domain, list);
    }
    const knownDomains = new Set(DOMAIN_ORDER);
    const unknownDomains = [...grouped.keys()].filter((d) => !knownDomains.has(d));
    return [...DOMAIN_ORDER, ...unknownDomains]
      .filter((d) => grouped.has(d))
      .map((d) => ({ domain: d, adapters: grouped.get(d)! }));
  }, [adapters]);

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
      <PageHeader
        eyebrow="System"
        title="Adapters"
        subtitle="Registered data adapters and sync status"
      />

      <div className="flex-1 overflow-y-auto" style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 20 }}>
        <StatGrid columns={3} className="shrink-0">
          <StatTile
            label="Total Adapters"
            value={adaptersQuery.isLoading ? '—' : `${adapters.length}`}
            delta={
              errorCount > 0
                ? { value: errorCount, direction: 'down', label: 'errors' }
                : undefined
            }
          />
          <StatTile
            label="Healthy"
            value={adaptersQuery.isLoading ? '—' : `${healthyCount}`}
          />
          <StatTile
            label="Domains Active"
            value={adaptersQuery.isLoading ? '—' : `${adaptersByDomain.length}`}
          />
        </StatGrid>

        {adaptersQuery.isLoading ? (
          <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-36 rounded-md animate-pulse"
                style={{ background: 'rgb(var(--canvas-card))', border: `1px solid rgb(var(--canvas-border))` }}
              />
            ))}
          </div>
        ) : adaptersQuery.isError ? (
          <div style={{ padding: 24, textAlign: 'center', color: 'rgb(var(--status-error))', fontSize: 13 }}>
            Failed to load adapter status
          </div>
        ) : adapters.length === 0 ? (
          <div style={{ padding: 32, textAlign: 'center', color: 'rgb(var(--canvas-fg-4))', fontSize: 13 }}>
            No adapters registered
          </div>
        ) : (
          <div className="flex flex-col gap-5">
            {adaptersByDomain.map(({ domain, adapters: domainAdapters }) => {
              const color = `rgb(var(--domain-${domain}, var(--canvas-fg-3)))`;
              const label = DOMAIN_LABELS[domain] ?? domain;
              return (
                <div key={domain} className="flex flex-col gap-2">
                  <div className="flex items-center gap-2">
                    <span
                      style={{ width: 7, height: 7, borderRadius: 2, background: color, display: 'inline-block', flexShrink: 0 }}
                    />
                    <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'rgb(var(--canvas-fg-3))' }}>
                      {label}
                    </span>
                  </div>
                  <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
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
                          <div style={{ padding: '8px 12px', display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
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
