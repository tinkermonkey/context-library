// Chunk inspector — GET /chunks/{hash}/provenance + version-chain
// The deepest view: one chunk, its full lineage, its embedding context, and ancestry chain

function ChunkInspectorScreen() {
  return (
    <Shell active="sources" breadcrumbs={['sources', 'obsidian/…/heimdall-graph-rag.md', 'chunks', '3f2a91ce8b14…']}>
      <div className="canvas-inner" style={{padding:'18px 24px 22px'}}>
        {/* Head */}
        <div className="page-head" style={{marginBottom:14, alignItems:'flex-start'}}>
          <div>
            <div className="eyebrow" style={{marginBottom:6}}>CHUNK · NOTES DOMAIN</div>
            <h1 style={{margin:0, fontFamily:'var(--font-mono)', fontSize:22, fontWeight:600,
                       display:'inline-flex', alignItems:'center', gap:10}}>
              3f2a91ce8b14a09c…
              <span className="version-pill deep">v3 · head</span>
            </h1>
            <div className="subtitle" style={{marginTop:6}}>
              SHA-256 of normalized content, never of the embedding context. Same content
              re-ingested from any adapter would produce this same hash. Active in 1 source ·
              chained from 2 ancestors.
            </div>
          </div>
          <div className="page-actions">
            <button className="btn btn-ghost"><Icon name="link" size={12}/> Copy hash</button>
            <button className="btn"><Icon name="ext" size={12}/> Open source</button>
            <button className="btn btn-primary"><Icon name="graph" size={13}/> Find similar</button>
          </div>
        </div>

        {/* Lineage rail */}
        <div className="panel" style={{padding:'14px 18px', marginBottom:14}}>
          <div className="row gap-12" style={{alignItems:'center'}}>
            <span className="eyebrow">PROVENANCE</span>
            <div className="lineage-rail">
              <span className="lr-node">
                <Icon name="cpu" size={11}/> obsidian
              </span>
              <span className="lr-arrow">→</span>
              <span className="lr-node">normalize v2.1</span>
              <span className="lr-arrow">→</span>
              <span className="lr-node">heimdall-graph-rag.md v3</span>
              <span className="lr-arrow">→</span>
              <span className="lr-node">notes.heading</span>
              <span className="lr-arrow">→</span>
              <span className="lr-node head">## Diff stage</span>
              <span className="lr-arrow">→</span>
              <span className="lr-node">all-MiniLM-L6-v2 · 384d</span>
              <span className="lr-arrow">→</span>
              <span className="lr-node">chromadb</span>
            </div>
          </div>
        </div>

        {/* Body: two columns */}
        <div style={{display:'grid', gridTemplateColumns:'1.6fr 1fr', gap:14}}>
          {/* Left: chunk content + context header + embedding */}
          <div>
            {/* Context header (embedded, not hashed) */}
            <div className="panel" style={{marginBottom:14}}>
              <div className="panel-head" style={{padding:'10px 14px'}}>
                <div className="panel-title" style={{fontSize:12.5}}>
                  <Icon name="layers" size={13}/>
                  context_header
                  <span className="badge-tiny" style={{marginLeft:6}}>EMBEDDED · NOT HASHED</span>
                </div>
                <span className="eyebrow">42 TOK</span>
              </div>
              <div style={{padding:'12px 16px', fontFamily:'var(--font-mono)', fontSize:12.5,
                            color:'var(--canvas-fg-2)', lineHeight:1.6,
                            background: 'rgba(251, 191, 36, 0.03)',
                            borderBottom:'1px solid var(--canvas-border)'}}>
                <span style={{color:'var(--canvas-fg-4)'}}># </span>Pipeline architecture
                <span style={{color:'var(--canvas-fg-4)'}}> &gt; ## </span>Diff stage
              </div>
            </div>

            {/* Content (hashed) */}
            <div className="panel" style={{marginBottom:14}}>
              <div className="panel-head" style={{padding:'10px 14px'}}>
                <div className="panel-title" style={{fontSize:12.5}}>
                  <Icon name="doc" size={13}/>
                  content
                  <span className="badge-tiny" style={{marginLeft:6}}>HASHED · SHA-256</span>
                </div>
                <div className="row gap-12">
                  <span className="eyebrow">186 TOK · 712 CHARS</span>
                  <div className="seg" style={{padding:1}}>
                    <button className="active" style={{padding:'2px 6px', fontSize:11}}>markdown</button>
                    <button style={{padding:'2px 6px', fontSize:11}}>normalized</button>
                    <button style={{padding:'2px 6px', fontSize:11}}>raw</button>
                  </div>
                </div>
              </div>
              <div style={{padding:'14px 16px'}}>
                <div className="md">
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
                </div>
              </div>
            </div>

            {/* Embedding input preview */}
            <div className="panel">
              <div className="panel-head" style={{padding:'10px 14px'}}>
                <div className="panel-title" style={{fontSize:12.5}}>
                  <Icon name="brain" size={13}/>
                  embedded input
                  <span className="badge-tiny" style={{marginLeft:6}}>context + content</span>
                </div>
                <span className="eyebrow">all-MiniLM-L6-v2</span>
              </div>
              <div style={{padding:'12px 16px', fontFamily:'var(--font-mono)', fontSize:11.5,
                            color:'var(--canvas-fg-2)', lineHeight:1.6, maxHeight:120, overflow:'auto'}}>
                <span style={{background:'rgba(251,191,36,0.10)', padding:'1px 3px', borderRadius:2, color:'var(--accent-primary-deep)'}}># Pipeline architecture &gt; ## Diff stage</span>
                <br/><br/>
                Chunks are content-addressed via SHA-256 of their normalized markdown. Comparing
                two versions is therefore a set operation on hash sets: added equals curr_hashes
                minus prev_hashes; removed equals prev_hashes minus curr_hashes; kept equals
                the intersection. No positional alignment. Reordering sections produces zero
                diff cost. …
              </div>
              <div style={{padding:'8px 16px', borderTop:'1px solid var(--canvas-border)',
                            background:'var(--canvas-bg-2)', display:'flex', gap:14,
                            fontFamily:'var(--font-mono)', fontSize:10.5, color:'var(--canvas-fg-3)'}}>
                <span>VECTOR · <span style={{color:'var(--canvas-fg-1)'}}>[0.124, -0.038, 0.211, …, -0.073]</span></span>
                <span style={{color:'var(--canvas-fg-4)'}}>·</span>
                <span>NORM 1.00</span>
                <span style={{color:'var(--canvas-fg-4)'}}>·</span>
                <span>384 DIMS</span>
              </div>
            </div>
          </div>

          {/* Right column: metadata + ancestry + sync */}
          <div style={{display:'flex', flexDirection:'column', gap:14}}>
            <div className="panel">
              <div className="panel-head" style={{padding:'10px 14px'}}>
                <div className="panel-title" style={{fontSize:12.5}}><Icon name="link" size={13}/>Identity & lineage</div>
              </div>
              <div className="kv-dense" style={{padding:'12px 14px'}}>
                <div className="k">CHUNK_HASH</div>
                <div className="v mono" style={{color:'var(--canvas-fg-1)'}}>3f2a91ce8b14a09c…</div>
                <div className="k">PARENT</div>
                <div className="v mono"><a style={{color:'var(--accent-primary-deep)', textDecoration:'none'}}>a431f8d1ce0c2b…</a></div>
                <div className="k">SOURCE_ID</div>
                <div className="v mono">obsidian/vault/projects/heimdall-graph-rag.md</div>
                <div className="k">SOURCE VER</div>
                <div className="v"><span className="version-pill">v3</span> <span className="muted" style={{marginLeft:6}}>(head)</span></div>
                <div className="k">DOMAIN</div>
                <div className="v"><span className="dom-dot notes"></span> <span className="mono">notes</span> · chunk_type: <span className="mono">heading</span></div>
                <div className="k">ADAPTER</div>
                <div className="v mono">obsidian · normalizer v2.1</div>
                <div className="k">EMBEDDING MODEL</div>
                <div className="v mono">all-MiniLM-L6-v2</div>
                <div className="k">FIRST SEEN</div>
                <div className="v mono">2024-10-23 14:42:18Z</div>
                <div className="k">RETIRED</div>
                <div className="v"><span className="muted">— (active)</span></div>
              </div>
            </div>

            {/* Ancestry */}
            <div className="panel">
              <div className="panel-head" style={{padding:'10px 14px'}}>
                <div className="panel-title" style={{fontSize:12.5}}><Icon name="history" size={13}/>Version chain</div>
                <span className="eyebrow">3 GENERATIONS</span>
              </div>
              <div style={{padding:'4px 0'}}>
                <ChainRow head label="v3" hash="3f2a91ce8b14a09c…" note="current — diff-stage rewrite"
                          when="2 min ago" sim={null}/>
                <ChainRow label="v2" hash="a431f8d1ce0c2b8a…" note="prior — positional-diff approach"
                          when="4 days ago" sim={0.62}/>
                <ChainRow label="v1" hash="0c8d1e22f7a31f08…" note="root — initial draft, no diff stage"
                          when="6 days ago" sim={0.41}/>
              </div>
              <div style={{padding:'8px 14px 12px', borderTop:'1px solid var(--canvas-border)',
                            display:'flex', justifyContent:'space-between', alignItems:'center'}}>
                <span className="eyebrow">CHAIN_SIM TO HEAD ↑</span>
                <button className="btn btn-ghost btn-sm">view chain →</button>
              </div>
            </div>

            {/* Sync log */}
            <div className="panel">
              <div className="panel-head" style={{padding:'10px 14px'}}>
                <div className="panel-title" style={{fontSize:12.5}}><Icon name="refresh" size={13}/>Sync log</div>
                <span className="chip emerald" style={{padding:'1px 6px'}}><span className="dot"></span>in sync</span>
              </div>
              <div style={{padding:'10px 14px', display:'flex', flexDirection:'column', gap:6,
                            fontFamily:'var(--font-mono)', fontSize:11}}>
                <SyncLine when="14:42:19" op="INSERT" target="chromadb" state="ok"/>
                <SyncLine when="14:42:18" op="WRITE"  target="sqlite"   state="ok"/>
                <SyncLine when="14:42:18" op="HASH"   target="—"        state="new"/>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function ChainRow({ label, hash, note, when, sim, head }) {
  return (
    <div style={{padding:'10px 14px', borderBottom:'1px solid var(--canvas-border)',
                  display:'flex', gap:12, alignItems:'flex-start'}}>
      <span className={'version-pill' + (head ? ' deep' : '')} style={{flexShrink:0, marginTop:1}}>{label}</span>
      <div style={{flex:1, minWidth:0}}>
        <div className="mono" style={{fontSize:11.5, color:'var(--canvas-fg-1)'}}>{hash}</div>
        <div style={{fontSize:11.5, color:'var(--canvas-fg-3)', marginTop:2}}>{note}</div>
      </div>
      <div style={{textAlign:'right', flexShrink:0}}>
        <div className="mono" style={{fontSize:10.5, color:'var(--canvas-fg-3)'}}>{when}</div>
        {sim != null && (
          <div className="mono" style={{fontSize:10.5, color:'var(--canvas-fg-3)', marginTop:3,
                                          display:'inline-flex', alignItems:'center', gap:6}}>
            <span className="sim-bar" style={{width:40, height:3,
                       background:'var(--canvas-bg-2)', borderRadius:2, position:'relative', display:'inline-block'}}>
              <i style={{position:'absolute', left:0, top:0, bottom:0, width:(sim*100)+'%',
                          background:'var(--canvas-fg-3)', borderRadius:2}}></i>
            </span>
            {sim.toFixed(2)}
          </div>
        )}
      </div>
    </div>
  );
}

function SyncLine({ when, op, target, state }) {
  const stateColor = state === 'ok' ? 'var(--status-emerald)' : state === 'new' ? 'var(--status-cyan)' : 'var(--status-rose)';
  return (
    <div style={{display:'flex', gap:10}}>
      <span style={{color:'var(--canvas-fg-4)'}}>{when}</span>
      <span style={{color:'var(--canvas-fg-2)', fontWeight:500, width:50}}>{op}</span>
      <span style={{color:'var(--canvas-fg-3)', flex:1}}>{target}</span>
      <span style={{color:stateColor, fontWeight:500}}>{state}</span>
    </div>
  );
}

window.ChunkInspectorScreen = ChunkInspectorScreen;
