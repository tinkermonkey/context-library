import React, { useState } from 'react'
import { useVirtualList } from '../hooks/useVirtualList'
import { VersionPill } from './VersionPill'
import './HashSetDiff.css'

export interface HashSetDiffProps extends React.HTMLAttributes<HTMLDivElement> {
  added?: string[]
  removed?: string[]
  kept?: string[]
  maxVisible?: number
}

const ITEM_HEIGHT = 28
const CONTAINER_HEIGHT = 400

export const HashSetDiff = React.forwardRef<HTMLDivElement, HashSetDiffProps>(
  ({ added = [], removed = [], kept = [], maxVisible = 10, className = '', ...props }, ref) => {
    const [expandedKept, setExpandedKept] = useState(false)

    const hasChanges = added.length > 0 || removed.length > 0 || kept.length > 0
    const showKeptCollapse = kept.length > maxVisible && !expandedKept

    const keptDisplayed = expandedKept ? kept : kept.slice(0, maxVisible)
    const keptHidden = kept.length - keptDisplayed.length

    const maxRows = Math.max(added.length, removed.length, showKeptCollapse ? maxVisible + 1 : kept.length)

    const { visibleRange, containerRef, sentinelRef } = useVirtualList({
      itemCount: maxRows,
      itemHeight: ITEM_HEIGHT,
      containerHeight: CONTAINER_HEIGHT,
    })

    const [startIdx, endIdx] = visibleRange

    const classNames = ['hash-set-diff', className].filter(Boolean).join(' ')

    if (!hasChanges) {
      return (
        <div ref={ref} className={classNames} {...props}>
          <div className="hash-set-diff__empty">No changes between these versions</div>
        </div>
      )
    }

    return (
      <div ref={ref} className={classNames} role="table" {...props}>
        <div className="hash-set-diff__header" role="row">
          <div className="hash-set-diff__column hash-set-diff__column--added" role="cell">
            <VersionPill tone="emerald" className="hash-set-diff__pill">
              Added
            </VersionPill>
            <span className="hash-set-diff__count">{added.length}</span>
          </div>
          <div className="hash-set-diff__column hash-set-diff__column--removed" role="cell">
            <VersionPill tone="rose" className="hash-set-diff__pill">
              Removed
            </VersionPill>
            <span className="hash-set-diff__count">{removed.length}</span>
          </div>
          <div className="hash-set-diff__column hash-set-diff__column--kept" role="cell">
            <VersionPill className="hash-set-diff__pill">
              Kept
            </VersionPill>
            <span className="hash-set-diff__count">{kept.length}</span>
          </div>
        </div>

        <div className="hash-set-diff__viewport" ref={containerRef}>
          <div
            className="hash-set-diff__content"
            style={{
              height: maxRows * ITEM_HEIGHT,
              position: 'relative',
            }}
          >
            <div
              ref={sentinelRef}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '1px',
                height: `${maxRows * ITEM_HEIGHT}px`,
                visibility: 'hidden',
                pointerEvents: 'none',
              }}
            />
            <div style={{ height: startIdx * ITEM_HEIGHT }} />
            {Array.from({ length: Math.min(endIdx - startIdx, maxRows - startIdx) }).map((_, relativeIdx) => {
              const index = startIdx + relativeIdx

              const addedItem = index < added.length ? added[index] : null
              const removedItem = index < removed.length ? removed[index] : null

              let keptItem: string | null = null
              let isCollapseRow = false

              if (showKeptCollapse && index === maxVisible) {
                isCollapseRow = true
              } else if (index < keptDisplayed.length) {
                keptItem = keptDisplayed[index]
              }

              return (
                <div key={index} className="hash-set-diff__row" style={{ height: ITEM_HEIGHT }} role="row">
                  <div className="hash-set-diff__cell hash-set-diff__cell--added" role="cell">
                    {addedItem && <div className="hash-set-diff__item">{addedItem}</div>}
                  </div>
                  <div className="hash-set-diff__cell hash-set-diff__cell--removed" role="cell">
                    {removedItem && <div className="hash-set-diff__item">{removedItem}</div>}
                  </div>
                  <div className="hash-set-diff__cell hash-set-diff__cell--kept" role="cell">
                    {isCollapseRow ? (
                      <button
                        type="button"
                        className="hash-set-diff__expand-button"
                        onClick={() => setExpandedKept(true)}
                        aria-label={`Show ${keptHidden} more kept items`}
                      >
                        … {keptHidden} more carried forward
                      </button>
                    ) : (
                      keptItem && <div className="hash-set-diff__item">{keptItem}</div>
                    )}
                  </div>
                </div>
              )
            })}
            <div style={{ height: Math.max(0, (maxRows - endIdx) * ITEM_HEIGHT) }} />
          </div>
        </div>
      </div>
    )
  }
)

HashSetDiff.displayName = 'HashSetDiff'

export default HashSetDiff
