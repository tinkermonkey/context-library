import React from 'react'
import './LineageRail.css'
import { Icon, type IconName } from './Icon'
import { Chip } from './Chip'

export interface LineageNode {
  icon?: IconName
  label: string
  onClick?: () => void
}

export interface LineageRailProps extends React.HTMLAttributes<HTMLDivElement> {
  nodes: LineageNode[]
  wrap?: boolean
  'aria-label'?: string
}

export const LineageRail = React.forwardRef<HTMLDivElement, LineageRailProps>(
  ({ nodes, wrap = false, className = '', 'aria-label': ariaLabel, ...props }, ref) => {
    if (nodes.length === 0) return null

    const containerClass = [
      'lineage-rail',
      wrap && 'lineage-rail--wrap',
      className,
    ]
      .filter(Boolean)
      .join(' ')

    const label = ariaLabel || `Lineage: ${nodes.map((n) => n.label).join(' → ')}`

    return (
      <div ref={ref} className={containerClass} role="list" aria-label={label} {...props}>
        {nodes.map((node, index) => {
          const isHead = index === 0

          return (
            <React.Fragment key={`${node.label}-${index}`}>
              {index > 0 && (
                <span className="lineage-rail__arrow" aria-hidden="true">
                  →
                </span>
              )}
              <LineageNodeElement node={node} isHead={isHead} />
            </React.Fragment>
          )
        })}
      </div>
    )
  }
)

LineageRail.displayName = 'LineageRail'

interface LineageNodeElementProps {
  node: LineageNode
  isHead: boolean
}

const LineageNodeElement: React.FC<LineageNodeElementProps> = ({ node, isHead }) => {
  const chipClasses = [
    'lineage-rail__node',
    node.onClick && 'lineage-rail__node--interactive',
    isHead && 'lineage-rail__node--head',
  ]
    .filter(Boolean)
    .join(' ')

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.key === 'Enter' || e.key === ' ') && node.onClick) {
      e.preventDefault()
      node.onClick()
    }
  }

  return (
    <Chip
      className={chipClasses}
      role="listitem"
      aria-current={isHead ? 'step' : undefined}
      onClick={node.onClick}
      onKeyDown={node.onClick ? handleKeyDown : undefined}
      tabIndex={node.onClick ? 0 : undefined}
    >
      {node.icon && <Icon name={node.icon} size={14} />}
      <span className="lineage-rail__label">{node.label}</span>
    </Chip>
  )
}

export default LineageRail
