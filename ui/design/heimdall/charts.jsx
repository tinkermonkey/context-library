// =============================================================================
// Heimdall design system — charts (LineChart, BarV, Donut).
// Ported verbatim from @tinkermonkey/heimdall-ui (src/components/*.tsx).
// SVG fragments converted to <g>; rest-spreads dropped for the runtime.
// =============================================================================
const { forwardRef: f3, useId: uid3, useState: us3 } = React;

// ---- chartColors.ts / chartTone.ts ----------------------------------------
const SERIES_COLORS = ['#22D3EE', '#10B981', '#F59E0B', '#818CF8', '#8B5CF6', '#F43F5E'];
const TONE = {
  light: { fg1: '#0B1220', fg2: '#475569', fg3: '#64748B', fg4: '#94A3B8', grid: '#EEF1F4', border: '#E5E9EE', card: '#FFFFFF', inset: '#F7F9FB' },
  dark:  { fg1: '#E2E8F0', fg2: '#94A3B8', fg3: '#64748B', fg4: '#475569', grid: '#1B2949', border: '#243763', card: '#1B2949', inset: '#13203A' },
};
function fmt(n) { return Math.abs(n) >= 1000 ? (n / 1000).toFixed(1) + 'k' : Number.isInteger(n) ? String(n) : n.toFixed(1); }

// ---- LineChart.tsx --------------------------------------------------------
const ACCENT_PRIMARY = '#F59E0B', ACCENT_PRIMARY_DEEP = '#B45309';
const POPOVER_BG = '#1B2949', POPOVER_BORDER = '#2A3A5C', POPOVER_FG = '#E6EDF3', POPOVER_FG_MUTED = '#A6B1BD';
const LineChart = f3(({ series, colors, xLabels, width = 480, height = 200, area = false, axes = false, grid = false, ticks = 4, threshold, markers, tooltip = false, tone = 'light', padding: paddingOverride, className = '', style }, ref) => {
  const T = TONE[tone];
  const gradBaseId = uid3();
  const cs = colors ?? (series.length === 1 ? [SERIES_COLORS[0]] : SERIES_COLORS);
  const pad = { top: 8, right: tooltip ? 12 : 8, bottom: axes ? 22 : 6, left: axes ? 30 : 6, ...paddingOverride };
  const innerW = width - pad.left - pad.right, innerH = height - pad.top - pad.bottom;
  const flat = series.flat();
  const [hover, setHover] = us3(null);
  if (flat.length === 0) return null;
  let lo = Math.min(...flat), hi = Math.max(...flat);
  const span = hi - lo || 1; lo -= span * 0.08; hi += span * 0.08;
  if (threshold) { lo = Math.min(lo, threshold.value); hi = Math.max(hi, threshold.value); }
  const n = Math.max(...series.map(s => s.length));
  const xAt = (i) => pad.left + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const yAt = (v) => pad.top + innerH - ((v - lo) / (hi - lo)) * innerH;
  const yTickVals = []; for (let i = 0; i <= ticks; i++) yTickVals.push(lo + (i / ticks) * (hi - lo));
  function onMove(e) { const rect = e.currentTarget.getBoundingClientRect(); const px = ((e.clientX - rect.left) / rect.width) * width; const idx = Math.max(0, Math.min(n - 1, Math.round(((px - pad.left) / innerW) * (n - 1)))); setHover(idx); }
  function makeLine(pts) { return pts.map(([x, y], i) => (i ? 'L' : 'M') + x.toFixed(2) + ',' + y.toFixed(2)).join(' '); }
  const seriesPts = series.map(s => s.map((v, i) => [xAt(i), yAt(v)]));
  return (
    <svg ref={ref} width={width} height={height} viewBox={`0 0 ${width} ${height}`} className={className} role="img" aria-label="Line chart"
      style={{ display: 'block', cursor: tooltip ? 'crosshair' : 'default', ...style }}
      onMouseMove={tooltip ? onMove : undefined} onMouseLeave={tooltip ? () => setHover(null) : undefined}>
      {grid && yTickVals.map((v, i) => <line key={'g' + i} x1={pad.left} x2={width - pad.right} y1={yAt(v)} y2={yAt(v)} stroke={T.grid} strokeWidth="1" />)}
      {axes && (
        <g>
          <line x1={pad.left} x2={pad.left} y1={pad.top} y2={pad.top + innerH} stroke={T.border} strokeWidth="1" />
          <line x1={pad.left} x2={width - pad.right} y1={pad.top + innerH} y2={pad.top + innerH} stroke={T.border} strokeWidth="1" />
          {yTickVals.map((v, i) => <text key={'yt' + i} x={pad.left - 6} y={yAt(v) + 3} textAnchor="end" fontFamily="JetBrains Mono, monospace" fontSize="10" fill={T.fg3}>{fmt(v)}</text>)}
          {xLabels && xLabels.map((lab, i) => <text key={'xt' + i} x={xAt(i)} y={pad.top + innerH + 14} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="10" fill={T.fg3}>{lab}</text>)}
        </g>
      )}
      {threshold && (
        <g>
          <line x1={pad.left} x2={width - pad.right} y1={yAt(threshold.value)} y2={yAt(threshold.value)} stroke={T.fg3} strokeWidth="1" strokeDasharray="3 3" />
          {threshold.label && <text x={width - pad.right - 4} y={yAt(threshold.value) - 4} textAnchor="end" fontFamily="JetBrains Mono, monospace" fontSize="9.5" fill={T.fg3} style={{ textTransform: 'uppercase', letterSpacing: '0.08em' }}>{threshold.label}</text>}
        </g>
      )}
      {markers && markers.map((m, i) => (
        <g key={'mk' + i}>
          <line x1={xAt(m.x)} x2={xAt(m.x)} y1={pad.top - 2} y2={pad.top + innerH} stroke={ACCENT_PRIMARY} strokeWidth="1" strokeDasharray="2 2" />
          <circle cx={xAt(m.x)} cy={pad.top + 4} r="3" fill={ACCENT_PRIMARY} />
          {m.label && <text x={xAt(m.x) + 6} y={pad.top + 7} fontFamily="JetBrains Mono, monospace" fontSize="9.5" fill={ACCENT_PRIMARY_DEEP} style={{ textTransform: 'uppercase', letterSpacing: '0.08em' }}>{m.label}</text>}
        </g>
      ))}
      {seriesPts.map((pts, si) => {
        const c = cs[si % cs.length];
        const line = makeLine(pts);
        const fillPath = `${line} L${pts[pts.length - 1][0].toFixed(2)},${pad.top + innerH} L${pts[0][0].toFixed(2)},${pad.top + innerH} Z`;
        const gradId = `${gradBaseId}-lg${si}`;
        return (
          <g key={'s' + si}>
            {area && (
              <g>
                <defs><linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={c} stopOpacity="0.22" /><stop offset="100%" stopColor={c} stopOpacity="0" /></linearGradient></defs>
                <path d={fillPath} fill={`url(#${gradId})`} />
              </g>
            )}
            <path d={line} stroke={c} strokeWidth={tooltip ? 1.75 : 1.5} fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </g>
        );
      })}
      {tooltip && hover !== null && (() => {
        const tw = 132, th = 18 + series.length * 16;
        let tx = xAt(hover) + 10; if (tx + tw > width - 4) tx = xAt(hover) - tw - 10;
        const ty = pad.top + 4;
        return (
          <g>
            <line x1={xAt(hover)} x2={xAt(hover)} y1={pad.top} y2={pad.top + innerH} stroke={T.fg3} strokeWidth="1" strokeDasharray="2 3" />
            {series.map((s, si) => s[hover] != null && <circle key={'h' + si} cx={xAt(hover)} cy={yAt(s[hover])} r="3" fill={T.card} stroke={cs[si % cs.length]} strokeWidth="1.75" />)}
            <rect x={tx} y={ty} width={tw} height={th} rx="6" fill={POPOVER_BG} stroke={POPOVER_BORDER} />
            <text x={tx + 9} y={ty + 13} fontFamily="JetBrains Mono, monospace" fontSize="9.5" fill={POPOVER_FG_MUTED} style={{ textTransform: 'uppercase', letterSpacing: '0.10em' }}>{xLabels ? xLabels[hover] : `t${hover}`}</text>
            {series.map((s, si) => (
              <g key={'tt' + si}>
                <rect x={tx + 9} y={ty + 22 + si * 16} width="6" height="6" rx="1" fill={cs[si % cs.length]} />
                <text x={tx + 20} y={ty + 28 + si * 16} fontFamily="JetBrains Mono, monospace" fontSize="10.5" fill={POPOVER_FG}>{s[hover] != null ? fmt(s[hover]) : '—'}</text>
              </g>
            ))}
          </g>
        );
      })()}
    </svg>
  );
});
LineChart.displayName = 'LineChart';

// ---- BarV.tsx -------------------------------------------------------------
const BarV = f3(({ values, xLabels, color, width = 480, height = 200, axes = false, grid = false, ticks = 4, threshold, tone = 'light', label, className = '', style }, ref) => {
  const T = TONE[tone];
  const c = color ?? SERIES_COLORS[2];
  const pad = { top: 8, right: 8, bottom: axes ? 22 : 6, left: axes ? 30 : 6 };
  const innerW = width - pad.left - pad.right, innerH = height - pad.top - pad.bottom;
  if (!values || values.length === 0) return null;
  const hi = Math.max(...values, threshold ? threshold.value : 0);
  const n = values.length;
  const gap = Math.max(2, (innerW / n) * 0.22);
  const bw = (innerW - gap * (n - 1)) / n;
  const yAt = (v) => pad.top + innerH - (v / (hi || 1)) * innerH;
  const yTickVals = []; for (let i = 0; i <= ticks; i++) yTickVals.push((i / ticks) * hi);
  return (
    <svg ref={ref} role="img" aria-label={label} width={width} height={height} viewBox={`0 0 ${width} ${height}`} className={className} style={{ display: 'block', ...style }}>
      {grid && yTickVals.map((v, i) => <line key={'g' + i} x1={pad.left} x2={width - pad.right} y1={yAt(v)} y2={yAt(v)} stroke={T.grid} strokeWidth="1" />)}
      {axes && (
        <g>
          <line x1={pad.left} x2={pad.left} y1={pad.top} y2={pad.top + innerH} stroke={T.border} strokeWidth="1" />
          <line x1={pad.left} x2={width - pad.right} y1={pad.top + innerH} y2={pad.top + innerH} stroke={T.border} strokeWidth="1" />
          {yTickVals.map((v, i) => <text key={'yt' + i} x={pad.left - 6} y={yAt(v) + 3} textAnchor="end" fontFamily="JetBrains Mono, monospace" fontSize="10" fill={T.fg3}>{fmt(v)}</text>)}
        </g>
      )}
      {values.map((v, i) => {
        const x = pad.left + i * (bw + gap), y = yAt(v);
        return (
          <g key={i}>
            <rect x={x} y={y} width={bw} height={pad.top + innerH - y} fill={c} rx="1" />
            {axes && xLabels && xLabels[i] !== undefined && <text x={x + bw / 2} y={pad.top + innerH + 14} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="10" fill={T.fg3}>{xLabels[i]}</text>}
          </g>
        );
      })}
      {threshold && (
        <g>
          <line x1={pad.left} x2={width - pad.right} y1={yAt(threshold.value)} y2={yAt(threshold.value)} stroke={T.fg3} strokeWidth="1" strokeDasharray="3 3" />
          {threshold.label && <text x={width - pad.right - 4} y={yAt(threshold.value) - 4} textAnchor="end" fontFamily="JetBrains Mono, monospace" fontSize="9.5" fill={T.fg3} style={{ textTransform: 'uppercase', letterSpacing: '0.08em' }}>{threshold.label}</text>}
        </g>
      )}
    </svg>
  );
});
BarV.displayName = 'BarV';

// ---- Donut.tsx ------------------------------------------------------------
const Donut = f3(({ slices, colors, width = 160, height = 160, thickness = 14, gap = 0.03, centerValue, centerLabel, 'aria-label': ariaLabel, tone = 'light', className = '', style }, ref) => {
  const T = TONE[tone];
  const cs = colors ?? SERIES_COLORS;
  if (!slices || slices.length === 0) return null;
  const cx = width / 2, cy = height / 2;
  const r = Math.min(width, height) / 2 - 4, ri = r - thickness;
  const total = slices.reduce((a, s) => a + s.value, 0) || 1;
  function arc(a0, a1) {
    const cos0 = Math.cos(a0), sin0 = Math.sin(a0), cos1 = Math.cos(a1), sin1 = Math.sin(a1);
    const large = a1 - a0 > Math.PI ? 1 : 0;
    return [`M ${cx + r * cos0} ${cy + r * sin0}`, `A ${r} ${r} 0 ${large} 1 ${cx + r * cos1} ${cy + r * sin1}`, `L ${cx + ri * cos1} ${cy + ri * sin1}`, `A ${ri} ${ri} 0 ${large} 0 ${cx + ri * cos0} ${cy + ri * sin0}`, 'Z'].join(' ');
  }
  const effectiveGap = slices.length > 1 ? gap : 0;
  let acc = -Math.PI / 2;
  const arcs = slices.map((s, i) => {
    const sp = (s.value / total) * Math.PI * 2;
    const a0 = acc + effectiveGap / 2;
    let a1 = acc + sp - effectiveGap / 2;
    if (a1 - a0 >= Math.PI * 2 - 1e-6) a1 = a0 + Math.PI * 2 - 1e-6;
    if (a1 <= a0) a1 = a0 + 1e-4;
    acc += sp;
    return { d: arc(a0, a1), color: s.color ?? cs[i % cs.length] };
  });
  const valFontSize = Math.min(width, height) * 0.22;
  const labelY = cy + Math.min(width, height) * 0.18;
  return (
    <svg ref={ref} role="img" aria-label={ariaLabel ?? 'Donut chart'} width={width} height={height} viewBox={`0 0 ${width} ${height}`} className={className} style={{ display: 'block', ...style }}>
      {arcs.map((a, i) => <path key={i} d={a.d} fill={a.color} />)}
      {centerValue != null && <text x={cx} y={cy + 1} textAnchor="middle" fontFamily="Inter, sans-serif" fontSize={valFontSize} fontWeight="700" fill={T.fg1} style={{ letterSpacing: '-0.02em', fontVariantNumeric: 'tabular-nums' }}>{centerValue}</text>}
      {centerLabel != null && <text x={cx} y={labelY} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="10" fill={T.fg3} style={{ textTransform: 'uppercase', letterSpacing: '0.08em' }}>{centerLabel}</text>}
    </svg>
  );
});
Donut.displayName = 'Donut';

Object.assign(window, { SERIES_COLORS, LineChart, BarV, Donut });
