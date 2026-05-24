// Sources Browser — explore all ingested sources (GET /sources)
// Table-driven, filter-faceted, with adapter + version counts

function SourcesScreen() {
  return (
    <Shell active="sources" breadcrumbs={['workspace', 'sources']}>
      <div className="canvas-inner" style={{padding:'20px 24px 24px'}}>
        <div className="page-head" style={{marginBottom:14}}>
          <div>
            <h1 style={{margin:0}}>
              Sources
              <span className="id-tag" style={{marginLeft:10}}>4,812 total</span>
            </h1>
            <div className="subtitle">
              Every external thing the pipeline has ingested. Click a row for version history,
              chunk-set, and origin-ref. Filter by domain or adapter to narrow.
            </div>
          </div>
          <div className="page-actions">
            <button className="btn"><Icon name="filter" size={13}/> Filters · 2</button>
            <button className="btn"><Icon name="ext" size={12}/> Export CSV</button>
          </div>
        </div>

        {/* Tabs (sources / versions / chunks) */}
        <div className="tabs" style={{marginBottom:14}}>
          <button className="tab active">Sources <span className="count">4,812</span></button>
          <button className="tab">Chunks <span className="count">18,724</span></button>
          <button className="tab">Versions <span className="count">2,406</span></button>
          <button className="tab">Retired <span className="count">221</span></button>
        </div>

        {/* Filter row */}
        <div className="row gap-12" style={{marginBottom:14, flexWrap:'wrap'}}>
          <FDPanel label="DOMAIN" value="notes, messages" active/>
          <FDPanel label="ADAPTER" value="obsidian" active/>
          <FDPanel label="VERSIONS" value="any"/>
          <FDPanel label="LAST FETCHED" value="any"/>
          <div className="seg">
            <button className="active">all</button>
            <button>active</button>
            <button>retired</button>
          </div>
          <div style={{flex:1}}></div>
          <div style={{display:'inline-flex', gap:6, padding:'5px 10px',
                       background:'var(--canvas-bg)', border:'1px solid var(--canvas-border-strong)',
                       borderRadius:'var(--radius-md)', alignItems:'center'}}>
            <Icon name="search" size={13}/>
            <input style={{border:0, outline:0, background:'transparent', fontSize:12.5,
                           width:220, color:'var(--canvas-fg-1)'}}
                   placeholder="filter by source_id, origin_ref…"
                   defaultValue="2024-q"/>
          </div>
        </div>

        {/* Data table */}
        <div className="panel" style={{padding:0}}>
          <table className="tbl">
            <thead>
              <tr>
                <th style={{width:24, paddingLeft:14}}></th>
                <th>SOURCE_ID</th>
                <th>DOMAIN</th>
                <th>ADAPTER</th>
                <th className="num">VER</th>
                <th className="num">CHUNKS</th>
                <th>LAST FETCHED</th>
                <th>STATE</th>
                <th style={{width:30}}></th>
              </tr>
            </thead>
            <tbody>
              <SourceRow selected dom="notes" id="obsidian/vault/projects/heimdall-graph-rag.md" adapter="obsidian" ver={3} chunks={28} when="2 min ago" status="ok"/>
              <SourceRow dom="notes" id="obsidian/vault/daily/2024-q4-review.md" adapter="obsidian" ver={2} chunks={14} when="2 min ago" status="updated"/>
              <SourceRow dom="messages" id="email.imap/work@studio/INBOX/12842" adapter="email" ver={1} chunks={6} when="14 min ago" status="ok"/>
              <SourceRow dom="messages" id="email.imap/work@studio/INBOX/12841" adapter="email" ver={1} chunks={4} when="14 min ago" status="ok"/>
              <SourceRow dom="notes" id="filesystem/docs/rag/lineage-design.md" adapter="filesystem" ver={2} chunks={11} when="3 weeks ago" status="ok"/>
              <SourceRow dom="tasks" id="apple.reminders/list:context-library/T-2024-09-12-a" adapter="apple.reminders" ver={4} chunks={1} when="5 weeks ago" status="done"/>
              <SourceRow dom="events" id="caldav/cal:work/2024-10-22T14:00:00Z" adapter="caldav" ver={1} chunks={1} when="2 hours ago" status="ok"/>
              <SourceRow dom="notes" id="apple.notes/folder:research/idea-graph-rag" adapter="apple.notes" ver={1} chunks={4} when="38 min ago" status="new"/>
              <SourceRow dom="notes" id="obsidian/vault/projects/2024-q4-followups.md" adapter="obsidian" ver={5} chunks={22} when="1 hour ago" status="ok"/>
              <SourceRow dom="events" id="apple.health/workout/2024-10-21" adapter="apple.health" ver={1} chunks={1} when="1 day ago" status="ok"/>
              <SourceRow dom="documents" id="filesystem.rich/papers/lewis-rag-2020.pdf" adapter="filesystem.rich" ver={1} chunks={42} when="2 weeks ago" status="ok"/>
              <SourceRow dom="messages" id="apple.imessage/thread:family/m-4812" adapter="apple.imessage" ver={2} chunks={1} when="3 hours ago" status="ok"/>
              <SourceRow dom="tasks" id="obsidian.tasks/vault/projects/heimdall.md#L42" adapter="obsidian.tasks" ver={3} chunks={1} when="1 day ago" status="in-progress"/>
              <SourceRow dom="notes" id="obsidian/vault/daily/2024-10-21.md" adapter="obsidian" ver={1} chunks={9} when="2 days ago" status="ok"/>
            </tbody>
          </table>

          {/* Pagination */}
          <div style={{display:'flex', alignItems:'center', justifyContent:'space-between',
                       padding:'10px 14px', borderTop:'1px solid var(--canvas-border)',
                       background:'var(--canvas-bg-2)'}}>
            <div className="eyebrow">14 OF 4,812 · 1 SELECTED</div>
            <div style={{display:'flex', gap:6, alignItems:'center'}}>
              <button className="btn btn-ghost btn-sm" disabled><Icon name="chevLeft" size={11}/></button>
              <span className="mono" style={{fontSize:11, color:'var(--canvas-fg-2)'}}>page 1 / 344</span>
              <button className="btn btn-ghost btn-sm"><Icon name="chevRight" size={11}/></button>
            </div>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function FDPanel({ label, value, active }) {
  return (
    <button className={'fd-trigger' + (active ? ' open' : '')}>
      <span className="fd-eyebrow">{label}</span>
      <span className="fd-value">{value}</span>
      <span className="fd-chev"><Icon name="chevDown" size={11}/></span>
    </button>
  );
}

function SourceRow({ dom, id, adapter, ver, chunks, when, status, selected }) {
  const statusChip = {
    ok:       <span className="chip"><span className="dot"></span>ok</span>,
    updated:  <span className="chip cyan"><span className="dot"></span>updated</span>,
    new:      <span className="chip emerald"><span className="dot"></span>new</span>,
    done:     <span className="chip emerald"><span className="dot"></span>done</span>,
    'in-progress': <span className="chip amber"><span className="dot"></span>in-progress</span>,
  }[status];
  return (
    <tr className={'selectable' + (selected ? ' selected' : '')}>
      <td style={{paddingLeft:14}}>
        <span className={'dom-bar ' + dom} style={{display:'inline-block', width:3, height:14, borderRadius:1, verticalAlign:'middle'}}></span>
      </td>
      <td className="mono" style={{fontSize:12}}>{id}</td>
      <td>
        <span style={{display:'inline-flex', alignItems:'center', gap:6}}>
          <span className={'dom-dot ' + dom}></span>
          <span className="mono" style={{fontSize:11.5, color:'var(--canvas-fg-2)'}}>{dom}</span>
        </span>
      </td>
      <td className="mono">{adapter}</td>
      <td className="num"><span className="version-pill">v{ver}</span></td>
      <td className="num">{chunks}</td>
      <td className="mono" style={{fontSize:11.5, color:'var(--canvas-fg-3)'}}>{when}</td>
      <td>{statusChip}</td>
      <td><button className="btn btn-ghost btn-sm" style={{padding:2}}><Icon name="more" size={13}/></button></td>
    </tr>
  );
}

window.SourcesScreen = SourcesScreen;
