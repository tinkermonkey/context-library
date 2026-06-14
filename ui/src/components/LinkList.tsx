import type { ReactNode } from 'react';
import { Icon } from '@tinkermonkey/heimdall-ui';

export interface LinkItem {
  label: string;
  url: string;
  description?: string;
}

export interface LinkListProps {
  links: LinkItem[];
  emptyMessage?: string;
  className?: string;
}

export function LinkList({
  links,
  emptyMessage = 'No links',
  className,
}: LinkListProps): ReactNode {
  if (links.length === 0) {
    return (
      <div
        className={className}
        style={{ padding: '8px 0', color: 'rgb(var(--canvas-fg-4))', fontSize: 13 }}
      >
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className={className} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {links.map((link, i) => (
        <a
          key={i}
          href={link.url}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 8,
            padding: '6px 8px',
            borderRadius: 'var(--radius-sm)',
            textDecoration: 'none',
            color: 'rgb(var(--accent-primary))',
            fontSize: 13,
            background: 'transparent',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'rgb(var(--canvas-fg-1) / 0.06)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent';
          }}
        >
          <span
            style={{ flexShrink: 0, marginTop: 2, color: 'rgb(var(--canvas-fg-3))' }}
          >
            <Icon name="link" size={13} />
          </span>
          <span style={{ flex: 1, minWidth: 0 }}>
            <span
              style={{
                display: 'block',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {link.label}
            </span>
            {link.description && (
              <span
                style={{
                  display: 'block',
                  fontSize: 11,
                  color: 'rgb(var(--canvas-fg-3))',
                  marginTop: 1,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {link.description}
              </span>
            )}
          </span>
        </a>
      ))}
    </div>
  );
}
