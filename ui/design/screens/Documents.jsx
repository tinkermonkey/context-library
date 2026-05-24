// Documents domain — rich-doc catalog (PDF, DOCX, images) + reader
// Adapter: filesystem.rich. DocumentMetadata: title, document_type.
// Each doc may produce many chunks (per chunking-strategy: tables/figures/code stay atomic).

function DocumentsScreen() {
  return (
    <Shell active="documents" breadcrumbs={['domain', 'documents', 'papers', 'lewis-rag-2020.pdf']}>
      <div className="canvas-inner" style={{padding:0, minWidth:0}}>
        <div style={{display:'grid', gridTemplateColumns:'240px 1fr 320px', gap:14,
                     padding:14, height:'100%', minHeight:0}}>

          {/* Left: file tree */}
          <div className="panel" style={{display:'flex', flexDirection:'column', overflow:'hidden'}}>
            <div className="panel-head" style={{padding:'10px 12px'}}>
              <div className="panel-title" style={{fontSize:12.5}}>
                <span className="dom-dot documents"></span>Documents · 260
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
                       placeholder="Filter documents…" defaultValue="rag"/>
              </div>
            </div>

            <div className="file-tree" style={{flex:1, overflow:'auto'}}>
              <div className="row dir"><Icon name="chevDown" size={11} className="chev"/>📁 filesystem.rich</div>
              <div className="row dir indent-1"><Icon name="chevDown" size={11} className="chev"/>papers</div>
              <div className="row indent-2 selected">lewis-rag-2020.pdf <span className="v-count">42c</span></div>
              <div className="row indent-2">karpukhin-dpr-2020.pdf <span className="v-count">38c</span></div>
              <div className="row indent-2">borgeaud-retro-2022.pdf <span className="v-count">104c</span></div>
              <div className="row indent-2">guu-realm-2020.pdf <span className="v-count">28c</span></div>
              <div className="row indent-2">liu-lost-middle-2023.pdf <span className="v-count">34c</span></div>
              <div className="row indent-2">gao-hyde-2022.pdf <span className="v-count">22c</span></div>
              <div className="row indent-2">santhanam-colbertv2.pdf <span className="v-count">48c</span></div>
              <div className="row indent-2">ram-icrag-2023.pdf <span className="v-count">36c</span></div>
              <div className="row dir indent-1"><Icon name="chevRight" size={11} className="chev"/>contracts</div>
              <div className="row dir indent-1"><Icon name="chevRight" size={11} className="chev"/>bills</div>
              <div className="row dir indent-1"><Icon name="chevRight" size={11} className="chev"/>receipts</div>
              <div className="row dir indent-1"><Icon name="chevDown" size={11} className="chev"/>manuals</div>
              <div className="row indent-2">heimdall-handbook-v2.pdf <span className="v-count">86c</span></div>
              <div className="row indent-2">api-reference.pdf <span className="v-count">128c</span></div>
              <div className="row indent-2">deploy-runbook.docx <span className="v-count">42c</span></div>
              <div className="row dir indent-1"><Icon name="chevDown" size={11} className="chev"/>handwritten <span className="v-count" style={{marginLeft:6}}>ocr</span></div>
              <div className="row indent-2">notebook-2024-q3.png <span className="v-count">12c</span></div>
              <div className="row indent-2">whiteboard-rag-arch.png <span className="v-count">6c</span></div>
              <div className="row indent-2">sketch-pipeline.png <span className="v-count">4c</span></div>
              <div className="row dir"><Icon name="chevRight" size={11} className="chev"/>📁 filesystem.rich (presentations)</div>
              <div className="row dir indent-1" style={{opacity:0.65}}><Icon name="chevRight" size={11} className="chev"/>q4-board-deck.pptx</div>
              <div className="row dir indent-1" style={{opacity:0.65}}><Icon name="chevRight" size={11} className="chev"/>roadmap-2025.pptx</div>
              <div className="row dir"><Icon name="chevRight" size={11} className="chev"/>📁 filesystem.rich (spreadsheets)</div>

              <div className="eyebrow" style={{padding:'10px 12px 4px', marginTop:8,
                                                  borderTop:'1px solid var(--canvas-border)'}}>FILTERS</div>
              <FacetItem label="pdf"    count={142} dot="#F87171" active/>
              <FacetItem label="docx"   count={42}  dot="#60A5FA"/>
              <FacetItem label="image · ocr" count={32} dot="#C084FC"/>
              <FacetItem label="ocr failed" count={4} dot="var(--status-rose)"/>
            </div>
          </div>

          {/* Center: catalog grid */}
          <div className="panel" style={{display:'flex', flexDirection:'column', overflow:'hidden'}}>
            <div className="panel-head" style={{padding:'10px 14px'}}>
              <div className="panel-title" style={{fontSize:13}}><Icon name="layers" size={14}/>papers · pdf · 7 matches</div>
              <div className="seg">
                <button className="active">grid</button>
                <button>list</button>
              </div>
            </div>

            <div style={{padding:14, overflow:'auto', flex:1,
                          display:'grid', gridTemplateColumns:'repeat(4, 1fr)', gap:12,
                          alignContent:'flex-start'}}>
              <DocTile selected ext="pdf" title="Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"
                       authors="Lewis et al · 2020" pages={16} chunks={42} when="2w" highlight/>
              <DocTile ext="pdf" title="Dense Passage Retrieval for Open-Domain Question Answering"
                       authors="Karpukhin · 2020" pages={14} chunks={38} when="3w" highlight/>
              <DocTile ext="pdf" title="Improving Language Models by Retrieving from Trillions of Tokens"
                       authors="Borgeaud · 2022" pages={42} chunks={104} when="1mo"/>
              <DocTile ext="pdf" title="REALM — Retrieval-Augmented Language Model Pre-Training"
                       authors="Guu et al · 2020" pages={12} chunks={28} when="1mo"/>
              <DocTile ext="pdf" title="Lost in the Middle — How Language Models Use Long Contexts"
                       authors="Liu et al · 2023" pages={14} chunks={34} when="1mo"/>
              <DocTile ext="pdf" title="HyDE — Precise Zero-Shot Dense Retrieval"
                       authors="Gao et al · 2022" pages={10} chunks={22} when="2mo"/>
              <DocTile ext="pdf" title="ColBERTv2 — Effective and Efficient Retrieval"
                       authors="Santhanam · 2022" pages={16} chunks={48} when="2mo"/>
              <DocTile ext="pdf" title="In-Context Retrieval-Augmented Language Models"
                       authors="Ram et al · 2023" pages={14} chunks={36} when="2mo"/>
            </div>

            <div style={{padding:'8px 14px', borderTop:'1px solid var(--canvas-border)',
                          background:'var(--canvas-bg-2)',
                          display:'flex', justifyContent:'space-between', alignItems:'center',
                          fontFamily:'var(--font-mono)', fontSize:11, color:'var(--canvas-fg-3)'}}>
              <span>8 of 62 documents · 354 chunks · 14.2 MB index</span>
              <span>1 selected</span>
            </div>
          </div>

          {/* Right: document detail */}
          <div className="panel" style={{display:'flex', flexDirection:'column', overflow:'hidden'}}>
            <div className="panel-head" style={{padding:'10px 12px'}}>
              <div className="panel-title" style={{fontSize:12.5}}><Icon name="doc" size={13}/>Document</div>
              <span className="version-pill">v1</span>
            </div>

            <div style={{padding:14, borderBottom:'1px solid var(--canvas-border)'}}>
              <div style={{display:'flex', gap:12, alignItems:'flex-start'}}>
                <div className="thumb" style={{width:54, height:68, background:'#F87171',
                                                  borderRadius:3, display:'flex', alignItems:'center',
                                                  justifyContent:'center', color:'#fff',
                                                  fontFamily:'var(--font-mono)', fontSize:11, fontWeight:600,
                                                  boxShadow:'2px 2px 0 var(--canvas-border)'}}>PDF</div>
                <div style={{flex:1, minWidth:0}}>
                  <div style={{fontSize:13.5, fontWeight:600, color:'var(--canvas-fg-1)',
                                lineHeight:1.35, letterSpacing:'-0.005em'}}>
                    Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks
                  </div>
                  <div style={{fontFamily:'var(--font-mono)', fontSize:10.5,
                                color:'var(--canvas-fg-3)', marginTop:4}}>
                    Lewis et al · 2020 · arxiv:2005.11401
                  </div>
                </div>
              </div>
            </div>

            <div style={{padding:'14px', overflow:'auto', flex:1}}>
              <div className="kv-dense" style={{marginBottom:14}}>
                <div className="k">DOC_TYPE</div>
                <div className="v mono" style={{fontSize:11.5}}>pdf · academic-paper</div>
                <div className="k">PAGES</div>
                <div className="v mono" style={{fontSize:11.5}}>16 (2 figures, 4 tables)</div>
                <div className="k">SOURCE</div>
                <div className="v mono" style={{fontSize:11, wordBreak:'break-all'}}>filesystem.rich/papers/lewis-rag-2020.pdf</div>
                <div className="k">EXTRACTOR</div>
                <div className="v mono" style={{fontSize:11.5}}>markitdown v1.2</div>
                <div className="k">OCR</div>
                <div className="v"><span className="chip emerald" style={{padding:'1px 6px', fontSize:10}}><span className="dot"></span>text-extracted</span></div>
                <div className="k">SIZE</div>
                <div className="v mono" style={{fontSize:11.5}}>892 KB · 14,820 tokens</div>
              </div>

              <div className="eyebrow" style={{marginBottom:6}}>CHUNKS · 42</div>
              <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:6, marginBottom:14}}>
                <ChunkPill kind="heading" n={11}/>
                <ChunkPill kind="paragraph" n={22}/>
                <ChunkPill kind="table" n={4}/>
                <ChunkPill kind="figure" n={2}/>
                <ChunkPill kind="code" n={1}/>
                <ChunkPill kind="oversized" n={2} flag/>
              </div>

              <div className="eyebrow" style={{marginBottom:6}}>OUTLINE</div>
              <div className="toc">
                <div className="row">Abstract</div>
                <div className="row">1 — Introduction</div>
                <div className="row active">2 — Methods</div>
                <div className="row h2 active">2.1 RAG-Sequence</div>
                <div className="row h2">2.2 RAG-Token</div>
                <div className="row">3 — Experiments</div>
                <div className="row h2">3.1 Open-Domain QA</div>
                <div className="row h2">3.2 Abstractive QA</div>
                <div className="row">4 — Discussion</div>
                <div className="row">5 — Related Work</div>
                <div className="row">References</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function FacetSection({ title, children }) {
  return (
    <div style={{padding:'8px 0', marginBottom:4}}>
      <div className="eyebrow" style={{padding:'4px 12px 6px'}}>{title}</div>
      <div style={{display:'flex', flexDirection:'column', gap:0}}>{children}</div>
    </div>
  );
}

function FacetItem({ label, count, dot, active, sub }) {
  return (
    <div style={{
      display:'flex', alignItems:'center', gap:8,
      padding:'5px 10px', margin:'0 4px',
      borderRadius:3,
      background: active ? 'rgba(251,191,36,0.06)' : 'transparent',
      borderLeft: active ? '2px solid var(--accent-primary)' : '2px solid transparent',
      paddingLeft: active ? 8 : 10,
      cursor:'pointer',
      fontFamily:'var(--font-mono)', fontSize:11.5,
      color: active ? 'var(--canvas-fg-1)' : 'var(--canvas-fg-2)',
    }}>
      {dot && <span style={{width:7, height:7, borderRadius:2, background:dot}}></span>}
      <span style={{flex:1}}>{label}</span>
      {sub && <span style={{fontSize:9.5, color:'var(--canvas-fg-4)', letterSpacing:'0.04em', textTransform:'uppercase'}}>{sub}</span>}
      <span style={{color:'var(--canvas-fg-3)', fontSize:10.5}}>{count}</span>
    </div>
  );
}

function DocTile({ ext, title, authors, pages, chunks, when, selected, highlight }) {
  const extColor = { pdf: '#F87171', docx: '#60A5FA', pptx: '#FB923C', xlsx: '#10B981', image: '#C084FC' }[ext] || '#94A3B8';
  const thumbBg = { pdf: 'linear-gradient(135deg, #FEE2E2 0%, #FCA5A5 100%)',
                    docx:'linear-gradient(135deg, #DBEAFE 0%, #93C5FD 100%)',
                    pptx:'linear-gradient(135deg, #FFEDD5 0%, #FDBA74 100%)',
                    xlsx:'linear-gradient(135deg, #D1FAE5 0%, #6EE7B7 100%)',
                    image:'linear-gradient(135deg, #EDE9FE 0%, #C4B5FD 100%)' }[ext] || 'linear-gradient(135deg, var(--canvas-bg-2) 0%, var(--canvas-card) 100%)';
  return (
    <div className={'doc-tile' + (selected ? ' selected' : '')}>
      <div className="thumb" style={{background: thumbBg}}>
        <div className="doc-page" style={{'--ext-color': extColor}}>
          <div className="lines">
            <i></i><i></i><i></i><i></i><i></i><i></i><i></i>
          </div>
          <div className="ext-tab">{ext.toUpperCase()}</div>
        </div>
        {highlight && <div className="highlight-badge">cited</div>}
      </div>
      <div className="meta">
        <div className="title">{title}</div>
        <div className="sub">
          <span>{authors}</span>
        </div>
        <div className="sub" style={{marginTop:3}}>
          <span>{pages}p</span>
          <span style={{color:'var(--canvas-fg-4)'}}>·</span>
          <span>{chunks} chunks</span>
          <span style={{color:'var(--canvas-fg-4)'}}>·</span>
          <span>{when}</span>
        </div>
      </div>
    </div>
  );
}

function ChunkPill({ kind, n, flag }) {
  return (
    <div style={{
      display:'flex', alignItems:'center', gap:6,
      padding:'5px 8px',
      background: flag ? 'var(--semantic-amber-bg)' : 'var(--canvas-bg-2)',
      border:'1px solid ' + (flag ? 'var(--semantic-amber-border)' : 'var(--canvas-border)'),
      borderRadius:'var(--radius-md)',
      fontFamily:'var(--font-mono)', fontSize:10.5,
    }}>
      <span style={{color: flag ? 'var(--status-amber)' : 'var(--canvas-fg-3)', flex:1}}>{kind}</span>
      <span style={{color:'var(--canvas-fg-1)', fontWeight:600}}>{n}</span>
    </div>
  );
}

window.DocumentsScreen = DocumentsScreen;
