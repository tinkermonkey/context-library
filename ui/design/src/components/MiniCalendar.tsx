import React, { useMemo } from 'react'
import './MiniCalendar.css'
import { getMonthGrid, isSameDay, isToday } from '../utils/dateUtils'

export interface MiniCalendarProps {
  focusedDate: Date | string
  selectedDate?: Date | string
  markers?: Date[]
  weekStartsOn?: 0 | 1
  onSelect?: (date: Date) => void
  className?: string
}

const formatMonthYear = (date: Date | string): string => {
  const d = typeof date === 'string' ? new Date(date) : new Date(date)
  return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}

export const MiniCalendar = React.forwardRef<HTMLDivElement, MiniCalendarProps>(
  (
    {
      focusedDate,
      selectedDate,
      markers = [],
      weekStartsOn = 0,
      onSelect,
      className = '',
      ...props
    },
    ref
  ) => {
    const focusedD = typeof focusedDate === 'string' ? new Date(focusedDate) : new Date(focusedDate)
    const selectedD = selectedDate ? (typeof selectedDate === 'string' ? new Date(selectedDate) : selectedDate) : null

    const grid = useMemo(() => getMonthGrid(focusedD, weekStartsOn), [focusedD.getTime(), weekStartsOn])

    const weekDays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    if (weekStartsOn === 1) {
      weekDays.push(weekDays.shift()!)
    }

    const hasMarker = (date: Date): boolean => {
      return markers.some((markerDate) => isSameDay(date, markerDate))
    }

    return (
      <div ref={ref} className={`mini-calendar ${className}`.trim()} {...props}>
        <div className="mini-calendar__header">
          <div className="mini-calendar__title">{formatMonthYear(focusedD)}</div>
        </div>

        <div className="mini-calendar__grid">
          <div className="mini-calendar__weekdays">
            {weekDays.map((day) => (
              <div key={day} className="mini-calendar__weekday">
                {day.toUpperCase()}
              </div>
            ))}
          </div>

          <div className="mini-calendar__dates">
            {grid.map((week) =>
              week.map((date) => {
                const isOutOfMonth = date.getMonth() !== focusedD.getMonth()
                const isSelected = selectedD ? isSameDay(date, selectedD) : false
                const isCurrentDay = isToday(date)
                const hasMarkerDot = hasMarker(date)

                return (
                  <button
                    key={date.toISOString()}
                    className={`mini-calendar__date ${
                      isOutOfMonth ? 'mini-calendar__date--out-of-month' : ''
                    } ${isSelected ? 'mini-calendar__date--selected' : ''} ${
                      isCurrentDay ? 'mini-calendar__date--today' : ''
                    } ${hasMarkerDot ? 'mini-calendar__date--has-marker' : ''}`}
                    onClick={() => !isOutOfMonth && onSelect?.(date)}
                    type="button"
                    aria-current={isCurrentDay ? 'date' : undefined}
                    aria-selected={isSelected}
                  >
                    <span className="mini-calendar__date-number">{date.getDate()}</span>
                    {hasMarkerDot && <span className="mini-calendar__marker" />}
                  </button>
                )
              })
            )}
          </div>
        </div>
      </div>
    )
  }
)

MiniCalendar.displayName = 'MiniCalendar'

export default MiniCalendar
