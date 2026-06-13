import type { ReactNode } from 'react';

export interface OutlineItem {
  id: string;
  label: string;
  /** Heading level 1–6, controls indentation */
  level: 1 | 2 | 3 | 4 | 5 | 6;
}

export interface OutlinePanelProps {
  items: OutlineItem[];
  activeId?: string;
  onItemClick: (item: OutlineItem) => void;
  className?: string;
}

const LEVEL_INDENT: Record<number, number> = {
  1: 0,
  2: 12,
  3: 22,
  4: 30,
  5: 36,
  6: 42,
};

export function OutlinePanel({
  items,
  activeId,
  onItemClick,
  className,
}: OutlinePanelProps): ReactNode {
  return (
    <div className={className} style={{ padding: '8px 0' }}>
      {items.map((item) => {
        const isActive = item.id === activeId;
        const indent = LEVEL_INDENT[item.level] ?? 0;

        return (
          <div
            key={item.id}
            onClick={() => onItemClick(item)}
            style={{
              display: 'flex',
              alignItems: 'center',
              padding: `5px 12px 5px ${12 + indent}px`,
              cursor: 'pointer',
              fontSize: item.level === 1 ? 12.5 : 12,
              fontWeight: item.level === 1 ? 600 : 400,
              color: isActive ? 'rgb(var(--canvas-fg-1))' : 'rgb(var(--canvas-fg-2))',
              background: isActive ? `rgb(var(--accent-primary) / 0.08)` : 'transparent',
              borderLeft: isActive
                ? `2px solid rgb(var(--accent-primary))`
                : '2px solid transparent',
              lineHeight: 1.35,
            }}
            onMouseEnter={(e) => {
              if (!isActive)
                e.currentTarget.style.background = `rgb(var(--canvas-fg-1) / 0.05)`;
            }}
            onMouseLeave={(e) => {
              if (!isActive) e.currentTarget.style.background = 'transparent';
            }}
          >
            <span
              style={{
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                flex: 1,
              }}
            >
              {item.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
