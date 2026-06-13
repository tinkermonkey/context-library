import type { ReactNode } from 'react';
import { Icon } from '@tinkermonkey/heimdall-ui';

export interface SearchHeroProps {
  query: string;
  onQueryChange: (value: string) => void;
  onSearch?: () => void;
  /** Summary text displayed after results load, e.g. "7 results · 84 ms" */
  resultMeta?: ReactNode;
  /** Filter controls (FilterDropdown, SegmentedControl) rendered below the input */
  filters?: ReactNode;
  className?: string;
}

export function SearchHero({
  query,
  onQueryChange,
  onSearch,
  resultMeta,
  filters,
  className,
}: SearchHeroProps): ReactNode {
  return (
    <div
      className={className}
      style={{
        border: `1px solid rgb(var(--canvas-border))`,
        borderRadius: 'var(--radius-lg)',
        background: 'rgb(var(--canvas-card))',
        marginBottom: 16,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '10px 14px',
          borderBottom: filters ? `1px solid rgb(var(--canvas-border))` : undefined,
        }}
      >
        <span style={{ color: 'rgb(var(--canvas-fg-3))', flexShrink: 0 }}>
          <Icon name="search" size={16} />
        </span>
        <input
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onSearch?.();
          }}
          placeholder="Search across all content…"
          style={{
            flex: 1,
            border: 0,
            outline: 'none',
            background: 'transparent',
            fontSize: 15,
            fontWeight: 500,
            color: 'rgb(var(--canvas-fg-1))',
            letterSpacing: '-0.01em',
          }}
        />
        {resultMeta && (
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: 'rgb(var(--canvas-fg-3))',
              flexShrink: 0,
            }}
          >
            {resultMeta}
          </span>
        )}
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'rgb(var(--canvas-fg-4))',
            border: `1px solid rgb(var(--canvas-border))`,
            borderRadius: 'var(--radius-sm)',
            padding: '2px 6px',
            flexShrink: 0,
          }}
        >
          ⌘ ↵
        </span>
      </div>
      {filters && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '8px 12px',
            flexWrap: 'wrap',
          }}
        >
          {filters}
        </div>
      )}
    </div>
  );
}
