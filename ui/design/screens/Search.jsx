// Semantic Search — POST /query with full provenance chain
// Centerpiece: query input, faceted filters, ranked results with similarity bars + lineage

function SearchScreen() {
  return (
    <Shell active="search" breadcrumbs={['workspace', 'search', 'graph rag pipelines']}>
      <div className="canvas-inner" style={{padding:'20px 24px 24px'}}>
        {/* Page head */}
        <div className="page-head" style={{marginBottom:14}}>
          <div>
            <h1 style={{margin:0}}>
              Semantic search
              <span className="id-tag" style={{marginLeft:10}}>POST /query</span>
            </h1>
            <div className="subtitle">
              Vector search across 18,724 chunks. Results carry full provenance back to source,
              version, and adapter. Reranker available for high-precision queries.
            </div>
          </div>
          <div className="page-actions">
            <button className="btn"><Icon name="history" size={13}/> History</button>
            <button className="btn"><Icon name="ext" size={12}/> Export</button>
          </div>
        </div>

        {/* Hero search */}
        <div className="search-hero">
          <div className="input-row">
            <span className="ico"><Icon name="search" size={16}/></span>
            <input defaultValue="graph rag pipelines I've worked on" />
            <span className="kbd">⌘ ↵ search</span>
          </div>
          <div className="filters-row">
            <FD label="DOMAIN" value="notes, messages"/>
            <FD label="ADAPTER" value="all (11)"/>
            <FD label="SOURCE" value="any"/>
            <FD label="WHEN" value="any time"/>
            <FD label="TOP K" value="20"/>
            <div className="seg">
              <button className="active">vector</button>
              <button>+ rerank</button>
              <button>hybrid</button>
            </div>
            <span style={{marginLeft:'auto', display:'inline-flex', alignItems:'center', gap:10}}>
              <span className="eyebrow">7 results · 84 ms · 12 ms rerank</span>
            </span>
          </div>
        </div>

        {/* Body: results + facets */}
        <div style={{display:'grid', gridTemplateColumns:'1fr 280px', gap:18}}>
          {/* Results column */}
          <div>
            <div className="row between" style={{marginBottom:10}}>
              <div className="eyebrow">RANKED · BY SIMILARITY ↓</div>
              <div className="seg">
                <button className="active">similarity</button>
                <button>recency</button>
                <button>source</button>
              </div>
            </div>

            <ResultCard
              dom="notes"
              source="obsidian/vault/projects/heimdall-graph-rag.md"
              section="# Pipeline architecture &gt; ## Diff stage"
              version="v3"
              sim={0.89}
              snippet={<>
                The <mark>diff stage between normalization and chunking</mark> means
                re-ingestion only produces new chunk versions when content actually changes.
                All source content is normalized to <mark>markdown</mark> before comparison,
                giving a stable surface for detecting meaningful changes.
              </>}
              chunkHash="3f2a91ce8b14…"
              when="ingested 6 days ago"
              adapter="obsidian"
              parent="0c8d1e22f7a3…"
              normalizer="v2.1"
            />

            <ResultCard
              dom="messages"
              source="email.imap/work@studio · subject: 'graph rag handoff'"
              section="Thread · 4 of 7 messages · from morgan"
              version="v1"
              sim={0.84}
              snippet={<>
                For the new pipeline, I want to <mark>preserve threading</mark> when chunking —
                individual messages stay atomic but reply chains carry as structured context.
                Then the retriever can <mark>reconstruct conversations</mark> at query time.
              </>}
              chunkHash="8a14ce0c9d2f…"
              when="ingested 2 days ago"
              adapter="email"
              parent={null}
              normalizer="v1.0"
            />

            <ResultCard
              dom="notes"
              source="filesystem/docs/rag/lineage-design.md"
              section="# Adapter contract &gt; ## Domain mapping"
              version="v2"
              sim={0.78}
              snippet={<>
                Adapters are cheap to write. The interface is small and the domain layer does
                the heavy lifting — <mark>adapters encode access</mark>, <mark>domains
                encode semantics</mark>. A Gmail adapter knows how to fetch email. The
                Messages domain knows how to chunk conversations.
              </>}
              chunkHash="c9d2f8e314a0…"
              when="ingested 3 weeks ago"
              adapter="filesystem"
              parent="a431f8d1ce…"
              normalizer="v1.8"
            />

            <ResultCard
              dom="tasks"
              source="apple.reminders/list 'context-library'"
              section="Task — done"
              version="v4"
              sim={0.71}
              snippet={<>
                <mark>Implement parent_chunk_hash field</mark> so the chunk table self-references
                its previous version. Enables version-chain queries without positional alignment.
                State: open → in-progress → done (2024-Q3).
              </>}
              chunkHash="412a9ce8b1f0…"
              when="state→done · 5 weeks ago"
              adapter="apple.reminders"
              parent="3f2a91ce8b14…"
              normalizer="v0.7"
            />

            <ResultCard
              dom="notes"
              source="obsidian/daily/2024-09-12.md"
              section="# Standup · ## RAG followups"
              version="v1"
              sim={0.66}
              snippet={<>
                Skim through the <mark>chunking strategy doc</mark>. Action: rewrite the
                notes-domain chunker so heading-level fluctuations don't trigger phantom diffs.
                Carry the breadcrumb in context_header so the embedding context survives edits.
              </>}
              chunkHash="d1e22f7a3091…"
              when="ingested 2 months ago"
              adapter="obsidian"
              parent={null}
              normalizer="v1.5"
            />
          </div>

          {/* Facets / inspector column */}
          <div>
            <div className="panel" style={{marginBottom:14}}>
              <div className="panel-head" style={{padding:'10px 12px'}}>
                <div className="panel-title" style={{fontSize:12}}><Icon name="filter" size={13}/>Facets</div>
                <span className="eyebrow">7 hits</span>
              </div>
              <div style={{padding:'4px 0 8px'}}>
                <FacetGroup title="DOMAIN" rows={[
                  ['notes',     3, 'notes'],
                  ['messages',  2, 'messages'],
                  ['tasks',     1, 'tasks'],
                  ['events',    1, 'events'],
                ]}/>
                <FacetGroup title="ADAPTER" rows={[
                  ['obsidian',          2],
                  ['email',             2],
                  ['filesystem',        1],
                  ['apple.reminders',   1],
                  ['caldav',            1],
                ]}/>
                <FacetGroup title="VERSION CHAIN" rows={[
                  ['head only',        5],
                  ['has parent',       4],
                  ['retired',          0],
                ]}/>
              </div>
            </div>

            <div className="panel">
              <div className="panel-head" style={{padding:'10px 12px'}}>
                <div className="panel-title" style={{fontSize:12}}><Icon name="brain" size={13}/>Query</div>
              </div>
              <div className="kv-dense" style={{padding:'12px'}}>
                <div className="k">EMBEDDING</div>
                <div className="v mono">all-MiniLM-L6-v2 · 384d</div>
                <div className="k">DOMAIN</div>
                <div className="v mono">notes, messages</div>
                <div className="k">TOP K</div>
                <div className="v mono">20</div>
                <div className="k">RERANK</div>
                <div className="v mono">off</div>
                <div className="k">FETCH</div>
                <div className="v mono">+ lineage, + parent</div>
                <div className="k">LATENCY</div>
                <div className="v mono">84 ms total</div>
              </div>
              <div style={{padding:'10px 12px', borderTop:'1px solid var(--canvas-border)',
                          background:'var(--canvas-bg-2)'}}>
                <div className="eyebrow" style={{marginBottom:6}}>EQUIVALENT cURL</div>
                <pre style={{margin:0, fontFamily:'var(--font-mono)', fontSize:10.5,
                             color:'var(--canvas-fg-2)', lineHeight:1.55, whiteSpace:'pre-wrap'}}>
{`curl -X POST :8000/query \\
  -d '{"query": "graph rag…",
       "top_k": 20,
       "domain_filter": ["notes","messages"]}'`}
                </pre>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function FD({ label, value }) {
  return (
    <button className="fd-trigger" style={{minWidth:0, padding:'6px 10px'}}>
      <span className="fd-eyebrow">{label}</span>
      <span className="fd-value">{value}</span>
      <span className="fd-chev"><Icon name="chevDown" size={11}/></span>
    </button>
  );
}

function ResultCard({ dom, source, section, version, sim, snippet, chunkHash, when, adapter, parent, normalizer }) {
  return (
    <div className="result-card">
      <div className={'dom-bar ' + dom}></div>
      <div className="body">
        <div className="head-row">
          <span className={'dom-dot ' + dom}></span>
          <span className="mono" style={{fontSize:12, fontWeight:600, color:'var(--canvas-fg-1)'}}>{source}</span>
          <span className="version-pill">{version}</span>
          <span className="similarity">
            <span className="sim-bar"><i style={{width: (sim*100) + '%'}}></i></span>
            <span>{sim.toFixed(2)}</span>
          </span>
        </div>
        <div className="ctx">
          <Icon name="link" size={11}/>
          <span>{section}</span>
          <span className="sep">·</span>
          <span>chunk_hash <span style={{color:'var(--canvas-fg-2)'}}>{chunkHash}</span></span>
        </div>
        <div className="snippet">{snippet}</div>
        <div className="meta-row">
          <span><b>adapter</b>{adapter}</span>
          <span><b>parent</b>{parent || <span style={{color:'var(--canvas-fg-4)'}}>none (root)</span>}</span>
          <span><b>normalizer</b>{normalizer}</span>
          <span><b>state</b>{when}</span>
          <span style={{marginLeft:'auto', display:'inline-flex', gap:8}}>
            <button className="btn btn-ghost btn-sm" style={{padding:'2px 8px'}}>view chunk →</button>
            <button className="btn btn-ghost btn-sm" style={{padding:'2px 8px'}}>open source →</button>
          </span>
        </div>
      </div>
    </div>
  );
}

function FacetGroup({ title, rows }) {
  return (
    <div style={{padding:'6px 0'}}>
      <div className="eyebrow" style={{padding:'4px 12px'}}>{title}</div>
      {rows.map(([name, n, dom]) => (
        <div key={name} className="fd-row" style={{margin:'0 4px', padding:'6px 10px'}}>
          {dom
            ? <span className={'dom-dot ' + dom} style={{width:7, height:7}}></span>
            : <span className="fd-checkbox"></span>}
          <span style={{fontFamily: dom ? 'var(--font-mono)' : 'var(--font-sans)'}}>{name}</span>
          <span className="fd-meta">{n}</span>
        </div>
      ))}
    </div>
  );
}

window.SearchScreen = SearchScreen;
