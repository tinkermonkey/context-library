// Notes domain · 3-pane reader — rebuilt on real heimdall components.
// Real DS: Panel, SegmentedControl, TabBar, VersionPill, Chip, Button, KVGrid, Icon.
// Reuse: file tree → HierarchyTree. Custom: markdown body w/ chunk markers, outline, wikilinks (app-level).

const { useState: useNotesState } = React;

function TreeRow({ depth = 0, dir, folder, selected, label, ver, open }) {
  return (
    <div className={'row' + (dir ? ' dir' : '') + (selected ? ' selected' : '') + (depth ? ' indent-' + depth : '')}>
      {dir && <Icon name={open ? 'chevronDown' : 'chevronRight'} size={11} className="chev" />}
      {folder && <Icon name="folder" size={12} />}
      <span>{label}</span>
      {ver && <span className="v-count">{ver}</span>}
    </div>
  );
}

function WLRow({ name, type, exists, arrow }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 8px', borderRadius: 4, cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 11.5, color: exists ? 'var(--cl-canvas-fg-1)' : 'var(--cl-canvas-fg-4)' }}>
      {arrow && <Icon name="arrowRight" size={10} />}
      <Icon name={type === 'ref' ? 'file' : type === 'adapter' ? 'component' : 'link'} size={11} />
      <span style={{ flex: 1 }}>{name}</span>
      {!exists && <Chip variant="rose">missing</Chip>}
    </div>
  );
}

function NotesScreen() {
  const [pane, setPane] = useNotesState('tree');
  const [tab, setTab] = useNotesState('chunked');
  return (
    <CLShell active="notes" breadcrumbs={['domain', 'notes', 'obsidian', 'projects', 'heimdall-graph-rag.md']}>
      <div className="split-3-domain">
        {/* Left: file tree */}
        <Panel noPadding className="cl-pane"
          title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}><span className="dom-dot notes"></span>Notes · 1,284</span>}
          headerAction={<SegmentedControl value={pane} onChange={setPane} options={[{ value: 'tree', label: 'tree' }, { value: 'recent', label: 'recent' }]} />}>
          <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--cl-canvas-border)', display: 'flex', gap: 8, alignItems: 'center' }}>
            <div style={{ display: 'inline-flex', gap: 6, padding: '5px 8px', background: 'var(--cl-canvas-bg-2)', border: '1px solid var(--cl-canvas-border)', borderRadius: 'var(--radius-md)', alignItems: 'center', flex: 1 }}>
              <Icon name="search" size={12} />
              <input style={{ border: 0, outline: 0, background: 'transparent', fontSize: 12, flex: 1, color: 'var(--cl-canvas-fg-1)' }} placeholder="Filter notes…" />
            </div>
            <span className="tbb-flag reuse"><Icon name="folder" size={10} /> reuse · HierarchyTree</span>
          </div>
          <div className="file-tree cl-scroll">
            <TreeRow dir folder open label="obsidian/vault" />
            <TreeRow dir depth={1} open label="projects" />
            <TreeRow depth={2} selected label="heimdall-graph-rag.md" ver="v3" />
            <TreeRow depth={2} label="2024-q4-followups.md" ver="v5" />
            <TreeRow depth={2} label="design-system-update.md" ver="v2" />
            <TreeRow depth={2} label="retrieval-benchmarks.md" ver="v1" />
            <TreeRow dir depth={1} label="daily" />
            <TreeRow dir depth={1} open label="research" />
            <TreeRow depth={2} label="rag-survey-2024.md" ver="v1" />
            <TreeRow depth={2} label="embedding-eval.md" ver="v3" />
            <TreeRow depth={2} label="graph-construction.md" ver="v2" />
            <TreeRow dir depth={1} label="reference" />
            <TreeRow dir folder label="filesystem/docs" />
            <TreeRow dir folder open label="apple.notes" />
            <TreeRow dir depth={1} open label="research" />
            <TreeRow depth={2} label="idea-graph-rag" ver="v1" />
            <TreeRow depth={2} label="followups-2024-q4" ver="v2" />
            <TreeRow dir folder label="filesystem.rich" />
          </div>
        </Panel>

        {/* Center: markdown reader */}
        <Panel noPadding className="cl-pane"
          title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13 }}><Icon name="file" size={14} /><span style={{ fontFamily: 'var(--font-mono)' }}>heimdall-graph-rag.md</span><VersionPill>v3</VersionPill><Chip variant="emerald">head</Chip></span>}
          headerAction={<span style={{ display: 'flex', gap: 6 }}><Button variant="ghost" size="sm">28 chunks</Button><Button variant="ghost" size="sm">history →</Button><Button variant="ghost" size="sm" icon aria-label="Open"><Icon name="upload" size={11} /></Button></span>}>
          <div style={{ padding: '0 16px', borderBottom: '1px solid var(--cl-canvas-border)' }}>
            <TabBar activeTabId={tab} onSelectTab={setTab} tabs={[
              { id: 'rendered', label: 'rendered' },
              { id: 'chunked', label: 'chunked', count: 28 },
              { id: 'raw', label: 'raw markdown' },
              { id: 'xref', label: 'cross-refs', count: 7 },
            ]} />
          </div>
          <div className="cl-scroll" style={{ padding: '18px 22px 22px' }}>
            <div className="md">
              <span className="chunk-mark">∙ chunk_01 · # Pipeline architecture · 7e3a91ff21…</span>
              <h1>Pipeline architecture</h1>
              <p>Heimdall ingests heterogeneous sources, normalizes them to markdown, and chunks them along semantic boundaries. The diff stage between normalization and chunking means that re-ingestion only produces new chunk versions when content has actually changed.</p>
              <span className="chunk-mark">∙ chunk_03 · ## Normalize · b3f29c4a18…</span>
              <h2>Normalize</h2>
              <p>Every adapter implements a deterministic normalizer. The same input should produce the same markdown on repeated runs. Trivial differences like whitespace are filtered out — the goal is paragraph-level change detection, not character-perfect diffs.</p>
              <ul>
                <li>Whitespace-only diffs are discarded</li>
                <li>Heading-level fluctuations are normalized</li>
                <li>Link formatting is canonicalized</li>
              </ul>
              <span className="chunk-mark">∙ chunk_04 · ## Diff stage · 3f2a91ce8b14… <span style={{ color: 'var(--cl-status-emerald)' }}>· new in v3</span></span>
              <h2>Diff stage</h2>
              <p>Chunks are content-addressed via <code>SHA-256</code> of their normalized markdown. Comparing two versions is therefore a set operation on hash sets:</p>
              <pre><code>{`added   = curr_hashes − prev_hashes
removed = prev_hashes − curr_hashes
kept    = curr_hashes ∩ prev_hashes`}</code></pre>
              <p>No positional alignment. Reordering sections produces zero diff cost. Performance is <code>O(n + m)</code> and embedding cost falls only on <code>added</code>.</p>
              <blockquote><strong>Cross-ref:</strong> <a href="#">lineage-design.md</a> — how <code>parent_chunk_hash</code> chains versions across edits.</blockquote>
            </div>
          </div>
        </Panel>

        {/* Right: outline + properties + links */}
        <Panel noPadding className="cl-pane"
          title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}><Icon name="layout" size={13} />Outline</span>}
          headerAction={<span className="eyebrow">7 SECTIONS</span>}>
          <div className="toc" style={{ padding: '10px 0', borderBottom: '1px solid var(--cl-canvas-border)' }}>
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
          <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--cl-canvas-border)' }}>
            <div className="eyebrow" style={{ marginBottom: 8 }}>PROPERTIES · YAML FRONTMATTER</div>
            <KVGrid keyWidth={92} rows={[
              { key: 'TAGS', value: <span style={{ display: 'inline-flex', gap: 6 }}><Chip variant="neutral">rag</Chip><Chip variant="neutral">pipeline</Chip><Chip variant="neutral">design</Chip></span> },
              { key: 'CREATED', value: <span className="mono">2024-10-17</span> },
              { key: 'UPDATED', value: <span className="mono">2024-10-23</span> },
              { key: 'STATUS', value: <Chip variant="amber">draft</Chip> },
            ]} />
          </div>
          <div className="cl-scroll" style={{ padding: '12px 14px' }}>
            <div className="eyebrow" style={{ marginBottom: 8 }}>WIKILINKS · 7</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <WLRow name="lineage-design.md" type="note" exists />
              <WLRow name="chunking-strategy.md" type="note" exists />
              <WLRow name="retrieval-benchmarks.md" type="note" exists />
              <WLRow name="rag-survey-2024.md" type="note" exists />
              <WLRow name="missing-spec.md" type="note" exists={false} />
              <WLRow name="differ.py" type="ref" exists />
              <WLRow name="apple-notes-bridge" type="adapter" exists />
            </div>
            <div className="eyebrow" style={{ marginTop: 14, marginBottom: 8 }}>BACKLINKS · 4</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <WLRow name="2024-q4-followups.md" type="note" exists arrow />
              <WLRow name="design-system-update.md" type="note" exists arrow />
              <WLRow name="daily/2024-10-21.md" type="note" exists arrow />
              <WLRow name="lineage-design.md" type="note" exists arrow />
            </div>
          </div>
        </Panel>
      </div>
    </CLShell>
  );
}

window.NotesScreen = NotesScreen;
