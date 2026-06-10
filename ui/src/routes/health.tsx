import { useState, useMemo, useEffect } from 'react';
import type { ReactNode } from 'react';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import {
  Icon, PageHeader,
  StatTile, StatGrid,
  Heatmap,
  StackedBar,
} from '@tinkermonkey/heimdall-ui';
import { SegmentedControl } from '../components/SegmentedControl';
import { FilterDropdown } from '../components/FilterDropdown';
import { fetchChunks } from '../api/client';
import { getDomainColor, getDomainColorWithAlpha } from '../lib/designTokens';
import type { ChunkResponse } from '../types/api';

const healthColor = getDomainColor('health');
const stepsColor = '#6366F1';

// ── Types ──────────────────────────────────────────────────────────

type MetricKey = 'steps' | 'sleep_score' | 'resting_heart_rate' | 'hrv';

const KNOWN_METRICS = new Set<MetricKey>(['steps', 'sleep_score', 'resting_heart_rate', 'hrv']);

interface HealthMetric {
  metric_type: MetricKey;
  value: number;
  unit: string;
  date: string;
  adapter_id: string;
}

interface MetricReading {
  value: number;
  adapter_id: string;
  hasConflict: boolean;
}

interface DayBucket {
  date: string;
  steps: MetricReading | null;
  sleep_score: MetricReading | null;
  resting_heart_rate: MetricReading | null;
  hrv: MetricReading | null;
}

interface ValueTrend {
  current: MetricReading | null;
  prev: MetricReading | null;
}

// ── Metadata extraction ────────────────────────────────────────────

function extractHealthMetric(chunk: ChunkResponse): HealthMetric | null {
  const dm = chunk.domain_metadata;
  if (!dm) return null;

  const raw = typeof dm.metric_type === 'string' ? dm.metric_type : '';
  if (!KNOWN_METRICS.has(raw as MetricKey)) return null;
  const metric_type = raw as MetricKey;

  const value =
    typeof dm.value === 'number' ? dm.value : parseFloat(String(dm.value ?? ''));
  if (isNaN(value)) return null;

  let date = typeof dm.date === 'string' ? dm.date.slice(0, 10) : '';
  if (!date && chunk.context_header) {
    const m = chunk.context_header.match(/(\d{4}-\d{2}-\d{2})/);
    if (m) date = m[1];
  }
  if (!date) return null;

  return {
    metric_type,
    value,
    unit: typeof dm.unit === 'string' ? dm.unit : '',
    date,
    adapter_id: chunk.lineage.adapter_id,
  };
}

// ── Date helpers ───────────────────────────────────────────────────

function todayKey(): string {
  return new Date().toISOString().slice(0, 10);
}

function daysAgoKey(n: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - n);
  return d.toISOString().slice(0, 10);
}

function dateRange(days: number): { from: string; to: string } {
  return { from: daysAgoKey(days - 1), to: todayKey() };
}

function datesBetween(from: string, to: string): string[] {
  const dates: string[] = [];
  const cur = new Date(from + 'T00:00:00Z');
  const end = new Date(to + 'T00:00:00Z');
  while (cur <= end) {
    dates.push(cur.toISOString().slice(0, 10));
    cur.setUTCDate(cur.getUTCDate() + 1);
  }
  return dates;
}

function shortDateLabel(key: string): string {
  const parts = key.split('-');
  return `${parseInt(parts[1])}/${parseInt(parts[2])}`;
}

// ── Source priority & labels ───────────────────────────────────────

function adapterPriority(adapterId: string): number {
  const base = (adapterId ?? '').split(':')[0].toLowerCase();
  if (base.includes('oura')) return 2;
  if (base.includes('apple_health') || base.includes('applehealth')) return 1;
  return 0;
}

function adapterDisplayName(adapterId: string): string {
  const base = (adapterId ?? '').split(':')[0].toLowerCase();
  if (base.includes('oura')) return 'Oura Ring';
  if (base.includes('apple_health') || base.includes('applehealth')) return 'Apple Health';
  return (adapterId ?? '').split(':')[0].replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function sourcesUsed(metrics: HealthMetric[]): string[] {
  const seen = new Set<string>();
  for (const m of metrics) seen.add(adapterDisplayName(m.adapter_id));
  return Array.from(seen).sort();
}

// ── Aggregation ────────────────────────────────────────────────────

function resolveReading(readings: HealthMetric[]): MetricReading | null {
  if (readings.length === 0) return null;
  const sorted = [...readings].sort(
    (a, b) => adapterPriority(b.adapter_id) - adapterPriority(a.adapter_id),
  );
  return {
    value: sorted[0].value,
    adapter_id: sorted[0].adapter_id,
    hasConflict: readings.length > 1,
  };
}

function aggregateByDay(metrics: HealthMetric[]): Map<string, DayBucket> {
  const raw = new Map<string, Record<MetricKey, HealthMetric[]>>();
  for (const m of metrics) {
    if (!raw.has(m.date)) {
      raw.set(m.date, { steps: [], sleep_score: [], resting_heart_rate: [], hrv: [] });
    }
    raw.get(m.date)![m.metric_type].push(m);
  }

  const map = new Map<string, DayBucket>();
  for (const [date, day] of raw) {
    map.set(date, {
      date,
      steps: resolveReading(day.steps),
      sleep_score: resolveReading(day.sleep_score),
      resting_heart_rate: resolveReading(day.resting_heart_rate),
      hrv: resolveReading(day.hrv),
    });
  }
  return map;
}

function latestValue(days: DayBucket[], key: MetricKey): ValueTrend {
  const sorted = [...days].sort((a, b) => b.date.localeCompare(a.date));
  let current: MetricReading | null = null;
  let prev: MetricReading | null = null;
  for (const d of sorted) {
    const r = d[key];
    if (r !== null) {
      if (current === null) current = r;
      else if (prev === null) { prev = r; break; }
    }
  }
  return { current, prev };
}

// ── Sleep score color ──────────────────────────────────────────────

function sleepScoreColor(score: number): string {
  if (score >= 80) return 'rgb(var(--status-ok))';
  if (score >= 60) return 'rgb(var(--status-amber))';
  return 'rgb(var(--status-error))';
}

// ── Metric config ──────────────────────────────────────────────────

const METRIC_CONFIG: Record<MetricKey, {
  label: string;
  unit: string;
  color: 'cyan' | 'violet' | 'rose' | 'emerald';
  lowerIsBetter?: boolean;
  formatValue?: (v: number) => string;
  goal?: number;
}> = {
  steps: { label: 'Steps', unit: 'steps', color: 'cyan', goal: 10_000, formatValue: v => v.toLocaleString() },
  sleep_score: { label: 'Sleep Score', unit: '/ 100', color: 'violet', formatValue: v => String(Math.round(v)) },
  resting_heart_rate: { label: 'Resting HR', unit: 'bpm', color: 'rose', lowerIsBetter: true },
  hrv: { label: 'HRV', unit: 'ms', color: 'emerald' },
};

// ── Date range presets ─────────────────────────────────────────────

const RANGE_OPTIONS = [
  { value: '7', label: '7d' },
  { value: '30', label: '30d' },
  { value: '90', label: '90d' },
  { value: '365', label: '1y' },
];

const RANGE_DAYS: Record<string, number> = { '7': 7, '30': 30, '90': 90, '365': 365 };

// ── Empty & Error states ───────────────────────────────────────────

function EmptyState(): ReactNode {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 64, height: 64, background: getDomainColorWithAlpha('health', '20') }}
      >
        <span style={{ color: healthColor }}>
          <Icon name="heart" size={32} />
        </span>
      </div>
      <div className="text-center">
        <p className="text-sm font-medium mb-1" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
          No health data found
        </p>
        <p style={{ fontSize: 12, color: 'rgb(var(--canvas-fg-3))' }}>
          Connect an Oura Ring or Apple Health source to see metrics here.
        </p>
      </div>
    </div>
  );
}

function ErrorState(): ReactNode {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 64, height: 64, background: 'rgb(var(--status-error) / 0.13)' }}
      >
        <span style={{ color: 'rgb(var(--status-error))' }}>
          <Icon name="alert" size={32} />
        </span>
      </div>
      <div className="text-center">
        <p className="text-sm font-medium mb-1" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
          Failed to load health data
        </p>
        <p style={{ fontSize: 12, color: 'rgb(var(--canvas-fg-3))' }}>
          There was a problem fetching your health metrics. Please try again.
        </p>
      </div>
    </div>
  );
}

// ── HealthPage ─────────────────────────────────────────────────────

export default function HealthPage(): ReactNode {
  const navigate = useNavigate();
  const search = useSearch({ from: '/health' });

  const today = todayKey();

  // Date range controlled by SegmentedControl
  const [rangeKey, setRangeKey] = useState<string>(
    search.dateFrom ? 'custom' : '30',
  );

  useEffect(() => {
    if (!search.dateFrom && rangeKey === 'custom') setRangeKey('30');
  }, [search.dateFrom]);

  const effectiveRange = useMemo((): { from: string; to: string } => {
    if (search.dateFrom && search.dateTo) return { from: search.dateFrom, to: search.dateTo };
    return dateRange(RANGE_DAYS[rangeKey] ?? 30);
  }, [rangeKey, search.dateFrom, search.dateTo]);

  function setRange(key: string): void {
    setRangeKey(key);
    void navigate({ to: '/health', search: {} });
  }

  // Metric visibility filter
  const [enabledMetrics, setEnabledMetrics] = useState<string[]>(
    ['steps', 'sleep_score', 'resting_heart_rate', 'hrv'],
  );

  // ── Data ─────────────────────────────────────────────────────────

  const { data, isLoading, isError } = useQuery({
    queryKey: ['chunks', { domain: 'health', limit: 5000 }],
    queryFn: () => fetchChunks({ domain: 'health', limit: 5000 }),
    staleTime: 5 * 60_000,
  });

  const allMetrics = useMemo<HealthMetric[]>(() => {
    if (!data?.chunks) return [];
    return data.chunks.flatMap(c => {
      const m = extractHealthMetric(c);
      return m ? [m] : [];
    });
  }, [data]);

  const rangeMetrics = useMemo(
    () => allMetrics.filter(m => m.date >= effectiveRange.from && m.date <= effectiveRange.to),
    [allMetrics, effectiveRange],
  );

  const dayMap = useMemo(() => aggregateByDay(rangeMetrics), [rangeMetrics]);

  const allDates = useMemo(
    () => datesBetween(effectiveRange.from, effectiveRange.to),
    [effectiveRange],
  );

  const orderedBuckets = useMemo(
    () => allDates.map(d =>
      dayMap.get(d) ?? { date: d, steps: null, sleep_score: null, resting_heart_rate: null, hrv: null },
    ),
    [allDates, dayMap],
  );

  // Trends — slow metrics use all-time data for a better baseline
  const allBuckets = useMemo(
    () => Array.from(aggregateByDay(allMetrics).values()),
    [allMetrics],
  );
  const stepsTrend = useMemo(() => latestValue(orderedBuckets, 'steps'), [orderedBuckets]);
  const sleepTrend = useMemo(() => latestValue(orderedBuckets, 'sleep_score'), [orderedBuckets]);
  const hrTrend = useMemo(() => latestValue(allBuckets, 'resting_heart_rate'), [allBuckets]);
  const hrvTrend = useMemo(() => latestValue(allBuckets, 'hrv'), [allBuckets]);

  const TRENDS: Record<MetricKey, ValueTrend> = {
    steps: stepsTrend,
    sleep_score: sleepTrend,
    resting_heart_rate: hrTrend,
    hrv: hrvTrend,
  };

  const sources = useMemo(() => sourcesUsed(allMetrics), [allMetrics]);
  const hasAnyData = allMetrics.length > 0;

  // ── Build heatmap data (steps intensity) ────────────────────────

  const heatmapData = useMemo(() => {
    const stepsMax = Math.max(1, ...orderedBuckets.map(b => b.steps?.value ?? 0));
    // Single row × N days, normalized 0–1
    const row = orderedBuckets.map(b => {
      const v = b.steps?.value;
      return v != null ? v / stepsMax : null;
    });
    return [row];
  }, [orderedBuckets]);

  // ── Build StackedBar data for each enabled metric ────────────────

  function metricStacks(key: MetricKey) {
    return allDates.map((date, i) => {
      const bucket = orderedBuckets[i];
      const v = bucket[key]?.value ?? 0;
      return { label: shortDateLabel(date), parts: [v] };
    });
  }

  // Delta helpers for StatTile
  function trendDelta(trend: ValueTrend, lowerIsBetter = false) {
    if (!trend.current || !trend.prev) return undefined;
    const delta = trend.current.value - trend.prev.value;
    if (Math.abs(delta) < 0.5) return undefined;
    return {
      value: Math.round(Math.abs(delta)),
      direction: (lowerIsBetter ? delta < 0 : delta > 0) ? 'up' as const : 'down' as const,
    };
  }

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
      <PageHeader
        eyebrow="Domains"
        title="Health"
        subtitle="Health metrics from Oura Ring and Apple Health"
      />

      {/* ── Toolbar ── */}
      <div
        className="flex items-center gap-3 px-5 py-2.5 shrink-0 flex-wrap"
        style={{ borderBottom: `1px solid rgb(var(--canvas-border))`, background: 'rgb(var(--canvas-surface))' }}
      >
        <SegmentedControl
          value={rangeKey}
          onChange={setRange}
          options={RANGE_OPTIONS}
        />

        <FilterDropdown
          mode="checkbox"
          value={enabledMetrics}
          onChange={setEnabledMetrics}
        >
          <FilterDropdown.Trigger
            label="Metrics"
            summary={enabledMetrics.length === 4 ? 'All metrics' : `${enabledMetrics.length} selected`}
          />
          <FilterDropdown.Panel>
            <FilterDropdown.Section title="Visible metrics">
              <FilterDropdown.Checkbox value="steps" label="Steps" />
              <FilterDropdown.Checkbox value="sleep_score" label="Sleep Score" />
              <FilterDropdown.Checkbox value="resting_heart_rate" label="Resting HR" />
              <FilterDropdown.Checkbox value="hrv" label="HRV" />
            </FilterDropdown.Section>
          </FilterDropdown.Panel>
        </FilterDropdown>

        <div className="flex-1" />

        {sources.length > 0 && (
          <div className="flex items-center gap-1.5">
            {sources.map(s => (
              <span
                key={s}
                className="px-2 py-0.5 rounded text-xs font-medium"
                style={{
                  background: getDomainColorWithAlpha('health', '18'),
                  color: healthColor,
                  border: `1px solid ${getDomainColorWithAlpha('health', '30')}`,
                }}
              >
                {s}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* ── Body ── */}
      {isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <div
            className="w-6 h-6 rounded-full border-2 animate-spin"
            style={{ borderColor: `${healthColor} transparent transparent transparent` }}
          />
        </div>
      ) : isError ? (
        <ErrorState />
      ) : !hasAnyData ? (
        <EmptyState />
      ) : (
        <div className="flex-1 flex flex-col gap-4 p-5 overflow-y-auto">

          {/* ── StatGrid — metric summary tiles ── */}
          <StatGrid columns={4}>
            {(Object.entries(METRIC_CONFIG) as [MetricKey, typeof METRIC_CONFIG[MetricKey]][])
              .filter(([key]) => enabledMetrics.includes(key))
              .map(([key, cfg]) => {
                const trend = TRENDS[key];
                const displayVal = trend.current !== null
                  ? (cfg.formatValue ? cfg.formatValue(trend.current.value) : String(Math.round(trend.current.value)))
                  : '—';
                const delta = trendDelta(trend, cfg.lowerIsBetter);
                return (
                  <StatTile
                    key={key}
                    label={cfg.label}
                    value={trend.current !== null ? `${displayVal} ${cfg.unit}` : '—'}
                    color={cfg.color}
                    delta={delta}
                  />
                );
              })
            }
          </StatGrid>

          {/* ── Heatmap: daily step intensity ── */}
          {enabledMetrics.includes('steps') && (
            <div
              className="rounded-lg p-4"
              style={{ background: 'rgb(var(--canvas-surface))', border: `1px solid rgb(var(--canvas-border))` }}
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-semibold" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
                  Daily Step Intensity — Last {allDates.length} Days
                </span>
                <span className="text-[10px]" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                  low → high
                </span>
              </div>
              <Heatmap
                data={heatmapData}
                baseColor={stepsColor}
                xLabels={allDates.map(shortDateLabel)}
                tone="dark"
                height={48}
                style={{ width: '100%' }}
                ariaLabel="Daily step intensity heatmap"
              />
            </div>
          )}

          {/* ── StackedBar charts ── */}
          {enabledMetrics.includes('steps') && (
            <div
              className="rounded-lg p-4"
              style={{ background: 'rgb(var(--canvas-surface))', border: `1px solid rgb(var(--canvas-border))` }}
            >
              <span className="text-xs font-semibold block mb-3" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
                Steps — Last {allDates.length} Days
              </span>
              <StackedBar
                stacks={metricStacks('steps')}
                colors={[stepsColor]}
                axes
                grid
                tone="dark"
                height={140}
                style={{ width: '100%' }}
              />
            </div>
          )}

          {enabledMetrics.includes('sleep_score') && (
            <div
              className="rounded-lg p-4"
              style={{ background: 'rgb(var(--canvas-surface))', border: `1px solid rgb(var(--canvas-border))` }}
            >
              <span className="text-xs font-semibold block mb-3" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
                Sleep Score — Last {allDates.length} Days
              </span>
              <StackedBar
                stacks={metricStacks('sleep_score')}
                colors={[sleepScoreColor(sleepTrend.current?.value ?? 0)]}
                axes
                grid
                tone="dark"
                height={140}
                style={{ width: '100%' }}
              />
            </div>
          )}

          {(enabledMetrics.includes('hrv') || enabledMetrics.includes('resting_heart_rate')) && (
            <div className="flex gap-4" style={{ minHeight: 180 }}>
              {enabledMetrics.includes('hrv') && (
                <div
                  className="flex-1 rounded-lg p-4"
                  style={{ background: 'rgb(var(--canvas-surface))', border: `1px solid rgb(var(--canvas-border))` }}
                >
                  <span className="text-xs font-semibold block mb-3" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
                    HRV — Last {allDates.length} Days
                  </span>
                  <StackedBar
                    stacks={metricStacks('hrv')}
                    colors={[healthColor]}
                    axes
                    grid
                    tone="dark"
                    height={120}
                    style={{ width: '100%' }}
                  />
                </div>
              )}
              {enabledMetrics.includes('resting_heart_rate') && (
                <div
                  className="flex-1 rounded-lg p-4"
                  style={{ background: 'rgb(var(--canvas-surface))', border: `1px solid rgb(var(--canvas-border))` }}
                >
                  <span className="text-xs font-semibold block mb-3" style={{ color: 'rgb(var(--canvas-fg-2))' }}>
                    Resting HR — Last {allDates.length} Days
                  </span>
                  <StackedBar
                    stacks={metricStacks('resting_heart_rate')}
                    colors={['#EC4899']}
                    axes
                    grid
                    tone="dark"
                    height={120}
                    style={{ width: '100%' }}
                  />
                </div>
              )}
            </div>
          )}

          {today && enabledMetrics.length === 0 && (
            <div className="flex items-center justify-center py-8">
              <p className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                Select metrics above to view charts.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
