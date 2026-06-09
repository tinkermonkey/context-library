// Location domain · map + visits — rebuilt on real heimdall components.
// Real DS: Panel, SegmentedControl, FilterDropdown, KVGrid, VersionPill, Button, Icon.
// Shipped in heimdall: MapCanvas. Reuse: VisitTimeline → ActivityTimeline.

const { useState: useLocState } = React;

function FakeMap() {
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
      <path d="M55,50 Q72,50 75,62 Q70,72 60,70 Q52,65 55,50 Z" fill="rgba(16,185,129,0.10)" stroke="rgba(16,185,129,0.20)" strokeWidth="0.2" />
      <path d="M10,20 L24,18 L30,30 L20,38 Z" fill="rgba(16,185,129,0.08)" />
      <path d="M0,5 Q40,8 60,18 L70,28 L80,40 L100,45 L100,0 L0,0 Z" fill="rgba(34,211,238,0.08)" stroke="rgba(34,211,238,0.15)" strokeWidth="0.2" />
      <g stroke="rgba(20,30,46,0.10)" strokeWidth="0.3">
        <line x1="0" y1="36" x2="100" y2="34" /><line x1="0" y1="52" x2="100" y2="50" /><line x1="0" y1="68" x2="100" y2="66" /><line x1="0" y1="84" x2="100" y2="82" />
        <line x1="20" y1="0" x2="22" y2="100" /><line x1="40" y1="0" x2="42" y2="100" /><line x1="60" y1="0" x2="62" y2="100" /><line x1="80" y1="0" x2="82" y2="100" />
      </g>
      <g stroke="rgba(20,30,46,0.18)" strokeWidth="0.5"><line x1="0" y1="58" x2="100" y2="56" /><line x1="48" y1="0" x2="50" y2="100" /></g>
      <polyline points="30,68 38,60 44,54 48,48 52,42 56,36 58,28 62,32 68,42 68,56 60,62 50,66 40,68 32,70" className="map-track" />
    </svg>
  );
}
function Pin({ x, y, label, active, detail }) {
  return (
    <div className={'map-pin' + (active ? ' active' : '')} style={{ left: x + '%', top: y + '%' }}>
      <div className="lbl">{label}</div>
      <div className="ring"></div>
      {active && <div style={{ position: 'absolute', top: '100%', marginTop: 6, left: '50%', transform: 'translateX(-50%)', padding: '5px 10px', background: 'var(--cl-canvas-card)', border: '1px solid rgb(var(--accent-primary))', borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--cl-canvas-fg-1)', whiteSpace: 'nowrap', boxShadow: '0 2px 8px rgba(0,0,0,0.10)' }}>{detail}</div>}
    </div>
  );
}
function Stat({ l, v, u }) {
  return (
    <div>
      <div className="eyebrow" style={{ marginBottom: 3, fontSize: 9.5 }}>{l}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 3 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 600, color: 'var(--cl-canvas-fg-1)', fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>{v}</span>
        {u && <span style={{ fontSize: 10.5, color: 'var(--cl-canvas-fg-3)' }}>{u}</span>}
      </div>
    </div>
  );
}
function Visit({ time, arrive, last, selected, name, addr, dwell, how, notes }) {
  return (
    <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--cl-canvas-border)', display: 'grid', gridTemplateColumns: '48px 1fr', gap: 12, cursor: 'pointer', background: selected ? 'rgba(251,191,36,0.05)' : 'transparent', borderLeft: selected ? '2px solid rgb(var(--accent-primary))' : '2px solid transparent', paddingLeft: selected ? 12 : 14 }}>
      <div style={{ textAlign: 'center', position: 'relative' }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--cl-canvas-fg-1)', fontWeight: 500 }}>{time}</div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--cl-canvas-fg-4)', letterSpacing: '0.08em', textTransform: 'uppercase', marginTop: 2 }}>{arrive ? 'arrive' : last ? 'last' : 'leave'}</div>
        {!last && <div style={{ position: 'absolute', left: '50%', top: 30, bottom: -10, borderLeft: '1px dashed var(--cl-canvas-border-strong)' }}></div>}
      </div>
      <div>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--cl-canvas-fg-1)', marginBottom: 2 }}>{name}</div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--cl-canvas-fg-3)', marginBottom: 4 }}>{addr}</div>
        <div style={{ display: 'flex', gap: 10, fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--cl-canvas-fg-3)' }}>
          <span>{dwell}</span><span style={{ color: 'var(--cl-canvas-fg-4)' }}>·</span><span>{how}</span>
        </div>
        {notes && <div style={{ marginTop: 6, padding: '4px 8px', background: 'var(--cl-canvas-bg-2)', borderLeft: '2px solid rgb(var(--accent-primary))', fontSize: 11.5, color: 'var(--cl-canvas-fg-2)' }}>{notes}</div>}
      </div>
    </div>
  );
}

function LocationScreen() {
  const [view, setView] = useLocState('visits');
  return (
    <CLShell active="location" breadcrumbs={['domain', 'location', 'oct 22', 'mission bay coffee']}>
      <div className="cl-fill" style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: 14 }}>
        <Panel noPadding className="cl-pane"
          title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13 }}><span className="dom-dot location"></span>San Francisco · oct 22</span>}
          headerAction={<span className="row" style={{ gap: 8 }}>
            <span className="tbb-flag shipped"><Icon name="tag" size={10} /> heimdall · MapCanvas</span>
            <SegmentedControl value={view} onChange={setView} options={[{ value: 'visits', label: 'visits' }, { value: 'track', label: 'track' }, { value: 'heatmap', label: 'heatmap' }]} />
          </span>}>
          <div style={{ position: 'relative', flex: 1, minHeight: 0 }}>
            <div className="map-wrap" style={{ borderRadius: 0, border: 0, height: '100%' }}>
              <div className="map-grid"></div>
              <FakeMap />
              <Pin x={30} y={68} label="Home" detail="6:14a → 8:42a" />
              <Pin x={48} y={48} label="Mission Bay Coffee" active detail="9:01a → 11:18a · selected" />
              <Pin x={58} y={28} label="Studio HQ" detail="11:42a → 17:38p" />
              <Pin x={68} y={56} label="Dolores Park" detail="18:02p → 19:24p" />
              <Pin x={32} y={70} label="Home" detail="19:48p →" />
            </div>
            <div style={{ position: 'absolute', right: 14, bottom: 14, padding: '6px 10px', background: 'rgba(247,243,234,0.92)', border: '1px solid var(--cl-canvas-border)', borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--cl-canvas-fg-3)', display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ width: 42, height: 0, borderBottom: '2px solid var(--cl-canvas-fg-2)' }}></div><span>1 km</span>
            </div>
          </div>
        </Panel>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minHeight: 0 }}>
          <Panel title="Day · oct 22" headerAction={<span className="eyebrow">5 VISITS · 12.4 KM</span>}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
              <Stat l="VISITS" v="5" /><Stat l="TRAVEL" v="12.4" u="km" /><Stat l="HOME" v="59" u="%" />
            </div>
          </Panel>
          <Panel noPadding className="cl-pane" style={{ flex: 1, minHeight: 0 }}
            title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}><Icon name="clock" size={13} />Visit log</span>}
            headerAction={<span className="eyebrow">EARLIEST ↑</span>}>
            <div className="cl-scroll">
              <Visit time="06:14" arrive name="Home" addr="Glen Park · sf" dwell="2h 28m" how="awake" />
              <Visit time="09:01" arrive selected name="Mission Bay Coffee" addr="3rd St · sf" dwell="2h 17m" how="walk + bus" notes="meeting · ana · diff stage walkthrough" />
              <Visit time="11:42" arrive name="Studio HQ" addr="Townsend · sf" dwell="5h 56m" how="walk" />
              <Visit time="18:02" arrive name="Dolores Park" addr="Dolores St · sf" dwell="1h 22m" how="walk" />
              <Visit time="19:48" arrive last name="Home" addr="Glen Park · sf" dwell="—" how="bus" />
            </div>
          </Panel>
          <Panel noPadding
            title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}><Icon name="link" size={13} />Mission Bay Coffee</span>}
            headerAction={<VersionPill>v2</VersionPill>}>
            <KVGrid keyWidth={110} rows={[
              { key: 'COORDS', value: <span className="mono" style={{ fontSize: 11 }}>37.7708, −122.3886</span> },
              { key: 'ARRIVAL', value: <span className="mono" style={{ fontSize: 11.5 }}>2024-10-22 09:01</span> },
              { key: 'DEPARTURE', value: <span className="mono" style={{ fontSize: 11.5 }}>2024-10-22 11:18</span> },
              { key: 'DWELL', value: <span className="mono" style={{ fontSize: 11.5 }}>2h 17m</span> },
              { key: 'CHUNK_HASH', value: <span className="mono" style={{ fontSize: 11.5 }}>f1a92e0b8c7d…</span> },
            ]} />
          </Panel>
        </div>
      </div>
    </CLShell>
  );
}

window.LocationScreen = LocationScreen;
