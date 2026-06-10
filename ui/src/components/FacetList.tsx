import type { ReactNode } from 'react';

export interface FacetItem {
  value: string;
  label: string;
  count: number;
  /** Optional CSS color for a domain-colored dot */
  color?: string;
}

export interface FacetGroup {
  title: string;
  items: FacetItem[];
}

export interface FacetListProps {
  groups: FacetGroup[];
  onItemClick?: (group: FacetGroup, item: FacetItem) => void;
  className?: string;
}

export function FacetList({ groups, onItemClick, className }: FacetListProps): ReactNode {
  return (
    <div className={className} style={{ padding: '4px 0 8px' }}>
      {groups.map((group) => (
        <div key={group.title} style={{ padding: '6px 0' }}>
          <div
            style={{
              padding: '4px 12px',
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'rgb(var(--canvas-fg-3))',
            }}
          >
            {group.title}
          </div>
          {group.items.map((item) => (
            <div
              key={item.value}
              onClick={() => onItemClick?.(group, item)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                margin: '0 4px',
                padding: '6px 10px',
                borderRadius: 3,
                cursor: onItemClick ? 'pointer' : 'default',
                fontFamily: 'var(--font-mono)',
                fontSize: 11.5,
                color: 'rgb(var(--canvas-fg-2))',
              }}
              onMouseEnter={(e) => {
                if (onItemClick)
                  e.currentTarget.style.background = `rgb(var(--canvas-fg-1) / 0.06)`;
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent';
              }}
            >
              {item.color ? (
                <span
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: 2,
                    background: item.color,
                    flexShrink: 0,
                    display: 'inline-block',
                  }}
                />
              ) : (
                <span
                  style={{
                    width: 7,
                    height: 7,
                    flexShrink: 0,
                    display: 'inline-block',
                  }}
                />
              )}
              <span style={{ flex: 1 }}>{item.label}</span>
              <span
                style={{ color: 'rgb(var(--canvas-fg-3))', fontSize: 10.5 }}
              >
                {item.count}
              </span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
