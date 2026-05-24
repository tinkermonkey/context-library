// Tasks domain — kanban + selected-task lifecycle detail
// Sources: obsidian.tasks, apple.reminders.
// TaskMetadata: title, status, due_date. Context header: "{title} [{status}]".
// State transitions create new chunk versions (per documentation/chunking-strategy.md).

function TasksScreen() {
  return (
    <Shell active="tasks" breadcrumbs={['domain', 'tasks', 'project · context-library']}>
      <div className="canvas-inner" style={{padding:'18px 22px 22px', display:'flex', flexDirection:'column', minHeight:0}}>
        {/* Page head */}
        <div className="page-head" style={{marginBottom:14}}>
          <div>
            <h1 style={{margin:0}}>
              Tasks <span className="id-tag" style={{marginLeft:10}}>142 active · 38 done</span>
            </h1>
            <div className="subtitle">
              One task = one chunk. State transitions generate new chunk versions even when
              text doesn't change — the domain layer synthesizes a textual description of the
              state change for embedding.
            </div>
          </div>
          <div className="page-actions">
            <button className="btn"><Icon name="filter" size={13}/> Filters</button>
            <button className="btn"><Icon name="ext" size={12}/> Open in Obsidian</button>
          </div>
        </div>

        {/* Filter strip */}
        <div className="row gap-12" style={{marginBottom:12, flexWrap:'wrap'}}>
          <FDPanel label="PROJECT" value="context-library" active/>
          <FDPanel label="SOURCE" value="all (2)"/>
          <FDPanel label="DUE" value="any"/>
          <FDPanel label="ASSIGNEE" value="@me"/>
          <div className="seg">
            <button className="active">board</button>
            <button>list</button>
            <button>timeline</button>
          </div>
          <div style={{flex:1}}></div>
          <span className="eyebrow">SHOWING 12 OF 142</span>
        </div>

        {/* Body: kanban + detail */}
        <div style={{display:'grid', gridTemplateColumns:'1fr 340px', gap:14, flex:1, minHeight:0}}>
          {/* Kanban */}
          <div className="kanban">
            <KanbanCol title="Open" count={4} color="var(--canvas-fg-3)">
              <TaskCard ctx="context-library / pipeline" title="Add parent_chunk_hash backfill migration"
                        due="—" src="obsidian.tasks" v="v1"/>
              <TaskCard ctx="context-library / search"   title="Hybrid retrieval flag — BM25 + dense"
                        due="oct 31" src="apple.reminders" v="v1"/>
              <TaskCard ctx="context-library / adapters" title="apple.health bridge: skip empty windows"
                        due="oct 28" overdue src="obsidian.tasks" v="v1"/>
              <TaskCard ctx="context-library / docs"     title="Document chunking strategy — finalize"
                        due="nov 5" src="obsidian.tasks" v="v1"/>
            </KanbanCol>

            <KanbanCol title="In Progress" count={3} color="var(--status-cyan)">
              <TaskCard ctx="context-library / pipeline" title="Diff stage rewrite — hash-set comparison"
                        due="oct 24" src="obsidian.tasks" v="v3" selected
                        notes="rewriting positional diff → hash-set ops"/>
              <TaskCard ctx="context-library / search"   title="Reranker latency profile — target &lt;40ms"
                        due="oct 30" src="apple.reminders" v="v2"/>
              <TaskCard ctx="context-library / api"      title="Provenance fetch — +lineage, +parent"
                        due="oct 26" src="obsidian.tasks" v="v2"/>
            </KanbanCol>

            <KanbanCol title="Blocked" count={2} color="var(--status-amber)">
              <TaskCard ctx="context-library / adapters" title="apple.health workouts endpoint flakiness"
                        due="—" src="obsidian.tasks" v="v2"
                        blocked="waiting on apple bridge fix"/>
              <TaskCard ctx="context-library / infra"    title="ChromaDB rebuild script — sync_log replay"
                        due="—" src="obsidian.tasks" v="v1"
                        blocked="blocked on schema migration"/>
            </KanbanCol>

            <KanbanCol title="Done" count={3} color="var(--status-emerald)">
              <TaskCard ctx="context-library / pipeline" title="Implement parent_chunk_hash field"
                        due="oct 16" done src="apple.reminders" v="v4"/>
              <TaskCard ctx="context-library / api"      title="POST /query — top_k + domain_filter"
                        due="oct 14" done src="obsidian.tasks" v="v3"/>
              <TaskCard ctx="context-library / adapters" title="email.imap thread reconstruction"
                        due="oct 12" done src="apple.reminders" v="v5"/>
            </KanbanCol>
          </div>

          {/* Task detail / version history */}
          <div className="panel" style={{display:'flex', flexDirection:'column', overflow:'hidden'}}>
            <div className="panel-head" style={{padding:'10px 12px'}}>
              <div className="panel-title" style={{fontSize:12.5}}><Icon name="check" size={13}/>Task detail</div>
              <span className="version-pill">v3</span>
            </div>

            <div style={{padding:'14px 14px', overflow:'auto', flex:1}}>
              <div className="eyebrow" style={{marginBottom:6}}>CONTEXT-LIBRARY / PIPELINE</div>
              <div style={{fontSize:14.5, fontWeight:600, color:'var(--canvas-fg-1)',
                            letterSpacing:'-0.015em', marginBottom:6, lineHeight:1.35}}>
                Diff stage rewrite — hash-set comparison
              </div>
              <div style={{display:'flex', gap:8, alignItems:'center', marginBottom:14}}>
                <span className="chip cyan" style={{padding:'1px 6px', fontSize:10.5}}><span className="dot"></span>in-progress</span>
                <span style={{fontFamily:'var(--font-mono)', fontSize:11, color:'var(--canvas-fg-2)'}}>due oct 24</span>
              </div>

              <div className="kv-dense" style={{marginBottom:14}}>
                <div className="k">SOURCE</div>
                <div className="v mono" style={{fontSize:11.5}}>obsidian.tasks/vault/projects/heimdall.md#L42</div>
                <div className="k">ASSIGNEE</div>
                <div className="v">@morgan</div>
                <div className="k">PROJECT</div>
                <div className="v mono" style={{fontSize:11.5}}>context-library</div>
                <div className="k">TAGS</div>
                <div className="v">
                  <span className="chip" style={{padding:'1px 6px'}}>pipeline</span>{' '}
                  <span className="chip" style={{padding:'1px 6px'}}>diff</span>{' '}
                  <span className="chip" style={{padding:'1px 6px'}}>refactor</span>
                </div>
              </div>

              <div className="eyebrow" style={{marginBottom:6}}>CONTEXT_HEADER</div>
              <div style={{padding:'8px 10px', background:'rgba(251,191,36,0.04)',
                            border:'1px solid var(--canvas-border)', borderRadius:'var(--radius-md)',
                            fontFamily:'var(--font-mono)', fontSize:11,
                            color:'var(--canvas-fg-1)', marginBottom:12}}>
                Diff stage rewrite [due: 2024-10-24] [in-progress]
              </div>

              <div className="eyebrow" style={{marginBottom:6}}>STATE TRANSITIONS · 3 CHUNK VERSIONS</div>
              <div className="version-list" style={{border:'1px solid var(--canvas-border)',
                                                       borderRadius:'var(--radius-md)', overflow:'hidden'}}>
                <TaskVersion label="v3" head from="open" to="in-progress" when="oct 21"
                             note="rewriting positional diff → hash-set ops"/>
                <TaskVersion label="v2" from="—" to="open · planned" when="oct 18"
                             note="due-date set, assigned to @morgan"/>
                <TaskVersion label="v1" from="—" to="—" when="oct 17"
                             note="created from obsidian.tasks · L42"/>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function KanbanCol({ title, count, color, children }) {
  return (
    <div className="kanban-col">
      <div className="kanban-col-head">
        <span className="dot" style={{background: color}}></span>
        <span className="title">{title}</span>
        <span className="count">{count}</span>
      </div>
      <div className="body">{children}</div>
    </div>
  );
}

function TaskCard({ ctx, title, due, src, v, overdue, selected, done, blocked, notes }) {
  return (
    <div className={'task-card' + (selected ? ' selected' : '')}
         style={done ? {opacity: 0.7} : {}}>
      <div className="row1">
        <input type="checkbox" defaultChecked={done} style={{margin:0, accentColor:'var(--accent-primary-deep)'}}/>
        <span className="ctx">{ctx}</span>
        <span className="version-pill" style={{marginLeft:'auto', padding:'1px 5px', fontSize:9.5}}>{v}</span>
      </div>
      <div className="title" style={done ? {textDecoration:'line-through', color:'var(--canvas-fg-3)'} : {}}>
        {title}
      </div>
      {notes && (
        <div style={{fontSize:11, color:'var(--canvas-fg-2)', marginTop:-4, marginBottom:6,
                      borderLeft:'2px solid var(--canvas-border-strong)', paddingLeft:8}}>
          {notes}
        </div>
      )}
      {blocked && (
        <div style={{fontSize:10.5, color:'var(--status-amber)', fontFamily:'var(--font-mono)',
                      marginBottom:6, display:'flex', alignItems:'center', gap:4}}>
          <span style={{width:5, height:5, borderRadius:'50%', background:'var(--status-amber)'}}></span>
          {blocked}
        </div>
      )}
      <div className="meta">
        <span className={'due' + (overdue ? ' overdue' : '')}>
          {overdue && <Icon name="warn" size={10} style={{verticalAlign:'middle', marginRight:3}}/>}
          due {due}
        </span>
        <span style={{color:'var(--canvas-fg-4)'}}>·</span>
        <span>{src}</span>
      </div>
    </div>
  );
}

function TaskVersion({ label, from, to, when, note, head }) {
  return (
    <div style={{padding:'10px 12px', borderBottom:'1px solid var(--canvas-border)',
                  display:'grid', gridTemplateColumns:'40px 1fr auto', gap:10, alignItems:'flex-start'}}>
      <span className={'version-pill' + (head ? ' deep' : '')} style={{justifySelf:'flex-start'}}>{label}</span>
      <div>
        <div style={{display:'flex', gap:6, alignItems:'center', marginBottom:3,
                      fontFamily:'var(--font-mono)', fontSize:11}}>
          <span style={{color:'var(--canvas-fg-3)'}}>{from}</span>
          <Icon name="arrow" size={10}/>
          <span style={{color:'var(--canvas-fg-1)', fontWeight:600}}>{to}</span>
        </div>
        <div style={{fontSize:11.5, color:'var(--canvas-fg-2)'}}>{note}</div>
      </div>
      <div style={{fontFamily:'var(--font-mono)', fontSize:10.5, color:'var(--canvas-fg-3)'}}>{when}</div>
    </div>
  );
}

window.TasksScreen = TasksScreen;
