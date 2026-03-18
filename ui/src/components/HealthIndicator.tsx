import { useState } from 'react';
import { Badge } from 'flowbite-react';
import { useHealth } from '../hooks/useHealth';
import type { HealthResponse, CollectorStatus, HelperHealth } from '../types/api';

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
  return `${Math.floor(diffSec / 60)}m ago`;
}

// ── Sub-components ───────────────────────────────────────────────

function StatusRow({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <span className={ok ? 'text-green-500' : 'text-red-500'}>{ok ? '✓' : '✗'}</span>
      <span className="text-gray-700 dark:text-gray-300">{label}</span>
    </div>
  );
}

function CollectorRow({
  collector,
  helperReachable,
}: {
  collector: CollectorStatus;
  helperReachable: boolean;
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

  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-gray-700 dark:text-gray-300 text-xs">
        {friendlyName(collector.adapter_type)}
      </span>
      <span className={`font-mono text-xs font-bold ${iconClass}`} title={collector.error ?? undefined}>
        {icon}
      </span>
    </div>
  );
}

function HelperSection({ helper }: { helper: HelperHealth }) {
  return (
    <>
      <hr className="my-2 border-gray-200 dark:border-gray-600" />
      <div className="mb-1.5 flex items-center gap-2">
        <span className="font-semibold text-gray-800 dark:text-white text-xs">Helper Service</span>
        <span
          className={`text-xs font-medium ${helper.reachable ? 'text-green-600' : 'text-red-500'}`}
        >
          {helper.reachable ? '● online' : '● offline'}
        </span>
      </div>
      {helper.collectors.length > 0 && (
        <div className="space-y-0.5 mb-1">
          {helper.collectors.map((c) => (
            <CollectorRow key={c.name} collector={c} helperReachable={helper.reachable} />
          ))}
        </div>
      )}
      {helper.error && (
        <p
          className="text-xs text-red-500 truncate max-w-[240px]"
          title={helper.error}
        >
          {helper.error}
        </p>
      )}
      <p className="mt-1.5 text-xs text-gray-400">Checked {timeAgo(helper.probed_at)}</p>
    </>
  );
}

function HealthDetail({ data }: { data: HealthResponse }) {
  return (
    <div className="min-w-[200px]">
      <p className="mb-1.5 font-semibold text-gray-800 dark:text-white text-xs">Server</p>
      <div className="space-y-0.5 text-xs">
        <StatusRow label="SQLite" ok={data.sqlite_ok} />
        <StatusRow label="ChromaDB" ok={data.chromadb_ok} />
        <p className="text-gray-500 dark:text-gray-400 pt-0.5">
          {data.vector_count.toLocaleString()} vectors &nbsp;·&nbsp; {data.embedding_model}
        </p>
      </div>
      {data.helper && <HelperSection helper={data.helper} />}
    </div>
  );
}

// ── Main export ──────────────────────────────────────────────────

export function HealthIndicator() {
  const { data, isLoading, isError } = useHealth();
  const [open, setOpen] = useState(false);

  let badgeColor: 'green' | 'yellow' | 'red' | 'gray';
  let badgeText: string;

  const helperOk = !data?.helper || data.helper.reachable;

  if (isLoading || isError || !data) {
    badgeColor = 'gray';
    badgeText = 'Unknown';
  } else if (data.sqlite_ok && data.chromadb_ok && helperOk) {
    badgeColor = 'green';
    badgeText = 'Healthy';
  } else if (!data.sqlite_ok && !data.chromadb_ok) {
    badgeColor = 'red';
    badgeText = 'Unhealthy';
  } else {
    badgeColor = 'yellow';
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
        <div className="absolute right-0 top-full mt-1 z-50 rounded-lg border border-gray-200 bg-white shadow-lg p-3 text-sm dark:border-gray-700 dark:bg-gray-800">
          <HealthDetail data={data} />
        </div>
      )}
    </div>
  );
}
