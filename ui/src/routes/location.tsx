import { useQuery } from '@tanstack/react-query';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { useState, useMemo } from 'react';
import type { ReactNode } from 'react';
import { MapPinIcon } from '@heroicons/react/24/outline';
import { fetchChunks } from '../api/client';
import { colors, getDomainColor } from '../lib/designTokens';
import type { ChunkResponse } from '../types/api';

const locationColor = getDomainColor('location'); // #14B8A6

// ── Color palette for place markers ───────────────────────────────

const PLACE_COLORS = [
  '#6366F1', '#06B6D4', '#10B981', '#F59E0B',
  '#F43F5E', '#A855F7', '#EC4899', '#14B8A6',
  '#3B82F6', '#F97316',
];

function placeColor(idx: number): string {
  return PLACE_COLORS[idx % PLACE_COLORS.length];
}

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
  // Support both latitude/longitude (model fields) and lat/lng (shorthand)
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

  // Group key: place_name if available, else rounded to ~100 m
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

function formatVisitDate(isoDate: string | null): string {
  if (!isoDate) return 'Unknown date';
  try {
    const d = new Date(isoDate);
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return isoDate;
  }
}

function formatDuration(minutes: number | null): string | null {
  if (minutes === null) return null;
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

// ── Mercator projection ────────────────────────────────────────────

function mercatorY(lat: number): number {
  // Clamp to Web Mercator limits to avoid ±Infinity at the poles
  const clamped = Math.max(-85.051129, Math.min(85.051129, lat));
  const rad = (clamped * Math.PI) / 180;
  return Math.log(Math.tan(Math.PI / 4 + rad / 2));
}

// ── Map Canvas ─────────────────────────────────────────────────────

const MAP_W = 1000;
const MAP_H = 600;
const MAP_PAD = 100;

function MapCanvas({
  places,
  selectedKey,
  hoveredKey,
  onSelectPlace,
  onHoverPlace,
}: {
  places: PlaceGroup[];
  selectedKey: string | null;
  hoveredKey: string | null;
  onSelectPlace: (key: string) => void;
  onHoverPlace: (key: string | null) => void;
}): ReactNode {
  const bounds = useMemo(() => {
    if (places.length === 0) return null;

    const lats = places.map(p => p.lat);
    const lngs = places.map(p => p.lng);
    let minLat = Math.min(...lats);
    let maxLat = Math.max(...lats);
    let minLng = Math.min(...lngs);
    let maxLng = Math.max(...lngs);

    // Ensure minimum span (~10 km)
    const MIN_SPAN = 0.1;
    if (maxLat - minLat < MIN_SPAN) {
      const c = (maxLat + minLat) / 2;
      minLat = c - MIN_SPAN / 2;
      maxLat = c + MIN_SPAN / 2;
    }
    if (maxLng - minLng < MIN_SPAN) {
      const c = (maxLng + minLng) / 2;
      minLng = c - MIN_SPAN / 2;
      maxLng = c + MIN_SPAN / 2;
    }

    // 25% padding
    const latPad = (maxLat - minLat) * 0.25;
    const lngPad = (maxLng - minLng) * 0.25;
    const bMinLat = minLat - latPad;
    const bMaxLat = maxLat + latPad;
    const bMinLng = minLng - lngPad;
    const bMaxLng = maxLng + lngPad;

    return {
      bMinLat, bMaxLat, bMinLng, bMaxLng,
      yTop: mercatorY(bMaxLat),
      yBot: mercatorY(bMinLat),
    };
  }, [places]);

  function toSVG(lat: number, lng: number): [number, number] {
    if (!bounds) return [MAP_W / 2, MAP_H / 2];
    const { bMinLng, bMaxLng, yTop, yBot } = bounds;
    const x = MAP_PAD + ((lng - bMinLng) / (bMaxLng - bMinLng)) * (MAP_W - 2 * MAP_PAD);
    const yM = mercatorY(lat);
    const y = MAP_PAD + ((yTop - yM) / (yTop - yBot)) * (MAP_H - 2 * MAP_PAD);
    return [x, y];
  }

  if (places.length === 0) {
    return (
      <div
        className="flex-1 flex flex-col items-center justify-center gap-3"
        style={{ background: '#0D1117', minWidth: 0 }}
      >
        <MapPinIcon className="w-10 h-10" style={{ color: '#1A2A3A' }} />
        <span className="text-xs" style={{ color: '#1A2A3A' }}>No location data for this period</span>
      </div>
    );
  }

  // Grid lines (5 vertical × 4 horizontal)
  const gridLines: ReactNode[] = [];
  for (let i = 0; i <= 5; i++) {
    const x = (i / 5) * MAP_W;
    gridLines.push(<line key={`gv${i}`} x1={x} y1={0} x2={x} y2={MAP_H} stroke="#0F1E35" strokeWidth={1} />);
  }
  for (let i = 0; i <= 4; i++) {
    const y = (i / 4) * MAP_H;
    gridLines.push(<line key={`gh${i}`} x1={0} y1={y} x2={MAP_W} y2={y} stroke="#0F1E35" strokeWidth={1} />);
  }

  return (
    <div className="flex-1 overflow-hidden" style={{ minWidth: 0, background: '#0D1117' }}>
      <svg
        viewBox={`0 0 ${MAP_W} ${MAP_H}`}
        className="w-full h-full"
        preserveAspectRatio="xMidYMid meet"
        style={{ display: 'block' }}
      >
        <defs>
          <radialGradient id="locMapBg" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#0A1628" />
            <stop offset="100%" stopColor="#050A12" />
          </radialGradient>
        </defs>
        <rect width={MAP_W} height={MAP_H} fill="url(#locMapBg)" />
        {gridLines}

        {places.map(place => {
          const [x, y] = toSVG(place.lat, place.lng);
          const isSelected = selectedKey === place.key;
          const isHovered = hoveredKey === place.key;
          const active = isSelected || isHovered;
          const dotR = active ? 9 : 6;
          const pulseR = active ? 22 : 14;

          // Clamp tooltip rect within SVG bounds (horizontal and vertical)
          const tooltipW = 150;
          const tooltipH = 30;
          const rectX = Math.max(4, Math.min(x - tooltipW / 2, MAP_W - tooltipW - 4));
          const rectY = Math.max(4, y - 44);

          return (
            <g
              key={place.key}
              onClick={() => onSelectPlace(place.key)}
              onMouseEnter={() => onHoverPlace(place.key)}
              onMouseLeave={() => onHoverPlace(null)}
              style={{ cursor: 'pointer' }}
            >
              {/* Pulse ring */}
              <circle
                cx={x} cy={y} r={pulseR}
                fill={place.color}
                opacity={active ? 0.22 : 0.1}
              />
              {/* Dot */}
              <circle cx={x} cy={y} r={dotR} fill={place.color} />
              {/* Selection ring */}
              {isSelected && (
                <circle
                  cx={x} cy={y} r={dotR + 4}
                  fill="none"
                  stroke={place.color}
                  strokeWidth={1.5}
                  opacity={0.5}
                />
              )}
              {/* Tooltip on active */}
              {active && (
                <>
                  <rect
                    x={rectX}
                    y={rectY}
                    width={tooltipW}
                    height={tooltipH}
                    rx={4}
                    fill="#111827"
                    opacity={0.92}
                  />
                  <text
                    x={rectX + tooltipW / 2}
                    y={rectY + 11}
                    textAnchor="middle"
                    fill="#F9FAFB"
                    fontSize={10}
                    fontFamily="Inter, sans-serif"
                    fontWeight="600"
                  >
                    {place.display_name.length > 24
                      ? place.display_name.slice(0, 22) + '…'
                      : place.display_name}
                  </text>
                  <text
                    x={rectX + tooltipW / 2}
                    y={rectY + 22}
                    textAnchor="middle"
                    fill="#6B7280"
                    fontSize={9}
                    fontFamily="Inter, sans-serif"
                  >
                    {place.visits.length} {place.visits.length === 1 ? 'visit' : 'visits'}
                  </text>
                </>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ── Visit Entry ────────────────────────────────────────────────────

function VisitEntry({
  visit,
  color,
  visitCount,
  isSelected,
  onClick,
}: {
  visit: Visit;
  color: string;
  visitCount: number;
  isSelected: boolean;
  onClick: () => void;
}): ReactNode {
  const dur = formatDuration(visit.meta.duration_minutes);
  const date = visit.meta.arrival_date ?? visit.meta.date_first_observed;

  return (
    <button
      onClick={onClick}
      className="w-full text-left flex gap-3 transition-colors"
      style={{
        padding: '10px 14px',
        background: isSelected ? `${color}12` : 'transparent',
        borderBottom: '1px solid #1A1A1A',
      }}
    >
      {/* Color dot */}
      <div className="flex flex-col items-center pt-1.5 shrink-0" style={{ width: 20 }}>
        <div
          className="rounded-full shrink-0"
          style={{ width: 10, height: 10, background: color }}
        />
      </div>

      {/* Content */}
      <div className="flex flex-col gap-1 flex-1 min-w-0">
        <span
          className="text-sm font-semibold truncate"
          style={{ color: colors.textPrimary }}
        >
          {visit.display_name}
        </span>
        <div className="flex items-center gap-2">
          <span className="text-[11px]" style={{ color: '#6B7280' }}>
            {formatVisitDate(date)}
          </span>
          {dur && (
            <span className="text-[11px]" style={{ color: '#4B5563' }}>
              {dur}
            </span>
          )}
        </div>
        <span className="text-[11px]" style={{ color }}>
          {visitCount} {visitCount === 1 ? 'visit' : 'visits'} total
        </span>
      </div>
    </button>
  );
}

// ── LocationPage ───────────────────────────────────────────────────

export default function LocationPage(): ReactNode {
  const navigate = useNavigate();
  const { place_key: selectedKey, range } = useSearch({ from: '/location' });
  const dateRange: DateRange = (range as DateRange | undefined) ?? '30d';

  const [hoveredKey, setHoveredKey] = useState<string | null>(null);
  const [showRangeMenu, setShowRangeMenu] = useState(false);

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

  // Build stable color map directly from allVisits so colors don't shift when
  // the filtered subset changes (avoids double-derivation through allPlaces).
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

  // Visit count by place_key within the filtered period
  const visitCountByKey = useMemo((): Map<string, number> => {
    const m = new Map<string, number>();
    for (const p of filteredPlaces) m.set(p.key, p.visits.length);
    return m;
  }, [filteredPlaces]);

  // Timeline: filtered visits sorted most-recent first
  const timelineVisits = useMemo((): Visit[] => {
    return [...filteredVisits].sort((a, b) => {
      const da = a.meta.arrival_date ?? a.meta.date_first_observed ?? '';
      const db = b.meta.arrival_date ?? b.meta.date_first_observed ?? '';
      return db.localeCompare(da);
    });
  }, [filteredVisits]);

  function setSelectedKey(key: string | undefined): void {
    void navigate({ to: '/location', search: { place_key: key, range: dateRange } });
  }

  function setDateRange(r: DateRange): void {
    void navigate({ to: '/location', search: { place_key: selectedKey, range: r } });
  }

  function handleSelectPlace(key: string): void {
    setSelectedKey(selectedKey === key ? undefined : key);
  }

  function handleSelectVisit(visit: Visit): void {
    setSelectedKey(selectedKey === visit.place_key ? undefined : visit.place_key);
  }

  const totalVisits = allVisits.length;

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: colors.bgBase }}>
      {/* ── Topbar ── */}
      <div
        className="flex items-center gap-3 shrink-0 px-5"
        style={{ height: 52, background: '#111111', borderBottom: '1px solid #1A1A1A' }}
      >
        <span className="font-semibold flex-1" style={{ fontSize: 16, color: colors.textPrimary }}>
          Location
        </span>
        {!chunksQuery.isLoading && totalVisits > 0 && (
          <div
            className="flex items-center"
            style={{ background: '#1F2937', borderRadius: 10, padding: '3px 10px' }}
          >
            <span className="text-[11px]" style={{ color: '#6B7280' }}>
              {totalVisits.toLocaleString()} {totalVisits === 1 ? 'visit' : 'visits'}
            </span>
          </div>
        )}
      </div>

      {/* ── Body: map + right panel ── */}
      <div className="flex-1 flex overflow-hidden">
        {/* ── Map ── */}
        {chunksQuery.isLoading ? (
          <div
            className="flex-1 flex items-center justify-center"
            style={{ background: '#0D1117', minWidth: 0 }}
          >
            <div className="animate-pulse text-xs" style={{ color: '#1A2A3A' }}>
              Loading…
            </div>
          </div>
        ) : chunksQuery.isError ? (
          <div
            className="flex-1 flex items-center justify-center"
            style={{ background: '#0D1117', minWidth: 0 }}
          >
            <span className="text-sm" style={{ color: colors.statusRed }}>
              Failed to load location data
            </span>
          </div>
        ) : (
          <MapCanvas
            places={filteredPlaces}
            selectedKey={selectedKey ?? null}
            hoveredKey={hoveredKey}
            onSelectPlace={handleSelectPlace}
            onHoverPlace={setHoveredKey}
          />
        )}

        {/* ── Right panel ── */}
        <div
          className="flex flex-col h-full shrink-0"
          style={{ width: 300, background: '#111111', borderLeft: '1px solid #1A1A1A' }}
        >
          {/* Panel header */}
          <div
            className="flex items-center gap-2 shrink-0 px-4"
            style={{ height: 48, borderBottom: '1px solid #1A1A1A' }}
          >
            <span
              className="font-semibold flex-1"
              style={{ fontSize: 13, color: colors.textPrimary }}
            >
              Recent Visits
            </span>
            {/* Date range dropdown */}
            <div className="relative">
              <button
                onClick={() => setShowRangeMenu(prev => !prev)}
                className="flex items-center gap-1 transition-opacity hover:opacity-75"
                style={{ fontSize: 11, color: '#6B7280' }}
              >
                {DATE_RANGE_LABELS[dateRange]}
                <svg width={10} height={6} viewBox="0 0 10 6" fill="none" aria-hidden>
                  <path d="M1 1l4 4 4-4" stroke="#6B7280" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
              {showRangeMenu && (
                <>
                  {/* Click-away overlay */}
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setShowRangeMenu(false)}
                  />
                  <div
                    className="absolute right-0 top-full mt-1 z-20 flex flex-col overflow-hidden"
                    style={{
                      background: '#1F2937',
                      border: '1px solid #374151',
                      borderRadius: 6,
                      minWidth: 130,
                      boxShadow: '0 4px 16px rgba(0,0,0,0.6)',
                    }}
                  >
                    {(Object.entries(DATE_RANGE_LABELS) as [DateRange, string][]).map(([key, label]) => (
                      <button
                        key={key}
                        onClick={() => { setDateRange(key); setShowRangeMenu(false); }}
                        className="text-left text-xs px-3 py-2 transition-colors hover:bg-[#374151]"
                        style={{ color: dateRange === key ? locationColor : '#D1D5DB' }}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Timeline list */}
          <div className="flex-1 overflow-y-auto">
            {chunksQuery.isLoading ? (
              <div className="flex flex-col">
                {[1, 2, 3, 4, 5].map(i => (
                  <div
                    key={i}
                    className="animate-pulse"
                    style={{ height: 68, borderBottom: '1px solid #1A1A1A', margin: '0 14px' }}
                  />
                ))}
              </div>
            ) : timelineVisits.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 gap-3 px-4">
                <div
                  className="flex items-center justify-center rounded-2xl"
                  style={{ width: 40, height: 40, background: `${locationColor}18` }}
                >
                  <MapPinIcon className="w-5 h-5" style={{ color: locationColor }} />
                </div>
                <span className="text-xs text-center" style={{ color: colors.textDim }}>
                  {allVisits.length === 0
                    ? 'No location visits ingested yet'
                    : `No visits in the ${DATE_RANGE_LABELS[dateRange].toLowerCase()}`}
                </span>
              </div>
            ) : (
              timelineVisits.map(visit => {
                const color = colorMap.get(visit.place_key) ?? locationColor;
                const count = visitCountByKey.get(visit.place_key) ?? 1;
                return (
                  <VisitEntry
                    key={visit.chunk_hash}
                    visit={visit}
                    color={color}
                    visitCount={count}
                    isSelected={selectedKey === visit.place_key}
                    onClick={() => handleSelectVisit(visit)}
                  />
                );
              })
            )}
          </div>

          {/* Footer count */}
          {!chunksQuery.isLoading && timelineVisits.length > 0 && (
            <div
              className="shrink-0 px-4 py-2"
              style={{ borderTop: `1px solid ${colors.border}` }}
            >
              <span className="text-[11px]" style={{ color: colors.textDim }}>
                {timelineVisits.length.toLocaleString()}{' '}
                {timelineVisits.length === 1 ? 'visit' : 'visits'}
                {dateRange !== 'all' && ` · ${DATE_RANGE_LABELS[dateRange]}`}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
