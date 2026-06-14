import { useQuery } from '@tanstack/react-query';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { useState, useMemo } from 'react';
import type { ReactNode } from 'react';
import { MapPinIcon } from '@heroicons/react/24/outline';
import {
  PageHeader,
  MapCanvas, ActivityTimeline,
} from '@tinkermonkey/heimdall-ui';
import type { MapPin, HeatmapDataPoint, ActivityEvent } from '@tinkermonkey/heimdall-ui';
import { FilterDropdown } from '../components/FilterDropdown';
import { fetchChunks } from '../api/client';
import { getDomainColor, getDomainColorWithAlpha } from '../lib/designTokens';
import type { ChunkResponse } from '../types/api';

const locationColor = getDomainColor('location');

// ── Location metadata ──────────────────────────────────────────────

interface LocationMeta {
  location_id: string;
  lat: number;
  lng: number;
  place_name: string | null;
  locality: string | null;
  country: string | null;
  arrival_date: string | null;
  departure_date: string | null;
  duration_minutes: number | null;
  source_type: string;
  date_first_observed: string | null;
}

function extractLocationMeta(dm: Record<string, unknown>): LocationMeta | null {
  const lat =
    typeof dm.latitude === 'number' ? dm.latitude :
    typeof dm.lat === 'number' ? dm.lat : null;
  const lng =
    typeof dm.longitude === 'number' ? dm.longitude :
    typeof dm.lng === 'number' ? dm.lng : null;
  if (lat === null || lng === null) return null;

  return {
    location_id: typeof dm.location_id === 'string' ? dm.location_id : '',
    lat,
    lng,
    place_name: typeof dm.place_name === 'string' ? dm.place_name : null,
    locality: typeof dm.locality === 'string' ? dm.locality : null,
    country: typeof dm.country === 'string' ? dm.country : null,
    arrival_date: typeof dm.arrival_date === 'string' ? dm.arrival_date : null,
    departure_date: typeof dm.departure_date === 'string' ? dm.departure_date : null,
    duration_minutes: typeof dm.duration_minutes === 'number' ? dm.duration_minutes : null,
    source_type: typeof dm.source_type === 'string' ? dm.source_type : 'location',
    date_first_observed: typeof dm.date_first_observed === 'string' ? dm.date_first_observed : null,
  };
}

// ── Visit ──────────────────────────────────────────────────────────

interface Visit {
  chunk_hash: string;
  source_id: string;
  meta: LocationMeta;
  display_name: string;
  place_key: string;
}

function makeVisit(chunk: ChunkResponse): Visit | null {
  if (!chunk.domain_metadata) return null;
  const meta = extractLocationMeta(chunk.domain_metadata);
  if (!meta) return null;

  const display_name =
    meta.place_name ??
    (meta.locality
      ? meta.country ? `${meta.locality}, ${meta.country}` : meta.locality
      : null) ??
    `${meta.lat.toFixed(4)}, ${meta.lng.toFixed(4)}`;

  const place_key =
    meta.place_name ??
    `${Math.round(meta.lat * 1000) / 1000},${Math.round(meta.lng * 1000) / 1000}`;

  return {
    chunk_hash: chunk.chunk_hash,
    source_id: chunk.lineage.source_id,
    meta,
    display_name,
    place_key,
  };
}

// ── Place group ────────────────────────────────────────────────────

const PLACE_COLORS = [
  '#6366F1', '#06B6D4', '#10B981', '#F59E0B',
  '#F43F5E', '#A855F7', '#EC4899', '#14B8A6',
  '#3B82F6', '#F97316',
];

function placeColor(idx: number): string {
  return PLACE_COLORS[idx % PLACE_COLORS.length];
}

interface PlaceGroup {
  key: string;
  display_name: string;
  lat: number;
  lng: number;
  visits: Visit[];
  color: string;
}

function groupByPlace(visits: Visit[], colorMap?: Map<string, string>): PlaceGroup[] {
  const map = new Map<string, PlaceGroup>();
  let colorIdx = 0;
  for (const v of visits) {
    if (!map.has(v.place_key)) {
      const color = colorMap?.get(v.place_key) ?? placeColor(colorIdx++);
      map.set(v.place_key, {
        key: v.place_key,
        display_name: v.display_name,
        lat: v.meta.lat,
        lng: v.meta.lng,
        visits: [],
        color,
      });
    }
    map.get(v.place_key)?.visits.push(v);
  }
  return Array.from(map.values());
}

// ── Date range ─────────────────────────────────────────────────────

type DateRange = '7d' | '30d' | '90d' | 'all';

const DATE_RANGE_LABELS: Record<DateRange, string> = {
  '7d': 'Last 7 days',
  '30d': 'Last 30 days',
  '90d': 'Last 90 days',
  'all': 'All time',
};

function getCutoff(range: DateRange): string | null {
  if (range === 'all') return null;
  const days = range === '7d' ? 7 : range === '30d' ? 30 : 90;
  return new Date(Date.now() - days * 86_400_000).toISOString();
}

function formatDuration(minutes: number | null): string | null {
  if (minutes === null) return null;
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function formatVisitDate(isoDate: string | null): string {
  if (!isoDate) return 'Unknown date';
  try {
    const d = new Date(isoDate);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return isoDate;
  }
}

// ── LocationPage ───────────────────────────────────────────────────

export default function LocationPage(): ReactNode {
  const navigate = useNavigate();
  const { place_key: selectedKey, range } = useSearch({ from: '/location' });
  const dateRange: DateRange = (range as DateRange | undefined) ?? '30d';

  const [showHeatmap, setShowHeatmap] = useState(false);

  const chunksQuery = useQuery({
    queryKey: ['chunks', 'location'],
    queryFn: () => fetchChunks({ domain: 'location', limit: 1000 }),
    staleTime: 60_000,
  });

  const allVisits = useMemo((): Visit[] => {
    const chunks = chunksQuery.data?.chunks ?? [];
    return chunks.flatMap(c => {
      const v = makeVisit(c);
      return v ? [v] : [];
    });
  }, [chunksQuery.data]);

  const colorMap = useMemo((): Map<string, string> => {
    const m = new Map<string, string>();
    groupByPlace(allVisits).forEach(p => m.set(p.key, p.color));
    return m;
  }, [allVisits]);

  const cutoff = useMemo(() => getCutoff(dateRange), [dateRange]);

  const filteredVisits = useMemo((): Visit[] => {
    if (!cutoff) return allVisits;
    return allVisits.filter(v => {
      const date = v.meta.arrival_date ?? v.meta.date_first_observed;
      return date != null && date >= cutoff;
    });
  }, [allVisits, cutoff]);

  const filteredPlaces = useMemo(
    () => groupByPlace(filteredVisits, colorMap),
    [filteredVisits, colorMap],
  );

  // Timeline: filtered visits sorted most-recent first
  const timelineVisits = useMemo((): Visit[] => {
    return [...filteredVisits].sort((a, b) => {
      const da = a.meta.arrival_date ?? a.meta.date_first_observed ?? '';
      const db = b.meta.arrival_date ?? b.meta.date_first_observed ?? '';
      return db.localeCompare(da);
    });
  }, [filteredVisits]);

  // Available source types for place type filter
  const sourceTypes = useMemo(() => {
    const types = new Set<string>();
    for (const v of allVisits) types.add(v.meta.source_type);
    return Array.from(types).sort();
  }, [allVisits]);

  const [placeTypeFilter, setPlaceTypeFilter] = useState<string[]>([]);

  const visiblePlaces = useMemo(() => {
    if (placeTypeFilter.length === 0) return filteredPlaces;
    return filteredPlaces.filter(p =>
      p.visits.some(v => placeTypeFilter.includes(v.meta.source_type)),
    );
  }, [filteredPlaces, placeTypeFilter]);

  // Map pins from visible places
  const mapPins = useMemo((): MapPin[] => {
    return visiblePlaces.map(place => ({
      id: place.key,
      lat: place.lat,
      lng: place.lng,
      label: place.display_name,
    }));
  }, [visiblePlaces]);

  // Heatmap data from all visits
  const heatmapData = useMemo((): HeatmapDataPoint[] => {
    return filteredVisits.map(v => ({
      lat: v.meta.lat,
      lng: v.meta.lng,
      value: v.meta.duration_minutes ?? 1,
    }));
  }, [filteredVisits]);

  // ActivityTimeline events from timeline visits
  const timelineEvents = useMemo((): ActivityEvent[] => {
    return timelineVisits.map(v => {
      const dur = formatDuration(v.meta.duration_minutes);
      const date = v.meta.arrival_date ?? v.meta.date_first_observed;
      return {
        id: v.chunk_hash,
        type: 'create' as const,
        subject: v.display_name,
        timestamp: date ?? new Date().toISOString(),
        meta: [formatVisitDate(date), dur].filter(Boolean).join(' · '),
        onClick: () => handleSelectVisit(v),
      };
    });
  }, [timelineVisits, colorMap]);

  function setSelectedKey(key: string | undefined): void {
    void navigate({ to: '/location', search: { place_key: key, range: dateRange } });
  }

  function setDateRange(r: DateRange): void {
    void navigate({ to: '/location', search: { place_key: selectedKey, range: r } });
  }

  function handleSelectPlace(pinId: string | null): void {
    setSelectedKey(pinId === selectedKey ? undefined : (pinId ?? undefined));
  }

  function handleSelectVisit(visit: Visit): void {
    setSelectedKey(selectedKey === visit.place_key ? undefined : visit.place_key);
  }

  const totalVisits = allVisits.length;

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
      <PageHeader
        eyebrow="Domains"
        title="Location"
        subtitle="Place visits and location history"
      />

      {/* ── Body: left panel + map ── */}
      <div className="flex-1 flex overflow-hidden">
        {/* ── Left panel: ActivityTimeline + filters ── */}
        <div
          className="flex flex-col h-full shrink-0 overflow-hidden"
          style={{ width: 300, borderRight: `1px solid rgb(var(--canvas-border))`, background: 'rgb(var(--canvas-surface))' }}
        >
          {/* Panel header */}
          <div
            className="flex items-center gap-2 shrink-0 px-4"
            style={{ height: 52, borderBottom: `1px solid rgb(var(--canvas-border))` }}
          >
            <span
              className="font-semibold flex-1"
              style={{ fontSize: 13, color: 'rgb(var(--canvas-fg-1))' }}
            >
              Recent Visits
            </span>
            {!chunksQuery.isLoading && totalVisits > 0 && (
              <span className="text-[11px]" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                {totalVisits.toLocaleString()} total
              </span>
            )}
          </div>

          {/* Filters */}
          <div
            className="flex items-center gap-2 px-4 py-2 shrink-0"
            style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}
          >
            <FilterDropdown
              mode="radio"
              value={[dateRange]}
              onChange={vals => setDateRange((vals[0] as DateRange) ?? '30d')}
            >
              <FilterDropdown.Trigger
                label="Range"
                summary={DATE_RANGE_LABELS[dateRange]}
              />
              <FilterDropdown.Panel>
                <FilterDropdown.Section title="Date range">
                  {(Object.entries(DATE_RANGE_LABELS) as [DateRange, string][]).map(([key, label]) => (
                    <FilterDropdown.Radio key={key} value={key} label={label} />
                  ))}
                </FilterDropdown.Section>
              </FilterDropdown.Panel>
            </FilterDropdown>

            {sourceTypes.length > 1 && (
              <FilterDropdown
                mode="checkbox"
                value={placeTypeFilter}
                onChange={setPlaceTypeFilter}
              >
                <FilterDropdown.Trigger
                  label="Type"
                  summary={placeTypeFilter.length === 0 ? 'All' : `${placeTypeFilter.length} types`}
                />
                <FilterDropdown.Panel>
                  <FilterDropdown.Section title="Source type">
                    {sourceTypes.map(t => (
                      <FilterDropdown.Checkbox key={t} value={t} label={t.replace(/_/g, ' ')} />
                    ))}
                  </FilterDropdown.Section>
                </FilterDropdown.Panel>
              </FilterDropdown>
            )}
          </div>

          {/* Timeline */}
          <div className="flex-1 overflow-y-auto p-3">
            {chunksQuery.isLoading ? (
              <div className="space-y-2">
                {[1, 2, 3, 4, 5].map(i => (
                  <div
                    key={i}
                    className="animate-pulse rounded"
                    style={{ height: 56, background: 'rgb(var(--canvas-bg-2))' }}
                  />
                ))}
              </div>
            ) : timelineVisits.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 gap-3">
                <div
                  className="flex items-center justify-center rounded-2xl"
                  style={{ width: 40, height: 40, background: getDomainColorWithAlpha('location', '18') }}
                >
                  <MapPinIcon className="w-5 h-5" style={{ color: locationColor }} />
                </div>
                <span className="text-xs text-center" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                  {allVisits.length === 0
                    ? 'No location visits ingested yet'
                    : `No visits in the ${DATE_RANGE_LABELS[dateRange].toLowerCase()}`}
                </span>
              </div>
            ) : (
              <ActivityTimeline
                events={timelineEvents}
                emptyState="No visits found"
              />
            )}
          </div>

          {!chunksQuery.isLoading && timelineVisits.length > 0 && (
            <div
              className="shrink-0 px-4 py-2"
              style={{ borderTop: `1px solid rgb(var(--canvas-border))` }}
            >
              <span className="text-[11px]" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
                {timelineVisits.length.toLocaleString()}{' '}
                {timelineVisits.length === 1 ? 'visit' : 'visits'}
                {dateRange !== 'all' && ` · ${DATE_RANGE_LABELS[dateRange]}`}
              </span>
            </div>
          )}
        </div>

        {/* ── Map area ── */}
        <div className="flex-1 flex flex-col overflow-hidden" style={{ minWidth: 0 }}>
          {/* Map toolbar */}
          <div
            className="flex items-center gap-3 shrink-0 px-4"
            style={{ height: 48, background: 'rgb(var(--canvas-surface))', borderBottom: `1px solid rgb(var(--canvas-border))` }}
          >
            <span className="flex-1 text-sm font-semibold" style={{ color: 'rgb(var(--canvas-fg-1))' }}>
              {visiblePlaces.length} {visiblePlaces.length === 1 ? 'place' : 'places'}
            </span>
            {/* Heatmap overlay toggle */}
            <button
              onClick={() => setShowHeatmap(h => !h)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors"
              style={{
                background: showHeatmap ? getDomainColorWithAlpha('location', '20') : 'rgb(var(--canvas-bg-2))',
                color: showHeatmap ? locationColor : 'rgb(var(--canvas-fg-2))',
                border: `1px solid ${showHeatmap ? getDomainColorWithAlpha('location', '40') : 'rgb(var(--canvas-border))'}`,
              }}
            >
              <span style={{ fontSize: 10 }}>⬛</span>
              Heatmap
            </button>
          </div>

          {/* MapCanvas */}
          {chunksQuery.isLoading ? (
            <div
              className="flex-1 flex items-center justify-center"
              style={{ background: 'rgb(var(--canvas-bg))' }}
            >
              <div
                className="w-6 h-6 rounded-full border-2 animate-spin"
                style={{ borderColor: `${locationColor} transparent transparent transparent` }}
              />
            </div>
          ) : chunksQuery.isError ? (
            <div
              className="flex-1 flex items-center justify-center"
            >
              <span className="text-sm" style={{ color: 'rgb(var(--status-error))' }}>
                Failed to load location data
              </span>
            </div>
          ) : showHeatmap && heatmapData.length > 0 ? (
            <MapCanvas
              mode="heatmap"
              heatmapData={heatmapData}
              heatmapColor={locationColor}
              style={{ flex: 1 }}
            />
          ) : (
            <MapCanvas
              mode="pins"
              pins={mapPins}
              selectedPinId={selectedKey ?? undefined}
              onSelectPin={handleSelectPlace}
              style={{ flex: 1 }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
