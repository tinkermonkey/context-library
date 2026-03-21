import type { ReactNode } from 'react';
import { useEffect, useRef, useMemo, useState } from 'react';
import { useNavigate, useSearch } from '@tanstack/react-router';
import type { ChunkResponse } from '../types/api';
import type { DomainViewProps } from './registry';
import { Timestamp } from '../components/shared/Timestamp';

/**
 * Health domain metadata structure.
 * Matches the backend HealthMetadata model.
 */
interface HealthMetadata {
  record_id: string;
  health_type: string;
  date: string; // ISO 8601 date (YYYY-MM-DD)
  source_type: string;
  date_first_observed: string;
  // Sleep metrics
  duration_minutes: number | null;
  deep_sleep_minutes: number | null;
  rem_sleep_minutes: number | null;
  light_sleep_minutes: number | null;
  efficiency: number | null;
  breathing_disturbance_index: number | null;
  // Activity metrics
  steps: number | null;
  active_calories: number | null;
  total_calories: number | null;
  calories_kcal: number | null;
  sedentary_minutes: number | null;
  distance_meters: number | null;
  // Heart rate / Cardiovascular metrics
  avg_heart_rate_bpm: number | null;
  max_heart_rate_bpm: number | null;
  min_bpm: number | null;
  resting_heart_rate: number | null;
  avg_hrv: number | null;
  avg_bpm: number | null;
  max_bpm: number | null;
  bpm: number | null;
  // Workout/Activity details
  activity_type: string | null;
  intensity: number | null;
  session_type: string | null;
  // Time-series details
  hour: number | null;
  sample_count: number | null;
  // Physiological metrics
  body_temperature_deviation: number | null;
  avg_spo2: number | null;
  // Scoring/Wellness metrics
  score: number | null;
  // Mindfulness / Journal entries
  mood: string | null;
  notes: string | null;
  context: string | null;
  // User health tags
  tag_text: string | null;
  text: string | null;
  timestamp: string | null;
}

/**
 * Cast domain_metadata to HealthMetadata with safety checks.
 */
function extractHealthMetadata(chunk: ChunkResponse): HealthMetadata | null {
  if (!chunk.domain_metadata) return null;

  const meta = chunk.domain_metadata;

  // Validate required fields
  if (typeof meta.record_id !== 'string' || typeof meta.health_type !== 'string') {
    return null;
  }

  return {
    record_id: meta.record_id as string,
    health_type: meta.health_type as string,
    date: typeof meta.date === 'string' ? meta.date : '',
    source_type: typeof meta.source_type === 'string' ? meta.source_type : '',
    date_first_observed: typeof meta.date_first_observed === 'string' ? meta.date_first_observed : '',
    // Sleep metrics
    duration_minutes: typeof meta.duration_minutes === 'number' ? meta.duration_minutes : null,
    deep_sleep_minutes: typeof meta.deep_sleep_minutes === 'number' ? meta.deep_sleep_minutes : null,
    rem_sleep_minutes: typeof meta.rem_sleep_minutes === 'number' ? meta.rem_sleep_minutes : null,
    light_sleep_minutes: typeof meta.light_sleep_minutes === 'number' ? meta.light_sleep_minutes : null,
    efficiency: typeof meta.efficiency === 'number' ? meta.efficiency : null,
    breathing_disturbance_index: typeof meta.breathing_disturbance_index === 'number' ? meta.breathing_disturbance_index : null,
    // Activity metrics
    steps: typeof meta.steps === 'number' ? meta.steps : null,
    active_calories: typeof meta.active_calories === 'number' ? meta.active_calories : null,
    total_calories: typeof meta.total_calories === 'number' ? meta.total_calories : null,
    calories_kcal: typeof meta.calories_kcal === 'number' ? meta.calories_kcal : null,
    sedentary_minutes: typeof meta.sedentary_minutes === 'number' ? meta.sedentary_minutes : null,
    distance_meters: typeof meta.distance_meters === 'number' ? meta.distance_meters : null,
    // Heart rate / Cardiovascular metrics
    avg_heart_rate_bpm: typeof meta.avg_heart_rate_bpm === 'number' ? meta.avg_heart_rate_bpm : null,
    max_heart_rate_bpm: typeof meta.max_heart_rate_bpm === 'number' ? meta.max_heart_rate_bpm : null,
    min_bpm: typeof meta.min_bpm === 'number' ? meta.min_bpm : null,
    resting_heart_rate: typeof meta.resting_heart_rate === 'number' ? meta.resting_heart_rate : null,
    avg_hrv: typeof meta.avg_hrv === 'number' ? meta.avg_hrv : null,
    avg_bpm: typeof meta.avg_bpm === 'number' ? meta.avg_bpm : null,
    max_bpm: typeof meta.max_bpm === 'number' ? meta.max_bpm : null,
    bpm: typeof meta.bpm === 'number' ? meta.bpm : null,
    // Workout/Activity details
    activity_type: typeof meta.activity_type === 'string' ? meta.activity_type : null,
    intensity: typeof meta.intensity === 'number' ? meta.intensity : null,
    session_type: typeof meta.session_type === 'string' ? meta.session_type : null,
    // Time-series details
    hour: typeof meta.hour === 'number' ? meta.hour : null,
    sample_count: typeof meta.sample_count === 'number' ? meta.sample_count : null,
    // Physiological metrics
    body_temperature_deviation: typeof meta.body_temperature_deviation === 'number' ? meta.body_temperature_deviation : null,
    avg_spo2: typeof meta.avg_spo2 === 'number' ? meta.avg_spo2 : null,
    // Scoring/Wellness metrics
    score: typeof meta.score === 'number' ? meta.score : null,
    // Mindfulness / Journal entries
    mood: typeof meta.mood === 'string' ? meta.mood : null,
    notes: typeof meta.notes === 'string' ? meta.notes : null,
    context: typeof meta.context === 'string' ? meta.context : null,
    // User health tags
    tag_text: typeof meta.tag_text === 'string' ? meta.tag_text : null,
    text: typeof meta.text === 'string' ? meta.text : null,
    timestamp: typeof meta.timestamp === 'string' ? meta.timestamp : null,
  };
}

/**
 * Format a date string as a human-readable day header.
 * Example: 'Friday, March 21 2026'
 */
function formatDayHeader(dateStr: string): string {
  try {
    const date = new Date(dateStr + 'T00:00:00Z');
    const formatter = new Intl.DateTimeFormat('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      timeZone: 'UTC',
    });
    return formatter.format(date);
  } catch {
    return dateStr;
  }
}

/**
 * Format efficiency as a percentage (0-1 -> 0-100%).
 */
function formatEfficiency(efficiency: number | null): string | null {
  if (efficiency === null) return null;
  // Handle both 0-1 and 0-100 ranges
  const value = efficiency > 1 ? efficiency : efficiency * 100;
  return `${Math.round(value)}%`;
}

/**
 * Format distance in meters consistently using metric units.
 * Shows meters for distances < 1 km, kilometers otherwise.
 */
function formatDistance(distanceMeters: number | null): string | null {
  if (distanceMeters === null) return null;
  if (distanceMeters < 1000) {
    return `${Math.round(distanceMeters)} m`;
  }
  const km = distanceMeters / 1000;
  return `${km.toFixed(1)} km`;
}

/**
 * Format duration in minutes to a human-readable string.
 */
function formatDuration(durationMinutes: number | null): string | null {
  if (durationMinutes === null || durationMinutes === 0) return null;
  const hours = Math.floor(durationMinutes / 60);
  const minutes = durationMinutes % 60;
  if (hours > 0 && minutes > 0) {
    return `${hours}h ${minutes}m`;
  } else if (hours > 0) {
    return `${hours}h`;
  } else {
    return `${minutes}m`;
  }
}

/**
 * Format calories with K suffix for thousands.
 */
function formatCalories(calories: number | null): string | null {
  if (calories === null) return null;
  if (calories >= 1000) {
    return `${(calories / 1000).toFixed(1)}K`;
  }
  return Math.round(calories).toString();
}

/**
 * Human-readable label for health types.
 */
function getHealthTypeLabel(healthType: string): string {
  const labels: Record<string, string> = {
    sleep_summary: 'Sleep',
    readiness_summary: 'Readiness',
    activity_summary: 'Activity',
    workout_session: 'Workout',
    heart_rate_series: 'Heart Rate',
    spo2_summary: 'SpO₂',
    mindfulness_session: 'Mindfulness',
    user_health_tag: 'Health Tag',
  };
  return labels[healthType] || healthType;
}

/**
 * Group chunks by health type and date, filtering by date range.
 */
function groupByHealthType(
  chunks: ChunkResponse[],
  dateFrom?: string,
  dateTo?: string,
  filterHealthType?: string
): Map<string, Map<string, ChunkResponse[]>> {
  const grouped = new Map<string, Map<string, ChunkResponse[]>>();

  // Parse date range
  let fromDate: Date | null = null;
  let toDate: Date | null = null;
  if (dateFrom) {
    fromDate = new Date(dateFrom + 'T00:00:00Z');
  }
  if (dateTo) {
    toDate = new Date(dateTo + 'T23:59:59Z');
  }

  // Process each chunk
  for (const chunk of chunks) {
    const metadata = extractHealthMetadata(chunk);
    if (!metadata || !metadata.date || !metadata.health_type) continue;

    // Apply health type filter if specified
    if (filterHealthType && metadata.health_type !== filterHealthType) continue;

    // Apply date range filter
    const chunkDate = new Date(metadata.date + 'T00:00:00Z');
    if (fromDate && chunkDate < fromDate) continue;
    if (toDate && chunkDate > toDate) continue;

    // Ensure health_type group exists
    if (!grouped.has(metadata.health_type)) {
      grouped.set(metadata.health_type, new Map());
    }

    const healthTypeGroup = grouped.get(metadata.health_type)!;

    // Ensure date group exists within health type
    if (!healthTypeGroup.has(metadata.date)) {
      healthTypeGroup.set(metadata.date, []);
    }
    healthTypeGroup.get(metadata.date)!.push(chunk);
  }

  return grouped;
}

/**
 * Render a sleep summary card.
 */
function SleepSummaryCard({ chunk }: { chunk: ChunkResponse }): ReactNode {
  const metadata = extractHealthMetadata(chunk);
  if (!metadata) return null;

  return (
    <div className="border border-gray-200 rounded-lg p-4 mb-4 bg-white hover:shadow-md transition-shadow">
      <div className="grid grid-cols-2 gap-4">
        {metadata.duration_minutes !== null && (
          <div>
            <div className="text-sm text-gray-600">Total Duration</div>
            <div className="text-lg font-semibold text-gray-900">{formatDuration(metadata.duration_minutes)}</div>
          </div>
        )}
        {metadata.deep_sleep_minutes !== null && (
          <div>
            <div className="text-sm text-gray-600">Deep Sleep</div>
            <div className="text-lg font-semibold text-gray-900">{formatDuration(metadata.deep_sleep_minutes)}</div>
          </div>
        )}
        {metadata.rem_sleep_minutes !== null && (
          <div>
            <div className="text-sm text-gray-600">REM Sleep</div>
            <div className="text-lg font-semibold text-gray-900">{formatDuration(metadata.rem_sleep_minutes)}</div>
          </div>
        )}
        {metadata.light_sleep_minutes !== null && (
          <div>
            <div className="text-sm text-gray-600">Light Sleep</div>
            <div className="text-lg font-semibold text-gray-900">{formatDuration(metadata.light_sleep_minutes)}</div>
          </div>
        )}
        {metadata.efficiency !== null && (
          <div>
            <div className="text-sm text-gray-600">Efficiency</div>
            <div className="text-lg font-semibold text-gray-900">{formatEfficiency(metadata.efficiency)}</div>
          </div>
        )}
        {metadata.breathing_disturbance_index !== null && (
          <div>
            <div className="text-sm text-gray-600">Breathing Index</div>
            <div className="text-lg font-semibold text-gray-900">{metadata.breathing_disturbance_index.toFixed(1)}</div>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Render an activity summary card.
 */
function ActivitySummaryCard({ chunk }: { chunk: ChunkResponse }): ReactNode {
  const metadata = extractHealthMetadata(chunk);
  if (!metadata) return null;

  return (
    <div className="border border-gray-200 rounded-lg p-4 mb-4 bg-white hover:shadow-md transition-shadow">
      <div className="grid grid-cols-2 gap-4">
        {metadata.steps !== null && (
          <div>
            <div className="text-sm text-gray-600">Steps</div>
            <div className="text-lg font-semibold text-gray-900">{metadata.steps.toLocaleString()}</div>
          </div>
        )}
        {metadata.active_calories !== null && (
          <div>
            <div className="text-sm text-gray-600">Active Calories</div>
            <div className="text-lg font-semibold text-gray-900">{formatCalories(metadata.active_calories)}</div>
          </div>
        )}
        {metadata.distance_meters !== null && (
          <div>
            <div className="text-sm text-gray-600">Distance</div>
            <div className="text-lg font-semibold text-gray-900">{formatDistance(metadata.distance_meters)}</div>
          </div>
        )}
        {metadata.sedentary_minutes !== null && (
          <div>
            <div className="text-sm text-gray-600">Sedentary Time</div>
            <div className="text-lg font-semibold text-gray-900">{formatDuration(metadata.sedentary_minutes)}</div>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Render a readiness summary card.
 */
function ReadinessSummaryCard({ chunk }: { chunk: ChunkResponse }): ReactNode {
  const metadata = extractHealthMetadata(chunk);
  if (!metadata) return null;

  return (
    <div className="border border-gray-200 rounded-lg p-4 mb-4 bg-white hover:shadow-md transition-shadow">
      {metadata.score !== null && (
        <div className="text-center">
          <div className="text-sm text-gray-600 mb-2">Readiness Score</div>
          <div className="text-5xl font-bold text-blue-600">{Math.round(metadata.score)}</div>
          <div className="text-xs text-gray-500 mt-2">out of 100</div>
        </div>
      )}
    </div>
  );
}

/**
 * Render a workout session card.
 */
function WorkoutSessionCard({ chunk }: { chunk: ChunkResponse }): ReactNode {
  const metadata = extractHealthMetadata(chunk);
  if (!metadata) return null;

  return (
    <div className="border border-gray-200 rounded-lg p-4 mb-4 bg-white hover:shadow-md transition-shadow">
      <div className="mb-3">
        {metadata.activity_type && (
          <h3 className="text-lg font-semibold text-gray-900">{metadata.activity_type}</h3>
        )}
        {metadata.intensity !== null && (
          <div className="text-sm text-gray-600">Intensity: {metadata.intensity.toFixed(1)}</div>
        )}
      </div>
      <div className="grid grid-cols-2 gap-4">
        {metadata.duration_minutes !== null && (
          <div>
            <div className="text-sm text-gray-600">Duration</div>
            <div className="text-lg font-semibold text-gray-900">{formatDuration(metadata.duration_minutes)}</div>
          </div>
        )}
        {metadata.active_calories !== null && (
          <div>
            <div className="text-sm text-gray-600">Calories</div>
            <div className="text-lg font-semibold text-gray-900">{formatCalories(metadata.active_calories)}</div>
          </div>
        )}
        {metadata.avg_heart_rate_bpm !== null && (
          <div>
            <div className="text-sm text-gray-600">Avg Heart Rate</div>
            <div className="text-lg font-semibold text-gray-900">{Math.round(metadata.avg_heart_rate_bpm)} bpm</div>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Render a heart rate series card.
 */
function HeartRateSeriesCard({ chunk }: { chunk: ChunkResponse }): ReactNode {
  const metadata = extractHealthMetadata(chunk);
  if (!metadata) return null;

  return (
    <div className="border border-gray-200 rounded-lg p-4 mb-4 bg-white hover:shadow-md transition-shadow">
      <div className="grid grid-cols-2 gap-4">
        {metadata.avg_heart_rate_bpm !== null && (
          <div>
            <div className="text-sm text-gray-600">Average</div>
            <div className="text-lg font-semibold text-gray-900">{Math.round(metadata.avg_heart_rate_bpm)} bpm</div>
          </div>
        )}
        {metadata.max_heart_rate_bpm !== null && (
          <div>
            <div className="text-sm text-gray-600">Maximum</div>
            <div className="text-lg font-semibold text-gray-900">{Math.round(metadata.max_heart_rate_bpm)} bpm</div>
          </div>
        )}
        {metadata.resting_heart_rate !== null && (
          <div>
            <div className="text-sm text-gray-600">Resting</div>
            <div className="text-lg font-semibold text-gray-900">{Math.round(metadata.resting_heart_rate)} bpm</div>
          </div>
        )}
        {metadata.avg_hrv !== null && (
          <div>
            <div className="text-sm text-gray-600">Heart Rate Variability</div>
            <div className="text-lg font-semibold text-gray-900">{metadata.avg_hrv.toFixed(1)}</div>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Render a SpO2 summary card.
 */
function SpO2SummaryCard({ chunk }: { chunk: ChunkResponse }): ReactNode {
  const metadata = extractHealthMetadata(chunk);
  if (!metadata) return null;

  return (
    <div className="border border-gray-200 rounded-lg p-4 mb-4 bg-white hover:shadow-md transition-shadow">
      {metadata.avg_spo2 !== null && (
        <div className="text-center">
          <div className="text-sm text-gray-600 mb-2">Blood Oxygen Saturation</div>
          <div className="text-5xl font-bold text-green-600">{Math.round(metadata.avg_spo2)}%</div>
        </div>
      )}
    </div>
  );
}

/**
 * Render a mindfulness session card.
 */
function MindfulnessSessionCard({ chunk }: { chunk: ChunkResponse }): ReactNode {
  const metadata = extractHealthMetadata(chunk);
  if (!metadata) return null;

  return (
    <div className="border border-gray-200 rounded-lg p-4 mb-4 bg-white hover:shadow-md transition-shadow">
      {metadata.duration_minutes !== null && (
        <div className="mb-3">
          <div className="text-sm text-gray-600">Duration</div>
          <div className="text-lg font-semibold text-gray-900">{formatDuration(metadata.duration_minutes)}</div>
        </div>
      )}
      {metadata.mood && (
        <div className="mb-3">
          <div className="text-sm text-gray-600">Mood</div>
          <div className="text-lg font-semibold text-gray-900">{metadata.mood}</div>
        </div>
      )}
      {metadata.context && (
        <div className="mb-3">
          <div className="text-sm text-gray-600">Context</div>
          <div className="text-sm text-gray-900">{metadata.context}</div>
        </div>
      )}
      {metadata.notes && (
        <div>
          <div className="text-sm text-gray-600">Notes</div>
          <div className="text-sm text-gray-900 italic">{metadata.notes}</div>
        </div>
      )}
    </div>
  );
}

/**
 * Render a health tag card.
 */
function HealthTagCard({ chunk }: { chunk: ChunkResponse }): ReactNode {
  const metadata = extractHealthMetadata(chunk);
  if (!metadata) return null;

  return (
    <div className="border border-gray-200 rounded-lg p-4 mb-4 bg-white hover:shadow-md transition-shadow">
      {metadata.tag_text && (
        <div className="mb-3">
          <span className="inline-block bg-blue-100 text-blue-900 text-sm font-medium px-3 py-1 rounded-full">
            {metadata.tag_text}
          </span>
        </div>
      )}
      {metadata.text && (
        <div className="mb-2">
          <div className="text-sm text-gray-900">{metadata.text}</div>
        </div>
      )}
      {metadata.timestamp && (
        <div className="text-xs text-gray-500">
          <Timestamp value={metadata.timestamp} granularity="datetime" />
        </div>
      )}
    </div>
  );
}

/**
 * Render the appropriate card component based on health type.
 */
function HealthMetricCard({ chunk, healthType }: { chunk: ChunkResponse; healthType: string }): ReactNode {
  switch (healthType) {
    case 'sleep_summary':
      return <SleepSummaryCard chunk={chunk} />;
    case 'activity_summary':
      return <ActivitySummaryCard chunk={chunk} />;
    case 'readiness_summary':
      return <ReadinessSummaryCard chunk={chunk} />;
    case 'workout_session':
      return <WorkoutSessionCard chunk={chunk} />;
    case 'heart_rate_series':
      return <HeartRateSeriesCard chunk={chunk} />;
    case 'spo2_summary':
      return <SpO2SummaryCard chunk={chunk} />;
    case 'mindfulness_session':
      return <MindfulnessSessionCard chunk={chunk} />;
    case 'user_health_tag':
      return <HealthTagCard chunk={chunk} />;
    default:
      return null;
  }
}

/**
 * Health metrics view for the health domain.
 *
 * Displays health data chunks grouped by metric type with date-range filtering.
 *
 * Features:
 * - Chunks grouped by health_type (sleep, activity, workout, etc.)
 * - Per-type display components with appropriate layouts
 * - Date-range filtering via dateFrom/dateTo URL params
 * - Health type filtering via healthType URL param
 * - Navigation tabs to jump between health type groups
 * - Shareable URLs with filters
 * - Empty state when no data matches filters
 */
export function HealthMetricsView({ sourceId, chunks }: DomainViewProps): ReactNode {
  const navigate = useNavigate();
  const search = useSearch({ from: '/browser/view/$domain/$sourceId' }) as {
    dateFrom?: string;
    dateTo?: string;
    healthType?: string;
  };

  // Local state for inputs during editing
  const [pendingDateFrom, setPendingDateFrom] = useState<string>(search.dateFrom || '');
  const [pendingDateTo, setPendingDateTo] = useState<string>(search.dateTo || '');
  const prevSearchRef = useRef({ dateFrom: search.dateFrom, dateTo: search.dateTo });

  // Sync pending state when URL params change
  // Intentionally sync state from URL on route changes (e.g., browser back/forward).
  // This is safe because we guard with prevSearchRef to avoid cascading renders.
  useEffect(() => {
    if (
      prevSearchRef.current.dateFrom !== search.dateFrom ||
      prevSearchRef.current.dateTo !== search.dateTo
    ) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setPendingDateFrom(search.dateFrom || '');
      setPendingDateTo(search.dateTo || '');
      prevSearchRef.current = { dateFrom: search.dateFrom, dateTo: search.dateTo };
    }
  }, [search.dateFrom, search.dateTo]);

  // Group metrics by health type and date (with optional single-type filter)
  const groupedMetrics = useMemo(
    () => groupByHealthType(chunks, search.dateFrom, search.dateTo, search.healthType),
    [chunks, search.dateFrom, search.dateTo, search.healthType]
  );

  // Get all available health types (for navigation tabs) from unfiltered data
  // This ensures tabs remain visible even when filtering to a single health type
  const allAvailableHealthTypes = useMemo(
    () => Array.from(groupByHealthType(chunks, search.dateFrom, search.dateTo).keys()).sort(),
    [chunks, search.dateFrom, search.dateTo]
  );

  // Get filtered health types (for content display)
  const displayedHealthTypes = Array.from(groupedMetrics.keys()).sort();

  // Handle date range filter application
  const handleApplyFilter = () => {
    navigate({
      to: '.',
      search: (prev: Record<string, unknown>) => ({
        ...prev,
        dateFrom: pendingDateFrom || undefined,
        dateTo: pendingDateTo || undefined,
      }),
    });
  };

  // Handle clear filter
  const handleClearFilter = () => {
    navigate({
      to: '.',
      search: (prev: Record<string, unknown>) => ({
        ...prev,
        dateFrom: undefined,
        dateTo: undefined,
      }),
    });
  };

  // Handle health type tab click
  const handleHealthTypeClick = (healthType: string | null) => {
    navigate({
      to: '.',
      search: (prev: Record<string, unknown>) => ({
        ...prev,
        healthType: healthType || undefined,
      }),
    });
  };

  return (
    <div className="max-w-4xl mx-auto">
      {/* Date range filter controls */}
      <div className="mb-8 p-6 border border-gray-200 rounded-lg bg-gray-50">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Filter by Date Range</h2>
        <div className="flex gap-4 items-end">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              From Date
            </label>
            <input
              type="date"
              value={pendingDateFrom}
              onChange={(e) => setPendingDateFrom(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              To Date
            </label>
            <input
              type="date"
              value={pendingDateTo}
              onChange={(e) => setPendingDateTo(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <button
            onClick={handleApplyFilter}
            className="px-6 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 transition-colors"
          >
            Apply Filter
          </button>
          {(search.dateFrom || search.dateTo) && (
            <button
              onClick={handleClearFilter}
              className="px-6 py-2 bg-gray-300 text-gray-900 text-sm font-medium rounded-md hover:bg-gray-400 transition-colors"
            >
              Clear Filter
            </button>
          )}
        </div>
      </div>

      {/* Health type navigation tabs */}
      {allAvailableHealthTypes.length > 1 && (
        <div className="mb-8 flex flex-wrap gap-2">
          {search.healthType && (
            <button
              onClick={() => handleHealthTypeClick(null)}
              className="px-4 py-2 rounded-md border-2 border-gray-300 text-gray-700 text-sm font-medium hover:border-gray-400 transition-colors"
            >
              All Types
            </button>
          )}
          {allAvailableHealthTypes.map((healthType) => (
            <button
              key={healthType}
              onClick={() => handleHealthTypeClick(healthType)}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                search.healthType === healthType
                  ? 'bg-blue-600 text-white border-2 border-blue-600'
                  : 'border-2 border-gray-300 text-gray-700 hover:border-gray-400'
              }`}
            >
              {getHealthTypeLabel(healthType)}
            </button>
          ))}
        </div>
      )}

      {/* Health metrics grouped by type */}
      {groupedMetrics.size > 0 ? (
        <div>
          {displayedHealthTypes.map((healthType) => {
            const dateGroups = groupedMetrics.get(healthType)!;
            const sortedDates = Array.from(dateGroups.keys()).sort().reverse(); // Reverse for newest first

            return (
              <div key={healthType} className="mb-12">
                {/* Health type header */}
                <h2 className="text-2xl font-bold text-gray-900 mb-4 pb-3 border-b-2 border-blue-200">
                  {getHealthTypeLabel(healthType)}
                </h2>

                {/* Metrics grouped by date */}
                {sortedDates.map((dateKey) => {
                  const dateChunks = dateGroups.get(dateKey)!;
                  return (
                    <div key={dateKey} className="mb-6">
                      {/* Date subheader */}
                      <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wide mb-3">
                        {formatDayHeader(dateKey)}
                      </h3>

                      {/* Metrics for this date */}
                      {dateChunks.map((chunk) => (
                        <HealthMetricCard key={chunk.chunk_hash} chunk={chunk} healthType={healthType} />
                      ))}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="p-8 bg-blue-50 border border-blue-200 rounded-lg text-center">
          <p className="text-blue-900 font-semibold mb-2">No health metrics found</p>
          <p className="text-blue-800 text-sm">
            {search.dateFrom || search.dateTo || search.healthType
              ? 'No health metrics match the selected filters. Try adjusting your filters.'
              : 'No health metrics available for this source.'}
          </p>
        </div>
      )}

      {/* View Raw Chunks link */}
      <div className="mt-8 pt-6 border-t border-gray-200">
        <button
          onClick={() =>
            navigate({
              to: '/browser',
              search: { table: 'chunks', source_id: sourceId },
            })
          }
          className="text-blue-600 hover:underline text-sm bg-none border-none cursor-pointer p-0"
        >
          View Raw Chunks
        </button>
      </div>
    </div>
  );
}
