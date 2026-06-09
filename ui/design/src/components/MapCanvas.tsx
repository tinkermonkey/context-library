import React, { useState, useRef, useCallback, useEffect, useId } from 'react'
import { usePanZoom } from '../hooks/usePanZoom'
import { useFocusTrap } from '../hooks/useFocusTrap'
import { getHeatmapColor, normalizeColorToHex } from '../utils/heatmapUtils'
import './MapCanvas.css'

// ─── Mercator Projection ──────────────────────────────────────────────────────

function latLngToPixels(lat: number, lng: number, zoom: number): { x: number; y: number } {
  const n = Math.pow(2, zoom)
  const x = ((lng + 180) / 360) * n * 256
  const clampedLat = Math.max(-85.05112878, Math.min(85.05112878, lat))
  const y = ((1 - Math.log(Math.tan((clampedLat * Math.PI) / 180) + 1 / Math.cos((clampedLat * Math.PI) / 180)) / Math.PI) / 2) * n * 256
  return { x, y }
}

function pixelsToLatLng(x: number, y: number, zoom: number): { lat: number; lng: number } {
  const n = Math.pow(2, zoom)
  const lng = (x / (n * 256)) * 360 - 180
  const lat = (Math.atan(Math.sinh(Math.PI * (1 - 2 * (y / (n * 256))))) * 180) / Math.PI
  return { lat, lng }
}

// ─── Public Types ─────────────────────────────────────────────────────────────

export interface LatLng {
  lat: number
  lng: number
}

export interface MapPin {
  id: string
  lat: number
  lng: number
  label?: string
  detail?: React.ReactNode
  timestamp?: string
}

export interface MapTrackPoint {
  lat: number
  lng: number
  timestamp?: string
}

export interface HeatmapDataPoint {
  lat: number
  lng: number
  value: number
}

type MapCanvasCommonProps = Omit<React.HTMLAttributes<HTMLDivElement>, 'onSelect'> & {
  bounds?: [LatLng, LatLng]
  tileUrl?: string | ((x: number, y: number, z: number) => string)
  scaleBar?: boolean
  minZoom?: number
  maxZoom?: number
  heatmapColor?: string
  onViewportChange?: (viewport: { center: { lat: number; lng: number }; zoom: number }) => void
  onModeChange?: (mode: 'pins' | 'track' | 'heatmap') => void
  pins?: MapPin[]
  selectedPinId?: string
  onSelectPin?: (pinId: string | null) => void
  trackPoints?: MapTrackPoint[]
  heatmapData?: HeatmapDataPoint[]
}

type MapCanvasPinsProps = MapCanvasCommonProps & {
  mode: 'pins'
  pins: MapPin[]
  trackPoints?: never
  heatmapData?: never
}

type MapCanvasTrackProps = MapCanvasCommonProps & {
  mode: 'track'
  trackPoints: MapTrackPoint[]
  pins?: never
  selectedPinId?: never
  onSelectPin?: never
  heatmapData?: never
}

type MapCanvasHeatmapProps = MapCanvasCommonProps & {
  mode: 'heatmap'
  heatmapData: HeatmapDataPoint[]
  pins?: never
  selectedPinId?: never
  onSelectPin?: never
  trackPoints?: never
}

export type MapCanvasProps = MapCanvasPinsProps | MapCanvasTrackProps | MapCanvasHeatmapProps

// ─── Grid Pattern ─────────────────────────────────────────────────────────────

interface GridPatternProps {
  patternId: string
  zoomLevel: number
}

function GridPattern({ patternId, zoomLevel }: GridPatternProps) {
  const tileSize = 32 * Math.pow(2, zoomLevel)
  return (
    <pattern
      id={patternId}
      x={0}
      y={0}
      width={tileSize}
      height={tileSize}
      patternUnits="userSpaceOnUse"
    >
      <rect width={tileSize} height={tileSize} fill="none" stroke="rgb(var(--canvas-fg-3))" strokeWidth="0.5" opacity="0.3" />
      <circle cx={0} cy={0} r={1} fill="rgb(var(--canvas-fg-3))" opacity="0.4" />
    </pattern>
  )
}

// ─── Pin Popover ──────────────────────────────────────────────────────────────

interface PinPopoverProps {
  pin: MapPin
  x: number
  y: number
  onClose: () => void
}

function PinPopover({ pin, x, y, onClose }: PinPopoverProps) {
  const popoverRef = useRef<HTMLDivElement>(null)
  useFocusTrap(popoverRef, true, { mode: 'popup' })

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }

    document.addEventListener('keydown', handleEscape)
    return () => {
      document.removeEventListener('keydown', handleEscape)
    }
  }, [onClose])

  return (
    <div
      ref={popoverRef}
      className="map-popover"
      style={{
        left: `${x}px`,
        top: `${y}px`,
      }}
      role="dialog"
    >
      {pin.label && <div className="map-popover__label">{pin.label}</div>}
      {pin.timestamp && <div className="map-popover__timestamp">{pin.timestamp}</div>}
      {pin.detail && <div className="map-popover__detail">{pin.detail}</div>}
    </div>
  )
}

// ─── MapCanvas ────────────────────────────────────────────────────────────────

export const MapCanvas = React.forwardRef<HTMLDivElement, MapCanvasProps>(
  (
    {
      mode,
      pins = [],
      selectedPinId,
      onSelectPin,
      trackPoints = [],
      heatmapData = [],
      heatmapColor = '#10b981',
      tileUrl,
      bounds,
      scaleBar = false,
      minZoom = 0,
      maxZoom = 18,
      onViewportChange,
      onModeChange,
      className = '',
      ...htmlProps
    },
    ref
  ) => {
    const containerRef = useRef<HTMLDivElement>(null)
    const [containerSize, setContainerSize] = useState<{ width: number; height: number } | null>(null)
    const [selectedPopover, setSelectedPopover] = useState<{ x: number; y: number } | null>(null)
    const didInitRef = useRef(false)

    const handleViewportChange = useCallback((vp: { x: number; y: number; zoom: number }) => {
      const center = pixelsToLatLng(vp.x / vp.zoom, vp.y / vp.zoom, Math.round(vp.zoom * 4))
      onViewportChange?.({
        center: { lat: center.lat, lng: center.lng },
        zoom: vp.zoom,
      })
    }, [onViewportChange])

    const { transform, viewport, bind, panTo } = usePanZoom({
      minZoom,
      maxZoom,
      onViewportChange: handleViewportChange,
    })

    const rawId = useId()
    const gridPatternId = `map-grid-${rawId.replace(/:/g, '')}`

    useEffect(() => {
      const container = containerRef.current
      if (!container) return
      const ro = new ResizeObserver((entries) => {
        const { width, height } = entries[0].contentRect
        if (width > 0 && height > 0) setContainerSize({ width, height })
      })
      ro.observe(container)
      return () => ro.disconnect()
    }, [])

    // Initialize bounds on first render
    useEffect(() => {
      if (didInitRef.current || !containerSize) return
      if (!bounds && pins.length === 0 && trackPoints.length === 0 && heatmapData.length === 0) return

      const items = [
        ...pins.map((p) => ({ lat: p.lat, lng: p.lng })),
        ...trackPoints.map((t) => ({ lat: t.lat, lng: t.lng })),
        ...heatmapData.map((h) => ({ lat: h.lat, lng: h.lng })),
      ]

      // Convert bounds tuple to object format, or derive from items
      let boundsToUse: { north: number; south: number; east: number; west: number } | null = null
      if (bounds) {
        boundsToUse = {
          north: Math.max(bounds[0].lat, bounds[1].lat),
          south: Math.min(bounds[0].lat, bounds[1].lat),
          east: Math.max(bounds[0].lng, bounds[1].lng),
          west: Math.min(bounds[0].lng, bounds[1].lng),
        }
      } else if (items.length > 0) {
        const lats = items.map((i) => i.lat)
        const lngs = items.map((i) => i.lng)
        boundsToUse = {
          north: Math.max(...lats),
          south: Math.min(...lats),
          east: Math.max(...lngs),
          west: Math.min(...lngs),
        }
      }

      if (!boundsToUse) return

      // Fit bounds: add padding and calculate zoom
      const padding = 60
      const northPixel = latLngToPixels(boundsToUse.north, boundsToUse.west, 10).y
      const southPixel = latLngToPixels(boundsToUse.south, boundsToUse.east, 10).y
      const westPixel = latLngToPixels(boundsToUse.north, boundsToUse.west, 10).x
      const eastPixel = latLngToPixels(boundsToUse.north, boundsToUse.east, 10).x

      const height = Math.abs(southPixel - northPixel)
      const width = Math.abs(eastPixel - westPixel)

      // Handle edge cases: zero dimensions or container too small
      if (height === 0 || width === 0 || containerSize.height <= padding * 2 || containerSize.width <= padding * 2) {
        // Fall back to a default zoom level
        panTo(containerSize.width / 2, containerSize.height / 2)
        didInitRef.current = true
        return
      }

      const zoomH = Math.log2((containerSize.height - padding * 2) / height)
      const zoomW = Math.log2((containerSize.width - padding * 2) / width)

      // Ensure zoom is valid (not NaN, not Infinity)
      if (!Number.isFinite(zoomH) || !Number.isFinite(zoomW)) {
        panTo(containerSize.width / 2, containerSize.height / 2)
        didInitRef.current = true
        return
      }

      const calculatedZoom = Math.max(minZoom, Math.min(maxZoom, Math.floor(Math.min(zoomH, zoomW))))

      const centerLat = (boundsToUse.north + boundsToUse.south) / 2
      const centerLng = (boundsToUse.east + boundsToUse.west) / 2
      const centerPixel = latLngToPixels(centerLat, centerLng, calculatedZoom)

      const panX = containerSize.width / 2 - centerPixel.x * calculatedZoom
      const panY = containerSize.height / 2 - centerPixel.y * calculatedZoom

      panTo(panX, panY)
      didInitRef.current = true
    }, [containerSize, bounds, pins.length, trackPoints.length, heatmapData.length, minZoom, maxZoom, panTo])

    const handlePointerDown = useCallback(
      (e: React.PointerEvent<HTMLDivElement>) => {
        if (
          e.target instanceof Element &&
          (e.target.closest('.map-pin') || e.target.closest('.map-popover') || e.target.closest('[data-no-drag]'))
        ) {
          return
        }
        bind.onPointerDown(e)
      },
      [bind]
    )

    const renderPins = useCallback(() => {
      if (mode !== 'pins' || !pins.length) return null

      return (
        <div className="map-pins" data-testid="map-pins" style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
          {pins.map((pin) => {
            const pixel = latLngToPixels(pin.lat, pin.lng, Math.round(viewport.zoom * 4))
            const screenX = viewport.x + pixel.x * viewport.zoom
            const screenY = viewport.y + pixel.y * viewport.zoom

            return (
              <button
                type="button"
                key={pin.id}
                className={['map-pin', selectedPinId === pin.id && 'map-pin--selected'].filter(Boolean).join(' ')}
                onClick={(e) => {
                  e.stopPropagation()
                  onSelectPin?.(pin.id)
                  const rect = (e.target as HTMLElement).getBoundingClientRect()
                  setSelectedPopover({ x: rect.right + 8, y: rect.top })
                }}
                aria-label={`${pin.label || 'Pin'} at latitude ${pin.lat.toFixed(4)}, longitude ${pin.lng.toFixed(4)}${
                  pin.timestamp ? ` on ${pin.timestamp}` : ''
                }`}
                data-testid={`map-pin-${pin.id}`}
                data-no-drag
                style={{
                  position: 'absolute',
                  left: `${screenX}px`,
                  top: `${screenY}px`,
                  pointerEvents: 'auto',
                }}
              >
                <span className="map-pin__dot" />
                {pin.label && <span className="map-pin__label">{pin.label}</span>}
              </button>
            )
          })}
        </div>
      )
    }, [mode, pins, viewport.zoom, viewport.x, viewport.y, selectedPinId, onSelectPin])

    const renderTrack = useCallback(() => {
      if (mode !== 'track' || !trackPoints.length) return null

      const points = trackPoints.map((p) => latLngToPixels(p.lat, p.lng, Math.round(viewport.zoom * 4)))
      const pathData = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')

      return (
        <g className="map-track" data-testid="map-track">
          <path d={pathData} className="map-track__line" />
        </g>
      )
    }, [mode, trackPoints, viewport.zoom])

    const renderHeatmap = useCallback(() => {
      if (mode !== 'heatmap' || !heatmapData.length) return null

      const values = heatmapData.map((h) => h.value).filter((v) => v != null)
      const minValue = Math.min(...values)
      const maxValue = Math.max(...values)

      return (
        <g className="map-heatmap" data-testid="map-heatmap">
          {heatmapData.map((point, i) => {
            const pixel = latLngToPixels(point.lat, point.lng, Math.round(viewport.zoom * 4))
            const t = (point.value - minValue) / (maxValue - minValue || 1)
            const fill = getHeatmapColor(point.value, minValue, maxValue, heatmapColor)

            return (
              <circle
                key={i}
                cx={pixel.x}
                cy={pixel.y}
                r={8 + t * 4}
                fill={fill}
                opacity={0.6}
                data-testid={`heatmap-point-${i}`}
              />
            )
          })}
        </g>
      )
    }, [mode, heatmapData, heatmapColor, viewport.zoom])

    const renderTiles = useCallback(() => {
      if (!tileUrl || !containerSize) return null

      const zoom = Math.min(Math.max(Math.floor(viewport.zoom * 4), 0), 28)
      const n = Math.pow(2, zoom)

      // Calculate visible tile range
      const xStart = Math.max(0, Math.floor(-viewport.x / (256 * viewport.zoom)))
      const yStart = Math.max(0, Math.floor(-viewport.y / (256 * viewport.zoom)))
      const xEnd = Math.min(n, Math.ceil((containerSize.width - viewport.x) / (256 * viewport.zoom)))
      const yEnd = Math.min(n, Math.ceil((containerSize.height - viewport.y) / (256 * viewport.zoom)))

      const getTileUrl = typeof tileUrl === 'function' ? tileUrl : (x: number, y: number, z: number) => {
        return (tileUrl as string).replace('{x}', String(x)).replace('{y}', String(y)).replace('{z}', String(z))
      }

      const tiles = []
      for (let x = xStart; x < xEnd; x++) {
        for (let y = yStart; y < yEnd; y++) {
          const url = getTileUrl(x, y, zoom)
          tiles.push(
            <image
              key={`${zoom}-${x}-${y}`}
              href={url}
              x={x * 256}
              y={y * 256}
              width={256}
              height={256}
              data-testid={`tile-${x}-${y}`}
            />
          )
        }
      }
      return tiles
    }, [tileUrl, containerSize, viewport])

    const handleRef = (el: HTMLDivElement | null) => {
      if (typeof ref === 'function') ref(el)
      else if (ref) (ref as React.MutableRefObject<HTMLDivElement | null>).current = el
      ;(containerRef as React.MutableRefObject<HTMLDivElement | null>).current = el
    }

    return (
      <div
        ref={handleRef}
        className={['map-canvas', className].filter(Boolean).join(' ')}
        {...bind}
        onPointerDown={handlePointerDown}
        role="application"
        aria-label="Map canvas"
        {...htmlProps}
      >
        <svg
          className="map-svg"
          width="100%"
          height="100%"
          style={{ position: 'absolute', inset: 0, overflow: 'visible' }}
        >
          <defs>
            <GridPattern patternId={gridPatternId} zoomLevel={viewport.zoom} />
          </defs>

          {/* Background: tiles or grid */}
          {tileUrl ? (
            <g className="map-tiles" transform={transform}>
              {renderTiles()}
            </g>
          ) : (
            <rect width="100%" height="100%" fill={`url(#${gridPatternId})`} className="map-grid" />
          )}

          {/* Content layer with pan/zoom */}
          <g className="map-viewport" transform={transform}>
            {renderTrack()}
            {renderHeatmap()}
          </g>
        </svg>

        {/* Pins rendered as HTML overlay */}
        {renderPins()}

        {/* Overlay chrome */}
        <div className="map-overlay">
          {mode === 'track' && (
            <div className="map-legend">
              <div className="map-legend__item">
                <div className="map-legend__line" style={{ backgroundColor: 'rgb(var(--status-cyan))' }} />
                Track
              </div>
            </div>
          )}

          {mode === 'heatmap' && (
            <div className="map-legend">
              <div className="map-legend__item">
                <div
                  className="map-legend__gradient"
                  style={{
                    backgroundImage: `linear-gradient(to right, ${normalizeColorToHex(heatmapColor)}20, ${normalizeColorToHex(heatmapColor)}cc)`,
                  }}
                />
                Density
              </div>
            </div>
          )}

          {onModeChange && (
            <div className="map-mode-switch">
              <button
                type="button"
                className={['map-mode-switch__button', mode === 'pins' && 'map-mode-switch__button--active'].filter(Boolean).join(' ')}
                onClick={() => onModeChange('pins')}
                aria-label="Switch to pins mode"
                title="Pins"
              >
                Pins
              </button>
              <button
                type="button"
                className={['map-mode-switch__button', mode === 'track' && 'map-mode-switch__button--active'].filter(Boolean).join(' ')}
                onClick={() => onModeChange('track')}
                aria-label="Switch to track mode"
                title="Track"
              >
                Track
              </button>
              <button
                type="button"
                className={['map-mode-switch__button', mode === 'heatmap' && 'map-mode-switch__button--active'].filter(Boolean).join(' ')}
                onClick={() => onModeChange('heatmap')}
                aria-label="Switch to heatmap mode"
                title="Heatmap"
              >
                Heatmap
              </button>
            </div>
          )}

          {scaleBar && (
            <div className="map-scale-bar">
              <div className="map-scale-bar__label">Zoom: {viewport.zoom.toFixed(1)}</div>
            </div>
          )}
        </div>

        {/* Pin popover */}
        {selectedPinId && selectedPopover && (() => {
          const selectedPin = pins.find((p) => p.id === selectedPinId)
          return selectedPin ? (
            <PinPopover
              pin={selectedPin}
              x={selectedPopover.x}
              y={selectedPopover.y}
              onClose={() => {
                onSelectPin?.(null)
                setSelectedPopover(null)
              }}
            />
          ) : null
        })()}
      </div>
    )
  }
)

MapCanvas.displayName = 'MapCanvas'

export default MapCanvas
