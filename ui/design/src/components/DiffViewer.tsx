import React, { useState, useEffect, ReactNode, createContext, useContext } from 'react'
import { HashSetDiff, type HashSetDiffProps } from './HashSetDiff'
import { SideBySideDiff, type SideBySideDiffProps } from './SideBySideDiff'
import { VersionPill, type VersionPillTone } from './VersionPill'
import './DiffViewer.css'

export type DiffViewerMode = 'hash-set' | 'side-by-side'

export interface DiffViewerProps extends React.HTMLAttributes<HTMLDivElement> {
  mode?: DiffViewerMode
  onModeChange?: (mode: DiffViewerMode) => void
  children?: ReactNode
}

export interface DiffViewerHashSetProps extends Omit<HashSetDiffProps, 'className'> {
  label?: string
  labelTone?: VersionPillTone
  className?: string
}

export interface DiffViewerSideBySideProps extends Omit<SideBySideDiffProps, 'className'> {
  addedLabel?: string
  removedLabel?: string
  addedLabelTone?: VersionPillTone
  removedLabelTone?: VersionPillTone
  className?: string
}

const DiffViewerModeContext = createContext<DiffViewerMode | null>(null)

const DiffViewerComponent = React.forwardRef<HTMLDivElement, DiffViewerProps>(
  ({ mode = 'hash-set', onModeChange, children, className = '', ...props }, ref) => {
    const [currentMode, setCurrentMode] = useState<DiffViewerMode>(mode)

    useEffect(() => {
      setCurrentMode(mode)
    }, [mode])

    const handleModeChange = (newMode: DiffViewerMode) => {
      setCurrentMode(newMode)
      onModeChange?.(newMode)
    }

    const handleTabKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
      const tabs = Array.from(
        (e.currentTarget as HTMLButtonElement).closest('[role="tablist"]')?.querySelectorAll('[role="tab"]') || []
      )
      const currentIndex = tabs.indexOf(e.currentTarget)

      if (e.key === 'ArrowLeft') {
        e.preventDefault()
        const prevIndex = currentIndex > 0 ? currentIndex - 1 : tabs.length - 1
        ;(tabs[prevIndex] as HTMLButtonElement)?.focus()
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        const nextIndex = currentIndex < tabs.length - 1 ? currentIndex + 1 : 0
        ;(tabs[nextIndex] as HTMLButtonElement)?.focus()
      } else if (e.key === 'Home') {
        e.preventDefault()
        ;(tabs[0] as HTMLButtonElement)?.focus()
      } else if (e.key === 'End') {
        e.preventDefault()
        ;(tabs[tabs.length - 1] as HTMLButtonElement)?.focus()
      }
    }

    const classNames = ['diff-viewer', className].filter(Boolean).join(' ')

    return (
      <DiffViewerModeContext.Provider value={currentMode}>
        <div
          ref={ref}
          className={classNames}
          role="region"
          aria-label="Diff Viewer"
          data-testid="diff-viewer"
          {...props}
        >
          <div className="diff-viewer__header" role="tablist">
            <button
              type="button"
              id="diff-viewer-hash-set-tab"
              role="tab"
              aria-selected={currentMode === 'hash-set'}
              aria-controls="diff-viewer-hash-set-panel"
              className={[
                'diff-viewer__tab',
                currentMode === 'hash-set' && 'diff-viewer__tab--active',
              ]
                .filter(Boolean)
                .join(' ')}
              onClick={() => handleModeChange('hash-set')}
              onKeyDown={handleTabKeyDown}
            >
              Hash Set
            </button>
            <button
              type="button"
              id="diff-viewer-side-by-side-tab"
              role="tab"
              aria-selected={currentMode === 'side-by-side'}
              aria-controls="diff-viewer-side-by-side-panel"
              className={[
                'diff-viewer__tab',
                currentMode === 'side-by-side' && 'diff-viewer__tab--active',
              ]
                .filter(Boolean)
                .join(' ')}
              onClick={() => handleModeChange('side-by-side')}
              onKeyDown={handleTabKeyDown}
            >
              Side by Side
            </button>
          </div>

          <div className="diff-viewer__content" data-testid="diff-viewer-content">
            {currentMode === 'hash-set' && (
              <div
                id="diff-viewer-hash-set-panel"
                role="tabpanel"
                aria-labelledby="diff-viewer-hash-set-tab"
                className="diff-viewer__panel diff-viewer__panel--hash-set"
              >
                {children}
              </div>
            )}
            {currentMode === 'side-by-side' && (
              <div
                id="diff-viewer-side-by-side-panel"
                role="tabpanel"
                aria-labelledby="diff-viewer-side-by-side-tab"
                className="diff-viewer__panel diff-viewer__panel--side-by-side"
              >
                {children}
              </div>
            )}
          </div>
        </div>
      </DiffViewerModeContext.Provider>
    )
  }
)

DiffViewerComponent.displayName = 'DiffViewer'

function DiffViewerHashSet({
  added,
  removed,
  kept,
  maxVisible,
  label = 'Changes',
  labelTone = 'amber',
  className = '',
  ...props
}: DiffViewerHashSetProps) {
  const currentMode = useContext(DiffViewerModeContext)

  if (currentMode !== 'hash-set') {
    return null
  }

  return (
    <div className={['diff-viewer-hash-set', className].filter(Boolean).join(' ')} {...props}>
      {label && (
        <div className="diff-viewer-hash-set__header">
          <VersionPill tone={labelTone} className="diff-viewer-hash-set__label">
            {label}
          </VersionPill>
        </div>
      )}
      <HashSetDiff added={added} removed={removed} kept={kept} maxVisible={maxVisible} />
    </div>
  )
}

DiffViewerHashSet.displayName = 'DiffViewerHashSet'

function DiffViewerSideBySide({
  lines,
  addedLabel = 'Version 2 (Added)',
  removedLabel = 'Version 1 (Removed)',
  addedLabelTone = 'emerald',
  removedLabelTone = 'rose',
  className = '',
  ...props
}: DiffViewerSideBySideProps) {
  const currentMode = useContext(DiffViewerModeContext)

  if (currentMode !== 'side-by-side') {
    return null
  }

  return (
    <div className={['diff-viewer-side-by-side', className].filter(Boolean).join(' ')} {...props}>
      {(addedLabel || removedLabel) && (
        <div className="diff-viewer-side-by-side__header">
          <div className="diff-viewer-side-by-side__labels">
            {addedLabel && (
              <VersionPill tone={addedLabelTone} className="diff-viewer-side-by-side__label">
                {addedLabel}
              </VersionPill>
            )}
            {removedLabel && (
              <VersionPill tone={removedLabelTone} className="diff-viewer-side-by-side__label">
                {removedLabel}
              </VersionPill>
            )}
          </div>
        </div>
      )}
      <SideBySideDiff lines={lines} />
    </div>
  )
}

DiffViewerSideBySide.displayName = 'DiffViewerSideBySide'

interface DiffViewerComponentType
  extends React.ForwardRefExoticComponent<DiffViewerProps & React.RefAttributes<HTMLDivElement>> {
  HashSet: typeof DiffViewerHashSet
  SideBySide: typeof DiffViewerSideBySide
}

const DiffViewer = Object.assign(DiffViewerComponent, {
  HashSet: DiffViewerHashSet,
  SideBySide: DiffViewerSideBySide,
}) as DiffViewerComponentType

export { DiffViewer }
export default DiffViewer
