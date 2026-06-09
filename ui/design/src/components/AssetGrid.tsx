import React from 'react'
import './AssetGrid.css'

export interface AssetGridProps extends React.HTMLAttributes<HTMLDivElement> {
  columns?: number
  gap?: number
  children: React.ReactNode
}

export const AssetGrid = React.forwardRef<HTMLDivElement, AssetGridProps>(
  ({ columns = 3, gap = 14, className = '', children, ...props }, ref) => {
    const classNames = ['asset-grid', className].filter(Boolean).join(' ')

    return (
      <div
        ref={ref}
        className={classNames}
        style={{
          '--asset-columns': columns,
          '--asset-gap': `${gap}px`,
        } as React.CSSProperties & { '--asset-columns': number; '--asset-gap': string }}
        {...props}
      >
        {children}
      </div>
    )
  }
)

AssetGrid.displayName = 'AssetGrid'

export default AssetGrid
