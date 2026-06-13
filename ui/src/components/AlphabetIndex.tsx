import type { ReactNode } from 'react';

const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');

export interface AlphabetIndexProps {
  /** Set of letters that have at least one item; inactive letters are dimmed */
  available?: Set<string>;
  /** Currently active/highlighted letter */
  active?: string;
  onLetterClick: (letter: string) => void;
  className?: string;
}

export function AlphabetIndex({
  available,
  active,
  onLetterClick,
  className,
}: AlphabetIndexProps): ReactNode {
  return (
    <div
      className={className}
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(6, 1fr)',
        gap: 2,
        padding: '4px 8px',
      }}
    >
      {ALPHABET.map((letter) => {
        const hasItems = available ? available.has(letter) : true;
        const isActive = letter === active;

        return (
          <div
            key={letter}
            onClick={() => hasItems && onLetterClick(letter)}
            style={{
              padding: '4px 0',
              textAlign: 'center',
              fontFamily: 'var(--font-mono)',
              fontSize: 10.5,
              fontWeight: isActive ? 700 : 400,
              color: isActive
                ? 'rgb(var(--canvas-fg-1))'
                : hasItems
                ? 'rgb(var(--canvas-fg-2))'
                : 'rgb(var(--canvas-fg-4))',
              background: isActive ? `rgb(var(--accent-primary) / 0.10)` : 'transparent',
              borderRadius: 3,
              cursor: hasItems ? 'pointer' : 'default',
              userSelect: 'none',
            }}
            onMouseEnter={(e) => {
              if (hasItems && !isActive)
                e.currentTarget.style.background = `rgb(var(--canvas-fg-1) / 0.07)`;
            }}
            onMouseLeave={(e) => {
              if (!isActive) e.currentTarget.style.background = 'transparent';
            }}
          >
            {letter}
          </div>
        );
      })}
    </div>
  );
}
