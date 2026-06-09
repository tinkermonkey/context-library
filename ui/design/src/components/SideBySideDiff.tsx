import React from 'react'
import { useVirtualList } from '../hooks/useVirtualList'
import { VersionPill } from './VersionPill'
import './SideBySideDiff.css'

export type DiffLineType = 'context' | 'added' | 'removed' | 'hunk'

export interface DiffLine {
  type: DiffLineType
  content: string
  lineNumber?: number
}

export interface SideBySideDiffProps extends React.HTMLAttributes<HTMLDivElement> {
  lines?: DiffLine[]
}

const ITEM_HEIGHT = 24
const CONTAINER_HEIGHT = 500

export const SideBySideDiff = React.forwardRef<HTMLDivElement, SideBySideDiffProps>(
  ({ lines = [], className = '', ...props }, ref) => {
    const { visibleRange, containerRef, sentinelRef } = useVirtualList({
      itemCount: lines.length,
      itemHeight: ITEM_HEIGHT,
      containerHeight: CONTAINER_HEIGHT,
    })

    const [startIdx, endIdx] = visibleRange

    const classNames = ['side-by-side-diff', className].filter(Boolean).join(' ')

    const hasLines = lines.length > 0

    if (!hasLines) {
      return (
        <div ref={ref} className={classNames} {...props}>
          <div className="side-by-side-diff__empty">No changes between these versions</div>
        </div>
      )
    }

    return (
      <div ref={ref} className={classNames} role="table" {...props}>
        <div className="side-by-side-diff__header" role="row">
          <div className="side-by-side-diff__gutter" role="cell" />
          <div role="cell" className="side-by-side-diff__header-cell">
            <VersionPill tone="emerald" className="side-by-side-diff__pill side-by-side-diff__pill--added">
              Version 2 (Added)
            </VersionPill>
          </div>
          <div role="cell" className="side-by-side-diff__header-cell">
            <VersionPill tone="rose" className="side-by-side-diff__pill side-by-side-diff__pill--removed">
              Version 1 (Removed)
            </VersionPill>
          </div>
        </div>

        <div className="side-by-side-diff__viewport" ref={containerRef}>
          <div
            className="side-by-side-diff__content"
            style={{
              height: lines.length * ITEM_HEIGHT,
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
                height: `${lines.length * ITEM_HEIGHT}px`,
                visibility: 'hidden',
                pointerEvents: 'none',
              }}
            />
            <div style={{ height: startIdx * ITEM_HEIGHT }} />
            {lines.slice(startIdx, endIdx).map((line, relativeIdx) => {
              const index = startIdx + relativeIdx
              const isHunk = line.type === 'hunk'
              const isAdded = line.type === 'added'
              const isRemoved = line.type === 'removed'

              return (
                <div
                  key={index}
                  className={[
                    'side-by-side-diff__row',
                    `side-by-side-diff__row--${line.type}`,
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  style={{ height: ITEM_HEIGHT }}
                  role="row"
                >
                  {isHunk ? (
                    <div className="side-by-side-diff__hunk" role="cell">{line.content}</div>
                  ) : (
                    <>
                      <div
                        className={[
                          'side-by-side-diff__gutter',
                          isAdded && 'side-by-side-diff__gutter--added',
                          isRemoved && 'side-by-side-diff__gutter--removed',
                        ]
                          .filter(Boolean)
                          .join(' ')}
                        role="cell"
                      >
                        <span className="sr-only">{isAdded ? 'added' : isRemoved ? 'removed' : ''}</span>
                      </div>
                      <div
                        className={[
                          'side-by-side-diff__line',
                          isAdded && 'side-by-side-diff__line--added',
                          isRemoved && 'side-by-side-diff__line--removed',
                        ]
                          .filter(Boolean)
                          .join(' ')}
                        role="cell"
                      >
                        <span className="side-by-side-diff__content">{line.content}</span>
                      </div>
                    </>
                  )}
                </div>
              )
            })}
            <div style={{ height: Math.max(0, (lines.length - endIdx) * ITEM_HEIGHT) }} />
          </div>
        </div>
      </div>
    )
  }
)

SideBySideDiff.displayName = 'SideBySideDiff'

export default SideBySideDiff
