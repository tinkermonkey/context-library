// Adapters / Pipeline admin — register, monitor, and re-process adapters

function AdaptersScreen() {
  return (
    <Shell active="adapters" breadcrumbs={['system', 'adapters']}>
      <div className="canvas-inner" style={{padding:'20px 24px 24px'}}>
        <div className="page-head" style={{marginBottom:14}}>
          <div>
            <h1 style={{margin:0}}>Adapters <span className="id-tag" style={{marginLeft:10}}>11 registered</span></h1>
            <div className="subtitle">
              Every external source the pipeline knows about. Adapters declare a domain and a
              normalizer version. Re-ingest is content-safe — only changed chunks re-embed.
            </div>
          </div>
          <div className="page-actions">
            <button className="btn"><Icon name="settings" size={13}/> Bulk re-poll</button>
            <button className="btn btn-primary"><Icon name="plus" size={13}/> Register adapter</button>
          </div>
        </div>

        {/* Filter strip */}
        <div className="row gap-12" style={{marginBottom:14}}>
          <div className="seg">
            <button className="active">all <span style={{color:'var(--canvas-fg-3)', marginLeft:4}}>11</span></button>
            <button>healthy <span style={{color:'var(--canvas-fg-3)', marginLeft:4}}>8</span></button>
            <button>warn <span style={{color:'var(--canvas-fg-3)', marginLeft:4}}>2</span></button>
            <button>error <span style={{color:'var(--canvas-fg-3)', marginLeft:4}}>1</span></button>
          </div>
          <FDPanel label="DOMAIN" value="all"/>
          <FDPanel label="POLL" value="all"/>
          <div style={{flex:1}}></div>
          <span className="eyebrow">SHOWING 11 OF 11</span>
        </div>

        {/* Adapter grid */}
        <div style={{display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:12, marginBottom:14}}>
          <AdapterCard name="obsidian.vault" domain="notes" status="running" version="v2.1" poll="pull · 5m" sources={284} chunks={5902} errors={0} desc="Obsidian vault — frontmatter + wikilinks." />
          <AdapterCard name="filesystem" domain="notes" status="ok" version="v1.8" poll="pull · 30m" sources={142} chunks={1284} errors={0} desc="Plain markdown files under /docs." />
          <AdapterCard name="filesystem.rich" domain="documents" status="ok" version="v0.4" poll="pull · 1h" sources={260} chunks={2618} errors={0} desc="PDF + Office + image OCR via MarkItDown." />
          <AdapterCard name="email.imap" domain="messages" status="ok" version="v1.0" poll="pull · 10m" sources={1892} chunks={6204} errors={0} desc="IMAP via EmailEngine — account work@studio." />
          <AdapterCard name="apple.imessage" domain="messages" status="ok" version="v0.7" poll="pull · 10m" sources={248} chunks={1914} errors={0} desc="iMessage via macOS context-helpers bridge." bridge="macOS"/>
          <AdapterCard name="caldav" domain="events" status="ok" version="v1.2" poll="pull · 1h" sources={86} chunks={86} errors={0} desc="CalDAV calendars from work + personal." />
          <AdapterCard name="apple.health" domain="events" status="warn" version="v0.9" poll="pull · 15m" sources={812} chunks={1816} errors={4} desc="HealthKit workouts + heart-rate windows." bridge="macOS"/>
          <AdapterCard name="apple.music" domain="events" status="ok" version="v0.6" poll="pull · 1h" sources={88} chunks={42} errors={0} desc="Apple Music listens — batched per day." bridge="macOS"/>
          <AdapterCard name="apple.notes" domain="notes" status="ok" version="v1.1" poll="pull · 15m" sources={184} chunks={612} errors={0} desc="Apple Notes via macOS context-helpers bridge." bridge="macOS"/>
          <AdapterCard name="apple.reminders" domain="tasks" status="ok" version="v0.7" poll="pull · 5m" sources={86} chunks={86} errors={0} desc="Apple Reminders — list 'context-library'." bridge="macOS"/>
          <AdapterCard name="obsidian.tasks" domain="tasks" status="error" version="v0.3" poll="pull · 30m" sources={56} chunks={56} errors={12} desc="Obsidian Tasks plugin — checkbox parser." />
        </div>

        {/* Bottom: pipeline detail (focused on the warn adapter) */}
        <div className="split-2">
          <div className="panel" style={{padding:0}}>
            <div className="panel-head">
              <div className="panel-title">
                <Icon name="pipeline" size={14}/>
                <span className="mono">apple.health</span>
                <span className="version-pill" style={{marginLeft:4}}>v0.9</span>
                <span className="chip amber" style={{padding:'1px 6px', marginLeft:6}}><span className="dot"></span>warn</span>
              </div>
              <div style={{display:'flex', gap:6}}>
                <button className="btn btn-ghost btn-sm">view log →</button>
                <button className="btn btn-sm"><Icon name="refresh" size={11}/> re-poll</button>
              </div>
            </div>

            <div style={{padding:'14px 16px 0'}}>
              <div className="eyebrow" style={{marginBottom:10}}>PIPELINE · CURRENT RUN</div>
              <div style={{display:'flex', alignItems:'center', gap:0}}>
                {['fetch','normalize','diff','chunk','embed','store'].map((s, i) => {
                  const step = i;
                  const at = 3;
                  const done = step < at;
                  const active = step === at;
                  return (
                    <React.Fragment key={s}>
                      <div style={{
                        flex:1,
                        padding:'10px 12px',
                        textAlign:'center',
                        background: done ? 'var(--semantic-emerald-bg)' : active ? 'var(--semantic-amber-bg)' : 'var(--canvas-bg-2)',
                        color: done ? 'var(--semantic-emerald-fg)' : active ? 'var(--semantic-amber-fg)' : 'var(--canvas-fg-3)',
                        border:'1px solid ' + (done ? 'var(--semantic-emerald-border)' : active ? 'var(--semantic-amber-border)' : 'var(--canvas-border)'),
                        borderRadius:4,
                        fontFamily:'var(--font-mono)', fontSize:11, fontWeight:500,
                      }}>
                        <div style={{fontWeight:600}}>{s}</div>
                        <div style={{fontSize:9.5, opacity:0.75, marginTop:2}}>
                          {done ? 'done' : active ? 'running' : 'pending'}
                        </div>
                      </div>
                      {i < 5 && <span style={{color:'var(--canvas-fg-4)', padding:'0 6px', fontFamily:'var(--font-mono)'}}>→</span>}
                    </React.Fragment>
                  );
                })}
              </div>
            </div>

            <div className="pipe-foot">
              <div><div className="l">FETCHED</div><div className="v">812</div></div>
              <div><div className="l">CHUNKED</div><div className="v">— </div></div>
              <div><div className="l">CREATED</div><div className="v created">+18</div></div>
              <div><div className="l">RETIRED</div><div className="v">−2</div></div>
              <div><div className="l">ERRORS</div><div className="v errors-warn">4</div></div>
            </div>

            <div style={{padding:'12px 16px', borderTop:'1px solid var(--canvas-border)'}}>
              <div className="eyebrow" style={{marginBottom:8}}>RECENT EVENTS</div>
              <div style={{display:'flex', flexDirection:'column', gap:6, fontFamily:'var(--font-mono)', fontSize:11}}>
                <LogLine when="14:42:18" level="warn"  text="workouts endpoint timed out (3rd time today)"/>
                <LogLine when="14:42:15" level="info"  text="fetched 812 sources from /workouts (window: 7d)"/>
                <LogLine when="14:42:01" level="info"  text="started run pipeline_apple_health"/>
                <LogLine when="14:38:44" level="error" text="connection refused at step 2 (retried) — recovered"/>
                <LogLine when="14:27:01" level="info"  text="completed prior run · +12 chunks · 0 errors"/>
              </div>
            </div>
          </div>

          {/* Config card */}
          <div className="panel">
            <div className="panel-head">
              <div className="panel-title"><Icon name="settings" size={14}/>Configuration</div>
              <span className="eyebrow">apple.health</span>
            </div>
            <div className="kv-grid">
              <div className="k">ADAPTER_ID</div>
              <div className="v"><span className="mono">apple_health_001</span></div>
              <div className="k">DOMAIN</div>
              <div className="v"><span className="dom-dot events"></span> <span className="mono">events</span></div>
              <div className="k">POLL</div>
              <div className="v mono">pull · every 15 min</div>
              <div className="k">NORMALIZER</div>
              <div className="v mono">v0.9 <span className="muted" style={{marginLeft:6}}>(2 versions behind)</span></div>
              <div className="k">BRIDGE</div>
              <div className="v mono">macOS · http://nyx.lab.local:7123</div>
              <div className="k">API KEY</div>
              <div className="v mono">•••••••••• <button className="btn btn-ghost btn-sm" style={{padding:'1px 6px', marginLeft:6}}>rotate</button></div>
              <div className="k">EMBEDDING</div>
              <div className="v mono">all-MiniLM-L6-v2</div>
              <div className="k">CHUNKER</div>
              <div className="v mono">events.time_window · 1 day</div>
            </div>
            <div style={{padding:'12px 16px', borderTop:'1px solid var(--canvas-border)',
                         background:'var(--canvas-bg-2)', display:'flex', gap:8, alignItems:'center'}}>
              <span className="eyebrow" style={{flex:1}}>SET <span style={{color:'var(--canvas-fg-1)'}}>CTX_APPLE_HELPER_URL</span> AT STARTUP</span>
              <button className="btn btn-ghost btn-sm">edit env</button>
              <button className="btn btn-ghost btn-sm" style={{color:'var(--status-rose)'}}>reset adapter</button>
            </div>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function AdapterCard({ name, domain, status, version, poll, sources, chunks, errors, desc, bridge }) {
  const statusChip = {
    ok:      <span className="chip emerald" style={{padding:'1px 7px'}}><span className="dot"></span>healthy</span>,
    running: <span className="chip amber" style={{padding:'1px 7px'}}><span className="dot"></span>running</span>,
    warn:    <span className="chip amber" style={{padding:'1px 7px'}}><span className="dot"></span>warn</span>,
    error:   <span className="chip rose" style={{padding:'1px 7px'}}><span className="dot"></span>error</span>,
  }[status];
  return (
    <div className="adapter-card">
      <div className="head">
        <div className="icon">
          <span className={'dom-bar ' + domain} style={{width:3, height:22, borderRadius:1, display:'inline-block'}}></span>
        </div>
        <div className="meta">
          <div style={{display:'flex', alignItems:'center', gap:8, flexWrap:'wrap'}}>
            <span className="name">{name}</span>
            <span className="version-pill">{version}</span>
            {bridge && <span className="badge-tiny">{bridge} bridge</span>}
          </div>
          <div className="desc">{desc}</div>
        </div>
        {statusChip}
      </div>
      <div className="row gap-12" style={{fontFamily:'var(--font-mono)', fontSize:11, color:'var(--canvas-fg-3)'}}>
        <span><span className="dom-dot" style={{background:'var(--dom-' + domain + ')', width:6, height:6, display:'inline-block', marginRight:5, verticalAlign:'middle'}}></span>{domain}</span>
        <span style={{color:'var(--canvas-fg-4)'}}>·</span>
        <span>{poll}</span>
      </div>
      <div className="stats">
        <div className="stat-mini"><div className="l">SOURCES</div><div className="v">{sources.toLocaleString()}</div></div>
        <div className="stat-mini"><div className="l">CHUNKS</div><div className="v">{chunks.toLocaleString()}</div></div>
        <div className="stat-mini"><div className="l">ERRORS 24H</div><div className="v" style={{color: errors > 0 ? 'var(--status-rose)' : 'var(--canvas-fg-1)'}}>{errors}</div></div>
      </div>
    </div>
  );
}

function LogLine({ when, level, text }) {
  const colorMap = { info: 'var(--canvas-fg-2)', warn: 'var(--status-amber)', error: 'var(--status-rose)' };
  return (
    <div style={{display:'flex', gap:10, alignItems:'baseline'}}>
      <span style={{color:'var(--canvas-fg-4)'}}>{when}</span>
      <span style={{
        color: colorMap[level],
        textTransform:'uppercase', fontSize:9.5, fontWeight:600, letterSpacing:'0.08em',
        width:36,
      }}>{level}</span>
      <span style={{color:'var(--canvas-fg-2)'}}>{text}</span>
    </div>
  );
}

window.AdaptersScreen = AdaptersScreen;
