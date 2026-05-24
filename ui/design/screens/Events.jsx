// Events domain — calendar + selected-event detail
// Sources: caldav, apple.calendar. EventsDomain chunks by time window.
// Context header: "{title} — {start_date}" per src/context_library/domains/events.py

function EventsScreen() {
  return (
    <Shell active="events" breadcrumbs={['domain', 'events', 'oct 2024', 'graph rag handoff sync']}>
      <div className="canvas-inner" style={{padding:0, minWidth:0}}>
        <div style={{display:'grid', gridTemplateColumns:'260px 1fr 340px', gap:14,
                     padding:14, height:'100%', minHeight:0}}>

          {/* Left: mini cal + calendar filters */}
          <div className="panel" style={{display:'flex', flexDirection:'column', overflow:'hidden'}}>
            <div className="panel-head" style={{padding:'10px 12px'}}>
              <div className="panel-title" style={{fontSize:12.5}}>
                <span className="dom-dot events"></span>Events · 986
              </div>
            </div>

            {/* Mini cal */}
            <div style={{padding:'12px 12px 4px'}}>
              <div style={{display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:8}}>
                <button className="btn btn-ghost btn-sm" style={{padding:'2px 6px'}}><Icon name="chevLeft" size={11}/></button>
                <span className="mono" style={{fontSize:11.5, fontWeight:600, color:'var(--canvas-fg-1)'}}>OCTOBER 2024</span>
                <button className="btn btn-ghost btn-sm" style={{padding:'2px 6px'}}><Icon name="chevRight" size={11}/></button>
              </div>
              <MiniCal/>
            </div>

            {/* Calendars filter */}
            <div style={{padding:'8px 12px', borderTop:'1px solid var(--canvas-border)'}}>
              <div className="eyebrow" style={{marginBottom:8}}>CALENDARS · 5</div>
              <CalCheck name="work · studio" color="var(--dom-events)" count={42}/>
              <CalCheck name="personal" color="var(--dom-messages)" count={28}/>
              <CalCheck name="gym · workouts" color="var(--dom-health)" count={18}/>
              <CalCheck name="focus blocks" color="var(--dom-notes)" count={12}/>
              <CalCheck name="apple.health (derived)" color="var(--dom-health)" count={812} muted/>
            </div>

            <div style={{padding:'10px 12px', borderTop:'1px solid var(--canvas-border)', flex:1}}>
              <div className="eyebrow" style={{marginBottom:8}}>SOURCES</div>
              <div style={{display:'flex', flexDirection:'column', gap:4}}>
                <SourceRow2 name="caldav" v="v1.2" status="ok"/>
                <SourceRow2 name="apple.calendar" v="v0.9" status="ok"/>
                <SourceRow2 name="apple.health" v="v0.9" status="warn"/>
                <SourceRow2 name="apple.music" v="v0.6" status="ok"/>
              </div>
            </div>
          </div>

          {/* Center: calendar grid */}
          <div className="panel" style={{display:'flex', flexDirection:'column', overflow:'hidden'}}>
            <div className="panel-head" style={{padding:'10px 14px'}}>
              <div className="panel-title" style={{fontSize:13}}>
                <Icon name="pipeline" size={14}/>October 2024
              </div>
              <div className="seg">
                <button>day</button>
                <button>week</button>
                <button className="active">month</button>
                <button>agenda</button>
              </div>
              <button className="btn btn-ghost btn-sm">today</button>
            </div>

            <div style={{padding:14, overflow:'auto', flex:1}}>
              {/* Day header */}
              <div className="cal-head">
                <div>MON</div><div>TUE</div><div>WED</div><div>THU</div><div>FRI</div><div>SAT</div><div>SUN</div>
              </div>
              {/* 5 weeks of cells */}
              <div className="cal-grid" style={{borderTop:0, borderTopLeftRadius:0, borderTopRightRadius:0}}>
                {buildMonthCells()}
              </div>
            </div>
          </div>

          {/* Right: event detail */}
          <div className="panel" style={{display:'flex', flexDirection:'column', overflow:'hidden'}}>
            <div className="panel-head" style={{padding:'10px 12px'}}>
              <div className="panel-title" style={{fontSize:12.5}}><Icon name="doc" size={13}/>Event</div>
              <span className="version-pill">v1</span>
            </div>

            <div style={{padding:'16px 14px', overflow:'auto', flex:1}}>
              <div className="eyebrow" style={{marginBottom:6}}>WED · 23 OCT</div>
              <div style={{fontSize:16, fontWeight:600, color:'var(--canvas-fg-1)', letterSpacing:'-0.01em', marginBottom:6}}>
                Graph RAG handoff sync
              </div>
              <div style={{fontFamily:'var(--font-mono)', fontSize:11.5, color:'var(--canvas-fg-3)', marginBottom:14}}>
                14:00 → 14:45 · 45 min · zoom
              </div>

              <div className="kv-dense" style={{marginBottom:14}}>
                <div className="k">CALENDAR</div>
                <div className="v"><span style={{display:'inline-block', width:8, height:8, borderRadius:2, background:'var(--dom-events)', verticalAlign:'middle', marginRight:6}}></span>work · studio</div>
                <div className="k">ATTENDEES</div>
                <div className="v">morgan, ana, sam, daniela</div>
                <div className="k">LOCATION</div>
                <div className="v mono" style={{fontSize:11.5}}>zoom.us/j/8472901138</div>
                <div className="k">SOURCE</div>
                <div className="v mono" style={{fontSize:11.5}}>caldav/cal:work/2024-10-23T14:00:00Z</div>
              </div>

              {/* Context header */}
              <div className="eyebrow" style={{marginBottom:6}}>CONTEXT_HEADER</div>
              <div style={{padding:'8px 10px', background:'rgba(251,191,36,0.04)',
                            border:'1px solid var(--canvas-border)', borderRadius:'var(--radius-md)',
                            fontFamily:'var(--font-mono)', fontSize:11.5,
                            color:'var(--canvas-fg-1)', marginBottom:12}}>
                Graph RAG handoff sync — 2024-10-23
              </div>

              {/* Description */}
              <div className="eyebrow" style={{marginBottom:6}}>DESCRIPTION · CHUNK 1 OF 1</div>
              <div style={{padding:'10px 12px', background:'var(--canvas-bg-2)',
                            border:'1px solid var(--canvas-border)', borderRadius:'var(--radius-md)',
                            fontSize:12.5, color:'var(--canvas-fg-1)', lineHeight:1.55,
                            marginBottom:14}}>
                Walk through the v3 pipeline arch. Topics:<br/>
                • diff stage rewrite (hash-set ops)<br/>
                • normalizer v2.1 — quote stripping<br/>
                • thread_id in domain_metadata<br/>
                • reranker latency budget<br/><br/>
                Pre-read: heimdall-graph-rag.md v3
              </div>

              {/* Lineage */}
              <div className="eyebrow" style={{marginBottom:6}}>LINEAGE</div>
              <div className="lineage-rail">
                <span className="lr-node">caldav</span>
                <span className="lr-arrow">→</span>
                <span className="lr-node">events.time_window</span>
                <span className="lr-arrow">→</span>
                <span className="lr-node head">1 chunk</span>
                <span className="lr-arrow">→</span>
                <span className="lr-node">embedded</span>
              </div>

              <div style={{marginTop:14, padding:'10px 12px',
                            background:'var(--canvas-bg-2)', border:'1px solid var(--canvas-border)',
                            borderRadius:'var(--radius-md)',
                            fontFamily:'var(--font-mono)', fontSize:10.5, color:'var(--canvas-fg-3)',
                            lineHeight:1.55}}>
                chunk_hash <span style={{color:'var(--canvas-fg-1)'}}>9c41ef028b…</span><br/>
                source_id <span style={{color:'var(--canvas-fg-1)'}}>caldav/cal:work/2024-10-23T14:00:00Z</span><br/>
                emb_model <span style={{color:'var(--canvas-fg-1)'}}>all-MiniLM-L6-v2</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function MiniCal() {
  // Oct 2024 — starts Tue
  const days = [];
  // prev month tail: Sep 30
  days.push({d: 30, out: true});
  for (let i = 1; i <= 31; i++) days.push({d: i, out: false});
  // pad to 35
  for (let i = 1; i <= 3; i++) days.push({d: i, out: true});
  const hasEvent = new Set([2, 4, 7, 9, 11, 14, 16, 18, 21, 23, 25, 28]);
  const today = 23;
  return (
    <div>
      <div className="cal-mini">
        {['M','T','W','T','F','S','S'].map((h,i) => <div key={i} className="h">{h}</div>)}
        {days.map((x, i) => (
          <div key={i} className={
            'd' + (x.out ? ' out' : '') +
            (!x.out && hasEvent.has(x.d) ? ' has' : '') +
            (!x.out && x.d === today ? ' today' : '')
          }>{x.d}</div>
        ))}
      </div>
    </div>
  );
}

function CalCheck({ name, color, count, muted }) {
  return (
    <div style={{display:'flex', alignItems:'center', gap:8, padding:'4px 0',
                  opacity: muted ? 0.65 : 1}}>
      <span style={{width:10, height:10, borderRadius:2, background:color,
                     border:'1px solid rgba(0,0,0,0.15)'}}></span>
      <span style={{fontFamily:'var(--font-mono)', fontSize:11.5, color:'var(--canvas-fg-1)',
                     flex:1, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>{name}</span>
      <span style={{fontFamily:'var(--font-mono)', fontSize:10.5, color:'var(--canvas-fg-3)'}}>{count}</span>
    </div>
  );
}

function SourceRow2({ name, v, status }) {
  const chip = {
    ok:   <span className="dot-em" style={{width:6, height:6, borderRadius:'50%', background:'var(--status-emerald)'}}></span>,
    warn: <span className="dot-em" style={{width:6, height:6, borderRadius:'50%', background:'var(--status-amber)'}}></span>,
    err:  <span className="dot-em" style={{width:6, height:6, borderRadius:'50%', background:'var(--status-rose)'}}></span>,
  }[status];
  return (
    <div style={{display:'flex', alignItems:'center', gap:8, padding:'4px 0'}}>
      {chip}
      <span style={{fontFamily:'var(--font-mono)', fontSize:11.5, color:'var(--canvas-fg-1)', flex:1}}>{name}</span>
      <span className="version-pill" style={{padding:'1px 5px', fontSize:9.5}}>{v}</span>
    </div>
  );
}

function buildMonthCells() {
  // Oct 2024 — 31 days, starts Tuesday (col 1)
  // Layout: 5 rows × 7 cols = 35 cells. Prefix with Sep 30, append Nov 1-3.
  const cells = [];
  cells.push({ day: 30, outside: true });
  for (let d = 1; d <= 31; d++) cells.push({ day: d, outside: false });
  for (let d = 1; d <= 3; d++) cells.push({ day: d, outside: true });

  const eventsByDay = {
    2:  [{t:'09:00', l:'standup', c:'cal-event'}, {t:'14:00', l:'1:1 morgan', c:'cal-personal'}],
    4:  [{t:'08:00', l:'long run', c:'cal-gym'}],
    7:  [{t:'10:30', l:'pipeline review', c:'cal-event'}, {t:'15:00', l:'focus · diff', c:'cal-focus'}],
    9:  [{t:'08:30', l:'gym · upper', c:'cal-gym'}, {t:'09:00', l:'standup', c:'cal-event'}],
    11: [{t:'13:00', l:'design crit', c:'cal-event'}, {t:'18:00', l:'family dinner', c:'cal-personal'}],
    14: [{t:'10:00', l:'rag survey readout', c:'cal-event'}],
    16: [{t:'08:30', l:'gym · lower', c:'cal-gym'}, {t:'14:00', l:'pairing · ana', c:'cal-personal'}],
    18: [{t:'13:00', l:'focus · normalize', c:'cal-focus'}],
    21: [{t:'09:00', l:'standup', c:'cal-event'}, {t:'17:00', l:'gym · upper', c:'cal-gym'}],
    23: [{t:'09:00', l:'standup', c:'cal-event'}, {t:'14:00', l:'graph rag handoff', c:'cal-event selected'}, {t:'16:30', l:'focus · diff', c:'cal-focus'}],
    25: [{t:'10:00', l:'reranker spike', c:'cal-event'}, {t:'18:30', l:'dinner · m+a', c:'cal-personal'}],
    28: [{t:'09:00', l:'standup', c:'cal-event'}, {t:'13:00', l:'q4 review', c:'cal-event'}],
    30: [{t:'14:00', l:'oura sync', c:'cal-gym'}],
  };

  return cells.map((c, i) => (
    <div key={i} className={'cal-cell' + (c.outside ? ' outside' : '') + (c.day === 23 && !c.outside ? ' today' : '')}>
      <span className="day">{c.day}</span>
      {!c.outside && (eventsByDay[c.day] || []).map((ev, j) => (
        <div key={j} className={ev.c}>
          <span className="time">{ev.t}</span>
          <span style={{overflow:'hidden', textOverflow:'ellipsis'}}>{ev.l}</span>
        </div>
      ))}
    </div>
  ));
}

window.EventsScreen = EventsScreen;
