import { useQuery } from '@tanstack/react-query';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { useMemo } from 'react';
import type { ReactNode } from 'react';
import {
  Icon, PageHeader,
  AssetCard, AssetGrid,
  ActivityTimeline,
  StatTile, StatGrid,
} from '@tinkermonkey/heimdall-ui';
import type { ActivityEvent } from '@tinkermonkey/heimdall-ui';
import { SegmentedControl } from '../components/SegmentedControl';
import { NowPlaying } from '../components/NowPlaying';
import { fetchChunks } from '../api/client';
import { getDomainColor, getDomainColorWithAlpha } from '../lib/designTokens';
import type { ChunkResponse } from '../types/api';

const musicColor = getDomainColor('music');

// ── Artwork gradient palette ───────────────────────────────────────

const ARTWORK_GRADIENTS: [string, string][] = [
  ['#1E1B4B', '#4C1D95'],
  ['#064E3B', '#065F46'],
  ['#7C2D12', '#9A3412'],
  ['#1E3A5F', '#1E40AF'],
  ['#14532D', '#166534'],
  ['#4A1D96', '#7C3AED'],
  ['#831843', '#BE185D'],
  ['#1C1917', '#44403C'],
  ['#0C4A6E', '#0369A1'],
  ['#713F12', '#92400E'],
];

function artworkGradient(title: string, artist: string): [string, string] {
  const key = title + artist;
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) & 0x7fffffff;
  return ARTWORK_GRADIENTS[h % ARTWORK_GRADIENTS.length];
}

// ── Music metadata ─────────────────────────────────────────────────

interface MusicMeta {
  track_title: string;
  artist: string;
  album: string;
  duration: number | null;
  play_count: number | null;
  last_played: string | null;
  genre: string | null;
  year: number | null;
}

function extractMusicMeta(dm: Record<string, unknown>): MusicMeta | null {
  const track_title = typeof dm.track_title === 'string' ? dm.track_title : null;
  const artist = typeof dm.artist === 'string' ? dm.artist : null;
  if (!track_title && !artist) return null;
  return {
    track_title: track_title ?? 'Unknown Track',
    artist: artist ?? 'Unknown Artist',
    album: typeof dm.album === 'string' ? dm.album : '',
    duration: typeof dm.duration === 'number' ? dm.duration : null,
    play_count: typeof dm.play_count === 'number' ? dm.play_count : null,
    last_played: typeof dm.last_played === 'string' ? dm.last_played : null,
    genre: typeof dm.genre === 'string' ? dm.genre : null,
    year: typeof dm.year === 'number' ? dm.year : null,
  };
}

interface Track {
  chunk_hash: string;
  source_id: string;
  meta: MusicMeta;
  gradient: [string, string];
}

function makeTrack(chunk: ChunkResponse): Track | null {
  if (!chunk.domain_metadata || typeof chunk.domain_metadata !== 'object') return null;
  const meta = extractMusicMeta(chunk.domain_metadata as Record<string, unknown>);
  if (!meta) return null;
  return {
    chunk_hash: chunk.chunk_hash,
    source_id: chunk.lineage.source_id,
    meta,
    gradient: artworkGradient(meta.track_title, meta.artist),
  };
}

// ── Format helpers ─────────────────────────────────────────────────

function formatLastPlayed(isoDate: string | null): string {
  if (!isoDate) return '—';
  try {
    const d = new Date(isoDate);
    const diff = Date.now() - d.getTime();
    const days = Math.floor(diff / 86_400_000);
    if (days === 0) return 'Today';
    if (days === 1) return 'Yesterday';
    if (days < 7) return `${days}d ago`;
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return isoDate;
  }
}

// ── Sort ───────────────────────────────────────────────────────────

type SortKey = 'last_played' | 'play_count' | 'title' | 'artist';

function sortTracks(tracks: Track[], key: SortKey): Track[] {
  return [...tracks].sort((a, b) => {
    switch (key) {
      case 'last_played': {
        const da = a.meta.last_played ?? '';
        const db = b.meta.last_played ?? '';
        return db.localeCompare(da);
      }
      case 'play_count':
        return (b.meta.play_count ?? 0) - (a.meta.play_count ?? 0);
      case 'title':
        return a.meta.track_title.localeCompare(b.meta.track_title);
      case 'artist':
        return a.meta.artist.localeCompare(b.meta.artist);
    }
  });
}

// ── View mode ──────────────────────────────────────────────────────

type ViewMode = 'albums' | 'artists' | 'history';

const VIEW_OPTIONS = [
  { value: 'albums', label: 'Albums' },
  { value: 'artists', label: 'Artists' },
  { value: 'history', label: 'Play History' },
];

// ── Album group ────────────────────────────────────────────────────

interface Album {
  title: string;
  artist: string;
  gradient: [string, string];
  trackCount: number;
  lastPlayed: string | null;
}

function buildAlbums(tracks: Track[]): Album[] {
  const map = new Map<string, Album>();
  for (const t of tracks) {
    const key = `${t.meta.album}|||${t.meta.artist}`;
    if (!map.has(key)) {
      map.set(key, {
        title: t.meta.album || t.meta.artist,
        artist: t.meta.artist,
        gradient: artworkGradient(t.meta.album || t.meta.artist, t.meta.artist),
        trackCount: 0,
        lastPlayed: null,
      });
    }
    const album = map.get(key)!;
    album.trackCount++;
    if (t.meta.last_played && (!album.lastPlayed || t.meta.last_played > album.lastPlayed)) {
      album.lastPlayed = t.meta.last_played;
    }
  }
  return Array.from(map.values())
    .sort((a, b) => (b.lastPlayed ?? '').localeCompare(a.lastPlayed ?? ''));
}

// ── Artist group ───────────────────────────────────────────────────

interface Artist {
  name: string;
  trackCount: number;
  albumCount: number;
  gradient: [string, string];
}

function buildArtists(tracks: Track[]): Artist[] {
  const artistAlbums = new Map<string, Set<string>>();
  const artistTracks = new Map<string, number>();
  for (const t of tracks) {
    const a = t.meta.artist;
    if (!artistAlbums.has(a)) artistAlbums.set(a, new Set());
    if (t.meta.album) artistAlbums.get(a)!.add(t.meta.album);
    artistTracks.set(a, (artistTracks.get(a) ?? 0) + 1);
  }
  return Array.from(artistTracks.entries())
    .map(([name, trackCount]) => ({
      name,
      trackCount,
      albumCount: artistAlbums.get(name)?.size ?? 0,
      gradient: artworkGradient(name, name),
    }))
    .sort((a, b) => b.trackCount - a.trackCount);
}

// ── MusicPage ──────────────────────────────────────────────────────

export default function MusicPage(): ReactNode {
  const navigate = useNavigate();
  const { view: viewParam = 'albums' } = useSearch({ from: '/music' });

  const viewMode = viewParam as ViewMode;

  function setViewMode(mode: ViewMode): void {
    void navigate({ to: '/music', search: { view: mode === 'albums' ? undefined : mode } });
  }

  const chunksQuery = useQuery({
    queryKey: ['chunks', 'music'],
    queryFn: () =>
      fetchChunks({
        domain: 'documents',
        metadata_filter: { source_type: 'apple_music' },
        limit: 500,
      }),
    staleTime: 60_000,
  });

  const allTracks = useMemo((): Track[] => {
    const chunks = chunksQuery.data?.chunks ?? [];
    return chunks.flatMap(c => {
      const t = makeTrack(c);
      return t ? [t] : [];
    });
  }, [chunksQuery.data]);

  const recentTracks = useMemo(
    (): Track[] => sortTracks(allTracks, 'last_played').slice(0, 50),
    [allTracks],
  );

  const albums = useMemo(() => buildAlbums(allTracks), [allTracks]);
  const artists = useMemo(() => buildArtists(allTracks), [allTracks]);

  // Stats
  const uniqueArtists = artists.length;
  const uniqueAlbums = albums.length;
  const totalPlays = useMemo(
    () => allTracks.reduce((sum, t) => sum + (t.meta.play_count ?? 0), 0),
    [allTracks],
  );

  // ActivityTimeline events from recent play history
  const timelineEvents = useMemo((): ActivityEvent[] => {
    return recentTracks.map(t => ({
      id: t.chunk_hash,
      type: 'update' as const,
      subject: t.meta.track_title,
      timestamp: t.meta.last_played ?? new Date().toISOString(),
      meta: [t.meta.artist, t.meta.album].filter(Boolean).join(' · '),
    }));
  }, [recentTracks]);

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'rgb(var(--canvas-bg))' }}>
      <PageHeader
        eyebrow="Domains"
        title="Music"
        subtitle="Apple Music library and listening history"
      />
      {/* Equalizer bar animation */}
      <style>{`@keyframes eqBar { from { height: 4px; } to { height: 14px; } }`}</style>

      {/* ── Toolbar ── */}
      <div
        className="flex items-center gap-4 shrink-0 px-5 py-2.5"
        style={{ borderBottom: `1px solid rgb(var(--canvas-border))`, background: 'rgb(var(--canvas-surface))' }}
      >
        <SegmentedControl
          value={viewMode}
          onChange={v => setViewMode(v as ViewMode)}
          options={VIEW_OPTIONS}
        />
        <div className="flex-1" />
        {!chunksQuery.isLoading && allTracks.length > 0 && (
          <span className="text-xs" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
            {allTracks.length.toLocaleString()} tracks
          </span>
        )}
      </div>

      {/* ── Body ── */}
      {chunksQuery.isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <div
            className="w-6 h-6 rounded-full border-2 animate-spin"
            style={{ borderColor: `${musicColor} transparent transparent transparent` }}
          />
        </div>
      ) : chunksQuery.isError ? (
        <div className="flex-1 flex items-center justify-center">
          <span className="text-sm" style={{ color: 'rgb(var(--status-error))' }}>
            Failed to load music library
          </span>
        </div>
      ) : allTracks.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-4">
          <div
            className="flex items-center justify-center rounded-2xl"
            style={{ width: 64, height: 64, background: getDomainColorWithAlpha('music', '20') }}
          >
            <span style={{ color: musicColor }}>
              <Icon name="bell" size={32} />
            </span>
          </div>
          <p className="text-sm" style={{ color: 'rgb(var(--canvas-fg-3))' }}>
            No music tracks ingested yet
          </p>
        </div>
      ) : (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* StatGrid row */}
          <div className="px-5 pt-4 pb-3 shrink-0">
            <StatGrid columns={4}>
              <StatTile label="Tracks" value={String(allTracks.length)} color="rose" />
              <StatTile label="Artists" value={String(uniqueArtists)} color="violet" />
              <StatTile label="Albums" value={String(uniqueAlbums)} color="amber" />
              <StatTile label="Total Plays" value={totalPlays > 0 ? totalPlays.toLocaleString() : '—'} color="cyan" />
            </StatGrid>
          </div>

          {/* Main content area */}
          <div className="flex-1 overflow-hidden flex">
            {/* Primary content by view */}
            <div className="flex-1 overflow-y-auto p-5">
              {viewMode === 'albums' && (
                <AssetGrid columns={5} gap={14}>
                  {albums.map(album => (
                    <AssetCard
                      key={`${album.title}|||${album.artist}`}
                      thumb={{
                        kind: 'cover',
                        gradient: `linear-gradient(135deg, ${album.gradient[0]}, ${album.gradient[1]})`,
                        glyph: 'bell',
                      }}
                      title={album.title}
                      subtitle={album.artist}
                      meta={
                        <span style={{ fontSize: 10, color: 'rgb(var(--canvas-fg-3))' }}>
                          {album.trackCount} {album.trackCount === 1 ? 'track' : 'tracks'}
                          {album.lastPlayed ? ` · ${formatLastPlayed(album.lastPlayed)}` : ''}
                        </span>
                      }
                    />
                  ))}
                </AssetGrid>
              )}

              {viewMode === 'artists' && (
                <AssetGrid columns={5} gap={14}>
                  {artists.map(artist => (
                    <AssetCard
                      key={artist.name}
                      thumb={{
                        kind: 'cover',
                        gradient: `linear-gradient(135deg, ${artist.gradient[0]}, ${artist.gradient[1]})`,
                        glyph: 'user',
                      }}
                      title={artist.name}
                      meta={
                        <span style={{ fontSize: 10, color: 'rgb(var(--canvas-fg-3))' }}>
                          {artist.trackCount} tracks · {artist.albumCount} {artist.albumCount === 1 ? 'album' : 'albums'}
                        </span>
                      }
                    />
                  ))}
                </AssetGrid>
              )}

              {viewMode === 'history' && (
                <div style={{ maxWidth: 640 }}>
                  <ActivityTimeline events={timelineEvents} emptyState="No play history available" />
                </div>
              )}
            </div>

            {/* Right: ActivityTimeline play history (always visible in Albums/Artists views) */}
            {viewMode !== 'history' && (
              <div
                className="shrink-0 flex flex-col overflow-hidden"
                style={{ width: 280, borderLeft: `1px solid rgb(var(--canvas-border))`, background: 'rgb(var(--canvas-surface))' }}
              >
                <div
                  className="px-4 py-3 shrink-0"
                  style={{ borderBottom: `1px solid rgb(var(--canvas-border))` }}
                >
                  <span
                    className="text-[10px] font-bold tracking-widest"
                    style={{ color: 'rgb(var(--canvas-fg-3))' }}
                  >
                    RECENTLY PLAYED
                  </span>
                </div>
                {recentTracks.length > 0 && (
                  <div className="px-3 pt-3 pb-1 shrink-0">
                    <NowPlaying
                      title={recentTracks[0].meta.track_title}
                      artist={recentTracks[0].meta.artist}
                      album={recentTracks[0].meta.album || undefined}
                      lastPlayedAt={recentTracks[0].meta.last_played ? formatLastPlayed(recentTracks[0].meta.last_played) : undefined}
                    />
                  </div>
                )}
                <div className="flex-1 overflow-y-auto p-2">
                  <ActivityTimeline
                    events={timelineEvents}
                    emptyState="No recent tracks"
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
