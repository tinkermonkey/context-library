import type { ReactNode } from 'react';

export interface MentionsListProps {
  mentions: string[];
  maxVisible?: number;
  className?: string;
}

export function MentionsList({
  mentions,
  maxVisible = 8,
  className,
}: MentionsListProps): ReactNode {
  if (mentions.length === 0) return null;

  const visible = mentions.slice(0, maxVisible);
  const overflow = mentions.length - visible.length;

  return (
    <div
      className={className}
      style={{ display: 'flex', flexWrap: 'wrap', gap: 4, alignItems: 'center' }}
    >
      {visible.map((mention) => (
        <span
          key={mention}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            padding: '2px 7px',
            borderRadius: 9999,
            background: 'rgb(var(--accent-primary) / 0.12)',
            color: 'rgb(var(--accent-primary))',
            fontSize: 11,
            fontWeight: 500,
            letterSpacing: '0.01em',
          }}
        >
          {mention.startsWith('@') ? mention : `@${mention}`}
        </span>
      ))}
      {overflow > 0 && (
        <span
          style={{
            fontSize: 11,
            color: 'rgb(var(--canvas-fg-4))',
            padding: '2px 4px',
          }}
        >
          +{overflow} more
        </span>
      )}
    </div>
  );
}
