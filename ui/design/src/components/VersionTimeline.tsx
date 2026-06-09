import React, { useEffect, useRef } from 'react'
import { VersionPill } from './VersionPill'
import { Chip } from './Chip'
import { formatTimestamp } from '../utils/dateUtils'
import './VersionTimeline.css'

export interface DiffStats {
  added?: number
  removed?: number
  kept?: number
}

export interface StateTransition {
  from: string
  to: string
}

export interface VersionEntry {
  id: string
  label: string
  headline?: string
  timestamp: Date | string
  head?: boolean
  stats?: DiffStats
  transition?: StateTransition
}

export interface VersionTimelineProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'onSelect'> {
  entries: VersionEntry[]
  selectedId?: string
  onSelect?: (id: string) => void
  order?: 'newest-first' | 'oldest-first'
  emptyState?: string
}

export const VersionTimeline = React.forwardRef<HTMLDivElement, VersionTimelineProps>(
  (
    {
      entries = [],
      selectedId,
      onSelect,
      order = 'newest-first',
      emptyState = 'No versions available',
      className = '',
      ...props
    },
    ref
  ) => {
    const listRef = useRef<HTMLDivElement>(null)

    // Apply order without mutating caller data
    const orderedEntries = React.useMemo(() => {
      const copy = [...entries]
      if (order === 'oldest-first') {
        return copy.reverse()
      }
      return copy
    }, [entries, order])

    // Find index of selected entry
    const selectedIndex = orderedEntries.findIndex(e => e.id === selectedId)

    // Keyboard navigation
    const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (!onSelect) return

      if (e.key === 'ArrowUp') {
        e.preventDefault()
        if (selectedIndex > 0) {
          onSelect(orderedEntries[selectedIndex - 1].id)
        }
      } else if (e.key === 'ArrowDown') {
        e.preventDefault()
        if (selectedIndex < orderedEntries.length - 1) {
          onSelect(orderedEntries[selectedIndex + 1].id)
        }
      } else if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        if (selectedIndex >= 0) {
          onSelect(orderedEntries[selectedIndex].id)
        }
      }
    }

    // Scroll selected entry into view
    useEffect(() => {
      if (selectedIndex >= 0 && listRef.current && selectedId) {
        const entryElement = listRef.current.querySelector(
          `[data-version-id="${CSS.escape(selectedId)}"]`
        ) as HTMLElement
        if (entryElement) {
          entryElement.scrollIntoView({ block: 'nearest' })
        }
      }
    }, [selectedId, selectedIndex])

    const classNames = ['version-timeline', className].filter(Boolean).join(' ')

    if (orderedEntries.length === 0) {
      return (
        <div ref={ref} className={classNames} data-testid="version-timeline" {...props}>
          <div className="version-timeline__empty" data-testid="version-timeline-empty">
            {emptyState}
          </div>
        </div>
      )
    }

    const showConnector = orderedEntries.length > 1

    return (
      <div
        ref={ref}
        className={classNames}
        data-testid="version-timeline"
        role="listbox"
        tabIndex={0}
        onKeyDown={handleKeyDown}
        {...props}
      >
        <div className="version-timeline__list" ref={listRef}>
          {orderedEntries.map((entry, index) => (
            <div
              key={entry.id}
              className={[
                'version-timeline__entry',
                selectedId === entry.id ? 'version-timeline__entry--selected' : '',
                onSelect ? 'version-timeline__entry--clickable' : '',
              ]
                .filter(Boolean)
                .join(' ')}
              data-version-id={entry.id}
              data-testid={`version-entry-${entry.id}`}
              role="option"
              aria-selected={selectedId === entry.id}
              {...(onSelect && {
                onClick: () => onSelect(entry.id),
                tabIndex: 0,
              })}
            >
              <div className="version-timeline__rail">
                {showConnector && index < orderedEntries.length - 1 && (
                  <div className="version-timeline__connector" />
                )}
                <div
                  className={[
                    'version-timeline__dot',
                    entry.head ? 'version-timeline__dot--head' : 'version-timeline__dot--hollow',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  data-testid={`version-dot-${entry.id}`}
                />
              </div>

              <div className="version-timeline__content">
                <div className="version-timeline__header">
                  <VersionPill tone="amber" className="version-timeline__pill">
                    {entry.label}
                  </VersionPill>
                  {entry.head && (
                    <Chip variant="amber" form="default" className="version-timeline__head-chip" data-testid={`version-head-${entry.id}`}>
                      head
                    </Chip>
                  )}
                </div>

                {entry.headline && (
                  <div className="version-timeline__headline" data-testid={`version-headline-${entry.id}`}>
                    {entry.headline}
                  </div>
                )}

                {entry.transition ? (
                  <div className="version-timeline__transition" data-testid={`version-transition-${entry.id}`}>
                    <span className="version-timeline__transition-label">{entry.transition.from}</span>
                    <span className="version-timeline__transition-arrow">→</span>
                    <span className="version-timeline__transition-label">{entry.transition.to}</span>
                  </div>
                ) : entry.stats ? (
                  <div className="version-timeline__stats" data-testid={`version-stats-${entry.id}`}>
                    {entry.stats.added !== undefined && (
                      <span className="version-timeline__stat version-timeline__stat--added">
                        <span className="version-timeline__stat-symbol">+{entry.stats.added}</span>
                        <span className="version-timeline__stat-label" aria-label={`${entry.stats.added} added`}>
                          {entry.stats.added} added
                        </span>
                      </span>
                    )}
                    {entry.stats.removed !== undefined && (
                      <span className="version-timeline__stat version-timeline__stat--removed">
                        <span className="version-timeline__stat-symbol">−{entry.stats.removed}</span>
                        <span className="version-timeline__stat-label" aria-label={`${entry.stats.removed} removed`}>
                          {entry.stats.removed} removed
                        </span>
                      </span>
                    )}
                    {entry.stats.kept !== undefined && (
                      <span className="version-timeline__stat version-timeline__stat--kept">
                        <span className="version-timeline__stat-symbol">∩{entry.stats.kept}</span>
                        <span className="version-timeline__stat-label" aria-label={`${entry.stats.kept} kept`}>
                          {entry.stats.kept} kept
                        </span>
                      </span>
                    )}
                  </div>
                ) : null}
              </div>

              <div className="version-timeline__timestamp" data-testid={`version-timestamp-${entry.id}`}>
                {formatTimestamp(entry.timestamp)}
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }
)

VersionTimeline.displayName = 'VersionTimeline'

export default VersionTimeline
