import React, { useState } from 'react'
import './Avatar.css'
import type { StatusColor } from './statusColors'

export type AvatarSize = 'xs' | 'sm' | 'md' | 'lg'
export type AvatarShape = 'circle' | 'rounded'

export interface AvatarProps extends React.HTMLAttributes<HTMLDivElement> {
  name: string
  src?: string
  size?: AvatarSize
  shape?: AvatarShape
  status?: StatusColor
  color?: StatusColor | string
  decorative?: boolean
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .slice(0, 2)
    .map((word) => word[0])
    .join('')
    .toUpperCase()
}

const COLOR_GRADIENTS: Record<StatusColor, string> = {
  amber: 'linear-gradient(135deg, rgb(var(--accent-primary)), rgb(var(--accent-primary-deep)))',
  emerald: 'linear-gradient(135deg, rgb(var(--status-emerald)), rgb(var(--semantic-emerald-fg)))',
  rose: 'linear-gradient(135deg, rgb(var(--status-rose)), rgb(var(--status-rose-deep)))',
  cyan: 'linear-gradient(135deg, rgb(var(--status-cyan)), rgb(var(--status-cyan-deep)))',
  violet: 'linear-gradient(135deg, rgb(var(--status-violet)), rgb(var(--semantic-violet-fg)))',
  neutral: 'linear-gradient(135deg, rgb(var(--status-neutral)), rgb(var(--semantic-neutral-fg)))',
}

const COLOR_KEYS = Object.keys(COLOR_GRADIENTS) as StatusColor[]

function hashString(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i)
    hash = ((hash << 5) - hash) + char
    hash = hash & hash
  }
  return Math.abs(hash)
}

function getColorFromName(name: string): StatusColor {
  const hash = hashString(name)
  const colorIndex = hash % COLOR_KEYS.length
  return COLOR_KEYS[colorIndex]
}

function getGradientBackground(color?: StatusColor | string, name?: string): string {
  if (color && color in COLOR_GRADIENTS) {
    return COLOR_GRADIENTS[color as StatusColor]
  }

  if (color) {
    return color
  }

  if (name) {
    const derivedColor = getColorFromName(name)
    return COLOR_GRADIENTS[derivedColor]
  }

  return COLOR_GRADIENTS.amber
}

export const Avatar = React.forwardRef<HTMLDivElement, AvatarProps>(
  ({ name, src, size = 'md', shape = 'circle', status, color, decorative, className = '', style, ...props }, ref) => {
    const [imageError, setImageError] = useState(false)

    const initials = getInitials(name)

    const showInitials = !src || imageError

    const classNames = [
      'avatar',
      `avatar--${size}`,
      `avatar--${shape}`,
      className,
    ]
      .filter(Boolean)
      .join(' ')

    const initialsStyle = !showInitials ? { display: 'none' } : {
      background: getGradientBackground(color, name),
    }

    const imageStyle = showInitials ? { display: 'none' } : {}

    return (
      <div
        ref={ref}
        className={classNames}
        style={style}
        role={decorative ? undefined : 'img'}
        aria-label={decorative ? undefined : (status ? `${name} (${status})` : name)}
        aria-hidden={decorative ? 'true' : undefined}
        {...props}
      >
        <div className="avatar__initials" style={initialsStyle}>
          {initials}
        </div>

        {src && (
          <img
            className="avatar__image"
            src={src}
            alt=""
            onError={() => setImageError(true)}
            style={imageStyle}
          />
        )}

        {status && (
          <div
            className={`avatar__status avatar__status--${status}`}
            aria-label={status}
          />
        )}
      </div>
    )
  }
)

Avatar.displayName = 'Avatar'

export default Avatar
