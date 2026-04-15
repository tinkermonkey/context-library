import { useQuery } from '@tanstack/react-query';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { useState, useMemo } from 'react';
import type { ReactNode } from 'react';
import { MagnifyingGlassIcon, MusicalNoteIcon } from '@heroicons/react/24/outline';
import { fetchChunks } from '../api/client';
import { colors, getDomainColor } from '../lib/designTokens';
import type { ChunkResponse } from '../types/api';

const musicColor = getDomainColor('music'); // #F43F5E

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

// ── Track ──────────────────────────────────────────────────────────

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

function formatDuration(seconds: number | null): string {
  if (seconds === null) return '--:--';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

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

const SORT_LABELS: Record<SortKey, string> = {
  last_played: 'Last Played',
  play_count: 'Play Count',
  title: 'Title',
  artist: 'Artist',
};

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

// ── Artwork Thumbnail ──────────────────────────────────────────────

function ArtworkThumb({ gradient, size = 36 }: { gradient: [string, string]; size?: number }): ReactNode {
  return (
    <div
      className="shrink-0"
      style={{
        width: size,
        height: size,
        background: `linear-gradient(135deg, ${gradient[0]}, ${gradient[1]})`,
        borderRadius: 4,
      }}
    />
  );
}

// ── Equalizer Bars ─────────────────────────────────────────────────

function EqualizerBars(): ReactNode {
  return (
    <div className="flex items-end gap-[2px]" style={{ height: 16, width: 16 }}>
      {([0, 1, 2] as const).map(i => (
        <div
          key={i}
          style={{
            width: 3,
            borderRadius: 1,
            background: musicColor,
            // Staggered animation per bar
            animation: `eqBar ${0.6 + i * 0.15}s ease-in-out ${i * 0.1}s infinite alternate`,
            height: 4,
          }}
        />
      ))}
    </div>
  );
}

// ── Recently Played Row (left panel) ───────────────────────────────

function RecentRow({ track, isActive }: { track: Track; isActive: boolean }): ReactNode {
  return (
    <div
      className="flex items-center gap-2.5"
      style={{
        padding: '7px 0',
        borderBottom: '1px solid #1A1A1A',
        background: isActive ? `${musicColor}0D` : 'transparent',
      }}
    >
      <ArtworkThumb gradient={track.gradient} size={28} />
      <div className="flex flex-col gap-0.5 flex-1 min-w-0">
        <span
          className="text-xs font-medium truncate"
          style={{ color: isActive ? '#FFFFFF' : colors.textPrimary }}
        >
          {track.meta.track_title}
        </span>
        <span className="text-[10px] truncate" style={{ color: '#6B7280' }}>
          {track.meta.artist}
          {track.meta.last_played ? ` · ${formatLastPlayed(track.meta.last_played)}` : ''}
        </span>
      </div>
    </div>
  );
}

// ── Track Row (main list) ──────────────────────────────────────────

function TrackRow({
  track,
  index,
  isActive,
}: {
  track: Track;
  index: number;
  isActive: boolean;
}): ReactNode {
  return (
    <div
      className="flex items-center gap-3.5 transition-colors hover:bg-white/[0.03]"
      style={{
        height: 56,
        padding: '0 20px',
        background: isActive ? '#1A1F3C' : 'transparent',
        borderBottom: '1px solid #1A1A1A',
      }}
    >
      {/* Track number or equalizer */}
      <div className="shrink-0 flex items-center justify-center" style={{ width: 20 }}>
        {isActive ? (
          <EqualizerBars />
        ) : (
          <span className="text-xs" style={{ color: '#4B5563' }}>{index + 1}</span>
        )}
      </div>

      {/* Artwork */}
      <ArtworkThumb gradient={track.gradient} size={36} />

      {/* Track info */}
      <div className="flex flex-col gap-0.5 flex-1 min-w-0">
        <span
          className="text-sm font-medium truncate"
          style={{ color: isActive ? '#FFFFFF' : colors.textPrimary }}
        >
          {track.meta.track_title}
        </span>
        <span className="text-xs truncate" style={{ color: '#6B7280' }}>
          {track.meta.artist}
          {track.meta.album ? ` · ${track.meta.album}` : ''}
        </span>
      </div>

      {/* Play count */}
      {track.meta.play_count !== null && (
        <span
          className="shrink-0 text-xs tabular-nums"
          style={{ color: '#4B5563', minWidth: 28, textAlign: 'right' }}
        >
          {track.meta.play_count}
        </span>
      )}

      {/* Last played */}
      {track.meta.last_played && (
        <span
          className="shrink-0 text-xs"
          style={{ color: '#4B5563', minWidth: 60, textAlign: 'right' }}
        >
          {formatLastPlayed(track.meta.last_played)}
        </span>
      )}

      {/* Duration */}
      <span
        className="shrink-0 text-xs tabular-nums"
        style={{ color: '#6B7280', minWidth: 36, textAlign: 'right' }}
      >
        {formatDuration(track.meta.duration)}
      </span>
    </div>
  );
}

// ── Now Playing Panel ──────────────────────────────────────────────

function NowPlayingPanel({
  nowPlaying,
  recentTracks,
}: {
  nowPlaying: Track | null;
  recentTracks: Track[]; // top 10 sorted by last_played, including nowPlaying at [0]
}): ReactNode {
  const [g0, g1] = nowPlaying?.gradient ?? ['#1E1B4B', '#312E81'];

  return (
    <div
      className="flex flex-col shrink-0 overflow-hidden"
      style={{
        width: 280,
        height: '100%',
        background: '#0D0D0D',
        borderRight: '1px solid #1A1A1A',
      }}
    >
      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto flex flex-col" style={{ padding: 20, gap: 16 }}>
        {/* NOW PLAYING label */}
        <span className="text-[10px] font-bold tracking-widest shrink-0" style={{ color: '#6366F1' }}>
          NOW PLAYING
        </span>

        {/* Album artwork */}
        <div
          className="shrink-0"
          style={{
            height: 240,
            background: `linear-gradient(135deg, ${g0}, ${g1})`,
            borderRadius: 12,
          }}
        />

        {/* Track info */}
        <div className="flex flex-col gap-1 shrink-0">
          {nowPlaying ? (
            <>
              <span className="text-[15px] font-bold truncate" style={{ color: '#FFFFFF' }}>
                {nowPlaying.meta.track_title}
              </span>
              <span className="text-[13px] truncate" style={{ color: '#9CA3AF' }}>
                {nowPlaying.meta.artist}
              </span>
              <span className="text-[11px] truncate" style={{ color: '#6B7280' }}>
                {nowPlaying.meta.album}
                {nowPlaying.meta.year ? ` · ${nowPlaying.meta.year}` : ''}
              </span>
            </>
          ) : (
            <span className="text-[13px]" style={{ color: '#4B5563' }}>
              No recent tracks
            </span>
          )}
        </div>

        {/* Progress bar — static, showing last known position */}
        <div className="flex flex-col gap-1.5 shrink-0">
          <div
            className="relative"
            style={{ height: 4, background: '#1F2937', borderRadius: 2 }}
          >
            <div
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                height: 4,
                width: nowPlaying ? '40%' : '0%',
                background: '#6366F1',
                borderRadius: 2,
              }}
            />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px]" style={{ color: '#6B7280' }}>
              {nowPlaying && nowPlaying.meta.duration
                ? formatDuration(Math.floor(nowPlaying.meta.duration * 0.4))
                : '0:00'}
            </span>
            <span className="text-[10px]" style={{ color: '#6B7280' }}>
              {formatDuration(nowPlaying?.meta.duration ?? null)}
            </span>
          </div>
        </div>

        {/* Play count / last played */}
        {nowPlaying && (
          <div className="flex items-center gap-2 flex-wrap shrink-0">
            {nowPlaying.meta.play_count !== null && (
              <span className="text-[10px]" style={{ color: '#4B5563' }}>
                {nowPlaying.meta.play_count} plays
              </span>
            )}
            {nowPlaying.meta.play_count !== null && nowPlaying.meta.last_played && (
              <span className="text-[10px]" style={{ color: '#2D2D2D' }}>·</span>
            )}
            {nowPlaying.meta.last_played && (
              <span className="text-[10px]" style={{ color: '#4B5563' }}>
                {formatLastPlayed(nowPlaying.meta.last_played)}
              </span>
            )}
          </div>
        )}

        {/* Recently Played list (tracks 2–10) */}
        {recentTracks.length > 1 && (
          <div className="flex flex-col shrink-0">
            <span
              className="text-[10px] font-bold tracking-widest mb-2"
              style={{ color: '#4B5563' }}
            >
              RECENTLY PLAYED
            </span>
            {recentTracks.slice(1, 10).map((track, i) => (
              <RecentRow
                key={track.chunk_hash}
                track={track}
                isActive={i === -1} // none active in the recent list
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── MusicPage ──────────────────────────────────────────────────────

export default function MusicPage(): ReactNode {
  const navigate = useNavigate();
  const { sort: sortParam, q: searchParam } = useSearch({ from: '/music' });

  const sortKey: SortKey = (sortParam as SortKey | undefined) ?? 'last_played';
  const searchText = searchParam ?? '';

  const [showSortMenu, setShowSortMenu] = useState(false);

  function setSearchText(value: string): void {
    void navigate({
      to: '/music',
      search: { sort: sortParam, q: value || undefined },
      replace: true,
    });
  }

  function setSortKey(key: SortKey): void {
    void navigate({
      to: '/music',
      search: { sort: key === 'last_played' ? undefined : key, q: searchParam },
    });
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

  // Top 10 by last_played for the Now Playing + recently played panel
  const recentTracks = useMemo(
    (): Track[] => sortTracks(allTracks, 'last_played').slice(0, 10),
    [allTracks],
  );

  const nowPlaying = recentTracks[0] ?? null;

  const filteredSortedTracks = useMemo((): Track[] => {
    let list = allTracks;
    if (searchText.trim()) {
      const q = searchText.toLowerCase();
      list = list.filter(
        t =>
          t.meta.track_title.toLowerCase().includes(q) ||
          t.meta.artist.toLowerCase().includes(q) ||
          t.meta.album.toLowerCase().includes(q),
      );
    }
    return sortTracks(list, sortKey);
  }, [allTracks, searchText, sortKey]);

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: colors.bgBase }}>
      {/* Equalizer bar animation */}
      <style>{`@keyframes eqBar { from { height: 4px; } to { height: 14px; } }`}</style>

      {/* ── Topbar ── */}
      <div
        className="flex items-center gap-3 shrink-0 px-5"
        style={{ height: 52, background: '#111111', borderBottom: '1px solid #1A1A1A' }}
      >
        <span className="font-semibold flex-1" style={{ fontSize: 16, color: colors.textPrimary }}>
          Music
        </span>
        <div
          className="flex items-center gap-1.5"
          style={{ background: '#1A1A1A', borderRadius: 4, padding: '4px 10px' }}
        >
          <MusicalNoteIcon className="w-3 h-3 shrink-0" style={{ color: '#6B7280' }} />
          <span className="text-[11px]" style={{ color: '#9CA3AF' }}>Apple Music Library</span>
        </div>
      </div>

      {/* ── Body ── */}
      <div className="flex-1 flex overflow-hidden">
        {/* Now Playing + Recently Played panel */}
        <NowPlayingPanel nowPlaying={nowPlaying} recentTracks={recentTracks} />

        {/* Track library */}
        <div className="flex-1 flex flex-col overflow-hidden" style={{ minWidth: 0 }}>
          {/* Library header */}
          <div
            className="flex items-center gap-3 shrink-0 px-5"
            style={{ height: 48, background: '#111111', borderBottom: '1px solid #1A1A1A' }}
          >
            <span className="font-semibold flex-1 text-sm" style={{ color: colors.textPrimary }}>
              Recently Played
            </span>
            {!chunksQuery.isLoading && allTracks.length > 0 && (
              <span className="text-xs" style={{ color: '#6B7280' }}>
                {allTracks.length.toLocaleString()} tracks
              </span>
            )}
          </div>

          {/* Search + Sort bar */}
          <div
            className="flex items-center gap-3 shrink-0 px-5"
            style={{ height: 44, borderBottom: '1px solid #1A1A1A', background: '#0F0F0F' }}
          >
            <div
              className="flex items-center gap-2 flex-1"
              style={{
                height: 30,
                background: '#1A1A1A',
                border: '1px solid #2D2D2D',
                borderRadius: 6,
                padding: '0 10px',
              }}
            >
              <MagnifyingGlassIcon className="w-3.5 h-3.5 shrink-0" style={{ color: '#4B5563' }} />
              <input
                type="text"
                value={searchText}
                onChange={e => setSearchText(e.target.value)}
                placeholder="Search by title, artist, or album…"
                className="flex-1 bg-transparent text-xs outline-none"
                style={{ color: colors.textPrimary }}
              />
            </div>

            {/* Sort dropdown */}
            <div className="relative shrink-0">
              <button
                onClick={() => setShowSortMenu(prev => !prev)}
                className="flex items-center gap-1.5 transition-opacity hover:opacity-75"
                style={{
                  height: 30,
                  background: '#1A1A1A',
                  border: '1px solid #2D2D2D',
                  borderRadius: 6,
                  padding: '0 10px',
                  fontSize: 12,
                  color: '#9CA3AF',
                  gap: 6,
                }}
              >
                <span style={{ color: '#4B5563' }}>Sort:</span>
                {SORT_LABELS[sortKey]}
                <svg width={10} height={6} viewBox="0 0 10 6" fill="none" aria-hidden>
                  <path
                    d="M1 1l4 4 4-4"
                    stroke="#6B7280"
                    strokeWidth={1.5}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
              {showSortMenu && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setShowSortMenu(false)} />
                  <div
                    className="absolute right-0 top-full mt-1 z-20 flex flex-col overflow-hidden"
                    style={{
                      background: '#1F2937',
                      border: '1px solid #374151',
                      borderRadius: 6,
                      minWidth: 140,
                      boxShadow: '0 4px 16px rgba(0,0,0,0.6)',
                    }}
                  >
                    {(Object.entries(SORT_LABELS) as [SortKey, string][]).map(([key, label]) => (
                      <button
                        key={key}
                        onClick={() => {
                          setSortKey(key);
                          setShowSortMenu(false);
                        }}
                        className="text-left text-xs px-3 py-2 transition-colors hover:bg-[#374151]"
                        style={{ color: sortKey === key ? musicColor : '#D1D5DB' }}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Track list */}
          <div className="flex-1 overflow-y-auto">
            {chunksQuery.isLoading ? (
              <div className="flex flex-col">
                {[1, 2, 3, 4, 5, 6, 7, 8].map(i => (
                  <div
                    key={i}
                    className="animate-pulse flex items-center gap-3.5 px-5"
                    style={{ height: 56, borderBottom: '1px solid #1A1A1A' }}
                  >
                    <div
                      className="rounded shrink-0"
                      style={{ width: 20, height: 12, background: '#1A1A1A' }}
                    />
                    <div
                      className="rounded shrink-0"
                      style={{ width: 36, height: 36, background: '#1A1A1A' }}
                    />
                    <div className="flex flex-col gap-1.5 flex-1">
                      <div className="rounded" style={{ height: 12, width: 160, background: '#1A1A1A' }} />
                      <div className="rounded" style={{ height: 10, width: 100, background: '#161616' }} />
                    </div>
                    <div
                      className="rounded shrink-0"
                      style={{ width: 32, height: 12, background: '#1A1A1A' }}
                    />
                  </div>
                ))}
              </div>
            ) : chunksQuery.isError ? (
              <div className="flex items-center justify-center py-16">
                <span className="text-sm" style={{ color: colors.statusRed }}>
                  Failed to load music library
                </span>
              </div>
            ) : filteredSortedTracks.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <div
                  className="flex items-center justify-center rounded-2xl"
                  style={{ width: 48, height: 48, background: `${musicColor}20` }}
                >
                  <MusicalNoteIcon className="w-6 h-6" style={{ color: musicColor }} />
                </div>
                <p className="text-sm" style={{ color: colors.textDim }}>
                  {searchText
                    ? 'No tracks match your search'
                    : 'No music tracks ingested yet'}
                </p>
              </div>
            ) : (
              filteredSortedTracks.map((track, index) => (
                <TrackRow
                  key={track.chunk_hash}
                  track={track}
                  index={index}
                  isActive={nowPlaying !== null && track.chunk_hash === nowPlaying.chunk_hash}
                />
              ))
            )}
          </div>

          {/* Footer */}
          {!chunksQuery.isLoading && allTracks.length > 0 && (
            <div
              className="shrink-0 flex items-center gap-3 px-5"
              style={{ height: 36, background: '#0D0D0D', borderTop: '1px solid #1A1A1A' }}
            >
              <span
                className="text-[10px] font-bold tracking-widest"
                style={{ color: '#4B5563' }}
              >
                LISTENING HISTORY
              </span>
              <span className="text-[11px]" style={{ color: '#4B5563' }}>
                {allTracks.length.toLocaleString()} tracks indexed · apple_music_library
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
