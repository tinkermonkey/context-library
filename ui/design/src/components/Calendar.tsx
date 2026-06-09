import React, { useCallback, useMemo } from 'react'
import './Calendar.css'
import { getMonthGrid, getWeekDays, isSameDay, isToday, formatMonthYear, formatDateOnly, formatWeekRange } from '../utils/dateUtils'
import { SegmentedControl, type SegmentedControlOption } from './SegmentedControl'
import { Button } from './Button'
import { Icon } from './Icon'
import { Chip } from './Chip'

export type CalendarView = 'month' | 'week' | 'day' | 'agenda'

export interface CalendarEvent {
  id: string
  title?: string
  calendarId: string
  startDate: Date | string
  endDate?: Date | string
}

export interface CalendarProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'onChange'> {
  view: CalendarView
  focusedDate: Date | string
  selectedDate?: Date | string
  events?: CalendarEvent[]
  calendarColors?: Record<string, string>
  weekStartsOn?: 0 | 1
  onChangeView?: (view: CalendarView) => void
  onNavigate?: (date: Date) => void
  onSelectDate?: (date: Date) => void
  onSelectEvent?: (eventId: string) => void
  renderEvent?: (event: CalendarEvent, calendarColor?: string) => React.ReactNode
}

const getEventsForDate = (date: Date | string, events: CalendarEvent[] = []): CalendarEvent[] => {
  return events.filter((event) => {
    const eventDate = typeof event.startDate === 'string' ? new Date(event.startDate) : new Date(event.startDate)
    return isSameDay(date, eventDate)
  })
}

const MonthView: React.FC<{
  focusedDate: Date | string
  selectedDate?: Date | string
  grid: Date[][]
  events?: CalendarEvent[]
  calendarColors?: Record<string, string>
  weekStartsOn: 0 | 1
  onSelectDate?: (date: Date) => void
  onSelectEvent?: (eventId: string) => void
  renderEvent?: (event: CalendarEvent, calendarColor?: string) => React.ReactNode
  onKeyDown?: (e: React.KeyboardEvent<HTMLDivElement>) => void
}> = ({
  focusedDate,
  selectedDate,
  grid,
  events,
  calendarColors,
  weekStartsOn,
  onSelectDate,
  onSelectEvent,
  renderEvent,
  onKeyDown,
}) => {
  const focusedD = typeof focusedDate === 'string' ? new Date(focusedDate) : focusedDate
  const selectedD = selectedDate ? (typeof selectedDate === 'string' ? new Date(selectedDate) : selectedDate) : null

  let weekDays = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
  if (weekStartsOn === 1) {
    weekDays = weekDays.slice(1).concat(weekDays.slice(0, 1))
  }

  return (
    <div
      className="calendar-month"
      role="grid"
      onKeyDown={onKeyDown}
      tabIndex={0}
    >
      <div className="calendar-month__header" role="row">
        {weekDays.map((day) => (
          <div key={day} className="calendar-month__weekday" role="columnheader">
            {day.slice(0, 3).toUpperCase()}
          </div>
        ))}
      </div>
      {grid.map((week, weekIndex) => (
        <div key={weekIndex} className="calendar-month__week" role="row">
          {week.map((date, dayIndex) => {
            const isOutOfMonth = date.getMonth() !== focusedD.getMonth()
            const isFocused = isSameDay(date, focusedD)
            const isSelected = selectedD ? isSameDay(date, selectedD) : false
            const isCurrentDay = isToday(date)
            const dayEvents = getEventsForDate(date, events)
            const displayCount = 3
            const hiddenCount = dayEvents.length - displayCount

            return (
              <div
                key={`${weekIndex}-${dayIndex}`}
                className={`calendar-month__cell ${isOutOfMonth ? 'calendar-month__cell--out-of-month' : ''} ${
                  isFocused ? 'calendar-month__cell--focused' : ''
                } ${isSelected ? 'calendar-month__cell--selected' : ''}`}
                role="gridcell"
                onClick={() => !isOutOfMonth && onSelectDate?.(date)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    !isOutOfMonth && onSelectDate?.(date)
                  }
                }}
              >
                <div className="calendar-month__date-number" aria-current={isCurrentDay ? 'date' : undefined}>
                  {isCurrentDay ? (
                    <Chip variant="amber" form="default">
                      {date.getDate()}
                    </Chip>
                  ) : (
                    <span>{date.getDate()}</span>
                  )}
                </div>
                <div className="calendar-month__events">
                  {dayEvents.slice(0, displayCount).map((event) => {
                    const color = calendarColors?.[event.calendarId] || 'rgb(var(--status-cyan))'
                    return (
                      <div
                        key={event.id}
                        className="calendar-month__event-bar"
                        style={{ borderLeftColor: color }}
                        onClick={(e) => {
                          e.stopPropagation()
                          onSelectEvent?.(event.id)
                        }}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            e.stopPropagation()
                            onSelectEvent?.(event.id)
                          }
                        }}
                      >
                        {renderEvent ? (
                          renderEvent(event, color)
                        ) : (
                          <span className="calendar-month__event-title">{event.title || 'Event'}</span>
                        )}
                      </div>
                    )
                  })}
                  {hiddenCount > 0 && (
                    <div className="calendar-month__event-overflow">+{hiddenCount} more</div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}

const WeekView: React.FC<{
  focusedDate: Date | string
  weekStartsOn: 0 | 1
  events?: CalendarEvent[]
  calendarColors?: Record<string, string>
  onSelectDate?: (date: Date) => void
  onSelectEvent?: (eventId: string) => void
  renderEvent?: (event: CalendarEvent, calendarColor?: string) => React.ReactNode
}> = ({ focusedDate, weekStartsOn, events, calendarColors, onSelectDate, onSelectEvent, renderEvent }) => {
  const days = getWeekDays(focusedDate, weekStartsOn)

  return (
    <div className="calendar-week">
      <div className="calendar-week__days">
        {days.map((date) => {
          const dayEvents = getEventsForDate(date, events)
          return (
            <div
              key={date.toISOString()}
              className="calendar-week__day"
              role="button"
              tabIndex={0}
              onClick={() => onSelectDate?.(date)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onSelectDate?.(date)
                }
              }}
            >
              <div className="calendar-week__header">
                {date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
              </div>
              <div className="calendar-week__events">
                {dayEvents.map((event) => {
                  const color = calendarColors?.[event.calendarId] || 'rgb(var(--status-cyan))'
                  return (
                    <div
                      key={event.id}
                      className="calendar-week__event"
                      style={{ borderLeftColor: color }}
                      role="button"
                      tabIndex={0}
                      onClick={(e) => {
                        e.stopPropagation()
                        onSelectEvent?.(event.id)
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          e.stopPropagation()
                          onSelectEvent?.(event.id)
                        }
                      }}
                    >
                      {renderEvent ? renderEvent(event, color) : <span>{event.title || 'Event'}</span>}
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

const DayView: React.FC<{
  focusedDate: Date | string
  events?: CalendarEvent[]
  calendarColors?: Record<string, string>
  onSelectEvent?: (eventId: string) => void
  renderEvent?: (event: CalendarEvent, calendarColor?: string) => React.ReactNode
}> = ({ focusedDate, events, calendarColors, onSelectEvent, renderEvent }) => {
  const dayEvents = getEventsForDate(focusedDate, events)

  return (
    <div className="calendar-day">
      <div className="calendar-day__title">
        {typeof focusedDate === 'string'
          ? new Date(focusedDate).toLocaleDateString('en-US', {
              weekday: 'long',
              month: 'long',
              day: 'numeric',
            })
          : focusedDate.toLocaleDateString('en-US', {
              weekday: 'long',
              month: 'long',
              day: 'numeric',
            })}
      </div>
      <div className="calendar-day__events">
        {dayEvents.length === 0 ? (
          <div className="calendar-day__empty">No events scheduled</div>
        ) : (
          dayEvents.map((event) => {
            const color = calendarColors?.[event.calendarId] || 'rgb(var(--status-cyan))'
            return (
              <div
                key={event.id}
                className="calendar-day__event"
                style={{ borderLeftColor: color }}
                role="button"
                tabIndex={0}
                onClick={() => onSelectEvent?.(event.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onSelectEvent?.(event.id)
                  }
                }}
              >
                {renderEvent ? renderEvent(event, color) : <span>{event.title || 'Event'}</span>}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

const AgendaView: React.FC<{
  focusedDate: Date | string
  events?: CalendarEvent[]
  calendarColors?: Record<string, string>
  onSelectEvent?: (eventId: string) => void
  renderEvent?: (event: CalendarEvent, calendarColor?: string) => React.ReactNode
}> = ({ focusedDate, events = [], calendarColors, onSelectEvent, renderEvent }) => {
  const focusedD = typeof focusedDate === 'string' ? new Date(focusedDate) : focusedDate
  const upcomingEvents = events
    .filter((event) => {
      const eventDate = typeof event.startDate === 'string' ? new Date(event.startDate) : new Date(event.startDate)
      return eventDate >= focusedD
    })
    .sort((a, b) => {
      const dateA = typeof a.startDate === 'string' ? new Date(a.startDate) : new Date(a.startDate)
      const dateB = typeof b.startDate === 'string' ? new Date(b.startDate) : new Date(b.startDate)
      return dateA.getTime() - dateB.getTime()
    })

  return (
    <div className="calendar-agenda">
      {upcomingEvents.length === 0 ? (
        <div className="calendar-agenda__empty">No upcoming events</div>
      ) : (
        <div className="calendar-agenda__list">
          {upcomingEvents.map((event) => {
            const color = calendarColors?.[event.calendarId] || 'rgb(var(--status-cyan))'
            return (
              <div
                key={event.id}
                className="calendar-agenda__item"
                role="button"
                tabIndex={0}
                onClick={() => onSelectEvent?.(event.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onSelectEvent?.(event.id)
                  }
                }}
              >
                <div
                  className="calendar-agenda__date"
                  style={{ color }}
                >
                  {typeof event.startDate === 'string'
                    ? new Date(event.startDate).toLocaleDateString('en-US', {
                        weekday: 'short',
                        month: 'short',
                        day: 'numeric',
                      })
                    : event.startDate.toLocaleDateString('en-US', {
                        weekday: 'short',
                        month: 'short',
                        day: 'numeric',
                      })}
                </div>
                <div className="calendar-agenda__content">
                  {renderEvent ? renderEvent(event, color) : <span>{event.title || 'Event'}</span>}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export const Calendar = React.forwardRef<HTMLDivElement, CalendarProps>(
  (
    {
      view,
      focusedDate,
      selectedDate,
      events,
      calendarColors,
      weekStartsOn = 0,
      onChangeView,
      onNavigate,
      onSelectDate,
      onSelectEvent,
      renderEvent,
      className = '',
      ...props
    },
    ref
  ) => {
    const focusedD = typeof focusedDate === 'string' ? new Date(focusedDate) : focusedDate
    const grid = useMemo(() => getMonthGrid(focusedD, weekStartsOn), [focusedD.getTime(), weekStartsOn])

    const viewOptions: SegmentedControlOption[] = [
      { value: 'month', label: 'Month' },
      { value: 'week', label: 'Week' },
      { value: 'day', label: 'Day' },
      { value: 'agenda', label: 'Agenda' },
    ]

    const handleKeyDown = useCallback(
      (e: React.KeyboardEvent<HTMLDivElement>) => {
        if (view !== 'month') return

        const d = new Date(focusedD)

        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 'ArrowUp' || e.key === 'ArrowDown') {
          e.preventDefault()
          const offset =
            e.key === 'ArrowLeft'
              ? -1
              : e.key === 'ArrowRight'
                ? 1
                : e.key === 'ArrowUp'
                  ? -7
                  : 7
          d.setDate(d.getDate() + offset)
          onNavigate?.(d)
        } else if (e.key === 'PageUp') {
          e.preventDefault()
          d.setMonth(d.getMonth() - 1)
          onNavigate?.(d)
        } else if (e.key === 'PageDown') {
          e.preventDefault()
          d.setMonth(d.getMonth() + 1)
          onNavigate?.(d)
        } else if (e.key === 'Home') {
          e.preventDefault()
          const week = getWeekDays(d, weekStartsOn)
          onNavigate?.(week[0])
        } else if (e.key === 'End') {
          e.preventDefault()
          const week = getWeekDays(d, weekStartsOn)
          onNavigate?.(week[6])
        }
      },
      [focusedD.getTime(), onNavigate, view, weekStartsOn]
    )

    const handleNavigatePrev = useCallback(() => {
      const d = new Date(focusedD)
      if (view === 'month') {
        d.setMonth(d.getMonth() - 1)
      } else if (view === 'week') {
        d.setDate(d.getDate() - 7)
      } else if (view === 'day') {
        d.setDate(d.getDate() - 1)
      } else if (view === 'agenda') {
        d.setDate(d.getDate() - 1)
      }
      onNavigate?.(d)
    }, [focusedD.getTime(), onNavigate, view])

    const handleNavigateNext = useCallback(() => {
      const d = new Date(focusedD)
      if (view === 'month') {
        d.setMonth(d.getMonth() + 1)
      } else if (view === 'week') {
        d.setDate(d.getDate() + 7)
      } else if (view === 'day') {
        d.setDate(d.getDate() + 1)
      } else if (view === 'agenda') {
        d.setDate(d.getDate() + 1)
      }
      onNavigate?.(d)
    }, [focusedD.getTime(), onNavigate, view])

    const handleNavigateToday = useCallback(() => {
      onNavigate?.(new Date())
    }, [onNavigate])

    return (
      <div ref={ref} className={`calendar ${className}`.trim()} {...props}>
        <div className="calendar__header">
          <div className="calendar__title">
            {view === 'month' && formatMonthYear(focusedD)}
            {view === 'week' && formatWeekRange(focusedD, weekStartsOn)}
            {view === 'day' && formatDateOnly(focusedD)}
            {view === 'agenda' && 'Agenda'}
          </div>

          <div className="calendar__controls">
            <Button variant="secondary" size="sm" onClick={handleNavigatePrev} aria-label="Previous">
              <Icon name="chevronLeft" size={16} />
            </Button>
            <Button variant="secondary" size="sm" onClick={handleNavigateToday}>
              Today
            </Button>
            <Button variant="secondary" size="sm" onClick={handleNavigateNext} aria-label="Next">
              <Icon name="chevronRight" size={16} />
            </Button>
          </div>
        </div>

        <div className="calendar__view-selector">
          <SegmentedControl
            value={view}
            onChange={(value) => onChangeView?.(value as CalendarView)}
            options={viewOptions}
          />
        </div>

        <div className="calendar__content">
          {view === 'month' && (
            <MonthView
              focusedDate={focusedD}
              selectedDate={selectedDate}
              grid={grid}
              events={events}
              calendarColors={calendarColors}
              weekStartsOn={weekStartsOn}
              onSelectDate={onSelectDate}
              onSelectEvent={onSelectEvent}
              renderEvent={renderEvent}
              onKeyDown={handleKeyDown}
            />
          )}
          {view === 'week' && (
            <WeekView
              focusedDate={focusedD}
              weekStartsOn={weekStartsOn}
              events={events}
              calendarColors={calendarColors}
              onSelectDate={onSelectDate}
              onSelectEvent={onSelectEvent}
              renderEvent={renderEvent}
            />
          )}
          {view === 'day' && (
            <DayView
              focusedDate={focusedD}
              events={events}
              calendarColors={calendarColors}
              onSelectEvent={onSelectEvent}
              renderEvent={renderEvent}
            />
          )}
          {view === 'agenda' && (
            <AgendaView
              focusedDate={focusedD}
              events={events}
              calendarColors={calendarColors}
              onSelectEvent={onSelectEvent}
              renderEvent={renderEvent}
            />
          )}
        </div>
      </div>
    )
  }
)

Calendar.displayName = 'Calendar'

export default Calendar
