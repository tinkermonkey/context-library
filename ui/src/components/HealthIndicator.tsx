import { useState } from 'react';
import { Badge } from '@tinkermonkey/heimdall-ui';
import { useHealth } from '../hooks/useHealth';
import type { HealthResponse, CollectorStatus, HelperHealth, CollectorDeliveryStatus, EndpointDeliveryStatus } from '../types/api';

// ── Adapter type → display name ─────────────────────────────────

const ADAPTER_NAMES: Record<string, string> = {
  AppleMusicAdapter: 'Apple Music (events)',
  AppleMusicLibraryAdapter: 'Apple Music (library)',
  AppleRemindersAdapter: 'Apple Reminders',
  AppleHealthAdapter: 'Apple Health',
  AppleiMessageAdapter: 'iMessage',
  AppleNotesAdapter: 'Apple Notes',
  FilesystemHelperAdapter: 'Filesystem',
  ObsidianHelperAdapter: 'Obsidian',
  OuraAdapter: 'Oura Ring',
};

function friendlyName(adapterType: string): string {
  return ADAPTER_NAMES[adapterType] ?? adapterType;
}

// ── Time formatting ──────────────────────────────────────────────

function timeAgo(isoString: string): string {
  const diffSec = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
  if (diffSec < 5) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}

// Allow cursor to trail watermark by up to 1s (clock skew / processing lag)
const WATERMARK_TOLERANCE_MS = 1_000;
// Endpoints idle more than this long relative to the most-active sibling are "no new data"
const NO_NEW_DATA_THRESHOLD_MS = 48 * 60 * 60 * 1_000;

function isUpToDate(cursorMs: number, watermark: string | null): boolean {
  const watermarkMs = watermark ? new Date(watermark).getTime() : null;
  if (watermarkMs !== null && cursorMs >= watermarkMs - WATERMARK_TOLERANCE_MS) return true;
  return (Date.now() - cursorMs) / 1000 < 120;
}

function deliveryLabel(d: CollectorDeliveryStatus, watermark: string | null): string {
  if (d.cursor === null) return 'never delivered';
  if (d.has_more || d.has_pending) return `syncing · ${timeAgo(d.cursor)}`;
  const cursorMs = new Date(d.cursor).getTime();
  const checkedSuffix = watermark ? ` · ${timeAgo(watermark)}` : '';
  if (isUpToDate(cursorMs, watermark)) return `up to date${checkedSuffix}`;
  return timeAgo(d.cursor);
}

function endpointLabel(ep: EndpointDeliveryStatus, newestCursorMs: number, watermark: string | null): string {
  if (ep.cursor === null) return 'never';
  if (ep.has_more) return `syncing · ${timeAgo(ep.cursor)}`;
  const cursorMs = new Date(ep.cursor).getTime();
  const checkedSuffix = watermark ? ` · ${timeAgo(watermark)}` : '';
  if (isUpToDate(cursorMs, watermark)) return `up to date${checkedSuffix}`;
  // Cursor is old but has_more: false — no new data exists beyond this point
  if (newestCursorMs - cursorMs > NO_NEW_DATA_THRESHOLD_MS) return `${timeAgo(ep.cursor)} · no new data`;
  return timeAgo(ep.cursor);
}

// ── Sub-components ───────────────────────────────────────────────

function StatusRow({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <span style={{ color: ok ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)' }}>{ok ? '✓' : '✗'}</span>
      <span style={{ color: 'rgb(var(--canvas-fg-2))' }}>{label}</span>
    </div>
  );
}

function CollectorRow({
  collector,
  helperReachable,
  watermark,
}: {
  collector: CollectorStatus;
  helperReachable: boolean;
  watermark: string | null;
}) {
  let icon: string;
  let iconClass: string;

  if (!helperReachable) {
    icon = '—';
    iconClass = 'text-gray-400';
  } else if (collector.healthy === null || collector.healthy === undefined) {
    icon = '·';
    iconClass = 'text-gray-400';
  } else if (collector.healthy) {
    icon = '✓';
    iconClass = 'text-green-500';
  } else {
    icon = '✗';
    iconClass = 'text-red-500';
  }

  const delivery = helperReachable ? collector.delivery : null;
  const endpointEntries = delivery?.endpoints ? Object.entries(delivery.endpoints) : null;
  const newestCursorMs = endpointEntries
    ? Math.max(...endpointEntries.map(([, ep]) => ep.cursor ? new Date(ep.cursor).getTime() : 0))
    : 0;

  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex flex-col min-w-0">
        <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
          {friendlyName(collector.adapter_type)}
        </span>
        {endpointEntries ? (
          <div className="mt-0.5 pl-2 space-y-0.5" style={{ borderLeft: `1px solid rgb(var(--canvas-border))` }}>
            {endpointEntries.map(([name, ep]) => (
              <div key={name} className="flex items-center justify-between gap-3">
                <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>{name}</span>
                <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>{endpointLabel(ep, newestCursorMs, watermark)}</span>
              </div>
            ))}
          </div>
        ) : delivery ? (
          <span className="text-xs leading-tight" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
            {deliveryLabel(delivery, watermark)}
          </span>
        ) : null}
      </div>
      <span className="font-mono text-xs font-bold flex-shrink-0 self-start" style={{ color: iconClass.includes('green') ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)' }} title={collector.error ?? undefined}>
        {icon}
      </span>
    </div>
  );
}

function HelperSection({ helper }: { helper: HelperHealth }) {
  return (
    <>
      <hr className="my-2" style={{ borderColor: 'rgb(var(--canvas-border))' }} />
      <div className="mb-1.5 flex items-center gap-2">
        <span className="font-semibold text-xs" style={{ color: 'rgb(var(--canvas-fg-1))' }}>Helper Service</span>
        <span className="text-xs font-medium" style={{ color: helper.reachable ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)' }}>
          {helper.reachable ? '● online' : '● offline'}
        </span>
      </div>
      {helper.collectors.length > 0 && (
        <div className="space-y-0.5 mb-1">
          {helper.collectors.map((c) => (
            <CollectorRow key={c.name} collector={c} helperReachable={helper.reachable} watermark={helper.watermark} />
          ))}
        </div>
      )}
      {helper.error && (
        <p className="text-xs truncate max-w-[240px]" style={{ color: 'rgb(239, 68, 68)' }} title={helper.error}>
          {helper.error}
        </p>
      )}
      <p className="mt-1.5 text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>Checked {timeAgo(helper.probed_at)}</p>
    </>
  );
}

function HealthDetail({ data }: { data: HealthResponse }) {
  return (
    <div className="min-w-[200px]">
      <p className="mb-1.5 font-semibold text-xs" style={{ color: 'rgb(var(--canvas-fg-1))' }}>Server</p>
      <div className="space-y-0.5 text-xs">
        <StatusRow label="SQLite" ok={data.sqlite_ok} />
        <StatusRow label="ChromaDB" ok={data.chromadb_ok} />
        <p className="pt-0.5" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
          {data.vector_count.toLocaleString()} vectors &nbsp;·&nbsp; {data.embedding_model}
        </p>
      </div>
      {data.helper && <HelperSection helper={data.helper} />}
    </div>
  );
}

// ── Main export ──────────────────────────────────────────────────

export function HealthIndicator() {
  const { data, isLoading, isError } = useHealth(120_000);
  const [open, setOpen] = useState(false);

  let badgeColor: 'emerald' | 'amber' | 'rose' | 'neutral';
  let badgeText: string;

  const helperOk = !data?.helper || data.helper.reachable;

  if (isLoading || isError || !data) {
    badgeColor = 'neutral';
    badgeText = 'Unknown';
  } else if (data.sqlite_ok && data.chromadb_ok && helperOk) {
    badgeColor = 'emerald';
    badgeText = 'Healthy';
  } else if (!data.sqlite_ok && !data.chromadb_ok) {
    badgeColor = 'rose';
    badgeText = 'Unhealthy';
  } else {
    badgeColor = 'amber';
    badgeText = 'Degraded';
  }

  return (
    <div
      className="relative"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <div className="cursor-default">
        <Badge color={badgeColor}>{badgeText}</Badge>
      </div>

      {open && data && (
        <div className="absolute right-0 top-full mt-1 z-50 rounded-lg shadow-lg p-3 text-sm" style={{ borderColor: 'rgb(var(--canvas-border))', border: `1px solid rgb(var(--canvas-border))`, background: 'rgb(var(--canvas-surface))' }}>
          <HealthDetail data={data} />
        </div>
      )}
    </div>
  );
}
