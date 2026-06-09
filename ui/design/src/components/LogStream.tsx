import React, { useEffect, useRef, useState } from 'react'
import './LogStream.css'
import { formatTime } from '../utils/dateUtils'

export interface LogEntry {
  id?: string
  timestamp: Date | string
  level: 'INFO' | 'WARN' | 'ERROR' | 'DEBUG'
  message: string
  op?: string
  target?: string
}

export interface LogStreamProps extends React.HTMLAttributes<HTMLDivElement> {
  entries: LogEntry[]
  follow?: boolean
  maxRows?: number
  showOps?: boolean
}

export const LogStream = React.forwardRef<HTMLDivElement, LogStreamProps>(
  (
    {
      entries = [],
      follow = true,
      maxRows = 500,
      showOps = false,
      className = '',
      'aria-label': ariaLabel,
      ...props
    },
    ref
  ) => {
    const containerRef = useRef<HTMLDivElement>(null)
    const bottomSentinelRef = useRef<HTMLDivElement>(null)
    const [isFollowing, setIsFollowing] = useState(follow)

    // Merge refs
    useEffect(() => {
      if (ref) {
        if (typeof ref === 'function') {
          ref(containerRef.current)
        } else {
          ref.current = containerRef.current
        }
      }
    }, [ref])

    // Set up IntersectionObserver to detect when bottom sentinel is visible
    useEffect(() => {
      if (!follow || !bottomSentinelRef.current) {
        return
      }

      const observer = new IntersectionObserver(
        (observerEntries) => {
          observerEntries.forEach((entry) => {
            if (entry.isIntersecting) {
              setIsFollowing(true)
            }
          })
        },
        { threshold: 0.1 }
      )

      observer.observe(bottomSentinelRef.current)

      return () => {
        observer.disconnect()
      }
    }, [follow])

    // Auto-scroll to bottom when following and new entries arrive
    useEffect(() => {
      if (isFollowing && follow && containerRef.current) {
        containerRef.current.scrollTop = containerRef.current.scrollHeight
      }
    }, [entries, follow, isFollowing])

    // Detect manual scroll-up to pause follow
    useEffect(() => {
      if (!follow || !containerRef.current) {
        return
      }

      const handleScroll = () => {
        const { scrollTop, scrollHeight, clientHeight } = containerRef.current!
        const isAtBottom = scrollHeight - scrollTop - clientHeight < 50
        if (!isAtBottom) {
          setIsFollowing(false)
        }
      }

      const container = containerRef.current
      container.addEventListener('scroll', handleScroll)
      return () => {
        container.removeEventListener('scroll', handleScroll)
      }
    }, [follow])

    // Slice entries to maxRows
    const visibleEntries = entries.slice(-maxRows)

    const getLogEntryKey = (entry: LogEntry): string => {
      if (entry.id) return entry.id

      const ts =
        typeof entry.timestamp === 'string'
          ? entry.timestamp
          : entry.timestamp.getTime()
      return `log-${ts}-${entry.level}-${entry.message}-${entry.op || ''}-${entry.target || ''}`
    }

    const classNames = ['log-stream', className]
      .filter(Boolean)
      .join(' ')

    return (
      <div
        ref={containerRef}
        className={classNames}
        role="log"
        aria-live={isFollowing && follow ? 'polite' : undefined}
        aria-label={ariaLabel ?? 'Log stream'}
        {...props}
      >
        <div className="log-stream__content">
          {visibleEntries.length === 0 ? (
            <div className="log-stream__empty">
              <span className="log-stream__empty-text">No log entries</span>
            </div>
          ) : (
            visibleEntries.map((entry) => {
              const timestamp = typeof entry.timestamp === 'string'
                ? new Date(entry.timestamp)
                : entry.timestamp
              const time = formatTime(timestamp)
              const levelClass = `log-stream__level log-stream__level--${entry.level.toLowerCase()}`

              const rowClass = showOps
                ? 'log-stream__row log-stream__row--with-ops'
                : 'log-stream__row'

              return (
                <div key={getLogEntryKey(entry)} className={rowClass}>
                  <span className="log-stream__time">{time}</span>
                  <span className={levelClass}>{entry.level}</span>
                  {showOps && (
                    <>
                      <span className="log-stream__op">{entry.op || ''}</span>
                      <span className="log-stream__target">{entry.target || ''}</span>
                    </>
                  )}
                  <span className="log-stream__message">{entry.message}</span>
                </div>
              )
            })
          )}
        </div>
        {follow && <div ref={bottomSentinelRef} className="log-stream__sentinel" />}
      </div>
    )
  }
)

LogStream.displayName = 'LogStream'

export default LogStream
