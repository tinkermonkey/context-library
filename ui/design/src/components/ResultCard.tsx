import React from 'react'
import './ResultCard.css'
import { Button } from './Button'
import { ProgressBar } from './ProgressBar'
import { VersionPill } from './VersionPill'
import { Icon, type IconName } from './Icon'

export interface ResultCardProvenance {
  collection?: string
  document?: string
  section?: string
}

export interface ResultCardProps extends React.HTMLAttributes<HTMLDivElement> {
  domain: string
  source: string
  version?: string
  snippet: React.ReactNode
  provenance?: ResultCardProvenance
  score?: number
  onOpen?: () => void
  actions?: Array<{
    label: string
    icon?: IconName
    onClick: () => void
  }>
  selected?: boolean
}

const domainColorMap: Record<string, string> = {
  life: 'var(--dom-life)',
  climate: 'var(--dom-climate)',
  software: 'var(--dom-software)',
  data: 'var(--dom-default)',
  infrastructure: 'var(--dom-default)',
}

const getDomainColor = (domain: string): string => {
  return domainColorMap[domain] || 'var(--accent-primary)'
}

const getDomainDotColor = (domain: string): string => {
  const colors = ['emerald', 'cyan', 'amber', 'rose', 'violet']
  const hash = domain.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0)
  return colors[hash % colors.length]
}

export const ResultCard = React.forwardRef<HTMLDivElement, ResultCardProps>(
  (
    { domain, source, version, snippet, provenance, score, onOpen, actions, selected = false, className = '', ...props },
    ref
  ) => {
    const domainColor = getDomainColor(domain)
    const domainDotColor = getDomainDotColor(domain)

    const handleKeyDown = React.useCallback(
      (event: React.KeyboardEvent<HTMLDivElement>) => {
        if ((event.key === 'Enter' || event.key === ' ') && onOpen) {
          event.preventDefault()
          onOpen()
        }
      },
      [onOpen]
    )

    const classNames = ['result-card', selected && 'result-card--selected', className]
      .filter(Boolean)
      .join(' ')

    const ariaLabel = version ? `${source} v${version}` : source

    return (
      <div
        ref={ref}
        className={classNames}
        role="article"
        aria-label={ariaLabel}
        tabIndex={onOpen ? 0 : undefined}
        onClick={onOpen}
        onKeyDown={onOpen ? handleKeyDown : undefined}
        style={{
          '--domain-color': domainColor,
        } as React.CSSProperties & { '--domain-color': string }}
        {...props}
      >
        <div className="result-card__header">
          <div className="result-card__header-left">
            <div className={`result-card__domain-dot result-card__domain-dot--${domainDotColor}`} />
            <span className="result-card__source">{source}</span>
            {version && <VersionPill>{version}</VersionPill>}
          </div>
          {score !== undefined && <span className="result-card__score-label">{score.toFixed(2)}</span>}
        </div>

        {score !== undefined && (
          <div className="result-card__score-bar">
            <ProgressBar percent={score * 100} color="amber" height={4} />
          </div>
        )}

        <div className="result-card__snippet">{snippet}</div>

        {provenance && Object.values(provenance).some(v => v !== undefined) && (
          <>
            <div className="result-card__divider" />
            <div className="result-card__provenance">
              {provenance.collection && (
                <span className="result-card__provenance-field">
                  <span className="result-card__provenance-label">Collection</span>
                  <span className="result-card__provenance-value">{provenance.collection}</span>
                </span>
              )}
              {provenance.document && (
                <span className="result-card__provenance-field">
                  <span className="result-card__provenance-label">Document</span>
                  <span className="result-card__provenance-value">{provenance.document}</span>
                </span>
              )}
              {provenance.section && (
                <span className="result-card__provenance-field">
                  <span className="result-card__provenance-label">Section</span>
                  <span className="result-card__provenance-value">{provenance.section}</span>
                </span>
              )}
            </div>
          </>
        )}

        {actions && actions.length > 0 && (
          <div className="result-card__actions">
            {actions.map((action, index) => (
              <Button
                key={index}
                variant="ghost"
                size="sm"
                icon={!!action.icon}
                title={action.label}
                onClick={(e) => {
                  e.stopPropagation()
                  action.onClick()
                }}
              >
                {action.icon ? (
                  <Icon name={action.icon} size={16} />
                ) : (
                  action.label
                )}
              </Button>
            ))}
          </div>
        )}
      </div>
    )
  }
)

ResultCard.displayName = 'ResultCard'

export default ResultCard
