// Health domain — time-series dashboard
// Adapters: apple.health, oura. HealthMetadata: health_type, date.
// Adapters perform time-window grouping BEFORE chunking; each window is a NormalizedContent.
// (see src/context_library/domains/health.py)

function HealthScreen() {
  return (
    <Shell active="health" breadcrumbs={['domain', 'health', 'oct 2024']}>
      <div className="canvas-inner" style={{padding:'18px 22px 22px', display:'flex', flexDirection:'column', minHeight:0}}>
        {/* Head */}
        <div className="page-head" style={{marginBottom:14}}>
          <div>
            <h1 style={{margin:0}}>
              Health <span className="id-tag" style={{marginLeft:10}}>14,981 windows · 7 metrics</span>
            </h1>
            <div className="subtitle">
              Adapter-windowed time-series. Apple Health groups heart-rate samples into hourly windows;
              Oura emits one window per night. Each window becomes one source → one chunk.
            </div>
          </div>
          <div className="page-actions">
            <FDPanel label="RANGE" value="oct 2024 · 23 d"/>
            <FDPanel label="SOURCE" value="apple.health, oura"/>
            <button className="btn"><Icon name="ext" size={12}/> Export</button>
          </div>
        </div>

        {/* Metric tiles row */}
        <div style={{display:'grid', gridTemplateColumns:'repeat(5, 1fr)', gap:12, marginBottom:14}}>
          <MetricTile label="RESTING HR · BPM"   v="58"   sub="-3 vs 30d"      trend="down" color="var(--status-emerald)" active/>
          <MetricTile label="HRV · MS"           v="62"   sub="+8 vs 30d"      trend="up"   color="var(--status-cyan)"/>
          <MetricTile label="SLEEP · HRS"        v="7.4"  sub="92% efficiency" trend="up"   color="var(--dom-notes)"/>
          <MetricTile label="STEPS · DAILY"      v="8,412" sub="goal 10k"      trend="flat" color="var(--accent-primary-deep)"/>
          <MetricTile label="WORKOUTS · WK"      v="4"    sub="60 min avg"     trend="up"   color="var(--dom-health)"/>
        </div>

        {/* Main chart + side panels */}
        <div style={{display:'grid', gridTemplateColumns:'1fr 360px', gap:14, flex:1, minHeight:0}}>
          {/* Chart */}
          <div className="panel" style={{display:'flex', flexDirection:'column', overflow:'hidden'}}>
            <div className="panel-head" style={{padding:'10px 14px'}}>
              <div className="panel-title" style={{fontSize:13}}>
                <Icon name="brain" size={14}/>
                resting heart rate · hourly
              </div>
              <div className="seg">
                <button>7d</button>
                <button className="active">30d</button>
                <button>90d</button>
                <button>1y</button>
              </div>
              <div className="row gap-12">
                <span className="eyebrow">SCROLL · ZOOM</span>
              </div>
            </div>

            <div style={{padding:'18px 22px', flex:1, minHeight:0, position:'relative'}}>
              <ChartArea/>
            </div>

            <div style={{padding:'10px 16px', borderTop:'1px solid var(--canvas-border)',
                          background:'var(--canvas-bg-2)',
                          display:'flex', gap:14, alignItems:'center',
                          fontFamily:'var(--font-mono)', fontSize:11}}>
              <span style={{color:'var(--canvas-fg-3)'}}>
                <span style={{display:'inline-block', width:8, height:8, background:'var(--status-emerald)', verticalAlign:'middle', marginRight:6, borderRadius:2}}></span>
                resting (apple.health)
              </span>
              <span style={{color:'var(--canvas-fg-3)'}}>
                <span style={{display:'inline-block', width:8, height:8, background:'var(--status-cyan)', verticalAlign:'middle', marginRight:6, borderRadius:2}}></span>
                oura · daily
              </span>
              <span style={{flex:1}}></span>
              <span style={{color:'var(--canvas-fg-3)'}}>720 hourly chunks · 24 nightly chunks · 384d</span>
            </div>
          </div>

          {/* Right: source breakdown + window inspector */}
          <div style={{display:'flex', flexDirection:'column', gap:14, minHeight:0}}>
            {/* Adapter breakdown */}
            <div className="panel">
              <div className="panel-head" style={{padding:'10px 12px'}}>
                <div className="panel-title" style={{fontSize:12.5}}><Icon name="cpu" size={13}/>Sources</div>
              </div>
              <div style={{padding:'12px 14px'}}>
                <SourceBar name="apple.health" detail="hourly windows · 7 types" pct={68} count="10,224"/>
                <SourceBar name="oura · sleep" detail="nightly windows · 1 type" pct={18} count="2,706"/>
                <SourceBar name="oura · readiness" detail="daily windows · 1 type" pct={12} count="1,803"/>
                <SourceBar name="apple.health workouts" detail="per-workout · 1 type" pct={2} count="248"/>
              </div>
            </div>

            {/* Selected window */}
            <div className="panel" style={{flex:1, minHeight:0, display:'flex', flexDirection:'column', overflow:'hidden'}}>
              <div className="panel-head" style={{padding:'10px 12px'}}>
                <div className="panel-title" style={{fontSize:12.5}}><Icon name="link" size={13}/>Window · Oct 22 · 14:00</div>
                <span className="version-pill">v1</span>
              </div>

              <div style={{padding:'12px 14px', overflow:'auto', flex:1, minHeight:0}}>
                <div className="eyebrow" style={{marginBottom:6}}>CONTEXT_HEADER</div>
                <div style={{padding:'8px 10px', background:'rgba(251,191,36,0.04)',
                              border:'1px solid var(--canvas-border)', borderRadius:'var(--radius-md)',
                              fontFamily:'var(--font-mono)', fontSize:11.5,
                              color:'var(--canvas-fg-1)', marginBottom:12}}>
                  resting_heart_rate — 2024-10-22T14:00:00Z
                </div>

                <div className="eyebrow" style={{marginBottom:6}}>WINDOW SUMMARY (EMBEDDED)</div>
                <div style={{padding:'10px 12px', background:'var(--canvas-bg-2)',
                              border:'1px solid var(--canvas-border)', borderRadius:'var(--radius-md)',
                              fontSize:12.5, color:'var(--canvas-fg-1)', lineHeight:1.5,
                              marginBottom:12}}>
                  Resting heart rate during 14:00–15:00: avg 62 bpm (min 58, max 68), 42 samples.
                  Steady reading consistent with afternoon focus block. No elevated periods detected.
                </div>

                <div className="eyebrow" style={{marginBottom:6}}>METRICS</div>
                <div className="kv-dense">
                  <div className="k">SAMPLES</div>
                  <div className="v mono">42</div>
                  <div className="k">AVG / MIN / MAX</div>
                  <div className="v mono">62 / 58 / 68 bpm</div>
                  <div className="k">SOURCE</div>
                  <div className="v mono" style={{fontSize:11.5}}>apple.health/hrv/2024-10-22T14:00:00Z</div>
                  <div className="k">CHUNK_HASH</div>
                  <div className="v mono" style={{fontSize:11.5}}>d72ac0148b91…</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function MetricTile({ label, v, sub, trend, color, active }) {
  const arrow = { up: '↑', down: '↓', flat: '→' }[trend];
  return (
    <div className={'panel'} style={{padding:'14px 16px',
      border: active ? '1px solid var(--accent-primary)' : '1px solid var(--canvas-border)',
      boxShadow: active ? '0 0 0 1px rgba(251,191,36,0.15)' : 'none'}}>
      <div className="eyebrow" style={{marginBottom:6, color: color}}>{label}</div>
      <div style={{display:'flex', alignItems:'baseline', gap:8}}>
        <span style={{fontFamily:'var(--font-mono)', fontSize:24, fontWeight:600,
                       color:'var(--canvas-fg-1)', fontVariantNumeric:'tabular-nums', lineHeight:1}}>
          {v}
        </span>
        <span style={{fontFamily:'var(--font-mono)', fontSize:11, color: color || 'var(--canvas-fg-3)'}}>
          {arrow}
        </span>
      </div>
      <div style={{fontFamily:'var(--font-mono)', fontSize:10.5, color:'var(--canvas-fg-3)', marginTop:6}}>
        {sub}
      </div>
      <Sparkline color={color}/>
    </div>
  );
}

function Sparkline({ color }) {
  const pts = [22,25,28,24,30,28,32,30,28,26,30,32,34,30,28,30,32];
  const max = Math.max(...pts), min = Math.min(...pts);
  const w = 220, h = 28;
  const norm = pts.map((p, i) => [
    (i / (pts.length - 1)) * w,
    h - ((p - min) / (max - min)) * (h - 4) - 2,
  ]);
  const path = norm.map((p, i) => (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
  const areaPath = path + ` L${w},${h} L0,${h} Z`;
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} style={{width:'100%', height:28, marginTop:8, color: color || 'var(--canvas-fg-3)'}}>
      <path className="area" d={areaPath} fill="currentColor"/>
      <path className="line" d={path}/>
    </svg>
  );
}

function ChartArea() {
  // 30 daily resting HR points
  const pts = [62,60,61,59,62,64,61,60,58,57,59,60,62,61,60,58,58,57,59,60,61,60,58,57,58,59,58,57,58,58];
  const max = 68, min = 54;
  const W = 700, H = 240;
  const padL = 36, padR = 16, padT = 12, padB = 26;
  const cw = W - padL - padR, ch = H - padT - padB;
  const norm = pts.map((p, i) => [
    padL + (i / (pts.length - 1)) * cw,
    padT + ch - ((p - min) / (max - min)) * ch,
  ]);
  const path = norm.map((p, i) => (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
  const areaPath = path + ` L${padL + cw},${padT + ch} L${padL},${padT + ch} Z`;
  const yTicks = [54, 58, 62, 66];
  const selIdx = 21;
  // Callout position as % of chart for absolute HTML overlay
  const selX = norm[selIdx][0] / W * 100;
  const selY = norm[selIdx][1] / H * 100;
  return (
    <div style={{position:'relative', width:'100%', height:'100%'}}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{width:'100%', height:'100%', display:'block'}}
           preserveAspectRatio="none">
        {/* gridlines */}
        {yTicks.map(t => {
          const y = padT + ch - ((t - min) / (max - min)) * ch;
          return (
            <line key={t} x1={padL} y1={y} x2={padL + cw} y2={y}
                  stroke="var(--canvas-border)" strokeDasharray="2 4"/>
          );
        })}
        {/* baseline 30d-avg */}
        <line x1={padL} y1={padT + ch - ((60 - min) / (max - min)) * ch}
              x2={padL + cw} y2={padT + ch - ((60 - min) / (max - min)) * ch}
              stroke="var(--canvas-fg-4)" strokeDasharray="3 5" opacity="0.6"/>
        {/* area + line */}
        <path d={areaPath} fill="var(--status-emerald)" opacity="0.15"/>
        <path d={path} stroke="var(--status-emerald)" strokeWidth="1.75" fill="none"
              vectorEffect="non-scaling-stroke"/>
        {/* dots */}
        {norm.map((p, i) => (
          <circle key={i} cx={p[0]} cy={p[1]} r={i === selIdx ? 4 : 2}
                  fill={i === selIdx ? 'var(--accent-primary)' : 'var(--status-emerald)'}
                  stroke={i === selIdx ? '#fff' : 'none'} strokeWidth={1.5}
                  vectorEffect="non-scaling-stroke"/>
        ))}
        {/* drop line from selected dot down to x-axis */}
        <line x1={norm[selIdx][0]} y1={norm[selIdx][1]}
              x2={norm[selIdx][0]} y2={padT + ch}
              stroke="var(--accent-primary)" strokeDasharray="2 3"
              vectorEffect="non-scaling-stroke"/>
      </svg>

      {/* y-axis labels — HTML so they don't skew */}
      {yTicks.map(t => {
        const y = (padT + ch - ((t - min) / (max - min)) * ch) / H * 100;
        return (
          <span key={t} style={{
            position:'absolute', left: 0, top: `${y}%`,
            transform: 'translate(0, -50%)',
            fontFamily:'var(--font-mono)', fontSize:9.5, color:'var(--canvas-fg-3)',
            paddingLeft: 0, width: 28, textAlign: 'right',
          }}>{t}</span>
        );
      })}

      {/* x-axis labels — HTML */}
      {[0, 7, 14, 21, 29].map(i => {
        const x = norm[i][0] / W * 100;
        return (
          <span key={i} style={{
            position:'absolute', left: `${x}%`, bottom: 0,
            transform: 'translate(-50%, 0)',
            fontFamily:'var(--font-mono)', fontSize:9.5,
            color: i === selIdx ? 'var(--canvas-fg-1)' : 'var(--canvas-fg-3)',
            fontWeight: i === selIdx ? 600 : 400,
            whiteSpace:'nowrap',
          }}>oct {i+1}</span>
        );
      })}

      {/* Callout — HTML, positioned over the selected dot */}
      <div style={{
        position:'absolute',
        left: `${selX}%`,
        top: `${selY}%`,
        transform: 'translate(-50%, calc(-100% - 14px))',
        background: 'var(--canvas-card)',
        border: '1px solid var(--accent-primary)',
        borderRadius: 'var(--radius-md)',
        padding: '6px 10px',
        fontFamily: 'var(--font-mono)',
        whiteSpace: 'nowrap',
        boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
        pointerEvents: 'none',
      }}>
        <div style={{fontSize: 11, fontWeight: 600, color: 'var(--canvas-fg-1)'}}>
          Oct 22 · 14:00 · 62 bpm
        </div>
        <div style={{fontSize: 10, color: 'var(--canvas-fg-3)', marginTop: 2}}>
          42 samples · apple.health
        </div>
        {/* arrow */}
        <div style={{
          position:'absolute', bottom: -5, left: '50%',
          transform: 'translateX(-50%) rotate(45deg)',
          width: 8, height: 8,
          background: 'var(--canvas-card)',
          borderRight: '1px solid var(--accent-primary)',
          borderBottom: '1px solid var(--accent-primary)',
        }}></div>
      </div>
    </div>
  );
}

function SourceBar({ name, detail, pct, count }) {
  return (
    <div style={{padding:'7px 0', borderBottom:'1px dashed var(--canvas-border)'}}>
      <div style={{display:'flex', alignItems:'center', gap:8, marginBottom:5}}>
        <span style={{fontFamily:'var(--font-mono)', fontSize:11.5, color:'var(--canvas-fg-1)', fontWeight:500, flex:1}}>{name}</span>
        <span style={{fontFamily:'var(--font-mono)', fontSize:10.5, color:'var(--canvas-fg-3)'}}>{count}</span>
      </div>
      <div style={{fontSize:10.5, color:'var(--canvas-fg-3)', marginBottom:4}}>{detail}</div>
      <div style={{height:4, background:'var(--canvas-bg-2)', borderRadius:2, overflow:'hidden'}}>
        <div style={{height:'100%', width: pct + '%', background:'var(--dom-health)', borderRadius:2}}></div>
      </div>
    </div>
  );
}

window.HealthScreen = HealthScreen;
