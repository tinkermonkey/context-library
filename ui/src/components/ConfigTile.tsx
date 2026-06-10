import type { ReactNode } from 'react';
import { Button, Icon, type IconName, type ButtonVariant } from '@tinkermonkey/heimdall-ui';

export interface ConfigTileAction {
  label: string;
  variant?: ButtonVariant;
  onClick: () => void;
  disabled?: boolean;
}

export interface ConfigTileStat {
  label: string;
  value: string;
}

export interface ConfigTileProps {
  icon: IconName;
  title: string;
  description?: string;
  stats?: ConfigTileStat[];
  actions?: ConfigTileAction[];
  onClick?: () => void;
  className?: string;
  children?: ReactNode;
  domainColor?: string;
}

export function ConfigTile({
  icon,
  title,
  description,
  stats,
  actions,
  onClick,
  className,
  children,
  domainColor,
}: ConfigTileProps): ReactNode {
  return (
    <div
      className={className}
      onClick={actions?.length ? undefined : onClick}
      style={{
        border: `1px solid rgb(var(--canvas-border))`,
        borderRadius: 'var(--radius-md)',
        background: 'rgb(var(--canvas-card))',
        overflow: 'hidden',
        cursor: !actions?.length && onClick ? 'pointer' : 'default',
        display: 'flex',
        flexDirection: 'row',
      }}
      onMouseEnter={(e) => {
        if (!actions?.length && onClick)
          e.currentTarget.style.borderColor = `rgb(var(--canvas-border-strong))`;
      }}
      onMouseLeave={(e) => {
        if (!actions?.length && onClick)
          e.currentTarget.style.borderColor = `rgb(var(--canvas-border))`;
      }}
    >
      {/* Domain color bar */}
      {domainColor && (
        <div style={{ width: 3, flexShrink: 0, background: domainColor }} />
      )}

      {/* Card body */}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        {/* Header */}
        <div style={{ padding: '12px 14px', display: 'flex', alignItems: 'flex-start', gap: 10 }}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 32,
              height: 32,
              borderRadius: 'var(--radius-sm)',
              background: `rgb(var(--canvas-surface-2))`,
              color: 'rgb(var(--canvas-fg-2))',
              flexShrink: 0,
            }}
          >
            <Icon name={icon} size={16} />
          </span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                fontWeight: 600,
                fontSize: 13,
                color: 'rgb(var(--canvas-fg-1))',
                marginBottom: description ? 2 : 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              {domainColor && (
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
              )}
              {title}
            </div>
            {description && (
              <div
                style={{
                  fontSize: 12,
                  color: 'rgb(var(--canvas-fg-3))',
                  lineHeight: 1.4,
                }}
              >
                {description}
              </div>
            )}
          </div>
        </div>

        {/* Stats grid */}
        {stats && stats.length > 0 && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: `repeat(${Math.min(stats.length, 3)}, 1fr)`,
              borderTop: `1px solid rgb(var(--canvas-border))`,
            }}
          >
            {stats.map((stat, i) => (
              <div
                key={stat.label}
                style={{
                  padding: '8px 12px',
                  borderRight:
                    i < stats.length - 1 ? `1px solid rgb(var(--canvas-border))` : undefined,
                }}
              >
                <div
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10,
                    fontWeight: 700,
                    letterSpacing: '0.06em',
                    textTransform: 'uppercase',
                    color: 'rgb(var(--canvas-fg-4))',
                    marginBottom: 2,
                  }}
                >
                  {stat.label}
                </div>
                <div
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 13,
                    fontWeight: 600,
                    color: 'rgb(var(--canvas-fg-1))',
                  }}
                >
                  {stat.value}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Custom content slot */}
        {children && (
          <div style={{ borderTop: `1px solid rgb(var(--canvas-border))` }}>{children}</div>
        )}

        {/* Actions */}
        {actions && actions.length > 0 && (
          <div
            style={{
              display: 'flex',
              gap: 6,
              padding: '8px 12px',
              borderTop: `1px solid rgb(var(--canvas-border))`,
              background: `rgb(var(--canvas-bg-2))`,
            }}
          >
            {actions.map((action) => (
              <Button
                key={action.label}
                variant={action.variant ?? 'ghost'}
                size="sm"
                disabled={action.disabled}
                onClick={(e) => {
                  e.stopPropagation();
                  action.onClick();
                }}
              >
                {action.label}
              </Button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
