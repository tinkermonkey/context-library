import type { ReactNode } from 'react';
import { StatusBadge, Button } from '@tinkermonkey/heimdall-ui';
import { ConfigTile } from './ConfigTile';
import type { AdminAdapterStatus } from '../types/api';
import {
  DOMAIN_ICONS,
  formatRelativeTime,
  healthToBadgeColor,
} from '../utils/adapterHelpers';
import type { AdapterHealth } from '../utils/adapterHelpers';

interface AdapterCardProps {
  adapter: AdminAdapterStatus;
  domain: string;
  adapterHealth: AdapterHealth;
  isSyncing: boolean;
  onSync: () => void;
  onReset: () => void;
}

export function AdapterCard({
  adapter,
  domain,
  adapterHealth,
  isSyncing,
  onSync,
  onReset,
}: AdapterCardProps): ReactNode {
  return (
    <div
      style={{
        border: `1px solid rgb(var(--canvas-border))`,
        borderRadius: 'var(--radius-md)',
        background: 'rgb(var(--canvas-card))',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <ConfigTile
        icon={DOMAIN_ICONS[domain] ?? 'component'}
        title={adapter.adapter_id}
        description={adapter.adapter_type}
        summary={[
          { label: 'Sources', value: adapter.source_count.toLocaleString() },
          { label: 'Last Poll', value: formatRelativeTime(adapter.last_run) },
        ]}
      />
      <div
        style={{
          padding: '6px 12px',
          borderTop: `1px solid rgb(var(--canvas-border))`,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <StatusBadge color={healthToBadgeColor(adapterHealth)}>
          {adapterHealth}
        </StatusBadge>
      </div>
      <div
        style={{
          display: 'flex',
          gap: 6,
          padding: '8px 12px',
          borderTop: `1px solid rgb(var(--canvas-border))`,
          background: `rgb(var(--canvas-bg-2))`,
        }}
      >
        <Button
          variant={adapterHealth === 'error' ? 'danger' : 'ghost'}
          size="sm"
          disabled={isSyncing}
          onClick={onSync}
        >
          {isSyncing ? 'Syncing…' : 'Re-poll'}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onReset}
        >
          Reset
        </Button>
      </div>
    </div>
  );
}
