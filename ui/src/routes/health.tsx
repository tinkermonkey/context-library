import { useState, useMemo, useEffect } from 'react';
import type { ReactNode } from 'react';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import {
  HeartIcon,
  ArrowTrendingUpIcon,
  ArrowTrendingDownIcon,
  MinusIcon,
} from '@heroicons/react/24/outline';
import { fetchChunks } from '../api/client';
import { colors, getDomainColor } from '../lib/designTokens';
import type { ChunkResponse } from '../types/api';

const healthColor = getDomainColor('health'); // #06B6D4
const stepsColor = '#6366F1';

// ── Types ──────────────────────────────────────────────────────────

type MetricKey = 'steps' | 'sleep_score' | 'resting_heart_rate' | 'hrv';

const KNOWN_METRICS = new Set<MetricKey>(['steps', 'sleep_score', 'resting_heart_rate', 'hrv']);

interface HealthMetric {
  metric_type: MetricKey;
  value: number;
  unit: string;
  date: string; // YYYY-MM-DD UTC
  adapter_id: string;
}

/** A resolved metric reading for a single day, with source attribution. */
interface MetricReading {
  value: number;
  adapter_id: string;
  /** true when multiple adapters reported this metric for the same day */
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
  /** Most recent prior day with a non-null value — used for delta/trend. */
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

  // Prefer domain_metadata.date; fall back to first YYYY-MM-DD in context_header
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

// ── Date helpers — UTC throughout ─────────────────────────────────
//
// All date keys are YYYY-MM-DD strings derived from UTC midnight so they
// match ISO dates returned by the API regardless of the user's timezone.

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

/** Generates YYYY-MM-DD keys for every calendar day from [from, to] inclusive. */
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

/**
 * When two adapters report the same metric on the same day, Oura Ring data
 * takes precedence. Apple Health can aggregate from many sources (including
 * Oura), so summing both would double-count.
 */
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
  return (adapterId ?? '')
    .split(':')[0]
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

function sourcesUsed(metrics: HealthMetric[]): string[] {
  const seen = new Set<string>();
  for (const m of metrics) seen.add(adapterDisplayName(m.adapter_id));
  return Array.from(seen).sort();
}

// ── Aggregation ────────────────────────────────────────────────────

/**
 * Selects the canonical reading when multiple adapters report the same
 * metric on the same day. Higher-priority adapter wins; conflict is flagged
 * so the UI can label the source.
 */
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
  // Pass 1: collect all raw readings per date × metric
  const raw = new Map<string, Record<MetricKey, HealthMetric[]>>();
  for (const m of metrics) {
    if (!raw.has(m.date)) {
      raw.set(m.date, { steps: [], sleep_score: [], resting_heart_rate: [], hrv: [] });
    }
    raw.get(m.date)![m.metric_type].push(m);
  }

  // Pass 2: resolve conflicts per day
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

// ── Latest value with trend ────────────────────────────────────────

function latestValue(days: DayBucket[], key: MetricKey): ValueTrend {
  const sorted = [...days].sort((a, b) => b.date.localeCompare(a.date));
  let current: MetricReading | null = null;
  let prev: MetricReading | null = null;
  for (const d of sorted) {
    const r = d[key];
    if (r !== null) {
      if (current === null) current = r;
      else if (prev === null) {
        prev = r;
        break;
      }
    }
  }
  return { current, prev };
}

// ── Trend badge ────────────────────────────────────────────────────

function TrendBadge({
  current,
  prev,
  unit,
  lowerIsBetter = false,
}: {
  current: MetricReading | null;
  prev: MetricReading | null;
  unit: string;
  lowerIsBetter?: boolean;
}): ReactNode {
  if (!current || !prev) return null;
  const delta = current.value - prev.value;
  if (Math.abs(delta) < 0.5) {
    return (
      <span className="flex items-center gap-0.5 text-xs" style={{ color: colors.textDim }}>
        <MinusIcon className="w-3 h-3" />
        No change
      </span>
    );
  }
  const isGood = lowerIsBetter ? delta < 0 : delta > 0;
  const color = isGood ? colors.statusGreen : colors.statusAmber;
  const sign = delta > 0 ? '+' : '';
  const label =
    Math.abs(delta) >= 1
      ? `${sign}${Math.round(delta)} ${unit}`
      : `${sign}${delta.toFixed(1)} ${unit}`;

  return (
    <span className="flex items-center gap-0.5 text-xs" style={{ color }}>
      {delta > 0 ? (
        <ArrowTrendingUpIcon className="w-3 h-3" />
      ) : (
        <ArrowTrendingDownIcon className="w-3 h-3" />
      )}
      {label} vs prev
    </span>
  );
}

// ── Metric card ────────────────────────────────────────────────────

const STEP_GOAL = 10_000;

function MetricCard({
  label,
  trend,
  unit,
  goal,
  lowerIsBetter,
  formatValue,
}: {
  label: string;
  trend: ValueTrend;
  unit: string;
  goal?: number;
  lowerIsBetter?: boolean;
  formatValue?: (v: number) => string;
}): ReactNode {
  const { current, prev } = trend;
  const displayVal =
    current !== null
      ? formatValue
        ? formatValue(current.value)
        : String(Math.round(current.value))
      : '—';

  return (
    <div
      className="flex-1 rounded-lg p-4 flex flex-col gap-1.5 min-w-0"
      style={{ background: colors.bgSurface, border: `1px solid ${colors.border}` }}
    >
      <span
        className="text-xs font-medium uppercase tracking-wide"
        style={{ color: colors.textDim }}
      >
        {label}
      </span>

      <div className="flex items-baseline gap-1.5">
        <span
          className="text-2xl font-bold tabular-nums"
          style={{ color: colors.textPrimary }}
        >
          {displayVal}
        </span>
        {current !== null && unit && (
          <span className="text-sm font-medium" style={{ color: colors.textMuted }}>
            {unit}
          </span>
        )}
      </div>

      {/* Source attribution — amber when two adapters reported the same day */}
      {current !== null && (
        <span
          className="self-start text-xs px-1.5 py-0.5 rounded"
          style={{
            background: current.hasConflict
              ? `${colors.statusAmber}15`
              : `${healthColor}15`,
            color: current.hasConflict ? colors.statusAmber : healthColor,
            border: `1px solid ${current.hasConflict ? `${colors.statusAmber}40` : `${healthColor}30`}`,
          }}
          title={
            current.hasConflict
              ? `Multiple sources — showing ${adapterDisplayName(current.adapter_id)}`
              : adapterDisplayName(current.adapter_id)
          }
        >
          {adapterDisplayName(current.adapter_id)}
          {current.hasConflict && ' ⚑'}
        </span>
      )}

      {goal !== undefined && current !== null && (
        <div className="mt-0.5">
          <div
            className="h-1 rounded-full overflow-hidden"
            style={{ background: colors.bgElevated }}
          >
            <div
              className="h-full rounded-full"
              style={{
                width: `${Math.min(100, (current.value / goal) * 100).toFixed(1)}%`,
                background: current.value >= goal ? colors.statusGreen : healthColor,
              }}
            />
          </div>
          <span className="text-xs mt-1 block" style={{ color: colors.textDim }}>
            Goal: {goal.toLocaleString()}
          </span>
        </div>
      )}

      <TrendBadge
        current={current}
        prev={prev}
        unit={unit}
        lowerIsBetter={lowerIsBetter}
      />
    </div>
  );
}

// ── Bar chart ──────────────────────────────────────────────────────

function BarChart({
  title,
  dates,
  readings,
  barColor,
  todayKey: today,
  unit,
  emptyLabel,
}: {
  title: string;
  dates: string[];
  readings: (MetricReading | null)[];
  barColor: (value: number, date: string) => string;
  todayKey: string;
  unit?: string;
  emptyLabel?: string;
}): ReactNode {
  const values = readings.map(r => r?.value ?? null);
  const maxValue = Math.max(1, ...values.filter((v): v is number => v !== null));
  const hasData = values.some(v => v !== null);

  return (
    <div
      className="flex-1 flex flex-col gap-3 rounded-lg p-4 min-w-0"
      style={{ background: colors.bgSurface, border: `1px solid ${colors.border}` }}
    >
      <span className="text-xs font-semibold" style={{ color: colors.textMuted }}>
        {title}
      </span>

      {!hasData ? (
        <div className="flex-1 flex items-center justify-center">
          <span className="text-xs" style={{ color: colors.textDim }}>
            {emptyLabel ?? 'No data'}
          </span>
        </div>
      ) : (
        <div className="flex-1 flex flex-col gap-1 min-h-0" style={{ minHeight: 120 }}>
          {/* Bars */}
          <div className="flex items-end gap-1 flex-1">
            {dates.map((date, i) => {
              const r = readings[i];
              const v = r?.value ?? null;
              const isToday = date === today;
              const heightPct = v !== null ? (v / maxValue) * 100 : 0;
              const color = v !== null ? barColor(v, date) : colors.bgElevated;
              // Tooltip includes source when there was a conflict that day
              const tooltipParts = [
                shortDateLabel(date),
                v !== null
                  ? `${Math.round(v)}${unit ? ' ' + unit : ''}`
                  : 'No data',
                r?.hasConflict
                  ? `source: ${adapterDisplayName(r.adapter_id)}`
                  : null,
              ].filter(Boolean);

              return (
                <div
                  key={date}
                  className="flex-1 flex flex-col items-center justify-end"
                  title={tooltipParts.join(' — ')}
                >
                  <div
                    className="w-full rounded-t-sm"
                    style={{
                      height: `${heightPct}%`,
                      minHeight: v !== null ? 4 : 0,
                      background: color,
                      opacity: isToday ? 1 : 0.72,
                      outline: isToday ? `1.5px solid ${color}` : 'none',
                      outlineOffset: 1,
                    }}
                  />
                </div>
              );
            })}
          </div>

          {/* X-axis labels — suppress alternating labels when > 10 bars */}
          <div className="flex gap-1">
            {dates.map((date, i) => {
              const suppress = dates.length > 10 && i % 2 !== 0 && i !== dates.length - 1;
              return (
                <div
                  key={date}
                  className="flex-1 text-center"
                  style={{
                    fontSize: 9,
                    color: date === today ? healthColor : colors.textDim,
                    fontWeight: date === today ? 600 : 400,
                    opacity: suppress ? 0 : 1,
                  }}
                >
                  {shortDateLabel(date)}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Sleep score color ──────────────────────────────────────────────

function sleepScoreColor(score: number): string {
  if (score >= 80) return colors.statusGreen;
  if (score >= 60) return colors.statusAmber;
  return colors.statusRed;
}

// ── Date range presets ─────────────────────────────────────────────

type RangePreset = '7' | '14' | '30' | 'custom';

const RANGE_PRESETS: { key: Exclude<RangePreset, 'custom'>; label: string; days: number }[] = [
  { key: '7', label: 'Last 7 days', days: 7 },
  { key: '14', label: '14 days', days: 14 },
  { key: '30', label: '30 days', days: 30 },
];

// ── Metrics toggle config ──────────────────────────────────────────

const METRIC_TOGGLES: { key: MetricKey; label: string }[] = [
  { key: 'steps', label: 'Steps' },
  { key: 'sleep_score', label: 'Sleep' },
  { key: 'resting_heart_rate', label: 'Heart Rate' },
  { key: 'hrv', label: 'HRV' },
];

// ── Empty state ────────────────────────────────────────────────────

function EmptyState(): ReactNode {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 64, height: 64, background: `${healthColor}20` }}
      >
        <HeartIcon className="w-8 h-8" style={{ color: healthColor }} />
      </div>
      <div className="text-center">
        <p className="text-sm font-medium mb-1" style={{ color: colors.textMuted }}>
          No health data found
        </p>
        <p style={{ fontSize: 12, color: colors.textDim }}>
          Connect an Oura Ring or Apple Health source to see metrics here.
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

  // ── Date range state ──────────────────────────────────────────────

  // Initialise from URL so a direct link with dateFrom/dateTo shows custom mode.
  const [rangePreset, setRangePreset] = useState<RangePreset>(
    search.dateFrom ? 'custom' : '7',
  );

  // Bug fix: keep rangePreset in sync when the URL changes via browser back/forward.
  useEffect(() => {
    setRangePreset(search.dateFrom ? 'custom' : '7');
  }, [search.dateFrom]);

  const effectiveRange = useMemo((): { from: string; to: string } => {
    if (search.dateFrom && search.dateTo) return { from: search.dateFrom, to: search.dateTo };
    const preset = RANGE_PRESETS.find(p => p.key === rangePreset);
    return dateRange(preset?.days ?? 7);
  }, [rangePreset, search.dateFrom, search.dateTo]);

  // Custom date inputs track effectiveRange so they stay current when the
  // user switches between presets and then re-opens the custom panel.
  const [customFrom, setCustomFrom] = useState(effectiveRange.from);
  const [customTo, setCustomTo] = useState(effectiveRange.to);

  useEffect(() => {
    setCustomFrom(effectiveRange.from);
    setCustomTo(effectiveRange.to);
  }, [effectiveRange]);

  function setPreset(preset: RangePreset): void {
    setRangePreset(preset);
    if (preset !== 'custom') {
      void navigate({ to: '/health', search: {} });
    }
  }

  function applyCustomRange(): void {
    void navigate({
      to: '/health',
      search: { dateFrom: customFrom, dateTo: customTo },
    });
  }

  const isCustom = rangePreset === 'custom';

  // ── Metrics visibility toggle ─────────────────────────────────────

  const [enabledMetrics, setEnabledMetrics] = useState<Set<MetricKey>>(
    () => new Set<MetricKey>(['steps', 'sleep_score', 'resting_heart_rate', 'hrv']),
  );

  function toggleMetric(key: MetricKey): void {
    setEnabledMetrics(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        if (next.size > 1) next.delete(key); // always keep at least one visible
      } else {
        next.add(key);
      }
      return next;
    });
  }

  // ── Data ─────────────────────────────────────────────────────────
  //
  // Fetch up to 5000 chunks once (enough for ~14 months × 4 metric types per day)
  // and filter client-side. This keeps date range changes instant without
  // additional API round-trips.

  const { data, isLoading } = useQuery({
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
    () =>
      allDates.map(
        d =>
          dayMap.get(d) ?? {
            date: d,
            steps: null,
            sleep_score: null,
            resting_heart_rate: null,
            hrv: null,
          },
      ),
    [allDates, dayMap],
  );

  // Steps and sleep trends are derived from the selected date window.
  const stepsTrend = useMemo(() => latestValue(orderedBuckets, 'steps'), [orderedBuckets]);
  const sleepTrend = useMemo(() => latestValue(orderedBuckets, 'sleep_score'), [orderedBuckets]);

  // HR and HRV trends use all available data, not just the range window.
  // These metrics update slowly (days/weeks), so a narrow 7-day window
  // often contains too few data points for a meaningful trend baseline.
  const allBuckets = useMemo(
    () => Array.from(aggregateByDay(allMetrics).values()),
    [allMetrics],
  );
  const hrTrend = useMemo(() => latestValue(allBuckets, 'resting_heart_rate'), [allBuckets]);
  const hrvTrend = useMemo(() => latestValue(allBuckets, 'hrv'), [allBuckets]);

  const sources = useMemo(() => sourcesUsed(allMetrics), [allMetrics]);
  const hasAnyData = allMetrics.length > 0;

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: colors.bgBase }}>
      {/* ── Toolbar ── */}
      <div
        className="flex items-center gap-3 px-5 py-2.5 shrink-0 flex-wrap"
        style={{ borderBottom: `1px solid ${colors.border}`, background: colors.bgSurface }}
      >
        <span className="text-sm font-semibold" style={{ color: colors.textPrimary }}>
          Health
        </span>

        {/* Metrics selector — toggle which metric cards/charts are visible */}
        <div className="flex items-center gap-1">
          {METRIC_TOGGLES.map(({ key, label }) => {
            const on = enabledMetrics.has(key);
            return (
              <button
                key={key}
                onClick={() => toggleMetric(key)}
                className="px-2.5 py-1 rounded text-xs font-medium transition-colors"
                style={{
                  background: on ? `${healthColor}20` : colors.bgElevated,
                  color: on ? healthColor : colors.textDim,
                  border: `1px solid ${on ? `${healthColor}50` : colors.border}`,
                }}
                title={on ? `Hide ${label}` : `Show ${label}`}
              >
                {label}
              </button>
            );
          })}
        </div>

        <div className="flex-1" />

        {/* Source badges — one per connected adapter */}
        {sources.length > 0 && (
          <div className="flex items-center gap-1.5">
            {sources.map(s => (
              <span
                key={s}
                className="px-2 py-0.5 rounded text-xs font-medium"
                style={{
                  background: `${healthColor}18`,
                  color: healthColor,
                  border: `1px solid ${healthColor}30`,
                }}
              >
                {s}
              </span>
            ))}
          </div>
        )}

        {/* Date range picker */}
        <div
          className="flex items-center rounded-lg gap-0.5"
          style={{ background: colors.bgElevated, padding: 2 }}
        >
          {RANGE_PRESETS.map(preset => (
            <button
              key={preset.key}
              onClick={() => setPreset(preset.key)}
              className="px-3 py-1 rounded-md transition-colors"
              style={{
                fontSize: 11,
                fontWeight: 500,
                background: rangePreset === preset.key ? colors.bgSurface : 'transparent',
                color: rangePreset === preset.key ? colors.textPrimary : colors.textDim,
                boxShadow: rangePreset === preset.key ? '0 1px 2px rgba(0,0,0,0.3)' : 'none',
              }}
            >
              {preset.label}
            </button>
          ))}
          <button
            onClick={() => setPreset('custom')}
            className="px-3 py-1 rounded-md transition-colors"
            style={{
              fontSize: 11,
              fontWeight: 500,
              background: isCustom ? colors.bgSurface : 'transparent',
              color: isCustom ? colors.textPrimary : colors.textDim,
              boxShadow: isCustom ? '0 1px 2px rgba(0,0,0,0.3)' : 'none',
            }}
          >
            Custom
          </button>
        </div>
      </div>

      {/* Custom date range inputs */}
      {isCustom && (
        <div
          className="flex items-center gap-2 px-5 py-2 shrink-0"
          style={{ borderBottom: `1px solid ${colors.border}`, background: colors.bgSurface }}
        >
          <span className="text-xs" style={{ color: colors.textDim }}>From</span>
          <input
            type="date"
            value={customFrom}
            onChange={e => setCustomFrom(e.target.value)}
            className="rounded px-2 py-1 text-xs outline-none"
            style={{
              background: colors.bgElevated,
              color: colors.textPrimary,
              border: `1px solid ${colors.border}`,
            }}
          />
          <span className="text-xs" style={{ color: colors.textDim }}>to</span>
          <input
            type="date"
            value={customTo}
            onChange={e => setCustomTo(e.target.value)}
            className="rounded px-2 py-1 text-xs outline-none"
            style={{
              background: colors.bgElevated,
              color: colors.textPrimary,
              border: `1px solid ${colors.border}`,
            }}
          />
          <button
            onClick={applyCustomRange}
            className="px-3 py-1 rounded text-xs font-medium transition-opacity hover:opacity-75"
            style={{ background: healthColor, color: '#000' }}
          >
            Apply
          </button>
        </div>
      )}

      {/* ── Body ── */}
      {isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <div
            className="w-6 h-6 rounded-full border-2 animate-spin"
            style={{
              borderColor: `${healthColor} transparent transparent transparent`,
            }}
          />
        </div>
      ) : !hasAnyData ? (
        <EmptyState />
      ) : (
        <div className="flex-1 flex flex-col gap-4 p-5 overflow-y-auto">
          {/* ── Metric cards ── */}
          <div className="flex gap-4">
            {enabledMetrics.has('steps') && (
              <MetricCard
                label="Steps"
                trend={stepsTrend}
                unit="steps"
                goal={STEP_GOAL}
                formatValue={v => v.toLocaleString()}
              />
            )}
            {enabledMetrics.has('sleep_score') && (
              <MetricCard
                label="Sleep Score"
                trend={sleepTrend}
                unit="/ 100"
                formatValue={v => String(Math.round(v))}
              />
            )}
            {enabledMetrics.has('resting_heart_rate') && (
              <MetricCard
                label="Resting HR"
                trend={hrTrend}
                unit="bpm"
                lowerIsBetter
              />
            )}
            {enabledMetrics.has('hrv') && (
              <MetricCard
                label="HRV"
                trend={hrvTrend}
                unit="ms"
              />
            )}
          </div>

          {/* ── Primary charts: Steps + Sleep ── */}
          {(enabledMetrics.has('steps') || enabledMetrics.has('sleep_score')) && (
            <div className="flex gap-4" style={{ minHeight: 200 }}>
              {enabledMetrics.has('steps') && (
                <BarChart
                  title={`Daily Steps — Last ${allDates.length} Days`}
                  dates={allDates}
                  readings={orderedBuckets.map(b => b.steps)}
                  barColor={() => stepsColor}
                  todayKey={today}
                  unit="steps"
                  emptyLabel="No step data in this range"
                />
              )}
              {enabledMetrics.has('sleep_score') && (
                <BarChart
                  title={`Sleep Score — Last ${allDates.length} Days`}
                  dates={allDates}
                  readings={orderedBuckets.map(b => b.sleep_score)}
                  barColor={v => sleepScoreColor(v)}
                  todayKey={today}
                  unit="score"
                  emptyLabel="No sleep data in this range"
                />
              )}
            </div>
          )}

          {/* ── Secondary charts: HRV + Resting HR ── */}
          {(enabledMetrics.has('hrv') || enabledMetrics.has('resting_heart_rate')) && (
            <div className="flex gap-4" style={{ minHeight: 180 }}>
              {enabledMetrics.has('hrv') && (
                <BarChart
                  title={`HRV — Last ${allDates.length} Days`}
                  dates={allDates}
                  readings={orderedBuckets.map(b => b.hrv)}
                  barColor={() => healthColor}
                  todayKey={today}
                  unit="ms"
                  emptyLabel="No HRV data in this range"
                />
              )}
              {enabledMetrics.has('resting_heart_rate') && (
                <BarChart
                  title={`Resting Heart Rate — Last ${allDates.length} Days`}
                  dates={allDates}
                  readings={orderedBuckets.map(b => b.resting_heart_rate)}
                  barColor={() => '#EC4899'}
                  todayKey={today}
                  unit="bpm"
                  emptyLabel="No HR data in this range"
                />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
