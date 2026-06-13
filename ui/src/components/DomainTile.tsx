import type { ReactNode } from 'react';
import { Chip } from '@tinkermonkey/heimdall-ui';

export interface DomainTileProps {
  domain: string;
  name: string;
  recordCount: number;
  adapterCount: number;
  chunkCount: number;
  adapters: string[];
  onClick?: () => void;
  className?: string;
}

export function DomainTile({
  domain,
  name,
  recordCount,
  adapterCount,
  chunkCount,
  adapters,
  onClick,
  className,
}: DomainTileProps): ReactNode {
  const domainColor = `rgb(var(--domain-${domain}, var(--canvas-fg-3)))`;

  return (
    <div
      className={className}
      onClick={onClick}
      style={{
        display: 'flex',
        border: `1px solid rgb(var(--canvas-border))`,
        borderRadius: 'var(--radius-md)',
        overflow: 'hidden',
        cursor: onClick ? 'pointer' : 'default',
        background: 'rgb(var(--canvas-card))',
      }}
      onMouseEnter={(e) => {
        if (onClick) e.currentTarget.style.borderColor = `rgb(var(--canvas-border-strong))`;
      }}
      onMouseLeave={(e) => {
        if (onClick) e.currentTarget.style.borderColor = `rgb(var(--canvas-border))`;
      }}
    >
      <div style={{ width: 3, flexShrink: 0, background: domainColor }} />
      <div style={{ padding: '10px 12px', flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
          <span
            style={{
              width: 7,
              height: 7,
              borderRadius: 2,
              background: domainColor,
              flexShrink: 0,
              display: 'inline-block',
            }}
          />
          <span
            style={{ fontWeight: 600, fontSize: 13, color: 'rgb(var(--canvas-fg-1))' }}
          >
            {name}
          </span>
        </div>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 20,
            fontWeight: 700,
            color: 'rgb(var(--canvas-fg-1))',
            lineHeight: 1.2,
            marginBottom: 2,
          }}
        >
          {recordCount.toLocaleString()}
        </div>
        <div
          style={{ fontSize: 11.5, color: 'rgb(var(--canvas-fg-3))', marginBottom: 8 }}
        >
          {adapterCount} adapter{adapterCount !== 1 ? 's' : ''} · {chunkCount.toLocaleString()} chunks
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {adapters.map((a) => (
            <Chip key={a} form="id-tag">
              {a}
            </Chip>
          ))}
        </div>
      </div>
    </div>
  );
}
