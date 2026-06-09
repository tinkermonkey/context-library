import React from 'react'
import './AssetCard.css'
import { Icon, type IconName } from './Icon'

export type AssetThumb =
  | { kind: 'doc'; ext: string }
  | { kind: 'cover'; gradient: string; glyph: IconName }
  | { kind: 'image'; src: string; fallbackGlyph?: IconName }

export interface AssetCardProps extends React.HTMLAttributes<HTMLDivElement> {
  thumb: AssetThumb
  title: string
  subtitle?: string
  meta?: React.ReactNode
  badge?: string
  selected?: boolean
}

export const AssetCard = React.forwardRef<HTMLDivElement, AssetCardProps>(
  (
    { thumb, title, subtitle, meta, badge, selected = false, className = '', ...props },
    ref
  ) => {
    const [imageLoadError, setImageLoadError] = React.useState(false)
    const [imageLoaded, setImageLoaded] = React.useState(false)

    React.useEffect(() => {
      setImageLoadError(false)
      setImageLoaded(false)
    }, [thumb.kind === 'image' ? thumb.src : null])

    const classNames = ['asset-card', selected && 'asset-card--selected', className]
      .filter(Boolean)
      .join(' ')

    const renderThumb = () => {
      if (thumb.kind === 'doc') {
        return (
          <div className="asset-card__thumb asset-card__thumb--doc">
            <div className="asset-card__doc-page" />
            <div className={`asset-card__doc-tab asset-card__doc-tab--${thumb.ext.toLowerCase()}`}>
              {thumb.ext.toUpperCase()}
            </div>
          </div>
        )
      }

      if (thumb.kind === 'cover') {
        return (
          <div
            className="asset-card__thumb asset-card__thumb--cover"
            style={{ '--cover-gradient': thumb.gradient } as React.CSSProperties & { '--cover-gradient': string }}
          >
            <Icon name={thumb.glyph} size={32} className="asset-card__cover-glyph" />
          </div>
        )
      }

      if (thumb.kind === 'image') {
        const showFallback = imageLoadError || (!imageLoaded && !thumb.src)

        if (showFallback && thumb.fallbackGlyph) {
          return (
            <div className="asset-card__thumb asset-card__thumb--image-fallback">
              <Icon name={thumb.fallbackGlyph} size={32} className="asset-card__image-glyph" />
            </div>
          )
        }

        return (
          <div className="asset-card__thumb asset-card__thumb--image">
            <img
              src={thumb.src}
              alt=""
              className="asset-card__image"
              onLoad={() => setImageLoaded(true)}
              onError={() => setImageLoadError(true)}
              aria-hidden="true"
            />
          </div>
        )
      }
    }

    return (
      <div
        ref={ref}
        className={classNames}
        aria-selected={selected}
        {...props}
      >
        <div className="asset-card__thumb-wrapper">
          {renderThumb()}
          {badge && (
            <div className="asset-card__badge">{badge}</div>
          )}
        </div>

        <div className="asset-card__body">
          <div className="asset-card__title">{title}</div>
          {subtitle && (
            <div className="asset-card__subtitle">{subtitle}</div>
          )}
          {meta && (
            <div className="asset-card__meta">{meta}</div>
          )}
        </div>
      </div>
    )
  }
)

AssetCard.displayName = 'AssetCard'

export default AssetCard
