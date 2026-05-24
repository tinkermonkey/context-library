// Notes domain · 3-pane Obsidian-style (file tree + markdown + outline/inspector)

function NotesScreen() {
  return (
    <Shell active="notes" breadcrumbs={['domain', 'notes', 'obsidian', 'projects', 'heimdall-graph-rag.md']}>
      <div className="canvas-inner" style={{padding:'0', minWidth:0}}>
        <div className="split-3-domain" style={{padding:'14px 14px 14px', height:'100%'}}>
          {/* Left: file tree */}
          <div className="panel" style={{display:'flex', flexDirection:'column', overflow:'hidden'}}>
            <div className="panel-head" style={{padding:'10px 12px'}}>
              <div className="panel-title" style={{fontSize:12.5}}>
                <span className="dom-dot notes"></span>Notes · 1,284
              </div>
              <div className="seg" style={{padding:1}}>
                <button className="active" style={{padding:'2px 6px', fontSize:11}}>tree</button>
                <button style={{padding:'2px 6px', fontSize:11}}>recent</button>
              </div>
            </div>
            <div style={{padding:'8px 12px', borderBottom:'1px solid var(--canvas-border)'}}>
              <div style={{display:'inline-flex', gap:6, padding:'5px 8px',
                           background:'var(--canvas-bg-2)', border:'1px solid var(--canvas-border)',
                           borderRadius:'var(--radius-md)', alignItems:'center', width:'100%'}}>
                <Icon name="search" size={12}/>
                <input style={{border:0, outline:0, background:'transparent', fontSize:12,
                               flex:1, color:'var(--canvas-fg-1)'}}
                       placeholder="Filter notes…"/>
              </div>
            </div>
            <div className="file-tree" style={{flex:1, overflow:'auto'}}>
              <div className="row dir"><Icon name="chevDown" size={11} className="chev"/>📁 obsidian/vault</div>
              <div className="row dir indent-1"><Icon name="chevDown" size={11} className="chev"/>projects</div>
              <div className="row indent-2 selected">heimdall-graph-rag.md <span className="v-count">v3</span></div>
              <div className="row indent-2">2024-q4-followups.md <span className="v-count">v5</span></div>
              <div className="row indent-2">design-system-update.md <span className="v-count">v2</span></div>
              <div className="row indent-2">retrieval-benchmarks.md <span className="v-count">v1</span></div>
              <div className="row dir indent-1"><Icon name="chevRight" size={11} className="chev"/>daily</div>
              <div className="row dir indent-1"><Icon name="chevDown" size={11} className="chev"/>research</div>
              <div className="row indent-2">rag-survey-2024.md <span className="v-count">v1</span></div>
              <div className="row indent-2">embedding-eval.md <span className="v-count">v3</span></div>
              <div className="row indent-2">graph-construction.md <span className="v-count">v2</span></div>
              <div className="row dir indent-1"><Icon name="chevRight" size={11} className="chev"/>reference</div>
              <div className="row dir"><Icon name="chevRight" size={11} className="chev"/>📁 filesystem/docs</div>
              <div className="row dir"><Icon name="chevDown" size={11} className="chev"/>📁 apple.notes</div>
              <div className="row dir indent-1"><Icon name="chevDown" size={11} className="chev"/>research</div>
              <div className="row indent-2">idea-graph-rag <span className="v-count">v1</span></div>
              <div className="row indent-2">followups-2024-q4 <span className="v-count">v2</span></div>
              <div className="row dir"><Icon name="chevRight" size={11} className="chev"/>📁 filesystem.rich</div>
            </div>
          </div>

          {/* Center: markdown reader */}
          <div className="panel" style={{display:'flex', flexDirection:'column', overflow:'hidden'}}>
            {/* Header row */}
            <div className="panel-head" style={{padding:'10px 16px'}}>
              <div className="panel-title" style={{fontSize:13}}>
                <Icon name="doc" size={14}/>
                <span style={{fontFamily:'var(--font-mono)'}}>heimdall-graph-rag.md</span>
                <span className="version-pill" style={{marginLeft:6}}>v3</span>
                <span className="chip emerald" style={{padding:'1px 6px', fontSize:10}}><span className="dot"></span>head</span>
              </div>
              <div style={{display:'flex', gap:6}}>
                <button className="btn btn-ghost btn-sm">28 chunks</button>
                <button className="btn btn-ghost btn-sm">history →</button>
                <button className="btn btn-ghost btn-sm"><Icon name="ext" size={11}/></button>
              </div>
            </div>

            {/* Tabs: rendered / chunked / raw */}
            <div style={{padding:'0 16px', borderBottom:'1px solid var(--canvas-border)'}}>
              <div className="tabs" style={{margin:0, borderBottom:0}}>
                <button className="tab">rendered</button>
                <button className="tab active">chunked <span className="count">28</span></button>
                <button className="tab">raw markdown</button>
                <button className="tab">cross-refs <span className="count">7</span></button>
              </div>
            </div>

            {/* Markdown content with chunk markers */}
            <div style={{padding:'18px 22px 22px', overflow:'auto', flex:1}}>
              <div className="md">
                <span className="chunk-mark">∙ chunk_01 · # Pipeline architecture · 7e3a91ff21…</span>
                <h1>Pipeline architecture</h1>
                <p>
                  Heimdall ingests heterogeneous sources, normalizes them to markdown, and chunks
                  them along semantic boundaries. The diff stage between normalization and
                  chunking means that re-ingestion only produces new chunk versions when content
                  has actually changed.
                </p>

                <span className="chunk-mark">∙ chunk_03 · ## Normalize · b3f29c4a18…</span>
                <h2>Normalize</h2>
                <p>
                  Every adapter implements a deterministic normalizer. The same input should
                  produce the same markdown on repeated runs. Trivial differences like whitespace
                  are filtered out — the goal is paragraph-level change detection, not character-
                  perfect diffs.
                </p>
                <ul>
                  <li>Whitespace-only diffs are discarded</li>
                  <li>Heading-level fluctuations are normalized</li>
                  <li>Link formatting is canonicalized</li>
                </ul>

                <span className="chunk-mark">∙ chunk_04 · ## Diff stage · 3f2a91ce8b14… <span style={{color:'var(--status-emerald)'}}>· new in v3</span></span>
                <h2>Diff stage</h2>
                <p>
                  Chunks are content-addressed via <code>SHA-256</code> of their normalized
                  markdown. Comparing two versions is therefore a set operation on hash sets:
                </p>
                <pre><code>{`added   = curr_hashes − prev_hashes
removed = prev_hashes − curr_hashes
kept    = curr_hashes ∩ prev_hashes`}</code></pre>
                <p>
                  No positional alignment. Reordering sections produces zero diff cost.
                  Performance is <code>O(n + m)</code> and embedding cost falls only on
                  <code>added</code>.
                </p>

                <blockquote>
                  <strong>Cross-ref:</strong>{' '}
                  <a href="#">lineage-design.md</a>{' '}— how
                  <code>parent_chunk_hash</code> chains versions across edits.
                </blockquote>
              </div>
            </div>
          </div>

          {/* Right: outline / metadata inspector */}
          <div className="panel" style={{display:'flex', flexDirection:'column', overflow:'hidden'}}>
            <div className="panel-head" style={{padding:'10px 12px'}}>
              <div className="panel-title" style={{fontSize:12.5}}><Icon name="layers" size={13}/>Outline</div>
              <span className="eyebrow">7 SECTIONS</span>
            </div>
            <div className="toc" style={{padding:'10px 0', borderBottom:'1px solid var(--canvas-border)'}}>
              <div className="row">Pipeline architecture</div>
              <div className="row h2">Sources</div>
              <div className="row h2">Normalize</div>
              <div className="row h2 active">Diff stage</div>
              <div className="row h2">Hash-set ops</div>
              <div className="row">Adapter contract</div>
              <div className="row h2">Domain mapping</div>
              <div className="row">Retrieval flow</div>
              <div className="row h2">Reranker</div>
              <div className="row">Normalizer rules</div>
              <div className="row">Recovery</div>
            </div>

            {/* Properties */}
            <div style={{padding:'12px 14px', borderBottom:'1px solid var(--canvas-border)'}}>
              <div className="eyebrow" style={{marginBottom:8}}>PROPERTIES · YAML FRONTMATTER</div>
              <div className="kv-dense">
                <div className="k">TAGS</div>
                <div className="v">
                  <span className="chip" style={{padding:'1px 6px'}}>rag</span>{' '}
                  <span className="chip" style={{padding:'1px 6px'}}>pipeline</span>{' '}
                  <span className="chip" style={{padding:'1px 6px'}}>design</span>
                </div>
                <div className="k">CREATED</div>
                <div className="v mono">2024-10-17</div>
                <div className="k">UPDATED</div>
                <div className="v mono">2024-10-23</div>
                <div className="k">STATUS</div>
                <div className="v"><span className="chip amber" style={{padding:'1px 6px'}}><span className="dot"></span>draft</span></div>
              </div>
            </div>

            {/* Wikilinks */}
            <div style={{padding:'12px 14px', flex:1, overflow:'auto'}}>
              <div className="eyebrow" style={{marginBottom:8}}>WIKILINKS · 7</div>
              <div style={{display:'flex', flexDirection:'column', gap:4}}>
                <WLRow name="lineage-design.md" type="note" exists/>
                <WLRow name="chunking-strategy.md" type="note" exists/>
                <WLRow name="retrieval-benchmarks.md" type="note" exists/>
                <WLRow name="rag-survey-2024.md" type="note" exists/>
                <WLRow name="missing-spec.md" type="note" exists={false}/>
                <WLRow name="differ.py" type="ref" exists/>
                <WLRow name="apple-notes-bridge" type="adapter" exists/>
              </div>

              <div className="eyebrow" style={{marginTop:14, marginBottom:8}}>BACKLINKS · 4</div>
              <div style={{display:'flex', flexDirection:'column', gap:4}}>
                <WLRow name="2024-q4-followups.md" type="note" exists arrow/>
                <WLRow name="design-system-update.md" type="note" exists arrow/>
                <WLRow name="daily/2024-10-21.md" type="note" exists arrow/>
                <WLRow name="lineage-design.md" type="note" exists arrow/>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function WLRow({ name, type, exists, arrow }) {
  return (
    <div style={{
      display:'flex', alignItems:'center', gap:8,
      padding:'5px 8px', borderRadius:4, cursor:'pointer',
      background: 'transparent',
      fontFamily: 'var(--font-mono)', fontSize: 11.5,
      color: exists ? 'var(--canvas-fg-1)' : 'var(--canvas-fg-4)',
    }}>
      {arrow && <Icon name="arrow" size={10}/>}
      <Icon name={type === 'ref' ? 'doc' : type === 'adapter' ? 'cpu' : 'link'} size={11}/>
      <span style={{flex:1}}>{name}</span>
      {!exists && <span className="badge-tiny" style={{color:'var(--status-rose)'}}>missing</span>}
    </div>
  );
}

window.NotesScreen = NotesScreen;
