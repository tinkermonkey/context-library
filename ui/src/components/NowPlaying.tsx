import type { ReactNode } from 'react';
import { Icon } from '@tinkermonkey/heimdall-ui';

export interface NowPlayingProps {
  title: string;
  artist: string;
  album?: string;
  isPlaying?: boolean;
  lastPlayedAt?: string | null;
  className?: string;
}

export function NowPlaying({
  title,
  artist,
  album,
  isPlaying = false,
  lastPlayedAt,
  className,
}: NowPlayingProps): ReactNode {
  return (
    <div
      className={className}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '10px 12px',
        borderRadius: 'var(--radius-md)',
        background: 'rgb(var(--canvas-surface-2))',
        border: `1px solid rgb(var(--canvas-border))`,
      }}
    >
      <div
        style={{
          width: 40,
          height: 40,
          borderRadius: 'var(--radius-sm)',
          background: `rgb(var(--domain-music, var(--canvas-border)))`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          color: 'rgb(var(--canvas-bg))',
        }}
      >
        <Icon name={isPlaying ? 'play' : 'music'} size={18} />
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: 'rgb(var(--canvas-fg-1))',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {title}
        </div>
        <div
          style={{
            fontSize: 12,
            color: 'rgb(var(--canvas-fg-3))',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {artist}
          {album ? ` · ${album}` : ''}
        </div>
        {lastPlayedAt && (
          <div
            style={{
              fontSize: 11,
              color: 'rgb(var(--canvas-fg-4))',
              marginTop: 2,
            }}
          >
            {lastPlayedAt}
          </div>
        )}
      </div>

      {isPlaying && (
        <div
          style={{
            flexShrink: 0,
            color: `rgb(var(--domain-music, var(--accent-primary)))`,
          }}
        >
          <Icon name="play" size={14} />
        </div>
      )}
    </div>
  );
}
