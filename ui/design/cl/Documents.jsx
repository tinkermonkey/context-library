// Documents domain · catalog — rebuilt on real heimdall components.
// Real DS: Panel, SegmentedControl, VersionPill, Chip, KVGrid, Icon.
// Shipped in heimdall: AssetCard / AssetGrid (doc-tile catalog).
// Reuse: file tree → HierarchyTree. Custom: outline / TOC (app-level).

const { useState: useDocState } = React;

function DTreeRow({ depth = 0, dir, folder, open, selected, label, ver, dim }) {
  return (
    <div className={'row' + (dir ? ' dir' : '') + (selected ? ' selected' : '') + (depth ? ' indent-' + depth : '')} style={dim ? { opacity: 0.65 } : {}}>
      {dir && <Icon name={open ? 'chevronDown' : 'chevronRight'} size={11} className="chev" />}
      {folder && <Icon name="folder" size={12} />}
      <span>{label}</span>
      {ver && <span className="v-count">{ver}</span>}
    </div>
  );
}
function FacetItem({ label, count, dot, active }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 10px', margin: '0 4px', borderRadius: 3, background: active ? 'rgba(251,191,36,0.06)' : 'transparent', borderLeft: active ? '2px solid rgb(var(--accent-primary))' : '2px solid transparent', paddingLeft: active ? 8 : 10, cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 11.5, color: active ? 'var(--cl-canvas-fg-1)' : 'var(--cl-canvas-fg-2)' }}>
      {dot && <span style={{ width: 7, height: 7, borderRadius: 2, background: dot }}></span>}
      <span style={{ flex: 1 }}>{label}</span>
      <span style={{ color: 'var(--cl-canvas-fg-3)', fontSize: 10.5 }}>{count}</span>
    </div>
  );
}
function DocTile({ ext, title, authors, pages, chunks, when, selected, highlight }) {
  const extColor = { pdf: '#F87171', docx: '#60A5FA', pptx: '#FB923C', xlsx: '#10B981', image: '#C084FC' }[ext] || '#94A3B8';
  const thumbBg = { pdf: 'linear-gradient(135deg, #FEE2E2 0%, #FCA5A5 100%)', docx: 'linear-gradient(135deg, #DBEAFE 0%, #93C5FD 100%)', pptx: 'linear-gradient(135deg, #FFEDD5 0%, #FDBA74 100%)', xlsx: 'linear-gradient(135deg, #D1FAE5 0%, #6EE7B7 100%)', image: 'linear-gradient(135deg, #EDE9FE 0%, #C4B5FD 100%)' }[ext] || 'var(--cl-canvas-bg-2)';
  return (
    <div className={'doc-tile' + (selected ? ' selected' : '')}>
      <div className="thumb" style={{ background: thumbBg }}>
        <div className="doc-page" style={{ '--ext-color': extColor }}>
          <div className="lines"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
          <div className="ext-tab">{ext.toUpperCase()}</div>
        </div>
        {highlight && <div className="highlight-badge">cited</div>}
      </div>
      <div className="meta">
        <div className="title">{title}</div>
        <div className="sub"><span>{authors}</span></div>
        <div className="sub" style={{ marginTop: 3 }}>
          <span>{pages}p</span><span style={{ color: 'var(--cl-canvas-fg-4)' }}>·</span><span>{chunks} chunks</span><span style={{ color: 'var(--cl-canvas-fg-4)' }}>·</span><span>{when}</span>
        </div>
      </div>
    </div>
  );
}
function ChunkPill({ kind, n, flag }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 8px', background: flag ? 'var(--cl-semantic-amber-bg)' : 'var(--cl-canvas-bg-2)', border: '1px solid ' + (flag ? 'var(--cl-semantic-amber-border)' : 'var(--cl-canvas-border)'), borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-mono)', fontSize: 10.5 }}>
      <span style={{ color: flag ? 'var(--cl-status-amber)' : 'var(--cl-canvas-fg-3)', flex: 1 }}>{kind}</span>
      <span style={{ color: 'var(--cl-canvas-fg-1)', fontWeight: 600 }}>{n}</span>
    </div>
  );
}

function DocumentsScreen() {
  const [pane, setPane] = useDocState('tree');
  const [layout, setLayout] = useDocState('grid');
  return (
    <CLShell active="documents" breadcrumbs={['domain', 'documents', 'papers', 'lewis-rag-2020.pdf']}>
      <div className="cl-fill" style={{ display: 'grid', gridTemplateColumns: '240px 1fr 320px', gap: 14 }}>
        {/* Left: file tree */}
        <Panel noPadding className="cl-pane"
          title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}><span className="dom-dot documents"></span>Documents · 260</span>}
          headerAction={<SegmentedControl value={pane} onChange={setPane} options={[{ value: 'tree', label: 'tree' }, { value: 'recent', label: 'recent' }]} />}>
          <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--cl-canvas-border)', display: 'flex', gap: 8, alignItems: 'center' }}>
            <div style={{ display: 'inline-flex', gap: 6, padding: '5px 8px', background: 'var(--cl-canvas-bg-2)', border: '1px solid var(--cl-canvas-border)', borderRadius: 'var(--radius-md)', alignItems: 'center', flex: 1 }}>
              <Icon name="search" size={12} />
              <input style={{ border: 0, outline: 0, background: 'transparent', fontSize: 12, flex: 1, color: 'var(--cl-canvas-fg-1)' }} placeholder="Filter documents…" defaultValue="rag" />
            </div>
            <span className="tbb-flag reuse"><Icon name="folder" size={10} /> reuse · HierarchyTree</span>
          </div>
          <div className="file-tree cl-scroll">
            <DTreeRow dir folder open label="filesystem.rich" />
            <DTreeRow dir depth={1} open label="papers" />
            <DTreeRow depth={2} selected label="lewis-rag-2020.pdf" ver="42c" />
            <DTreeRow depth={2} label="karpukhin-dpr-2020.pdf" ver="38c" />
            <DTreeRow depth={2} label="borgeaud-retro-2022.pdf" ver="104c" />
            <DTreeRow depth={2} label="guu-realm-2020.pdf" ver="28c" />
            <DTreeRow depth={2} label="liu-lost-middle-2023.pdf" ver="34c" />
            <DTreeRow depth={2} label="gao-hyde-2022.pdf" ver="22c" />
            <DTreeRow depth={2} label="santhanam-colbertv2.pdf" ver="48c" />
            <DTreeRow depth={2} label="ram-icrag-2023.pdf" ver="36c" />
            <DTreeRow dir depth={1} label="contracts" />
            <DTreeRow dir depth={1} label="bills" />
            <DTreeRow dir depth={1} label="receipts" />
            <DTreeRow dir depth={1} open label="manuals" />
            <DTreeRow depth={2} label="heimdall-handbook-v2.pdf" ver="86c" />
            <DTreeRow depth={2} label="api-reference.pdf" ver="128c" />
            <DTreeRow depth={2} label="deploy-runbook.docx" ver="42c" />
            <DTreeRow dir depth={1} open label="handwritten · ocr" />
            <DTreeRow depth={2} label="notebook-2024-q3.png" ver="12c" />
            <DTreeRow depth={2} label="whiteboard-rag-arch.png" ver="6c" />
            <DTreeRow depth={2} label="sketch-pipeline.png" ver="4c" />
            <div className="eyebrow" style={{ padding: '10px 12px 4px', marginTop: 8, borderTop: '1px solid var(--cl-canvas-border)' }}>FILTERS</div>
            <FacetItem label="pdf" count={142} dot="#F87171" active />
            <FacetItem label="docx" count={42} dot="#60A5FA" />
            <FacetItem label="image · ocr" count={32} dot="#C084FC" />
            <FacetItem label="ocr failed" count={4} dot="var(--cl-status-rose)" />
          </div>
        </Panel>

        {/* Center: catalog */}
        <Panel noPadding className="cl-pane"
          title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13 }}><Icon name="layout" size={14} />papers · pdf · 7 matches</span>}
          headerAction={<span className="row" style={{ gap: 8 }}><span className="tbb-flag shipped"><Icon name="layout" size={10} /> heimdall · AssetGrid</span><SegmentedControl value={layout} onChange={setLayout} options={[{ value: 'grid', label: 'grid' }, { value: 'list', label: 'list' }]} /></span>}
          footer={<div className="between" style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--cl-canvas-fg-3)' }}><span>8 of 62 documents · 354 chunks · 14.2 MB index</span><span>1 selected</span></div>}>
          <div className="cl-scroll" style={{ padding: 14, display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, alignContent: 'flex-start' }}>
            <DocTile selected ext="pdf" title="Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks" authors="Lewis et al · 2020" pages={16} chunks={42} when="2w" highlight />
            <DocTile ext="pdf" title="Dense Passage Retrieval for Open-Domain Question Answering" authors="Karpukhin · 2020" pages={14} chunks={38} when="3w" highlight />
            <DocTile ext="pdf" title="Improving Language Models by Retrieving from Trillions of Tokens" authors="Borgeaud · 2022" pages={42} chunks={104} when="1mo" />
            <DocTile ext="pdf" title="REALM — Retrieval-Augmented Language Model Pre-Training" authors="Guu et al · 2020" pages={12} chunks={28} when="1mo" />
            <DocTile ext="pdf" title="Lost in the Middle — How Language Models Use Long Contexts" authors="Liu et al · 2023" pages={14} chunks={34} when="1mo" />
            <DocTile ext="pdf" title="HyDE — Precise Zero-Shot Dense Retrieval" authors="Gao et al · 2022" pages={10} chunks={22} when="2mo" />
            <DocTile ext="pdf" title="ColBERTv2 — Effective and Efficient Retrieval" authors="Santhanam · 2022" pages={16} chunks={48} when="2mo" />
            <DocTile ext="pdf" title="In-Context Retrieval-Augmented Language Models" authors="Ram et al · 2023" pages={14} chunks={36} when="2mo" />
          </div>
        </Panel>

        {/* Right: document detail */}
        <Panel noPadding className="cl-pane"
          title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}><Icon name="file" size={13} />Document</span>}
          headerAction={<VersionPill>v1</VersionPill>}>
          <div style={{ padding: 14, borderBottom: '1px solid var(--cl-canvas-border)' }}>
            <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
              <div style={{ width: 54, height: 68, background: '#F87171', borderRadius: 3, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, boxShadow: '2px 2px 0 var(--cl-canvas-border)' }}>PDF</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--cl-canvas-fg-1)', lineHeight: 1.35, letterSpacing: '-0.005em' }}>Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--cl-canvas-fg-3)', marginTop: 4 }}>Lewis et al · 2020 · arxiv:2005.11401</div>
              </div>
            </div>
          </div>
          <div className="cl-scroll" style={{ padding: 14 }}>
            <KVGrid keyWidth={92} rows={[
              { key: 'DOC_TYPE', value: <span className="mono" style={{ fontSize: 11.5 }}>pdf · academic-paper</span> },
              { key: 'PAGES', value: <span className="mono" style={{ fontSize: 11.5 }}>16 (2 figures, 4 tables)</span> },
              { key: 'SOURCE', value: <span className="mono" style={{ fontSize: 11, wordBreak: 'break-all' }}>filesystem.rich/papers/lewis-rag-2020.pdf</span> },
              { key: 'EXTRACTOR', value: <span className="mono" style={{ fontSize: 11.5 }}>markitdown v1.2</span> },
              { key: 'OCR', value: <Chip variant="emerald">text-extracted</Chip> },
              { key: 'SIZE', value: <span className="mono" style={{ fontSize: 11.5 }}>892 KB · 14,820 tokens</span> },
            ]} />
            <div className="eyebrow" style={{ margin: '10px 0 6px' }}>CHUNKS · 42</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 14 }}>
              <ChunkPill kind="heading" n={11} />
              <ChunkPill kind="paragraph" n={22} />
              <ChunkPill kind="table" n={4} />
              <ChunkPill kind="figure" n={2} />
              <ChunkPill kind="code" n={1} />
              <ChunkPill kind="oversized" n={2} flag />
            </div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>OUTLINE</div>
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
        </Panel>
      </div>
    </CLShell>
  );
}

window.DocumentsScreen = DocumentsScreen;
