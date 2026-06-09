export function normalizeColorToHex(color: string): string {
  const trimmed = color.trim()

  // Already hex format
  if (/^#[0-9a-fA-F]{6}$/i.test(trimmed)) {
    return trimmed
  }

  // 3-digit hex — expand to 6-digit
  if (/^#[0-9a-fA-F]{3}$/i.test(trimmed)) {
    const shortColor = trimmed.slice(1)
    return '#' + shortColor[0] + shortColor[0] + shortColor[1] + shortColor[1] + shortColor[2] + shortColor[2]
  }

  // rgb(r, g, b) or rgba(r, g, b, a)
  const rgbMatch = trimmed.match(/rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/)
  if (rgbMatch) {
    const r = Math.max(0, Math.min(255, parseInt(rgbMatch[1], 10)))
    const g = Math.max(0, Math.min(255, parseInt(rgbMatch[2], 10)))
    const b = Math.max(0, Math.min(255, parseInt(rgbMatch[3], 10)))
    return '#' + [r, g, b].map((x) => x.toString(16).padStart(2, '0')).join('')
  }

  // hsl(h, s%, l%) or hsla(h, s%, l%, a)
  const hslMatch = trimmed.match(/hsla?\s*\(\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)%\s*,\s*(\d+(?:\.\d+)?)%/)
  if (hslMatch) {
    const h = parseFloat(hslMatch[1]) / 360
    const s = parseFloat(hslMatch[2]) / 100
    const l = parseFloat(hslMatch[3]) / 100

    const c = (1 - Math.abs(2 * l - 1)) * s
    const x = c * (1 - Math.abs(((h * 6) % 2) - 1))
    const m = l - c / 2

    let r = 0,
      g = 0,
      b = 0
    if (h < 1 / 6) {
      r = c
      g = x
    } else if (h < 2 / 6) {
      r = x
      g = c
    } else if (h < 3 / 6) {
      g = c
      b = x
    } else if (h < 4 / 6) {
      g = x
      b = c
    } else if (h < 5 / 6) {
      r = x
      b = c
    } else {
      r = c
      b = x
    }

    const toHex = (v: number) => Math.round((v + m) * 255)
      .toString(16)
      .padStart(2, '0')
    return '#' + toHex(r) + toHex(g) + toHex(b)
  }

  // Named colors — map common ones and CSS standard colors
  const namedColors: Record<string, string> = {
    black: '#000000',
    white: '#ffffff',
    red: '#ff0000',
    green: '#008000',
    blue: '#0000ff',
    yellow: '#ffff00',
    cyan: '#00ffff',
    magenta: '#ff00ff',
    gray: '#808080',
    grey: '#808080',
    silver: '#c0c0c0',
    maroon: '#800000',
    olive: '#808000',
    lime: '#00ff00',
    aqua: '#00ffff',
    teal: '#008080',
    navy: '#000080',
    purple: '#800080',
    fuchsia: '#ff00ff',
  }

  const lowerColor = trimmed.toLowerCase()
  if (lowerColor in namedColors) {
    return namedColors[lowerColor]
  }

  // Unrecognized color — provide diagnostic feedback
  if (process.env.NODE_ENV === 'development') {
    console.warn(
      `normalizeColorToHex: Unrecognized color format "${color}". Supported formats: hex (#rrggbb), rgb(r, g, b), hsl(h, s%, l%), or CSS named colors. Falling back to emerald (#10b981).`
    )
  }

  // Default to emerald (standard Tailwind color) instead of black
  return '#10b981'
}

export function getHeatmapColor(value: number, minValue: number, maxValue: number, baseColor: string): string {
  const t = (value - minValue) / (maxValue - minValue || 1)
  const alpha = Math.round((0.12 + t * 0.88) * 255)
    .toString(16)
    .padStart(2, '0')
  const hex = normalizeColorToHex(baseColor)
  return `${hex}${alpha}`
}
