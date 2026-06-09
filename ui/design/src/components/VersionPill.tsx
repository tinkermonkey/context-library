import React from 'react'
import './VersionPill.css'

export type VersionPillTone = 'amber' | 'emerald' | 'rose'

export interface VersionPillProps extends React.HTMLAttributes<HTMLSpanElement> {
  children: React.ReactNode
  tone?: VersionPillTone
}

export const VersionPill = React.forwardRef<HTMLSpanElement, VersionPillProps>(
  ({ className = '', children, tone = 'amber', ...props }, ref) => {
    const classNames = ['version-pill', `version-pill--${tone}`, className]
      .filter(Boolean)
      .join(' ')

    return (
      <span ref={ref} className={classNames} {...props}>
        {children}
      </span>
    )
  }
)

VersionPill.displayName = 'VersionPill'

export default VersionPill
