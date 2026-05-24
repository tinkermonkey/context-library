// Location domain — map + visit log
// Adapters: apple.location. LocationMetadata: place_name, latitude, longitude, arrival_date.
// Context header: "{place_name} — {arrival_date}" or "Current location — …" for snapshots.

function LocationScreen() {
  return (
    <Shell active="location" breadcrumbs={['domain', 'location', 'oct 22', 'mission bay coffee']}>
      <div className="canvas-inner" style={{padding:0, minWidth:0}}>
        <div style={{display:'grid', gridTemplateColumns:'1fr 380px', gap:14, padding:14,
                     height:'100%', minHeight:0}}>

          {/* Map */}
          <div className="panel" style={{padding:0, display:'flex', flexDirection:'column', overflow:'hidden'}}>
            <div className="panel-head" style={{padding:'10px 14px'}}>
              <div className="panel-title" style={{fontSize:13}}>
                <span className="dom-dot location"></span>San Francisco · oct 22
              </div>
              <div className="seg">
                <button className="active">visits</button>
                <button>track</button>
                <button>heatmap</button>
              </div>
              <FDPanel label="DATE" value="oct 22 · tue"/>
              <button className="btn btn-ghost btn-sm">today</button>
            </div>

            <div style={{position:'relative', flex:1, minHeight:0}}>
              <div className="map-wrap" style={{borderRadius:0, border:0}}>
                <div className="map-grid"></div>
                <FakeMap/>
                <Pin x={30} y={68} label="Home" detail="6:14a → 8:42a"/>
                <Pin x={48} y={48} label="Mission Bay Coffee" active detail="9:01a → 11:18a · selected"/>
                <Pin x={58} y={28} label="Studio HQ" detail="11:42a → 17:38p"/>
                <Pin x={68} y={56} label="Dolores Park" detail="18:02p → 19:24p"/>
                <Pin x={32} y={70} label="Home" detail="19:48p →"/>
              </div>

              {/* Map overlay legend */}
              <div style={{position:'absolute', left:14, top:14,
                            padding:'8px 12px', background:'rgba(247,243,234,0.92)',
                            backdropFilter:'blur(4px)',
                            border:'1px solid var(--canvas-border)',
                            borderRadius:'var(--radius-md)',
                            fontFamily:'var(--font-mono)', fontSize:10.5,
                            display:'flex', flexDirection:'column', gap:4}}>
                <div style={{display:'flex', alignItems:'center', gap:6}}>
                  <span style={{width:8, height:8, borderRadius:'50%', background:'var(--dom-location)'}}></span>
                  <span>place visit · ≥ 5 min</span>
                </div>
                <div style={{display:'flex', alignItems:'center', gap:6}}>
                  <span style={{display:'inline-block', width:14, height:0,
                                 borderBottom:'2px dashed rgba(20, 184, 166, 0.45)'}}></span>
                  <span>track · gps</span>
                </div>
              </div>

              {/* Scale */}
              <div style={{position:'absolute', right:14, bottom:14,
                            padding:'6px 10px', background:'rgba(247,243,234,0.92)',
                            border:'1px solid var(--canvas-border)',
                            borderRadius:'var(--radius-md)',
                            fontFamily:'var(--font-mono)', fontSize:10.5,
                            color:'var(--canvas-fg-3)',
                            display:'flex', alignItems:'center', gap:8}}>
                <div style={{width:42, height:0, borderBottom:'2px solid var(--canvas-fg-2)'}}></div>
                <span>1 km</span>
              </div>
            </div>
          </div>

          {/* Right: visit log + selected place */}
          <div style={{display:'flex', flexDirection:'column', gap:14, minHeight:0}}>
            {/* Day summary */}
            <div className="panel">
              <div className="panel-head" style={{padding:'10px 12px'}}>
                <div className="panel-title" style={{fontSize:12.5}}><Icon name="globe" size={13}/>Day · oct 22</div>
                <span className="eyebrow">5 VISITS · 12.4 KM</span>
              </div>
              <div style={{padding:'10px 14px', display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:10}}>
                <Stat l="VISITS" v="5"/>
                <Stat l="TRAVEL" v="12.4" u="km"/>
                <Stat l="HOME" v="59" u="%"/>
              </div>
            </div>

            {/* Visit log */}
            <div className="panel" style={{flex:1, minHeight:0, display:'flex', flexDirection:'column', overflow:'hidden'}}>
              <div className="panel-head" style={{padding:'10px 12px'}}>
                <div className="panel-title" style={{fontSize:12.5}}><Icon name="history" size={13}/>Visit log</div>
                <span className="eyebrow">EARLIEST ↑</span>
              </div>
              <div style={{flex:1, overflow:'auto'}}>
                <Visit time="06:14"  arrive name="Home" addr="Glen Park · sf" dwell="2h 28m" how="awake"/>
                <Visit time="09:01" arrive selected name="Mission Bay Coffee" addr="3rd St · sf" dwell="2h 17m" how="walk + bus" notes="meeting · ana · diff stage walkthrough"/>
                <Visit time="11:42" arrive name="Studio HQ" addr="Townsend · sf" dwell="5h 56m" how="walk"/>
                <Visit time="18:02" arrive name="Dolores Park" addr="Dolores St · sf" dwell="1h 22m" how="walk"/>
                <Visit time="19:48" arrive last name="Home" addr="Glen Park · sf" dwell="—" how="bus"/>
              </div>
            </div>

            {/* Selected visit detail */}
            <div className="panel">
              <div className="panel-head" style={{padding:'10px 12px'}}>
                <div className="panel-title" style={{fontSize:12.5}}><Icon name="link" size={13}/>Mission Bay Coffee</div>
                <span className="version-pill">v2</span>
              </div>
              <div className="kv-dense" style={{padding:'10px 14px'}}>
                <div className="k">COORDS</div>
                <div className="v mono" style={{fontSize:11}}>37.7708, −122.3886</div>
                <div className="k">ARRIVAL</div>
                <div className="v mono" style={{fontSize:11.5}}>2024-10-22 09:01</div>
                <div className="k">DEPARTURE</div>
                <div className="v mono" style={{fontSize:11.5}}>2024-10-22 11:18</div>
                <div className="k">DWELL</div>
                <div className="v mono" style={{fontSize:11.5}}>2h 17m</div>
                <div className="k">CHUNK_HASH</div>
                <div className="v mono" style={{fontSize:11.5}}>f1a92e0b8c7d…</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function FakeMap() {
  // Simplified street/park overlay
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none"
         style={{position:'absolute', inset:0, width:'100%', height:'100%'}}>
      {/* parks */}
      <path d="M55,50 Q72,50 75,62 Q70,72 60,70 Q52,65 55,50 Z" fill="rgba(16,185,129,0.10)" stroke="rgba(16,185,129,0.20)" strokeWidth="0.2"/>
      <path d="M10,20 L24,18 L30,30 L20,38 Z" fill="rgba(16,185,129,0.08)"/>
      {/* water bay */}
      <path d="M0,5 Q40,8 60,18 L70,28 L80,40 L100,45 L100,0 L0,0 Z" fill="rgba(34,211,238,0.08)" stroke="rgba(34,211,238,0.15)" strokeWidth="0.2"/>
      {/* streets — orthogonal grid suggestion */}
      <g stroke="rgba(20,30,46,0.10)" strokeWidth="0.3">
        <line x1="0" y1="36" x2="100" y2="34"/>
        <line x1="0" y1="52" x2="100" y2="50"/>
        <line x1="0" y1="68" x2="100" y2="66"/>
        <line x1="0" y1="84" x2="100" y2="82"/>
        <line x1="20" y1="0" x2="22" y2="100"/>
        <line x1="40" y1="0" x2="42" y2="100"/>
        <line x1="60" y1="0" x2="62" y2="100"/>
        <line x1="80" y1="0" x2="82" y2="100"/>
      </g>
      <g stroke="rgba(20,30,46,0.18)" strokeWidth="0.5">
        <line x1="0" y1="58" x2="100" y2="56"/>
        <line x1="48" y1="0" x2="50" y2="100"/>
      </g>
      {/* gps track polyline */}
      <polyline points="30,68 38,60 44,54 48,48 52,42 56,36 58,28 62,32 68,42 68,56 60,62 50,66 40,68 32,70"
                className="map-track" />
    </svg>
  );
}

function Pin({ x, y, label, active, detail }) {
  return (
    <div className={'map-pin' + (active ? ' active' : '')} style={{left: x + '%', top: y + '%'}}>
      <div className="lbl">{label}</div>
      <div className="ring"></div>
      {active && (
        <div style={{position:'absolute', top:'100%', marginTop:6, left:'50%',
                       transform:'translateX(-50%)',
                       padding:'5px 10px',
                       background:'var(--canvas-card)',
                       border:'1px solid var(--accent-primary)',
                       borderRadius:'var(--radius-md)',
                       fontFamily:'var(--font-mono)', fontSize:10,
                       color:'var(--canvas-fg-1)',
                       whiteSpace:'nowrap',
                       boxShadow:'0 2px 8px rgba(0,0,0,0.10)'}}>
          {detail}
        </div>
      )}
    </div>
  );
}

function Stat({ l, v, u }) {
  return (
    <div>
      <div className="eyebrow" style={{marginBottom:3, fontSize:9.5}}>{l}</div>
      <div style={{display:'flex', alignItems:'baseline', gap:3}}>
        <span style={{fontFamily:'var(--font-mono)', fontSize:18, fontWeight:600,
                       color:'var(--canvas-fg-1)', fontVariantNumeric:'tabular-nums', lineHeight:1}}>{v}</span>
        {u && <span style={{fontSize:10.5, color:'var(--canvas-fg-3)'}}>{u}</span>}
      </div>
    </div>
  );
}

function Visit({ time, arrive, last, selected, name, addr, dwell, how, notes }) {
  return (
    <div style={{
      padding:'10px 14px',
      borderBottom:'1px solid var(--canvas-border)',
      display:'grid', gridTemplateColumns:'48px 1fr', gap:12,
      cursor:'pointer',
      background: selected ? 'rgba(251,191,36,0.05)' : 'transparent',
      borderLeft: selected ? '2px solid var(--accent-primary)' : '2px solid transparent',
      paddingLeft: selected ? 12 : 14,
    }}>
      <div style={{textAlign:'center', position:'relative'}}>
        <div style={{fontFamily:'var(--font-mono)', fontSize:11.5, color:'var(--canvas-fg-1)', fontWeight:500}}>{time}</div>
        <div style={{fontFamily:'var(--font-mono)', fontSize:9, color:'var(--canvas-fg-4)',
                       letterSpacing:'0.08em', textTransform:'uppercase', marginTop:2}}>
          {arrive ? 'arrive' : last ? 'last' : 'leave'}
        </div>
        {!last && (
          <div style={{position:'absolute', left:'50%', top:30, bottom:-10,
                         borderLeft:'1px dashed var(--canvas-border-strong)'}}></div>
        )}
      </div>
      <div>
        <div style={{fontSize:13, fontWeight:600, color: selected ? 'var(--canvas-fg-1)' : 'var(--canvas-fg-1)', marginBottom:2}}>
          {name}
        </div>
        <div style={{fontFamily:'var(--font-mono)', fontSize:10.5, color:'var(--canvas-fg-3)', marginBottom:4}}>
          {addr}
        </div>
        <div style={{display:'flex', gap:10, fontFamily:'var(--font-mono)', fontSize:10.5,
                       color:'var(--canvas-fg-3)'}}>
          <span>{dwell}</span>
          <span style={{color:'var(--canvas-fg-4)'}}>·</span>
          <span>{how}</span>
        </div>
        {notes && (
          <div style={{marginTop:6, padding:'4px 8px',
                         background:'var(--canvas-bg-2)', borderLeft:'2px solid var(--accent-primary)',
                         fontSize:11.5, color:'var(--canvas-fg-2)'}}>
            {notes}
          </div>
        )}
      </div>
    </div>
  );
}

window.LocationScreen = LocationScreen;
