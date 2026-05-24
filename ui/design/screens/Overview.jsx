// Overview / Dashboard — system state across the library
// Shows: stats grid, domains breakdown, active pipelines, recent ingests, quick actions

function OverviewScreen() {
  return (
    <Shell active="overview" breadcrumbs={['workspace', 'overview']}>
      <div className="canvas-inner" style={{padding:'20px 24px 24px'}}>
        {/* Page head */}
        <div className="page-head" style={{marginBottom:18}}>
          <div>
            <div style={{display:'flex', alignItems:'center', gap:10, marginBottom:8}}>
              <span className="chip emerald"><span className="dot"></span>pipeline healthy</span>
              <span className="muted mono" style={{fontSize:11}}>last ingest 2 min ago</span>
            </div>
            <h1 style={{margin:0}}>
              Overview
              <span className="id-tag" style={{marginLeft:10}}>localhost:8000</span>
            </h1>
            <div className="subtitle">
              Versioned RAG over 11 adapters across 9 domains. Source-of-truth in SQLite, semantic
              index in ChromaDB. All sync queues drained.
            </div>
          </div>
          <div className="page-actions">
            <button className="btn"><Icon name="refresh" size={13}/> Re-poll all</button>
            <button className="btn btn-primary"><Icon name="plus" size={13}/> Add adapter</button>
          </div>
        </div>

        {/* Stat grid */}
        <div className="stat-grid" style={{marginBottom:16}}>
          <div className="stat" data-color="amber">
            <div className="label">SOURCES</div>
            <div className="num">4,812</div>
            <div className="meta"><span className="delta-up">+38</span> · 24h</div>
          </div>
          <div className="stat" data-color="emerald">
            <div className="label">CHUNKS · ACTIVE</div>
            <div className="num">18,724</div>
            <div className="meta">221 retired · 0.18 GB index</div>
          </div>
          <div className="stat" data-color="cyan">
            <div className="label">EMBEDDINGS · 384 dim</div>
            <div className="num">18,724</div>
            <div className="meta">all-MiniLM-L6-v2 · 1 model</div>
          </div>
          <div className="stat" data-color="violet">
            <div className="label">VERSIONS · 30d</div>
            <div className="num">2,406</div>
            <div className="meta">avg 1.4 / source</div>
          </div>
        </div>

        {/* Two-column main */}
        <div className="split-2" style={{marginBottom:16}}>
          {/* Domains panel */}
          <div className="panel">
            <div className="panel-head">
              <div className="panel-title"><Icon name="layers" size={14}/>Domains</div>
              <div className="row gap-12">
                <span className="eyebrow">SOURCES · CHUNKS</span>
              </div>
            </div>
            <div className="panel-body" style={{padding:14}}>
              <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:10}}>
                {[
                  { d:'notes',     name:'Notes',     count:'1,284', meta:'4 adapters · 5,902 chunks', adapters:['obsidian','filesystem','filesystem.rich','apple.notes'] },
                  { d:'messages',  name:'Messages',  count:'2,140', meta:'2 adapters · 8,118 chunks', adapters:['email','apple.imessage'] },
                  { d:'events',    name:'Events',    count:'986',   meta:'3 adapters · 1,944 chunks', adapters:['caldav','apple.health','apple.music'] },
                  { d:'tasks',     name:'Tasks',     count:'142',   meta:'2 adapters · 142 chunks',   adapters:['obsidian.tasks','apple.reminders'] },
                  { d:'documents', name:'Documents', count:'260',   meta:'1 adapter · 2,618 chunks',  adapters:['filesystem.rich'] },
                  { d:'people',    name:'People',    count:'94',    meta:'derived · 0 chunks',         adapters:['(derived)'] },
                ].map(t => (
                  <div key={t.d} className="dom-tile">
                    <div className={'bar dom-bar ' + t.d}></div>
                    <div className="body">
                      <div className="name">
                        <span className={'dom-dot ' + t.d}></span> {t.name}
                      </div>
                      <div className="num">{t.count}</div>
                      <div className="meta">{t.meta}</div>
                      <div className="adapters">
                        {t.adapters.map(a => <span key={a} className="pill">{a}</span>)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Pipeline activity */}
          <div className="panel">
            <div className="panel-head">
              <div className="panel-title"><Icon name="pipeline" size={14}/>Active pipelines</div>
              <button className="btn btn-ghost btn-sm">view all <Icon name="chevRight" size={11}/></button>
            </div>
            <div className="panel-body" style={{padding:0}}>
              <PipelineMini
                name="obsidian.vault"
                status="running"
                step={2}
                steps={['fetch','normalize','diff','chunk','embed','store']}
                detail="diffing 412 of 1,182 notes"
                version="v2.1"
              />
              <PipelineMini
                name="email.imap"
                status="idle"
                step={6}
                steps={['fetch','normalize','diff','chunk','embed','store']}
                detail="last run 14 min ago · +18 chunks"
                version="v1.0"
              />
              <PipelineMini
                name="apple.health"
                status="warn"
                step={3}
                steps={['fetch','normalize','diff','chunk','embed','store']}
                detail="2 sources skipped (rate-limited)"
                version="v0.9"
              />
              <div style={{padding:'12px 14px', borderTop:'1px solid var(--canvas-border)',
                          display:'flex', justifyContent:'space-between', alignItems:'center'}}>
                <div className="eyebrow">SYNC QUEUE</div>
                <div className="mono" style={{fontSize:12, color:'var(--canvas-fg-2)'}}>
                  <span className="dot-em" style={{marginRight:8}}></span>
                  0 pending · 0 failed · 12,602 synced today
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Recent activity (full width) */}
        <div className="split-2">
          <div className="panel">
            <div className="panel-head">
              <div className="panel-title"><Icon name="history" size={14}/>Recent ingests</div>
              <span className="eyebrow">LAST 24 HOURS</span>
            </div>
            <div className="activity-list" style={{padding:0}}>
              <Activity kind="create" when="2m"  headline={<>Ingested <b>obsidian/vault/notes/2024-q4-review.md</b></>} meta="+12 chunks · v1 → v2 · obsidian @ normalizer 2.1" tag="VERSION"/>
              <Activity kind="update" when="14m" headline={<>Re-embed batch finished</>} meta="412 chunks · all-MiniLM-L6-v2 · obsidian.vault" tag="EMBED"/>
              <Activity kind="run"    when="22m" headline={<>Polled <b>email.imap</b> account <span className="mono">work@studio</span></>} meta="62 messages fetched · 18 new chunks · 4 retired" tag="POLL"/>
              <Activity kind="create" when="38m" headline={<>Created new source <b>apple.notes/idea-graph-rag</b></>} meta="domain=notes · 4 chunks · 1 version" tag="SOURCE"/>
              <Activity kind="error"  when="1h"  headline={<>Skipped <b>apple.health</b> · workouts endpoint</>} meta="connection refused at step 2 · retry in 8m" tag="ERROR"/>
            </div>
          </div>

          {/* Quick access */}
          <div>
            <div className="eyebrow" style={{marginBottom:8}}>QUICK ACTIONS</div>
            <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:10, marginBottom:14}}>
              <QA icon="search"    title="Run a semantic query"    desc="POST /query — search with provenance"/>
              <QA icon="plus"      title="Register adapter"        desc="POST /adapters — new ingestion source"/>
              <QA icon="refresh"   title="Re-embed model"          desc="Swap embedder, replay sync log"/>
              <QA icon="data"      title="Browse raw chunks"       desc="GET /chunks/&#123;hash&#125; — provenance"/>
            </div>

            {/* Mini stat: storage health */}
            <div className="panel">
              <div className="panel-head">
                <div className="panel-title"><Icon name="cpu" size={14}/>Storage</div>
                <span className="eyebrow">DUAL-STORE</span>
              </div>
              <div className="panel-body" style={{padding:'10px 16px 14px'}}>
                <Bar label="SQLite · sources" pct={42} val="412 MB / 1 GB"/>
                <Bar label="ChromaDB · vectors" pct={28} val="184 MB / 650 MB"/>
                <Bar label="Sync log" pct={2} val="2 ops"/>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function PipelineMini({ name, status, step, steps, detail, version }) {
  const statusColor = status === 'running' ? 'amber'
                   : status === 'idle' ? 'neutral'
                   : status === 'warn' ? 'rose' : 'emerald';
  return (
    <div style={{padding:'12px 14px', borderBottom:'1px solid var(--canvas-border)'}}>
      <div style={{display:'flex', alignItems:'center', gap:10, marginBottom:8}}>
        <span className="mono" style={{fontWeight:600, fontSize:12.5, color:'var(--canvas-fg-1)'}}>{name}</span>
        <span className="version-pill">{version}</span>
        <span style={{marginLeft:'auto', display:'inline-flex', alignItems:'center', gap:6}}>
          {status === 'running' && <span className="pulse amber sm"></span>}
          <span className="eyebrow">{status}</span>
        </span>
      </div>
      <div style={{display:'flex', gap:0, alignItems:'center'}}>
        {steps.map((s, i) => (
          <React.Fragment key={s}>
            <div style={{
              padding:'3px 8px',
              fontFamily:'var(--font-mono)', fontSize:10.5,
              borderRadius:3,
              background: i < step ? 'var(--semantic-emerald-bg)' : i === step ? 'var(--semantic-amber-bg)' : 'var(--canvas-bg-2)',
              color: i < step ? 'var(--semantic-emerald-fg)' : i === step ? 'var(--semantic-amber-fg)' : 'var(--canvas-fg-3)',
              border:'1px solid ' + (i < step ? 'var(--semantic-emerald-border)' : i === step ? 'var(--semantic-amber-border)' : 'var(--canvas-border)'),
            }}>{s}</div>
            {i < steps.length - 1 && <span style={{color:'var(--canvas-fg-4)', padding:'0 4px', fontFamily:'var(--font-mono)'}}>→</span>}
          </React.Fragment>
        ))}
      </div>
      <div style={{marginTop:8, fontSize:11.5, color:'var(--canvas-fg-3)'}}>{detail}</div>
    </div>
  );
}

function Activity({ kind, when, headline, meta, tag }) {
  return (
    <div className="activity-row" data-kind={kind}>
      <div className="dot"></div>
      <div>
        <div className="headline">{headline}<span className="kind-tag">{tag}</span></div>
        <div className="meta">{meta}</div>
      </div>
      <div className="when">{when}</div>
    </div>
  );
}

function QA({ icon, title, desc }) {
  return (
    <button className="qa-tile">
      <div className="icon"><Icon name={icon} size={16}/></div>
      <div className="body">
        <div className="n">{title}</div>
        <div className="d">{desc}</div>
      </div>
      <div className="chev"><Icon name="chevRight" size={13}/></div>
    </button>
  );
}

function Bar({ label, pct, val }) {
  return (
    <div className="bar-row">
      <div className="lab">{label}</div>
      <div className="bar"><i style={{width: pct + '%'}}></i></div>
      <div className="num">{val}</div>
    </div>
  );
}

window.OverviewScreen = OverviewScreen;
