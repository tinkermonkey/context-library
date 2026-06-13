import { useState, useMemo } from 'react';
import type { ReactNode } from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import {
  PageHeader,
  Button,
  VersionPill,
  VersionTimeline,
  DiffViewer,
} from '@tinkermonkey/heimdall-ui';
import type { DiffViewerMode, VersionEntry } from '@tinkermonkey/heimdall-ui';
import { KVGrid } from '../components/KVGrid';
import { FilterDropdown } from '../components/FilterDropdown';
import { useSource, useVersionHistory, useVersionDiff, useVersionDetail } from '../hooks/useSources';
import { capitalize } from '../utils/formatters';
import { computeLineDiff } from '../utils/computeLineDiff';

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return 'Never';
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function SectionHeading({ children }: { children: ReactNode }) {
  return (
    <h2
      className="text-xs font-medium uppercase tracking-wider mb-3"
      style={{ color: 'rgb(var(--canvas-fg-3))' }}
    >
      {children}
    </h2>
  );
}

export default function SourceDetailPage(): ReactNode {
  const { sourceId } = useParams({ from: '/sources/$sourceId' });
  const navigate = useNavigate();

  const [fromVersion, setFromVersion] = useState<number | null>(null);
  const [toVersion, setToVersion] = useState<number | null>(null);
  const [diffMode, setDiffMode] = useState<DiffViewerMode>('hash-set');

  const sourceQuery = useSource(sourceId);
  const historyQuery = useVersionHistory(sourceId);

  const canCompare = fromVersion !== null && toVersion !== null && fromVersion !== toVersion;

  const diffQuery = useVersionDiff(sourceId, fromVersion ?? 0, toVersion ?? 0, canCompare);
  const fromDetailQuery = useVersionDetail(
    sourceId,
    fromVersion ?? 0,
    diffMode === 'side-by-side' && canCompare
  );
  const toDetailQuery = useVersionDetail(
    sourceId,
    toVersion ?? 0,
    diffMode === 'side-by-side' && canCompare
  );

  const source = sourceQuery.data;

  const timelineEntries: VersionEntry[] = useMemo(
    () =>
      (historyQuery.data?.versions ?? []).map((v) => ({
        id: String(v.version),
        label: `v${v.version}`,
        timestamp: v.fetch_timestamp,
        head: source ? v.version === source.current_version : false,
        stats: {
          added: v.added_chunks,
          removed: v.removed_chunks,
          kept: v.unchanged_chunks,
        },
      })),
    [historyQuery.data, source]
  );

  const diffLines = useMemo(() => {
    if (diffMode !== 'side-by-side' || !canCompare) return [];
    const fromMd = fromDetailQuery.data?.markdown;
    const toMd = toDetailQuery.data?.markdown;
    if (!fromMd || !toMd) return [];
    return computeLineDiff(fromMd, toMd);
  }, [diffMode, canCompare, fromDetailQuery.data, toDetailQuery.data]);

  if (sourceQuery.isLoading || historyQuery.isLoading) {
    return (
      <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
        <PageHeader eyebrow="Sources" title="Loading…" />
        <div className="flex-1 flex items-center justify-center">
          <span className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>Loading…</span>
        </div>
      </div>
    );
  }

  if (sourceQuery.isError || !source) {
    return (
      <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
        <PageHeader eyebrow="Sources" title="Source Detail" />
        <div className="px-6 py-4">
          <Button size="sm" variant="secondary" onClick={() => navigate({ to: '/sources' })}>
            ← Back to Sources
          </Button>
        </div>
        <div className="flex-1 flex items-center justify-center">
          <span className="text-sm" style={{ color: 'rgb(var(--status-error))' }}>
            Failed to load source
          </span>
        </div>
      </div>
    );
  }

  const kvRows = [
    { key: 'Adapter', value: source.adapter_id },
    { key: 'Domain', value: capitalize(source.domain) },
    { key: 'Last Fetched', value: timeAgo(source.last_fetched_at) },
    { key: 'Chunks', value: source.chunk_count.toLocaleString() },
    { key: 'State', value: source.poll_strategy },
  ];

  const isDiffLoading =
    diffQuery.isLoading ||
    (diffMode === 'side-by-side' && (fromDetailQuery.isLoading || toDetailQuery.isLoading));

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
      <PageHeader
        eyebrow="Sources"
        title={source.display_name ?? source.source_id}
        idChip={sourceId.substring(0, 16)}
        subtitle={`${capitalize(source.domain)} · ${source.adapter_id}`}
        actions={<VersionPill>v{source.current_version}</VersionPill>}
      />

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        {/* Metadata */}
        <section>
          <SectionHeading>Metadata</SectionHeading>
          <KVGrid rows={kvRows} keyWidth={120} />
        </section>

        {/* Version Timeline */}
        <section>
          <SectionHeading>Version History</SectionHeading>
          {historyQuery.isError ? (
            <span className="text-sm" style={{ color: 'rgb(var(--status-error))' }}>
              Failed to load versions
            </span>
          ) : (
            <VersionTimeline
              entries={timelineEntries}
              order="newest-first"
              emptyState="No versions recorded"
            />
          )}
        </section>

        {/* Version Selectors */}
        {(historyQuery.data?.versions.length ?? 0) >= 2 && (
          <section>
            <SectionHeading>Compare Versions</SectionHeading>
            <div className="flex items-center gap-3 flex-wrap">
              <FilterDropdown
                mode="radio"
                value={fromVersion !== null ? [String(fromVersion)] : []}
                onChange={(vals) => setFromVersion(vals[0] ? Number(vals[0]) : null)}
              >
                <FilterDropdown.Trigger
                  label="From"
                  summary={fromVersion !== null ? `v${fromVersion}` : 'Select…'}
                />
                <FilterDropdown.Panel>
                  <FilterDropdown.Section>
                    {historyQuery.data?.versions.map((v) => (
                      <FilterDropdown.Radio
                        key={v.version}
                        value={String(v.version)}
                        label={`v${v.version}`}
                      />
                    ))}
                  </FilterDropdown.Section>
                </FilterDropdown.Panel>
              </FilterDropdown>

              <span className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>→</span>

              <FilterDropdown
                mode="radio"
                value={toVersion !== null ? [String(toVersion)] : []}
                onChange={(vals) => setToVersion(vals[0] ? Number(vals[0]) : null)}
              >
                <FilterDropdown.Trigger
                  label="To"
                  summary={toVersion !== null ? `v${toVersion}` : 'Select…'}
                />
                <FilterDropdown.Panel>
                  <FilterDropdown.Section>
                    {historyQuery.data?.versions.map((v) => (
                      <FilterDropdown.Radio
                        key={v.version}
                        value={String(v.version)}
                        label={`v${v.version}`}
                      />
                    ))}
                  </FilterDropdown.Section>
                </FilterDropdown.Panel>
              </FilterDropdown>
            </div>
          </section>
        )}

        {/* Diff View */}
        {canCompare && (
          <section>
            {isDiffLoading ? (
              <div className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                Computing diff…
              </div>
            ) : diffQuery.isError ? (
              <div className="text-sm" style={{ color: 'rgb(var(--status-error))' }}>
                Failed to load diff
              </div>
            ) : diffQuery.data ? (
              <DiffViewer mode={diffMode} onModeChange={setDiffMode}>
                {diffMode === 'hash-set' ? (
                  <DiffViewer.HashSet
                    added={diffQuery.data.added_hashes}
                    removed={diffQuery.data.removed_hashes}
                    kept={diffQuery.data.unchanged_hashes}
                  />
                ) : (
                  <DiffViewer.SideBySide
                    lines={diffLines}
                    addedLabel={`v${toVersion}`}
                    removedLabel={`v${fromVersion}`}
                  />
                )}
              </DiffViewer>
            ) : null}
          </section>
        )}
      </div>
    </div>
  );
}
