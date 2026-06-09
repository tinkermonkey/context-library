import React, { useState, useRef, useCallback, useMemo } from 'react'
import './KanbanBoard.css'
import { Panel } from './Panel'
import { Chip } from './Chip'
import { Icon } from './Icon'
import { VersionPill } from './VersionPill'
import { StatusColor, statusColorMap } from './statusColors'

export interface KanbanCard {
  id: string
  columnId: string
  title: string
  context?: string
  version?: string
  dueDate?: string
  badges?: string[]
  blocked?: string
  done?: boolean
}

export interface KanbanColumn {
  id: string
  title: string
  statusColor?: StatusColor
  wipLimit?: number
}

export interface KanbanBoardProps extends React.HTMLAttributes<HTMLDivElement> {
  columns: KanbanColumn[]
  cards: KanbanCard[]
  selectedId?: string
  onSelectCard?: (cardId: string) => void
  onMoveCard: (cardId: string, toColumnId: string, index: number) => void
  renderCard?: (card: KanbanCard, isSelected: boolean) => React.ReactNode
}

const KanbanCardComponent = ({
  card,
  isSelected,
  renderCard,
  onSelect,
  onCardPointerDown,
  onCardKeyDown,
}: {
  card: KanbanCard
  isSelected: boolean
  renderCard?: (card: KanbanCard, isSelected: boolean) => React.ReactNode
  onSelect: (cardId: string) => void
  onCardPointerDown: (e: React.PointerEvent<HTMLDivElement>, cardId: string) => void
  onCardKeyDown: (e: React.KeyboardEvent<HTMLDivElement>, cardId: string) => void
}) => {
  if (renderCard) {
    return (
      <div
        className={`kanban-card ${isSelected ? 'kanban-card--selected' : ''}`}
        onPointerDown={(e) => onCardPointerDown(e, card.id)}
        onKeyDown={(e) => onCardKeyDown(e, card.id)}
        onClick={() => onSelect(card.id)}
        tabIndex={0}
        role="button"
        aria-pressed={isSelected}
      >
        {renderCard(card, isSelected)}
      </div>
    )
  }

  return (
    <div
      className={`kanban-card ${isSelected ? 'kanban-card--selected' : ''} ${card.done ? 'kanban-card--done' : ''}`}
      onPointerDown={(e) => onCardPointerDown(e, card.id)}
      onKeyDown={(e) => onCardKeyDown(e, card.id)}
      onClick={() => onSelect(card.id)}
      tabIndex={0}
      role="button"
      aria-pressed={isSelected}
    >
      {card.context && <div className="kanban-card__context">{card.context}</div>}
      <div className="kanban-card__title">{card.title}</div>

      {card.version && (
        <div className="kanban-card__version">
          <VersionPill>{card.version}</VersionPill>
        </div>
      )}

      {(card.dueDate || card.badges) && (
        <div className="kanban-card__meta">
          {card.dueDate && <div className="kanban-card__due-date">{card.dueDate}</div>}
          {card.badges && card.badges.length > 0 && (
            <div className="kanban-card__badges">
              {card.badges.map((badge) => (
                <span key={badge} className="kanban-card__badge">
                  {badge}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {card.blocked && (
        <div className="kanban-card__blocked">
          <Icon name="alert" size={16} />
          {card.blocked}
        </div>
      )}
    </div>
  )
}

const KanbanColumnComponent = ({
  column,
  cards,
  selectedId,
  onSelectCard,
  renderCard,
  draggedCardId,
  insertionIndex,
  onCardPointerDown,
  onCardKeyDown,
}: {
  column: KanbanColumn
  cards: KanbanCard[]
  selectedId?: string
  onSelectCard?: (cardId: string) => void
  renderCard?: (card: KanbanCard, isSelected: boolean) => React.ReactNode
  draggedCardId?: string
  insertionIndex?: number
  onCardPointerDown: (e: React.PointerEvent<HTMLDivElement>, cardId: string) => void
  onCardKeyDown: (e: React.KeyboardEvent<HTMLDivElement>, cardId: string) => void
}) => {
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  const isOverWipLimit = column.wipLimit && cards.length > column.wipLimit

  return (
    <Panel className="kanban-column" noPadding>
      <div className="kanban-column__header">
        <div className="kanban-column__header-left">
          {column.statusColor && (
            <div
              className="kanban-column__status-dot"
              style={{ backgroundColor: statusColorMap[column.statusColor] }}
            />
          )}
          <div className="kanban-column__title">{column.title}</div>
        </div>
        <div className="kanban-column__header-right">
          <Chip variant="neutral">{cards.length}</Chip>
          {isOverWipLimit && (
            <div className="kanban-column__wip-warning" title={`Over WIP limit of ${column.wipLimit}`}>
              <Icon name="alert" size={14} />
            </div>
          )}
        </div>
      </div>

      <div
        ref={scrollContainerRef}
        className="kanban-column__body"
      >
          {cards.length === 0 ? (
            <div className="kanban-column__empty">Drop cards here</div>
          ) : (
            cards.map((card, index) => (
              <React.Fragment key={card.id}>
                {draggedCardId && insertionIndex === index && (
                  <div className="kanban-column__insertion-line" />
                )}
                <KanbanCardComponent
                  card={card}
                  isSelected={selectedId === card.id}
                  renderCard={renderCard}
                  onSelect={(cardId) => onSelectCard?.(cardId)}
                  onCardPointerDown={onCardPointerDown}
                  onCardKeyDown={onCardKeyDown}
                />
              </React.Fragment>
            ))
          )}
        {draggedCardId && insertionIndex === cards.length && (
          <div className="kanban-column__insertion-line" />
        )}
      </div>
    </Panel>
  )
}

interface DragState {
  cardId: string
  sourceColumnId: string
  sourceIndex: number
  offsetY: number
  isKeyboardGrab?: boolean
  originalColumnId?: string
  originalIndex?: number
  pointerId?: number
  capturingElement?: HTMLElement
}

export const KanbanBoard = React.forwardRef<HTMLDivElement, KanbanBoardProps>(
  ({
    columns,
    cards,
    selectedId,
    onSelectCard,
    onMoveCard,
    renderCard,
    className = '',
    ...props
  }, ref) => {
    const dragStateRef = useRef<DragState | null>(null)
    const [draggedCardId, setDraggedCardId] = useState<string | null>(null)
    const [insertionIndex, setInsertionIndex] = useState<number | null>(null)
    const [hoveredColumnId, setHoveredColumnId] = useState<string | null>(null)
    const liveRegionRef = useRef<HTMLDivElement>(null)
    const boardRef = useRef<HTMLDivElement>(null)

    const cardsByColumn = useMemo(() => {
      const map: Record<string, KanbanCard[]> = {}
      columns.forEach((col) => {
        map[col.id] = cards.filter((c) => c.columnId === col.id)
      })
      return map
    }, [columns, cards])

    const announceMove = useCallback((cardTitle: string, toColumnTitle: string, index: number) => {
      if (liveRegionRef.current) {
        liveRegionRef.current.textContent = `Card "${cardTitle}" moved to ${toColumnTitle} at position ${index + 1}`
      }
    }, [])

    const handleCardPointerDown = useCallback(
      (e: React.PointerEvent, cardId: string) => {
        const card = cards.find((c) => c.id === cardId)
        if (!card) return

        const target = e.currentTarget as HTMLElement
        target.setPointerCapture(e.pointerId)

        dragStateRef.current = {
          cardId,
          sourceColumnId: card.columnId,
          sourceIndex: cardsByColumn[card.columnId].findIndex((c) => c.id === cardId),
          offsetY: e.clientY,
          pointerId: e.pointerId,
          capturingElement: target,
        }

        setDraggedCardId(cardId)
        setHoveredColumnId(card.columnId)
      },
      [cards, cardsByColumn]
    )

    const handlePointerMove = useCallback(
      (e: React.PointerEvent) => {
        if (!dragStateRef.current) return

        const rect = boardRef.current?.getBoundingClientRect()
        if (!rect) return

        // Find which column the pointer is over
        let currentColumn: KanbanColumn | null = null

        for (const column of columns) {
          const colElement = document.querySelector(`[data-column-id="${CSS.escape(column.id)}"]`)
          if (colElement) {
            const colRect = colElement.getBoundingClientRect()
            if (e.clientX >= colRect.left && e.clientX < colRect.right) {
              currentColumn = column
              setHoveredColumnId(column.id)
              break
            }
          }
        }

        if (!currentColumn) return

        // Find insertion index based on Y position
        const columnBody = document.querySelector(`[data-column-id="${CSS.escape(currentColumn.id)}"] .kanban-column__body`)
        if (!columnBody) return

        const bodyRect = columnBody.getBoundingClientRect()
        const relativeY = e.clientY - bodyRect.top

        const cardElements = columnBody.querySelectorAll('.kanban-card')
        let insertIdx = 0

        for (let i = 0; i < cardElements.length; i++) {
          const cardRect = cardElements[i].getBoundingClientRect()
          const cardRelativeY = cardRect.top - bodyRect.top

          if (relativeY < cardRelativeY + cardRect.height / 2) {
            insertIdx = i
            break
          } else {
            insertIdx = i + 1
          }
        }

        setInsertionIndex(insertIdx)
      },
      [columns]
    )

    const handlePointerUp = useCallback(
      (_e: React.PointerEvent) => {
        if (!dragStateRef.current) return

        const state = dragStateRef.current
        dragStateRef.current = null

        if (hoveredColumnId && insertionIndex !== null) {
          const fromColumn = columns.find((c) => c.id === state.sourceColumnId)
          const toColumn = columns.find((c) => c.id === hoveredColumnId)

          if (toColumn && fromColumn) {
            const card = cards.find((c) => c.id === state.cardId)
            if (card) {
              onMoveCard(state.cardId, hoveredColumnId, insertionIndex)
              announceMove(card.title, toColumn.title, insertionIndex)
            }
          }
        }

        setDraggedCardId(null)
        setInsertionIndex(null)
        setHoveredColumnId(null)

        if (state.capturingElement && state.pointerId !== undefined) {
          try {
            state.capturingElement.releasePointerCapture(state.pointerId)
          } catch {
            // Element may have been unmounted, ignore the error
          }
        }
      },
      [columns, cards, hoveredColumnId, insertionIndex, onMoveCard, announceMove]
    )

    const handleCardKeyDown = useCallback(
      (e: React.KeyboardEvent, cardId: string) => {
        const card = cards.find((c) => c.id === cardId)
        if (!card) return

        if (e.key === ' ') {
          e.preventDefault()
          const state = dragStateRef.current
          if (state?.isKeyboardGrab) {
            // Space while grabbed commits the move
            onMoveCard(state.cardId, state.sourceColumnId, state.sourceIndex)
            const targetColumn = columns.find((c) => c.id === state.sourceColumnId)
            announceMove(card.title, targetColumn?.title || '', state.sourceIndex)
            dragStateRef.current = null
            setDraggedCardId(null)
            setInsertionIndex(null)
            setHoveredColumnId(null)
          } else {
            // Space initiates grab
            const sourceIndex = cardsByColumn[card.columnId].findIndex((c) => c.id === cardId)
            dragStateRef.current = {
              cardId,
              sourceColumnId: card.columnId,
              sourceIndex,
              offsetY: 0,
              isKeyboardGrab: true,
              originalColumnId: card.columnId,
              originalIndex: sourceIndex,
            }
            setDraggedCardId(cardId)
            setHoveredColumnId(card.columnId)
          }
        } else if (e.key === 'ArrowUp' || e.key === 'ArrowDown' || e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
          e.preventDefault()
          const state = dragStateRef.current
          if (!state || !state.isKeyboardGrab) return

          const currentColumnIndex = columns.findIndex((c) => c.id === state.sourceColumnId)
          const currentColumnCards = cardsByColumn[state.sourceColumnId]

          if (!currentColumnCards) {
            // Source column no longer exists, cancel grab
            dragStateRef.current = null
            setDraggedCardId(null)
            setInsertionIndex(null)
            setHoveredColumnId(null)
            return
          }

          const currentIndex = state.sourceIndex

          let newColumnId = state.sourceColumnId
          let newIndex = currentIndex

          if (e.key === 'ArrowUp' && currentIndex > 0) {
            newIndex = currentIndex - 1
          } else if (e.key === 'ArrowDown' && currentIndex < currentColumnCards.length - 1) {
            newIndex = currentIndex + 1
          } else if (e.key === 'ArrowLeft' && currentColumnIndex > 0) {
            newColumnId = columns[currentColumnIndex - 1].id
            newIndex = 0
          } else if (e.key === 'ArrowRight' && currentColumnIndex < columns.length - 1) {
            newColumnId = columns[currentColumnIndex + 1].id
            newIndex = 0
          }

          dragStateRef.current = {
            ...state,
            sourceColumnId: newColumnId,
            sourceIndex: newIndex,
          }
          setHoveredColumnId(newColumnId)
          setInsertionIndex(newIndex)
          announceMove(card.title, columns.find((c) => c.id === newColumnId)?.title || '', newIndex)
        } else if (e.key === 'Escape') {
          const state = dragStateRef.current
          if (state?.isKeyboardGrab && state.originalColumnId !== undefined && state.originalIndex !== undefined) {
            onMoveCard(state.cardId, state.originalColumnId, state.originalIndex)
            announceMove(card.title, columns.find((c) => c.id === state.originalColumnId)?.title || '', state.originalIndex)
          }
          dragStateRef.current = null
          setDraggedCardId(null)
          setInsertionIndex(null)
          setHoveredColumnId(null)
        }
      },
      [cards, cardsByColumn, columns, onMoveCard, announceMove]
    )

    return (
      <div
        ref={ref}
        className={`kanban-board ${className}`}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        {...props}
      >
        <div ref={boardRef} className="kanban-board__columns">
          {columns.map((column) => (
            <div key={column.id} data-column-id={column.id} className="kanban-board__column-wrapper">
              <KanbanColumnComponent
                column={column}
                cards={cardsByColumn[column.id] || []}
                selectedId={selectedId}
                onSelectCard={(cardId) => onSelectCard?.(cardId)}
                renderCard={renderCard}
                draggedCardId={draggedCardId || undefined}
                insertionIndex={hoveredColumnId === column.id ? (insertionIndex ?? 0) : undefined}
                onCardPointerDown={handleCardPointerDown}
                onCardKeyDown={handleCardKeyDown}
              />
            </div>
          ))}
        </div>

        <div ref={liveRegionRef} className="kanban-board__live-region" role="status" aria-live="polite" aria-atomic="true" />
      </div>
    )
  }
)

KanbanBoard.displayName = 'KanbanBoard'

export default KanbanBoard
