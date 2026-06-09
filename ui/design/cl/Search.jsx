// Semantic Search — rebuilt on real heimdall components.
// Real DS: PageHeader, FilterDropdown, SegmentedControl, VersionPill, Chip,
// Button, Panel, KVGrid, Icon.
// Custom (flagged): the search hero shell (compose-only). Shipped in heimdall: ResultCard.

const { useState: useSearchState } = React;

function Facet({ label, summary, section, options, selected }) {
  return (
    <FilterDropdown mode="checkbox" defaultValue={selected}>
      <FilterDropdown.Trigger label={label} summary={summary} />
      <FilterDropdown.Panel>
        <FilterDropdown.Section title={section}>
          {options.map(o => <FilterDropdown.Checkbox key={o} value={o} label={o} />)}
        </FilterDropdown.Section>
      </FilterDropdown.Panel>
    </FilterDropdown>
  );
}

function ResultCard({ dom, source, section, version, sim, snippet, chunkHash, when, adapter, parent, normalizer }) {
  return (
    <div className="result-card">
      <div className={'dom-bar ' + dom}></div>
      <div className="body">
        <div className="head-row">
          <span className={'dom-dot ' + dom}></span>
          <span className="mono" style={{ fontSize: 12, fontWeight: 600, color: 'var(--cl-canvas-fg-1)' }}>{source}</span>
          <VersionPill>{version}</VersionPill>
          <span className="similarity">
            <span className="sim-bar"><i style={{ width: (sim * 100) + '%' }}></i></span>
            <span>{sim.toFixed(2)}</span>
          </span>
        </div>
        <div className="ctx">
          <Icon name="link" size={11} />
          <span>{section}</span>
          <span className="sep">·</span>
          <span>chunk_hash <span style={{ color: 'var(--cl-canvas-fg-2)' }}>{chunkHash}</span></span>
        </div>
        <div className="snippet">{snippet}</div>
        <div className="meta-row">
          <span><b>adapter</b>{adapter}</span>
          <span><b>parent</b>{parent || <span style={{ color: 'var(--cl-canvas-fg-4)' }}>none (root)</span>}</span>
          <span><b>normalizer</b>{normalizer}</span>
          <span><b>state</b>{when}</span>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8 }}>
            <Button variant="ghost" size="sm">view chunk →</Button>
            <Button variant="ghost" size="sm">open source →</Button>
          </span>
        </div>
      </div>
    </div>
  );
}

function FacetGroup({ title, rows }) {
  return (
    <div style={{ padding: '6px 0' }}>
      <div className="eyebrow" style={{ padding: '4px 12px' }}>{title}</div>
      {rows.map(([name, n, dom]) => (
        <div key={name} className="fd-row" style={{ margin: '0 4px', padding: '6px 10px' }}>
          {dom ? <span className={'dom-dot ' + dom} style={{ width: 7, height: 7 }}></span> : <span className="fd-checkbox"></span>}
          <span style={{ fontFamily: dom ? 'var(--font-mono)' : 'var(--font-sans)' }}>{name}</span>
          <span className="fd-meta">{n}</span>
        </div>
      ))}
    </div>
  );
}

function SearchScreen() {
  const [mode, setMode] = useSearchState('vector');
  const [sort, setSort] = useSearchState('similarity');
  return (
    <CLShell active="search" breadcrumbs={['workspace', 'search', 'graph rag pipelines']}>
      <PageHeader
        title="Semantic search"
        idChip="POST /query"
        subtitle="Vector search across 18,724 chunks. Results carry full provenance back to source, version, and adapter. Reranker available for high-precision queries."
        actions={[
          <Button key="hist" variant="ghost"><Icon name="clock" size={13} /> History</Button>,
          <Button key="exp" variant="ghost"><Icon name="download" size={13} /> Export</Button>,
        ]}
      />

      {/* Custom: search hero shell */}
      <div className="search-hero">
        <div className="between" style={{ marginBottom: 12 }}>
          <span className="eyebrow">QUERY SURFACE</span>
          <span className="tbb-flag"><Icon name="layout" size={10} /> custom · SearchHero</span>
        </div>
        <div className="input-row">
          <span className="ico"><Icon name="search" size={16} /></span>
          <input defaultValue="graph rag pipelines I've worked on" />
          <span className="kbd">⌘ ↵ search</span>
        </div>
        <div className="filters-row">
          <Facet label="DOMAIN" summary="notes, messages" section="Domain" selected={['Notes', 'Messages']} options={['Notes', 'Messages', 'Events', 'Tasks', 'Documents', 'People']} />
          <Facet label="ADAPTER" summary="all (11)" section="Adapter" selected={[]} options={['obsidian', 'email', 'filesystem', 'caldav', 'apple.notes']} />
          <Facet label="SOURCE" summary="any" section="Source" selected={[]} options={['any source']} />
          <Facet label="WHEN" summary="any time" section="Time range" selected={[]} options={['Today', 'This week', 'This month', 'Any time']} />
          <Facet label="TOP K" summary="20" section="Result count" selected={['20']} options={['10', '20', '50', '100']} />
          <SegmentedControl value={mode} onChange={setMode} options={[{ value: 'vector', label: 'vector' }, { value: 'rerank', label: '+ rerank' }, { value: 'hybrid', label: 'hybrid' }]} />
          <span style={{ marginLeft: 'auto' }}><span className="eyebrow">7 results · 84 ms · 12 ms rerank</span></span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 18 }}>
        <div>
          <div className="row between" style={{ marginBottom: 10 }}>
            <div className="eyebrow">RANKED · BY SIMILARITY ↓</div>
            <div className="row" style={{ gap: 10 }}>
              <span className="tbb-flag shipped"><Icon name="layout" size={10} /> heimdall · ResultCard</span>
              <SegmentedControl value={sort} onChange={setSort} options={[{ value: 'similarity', label: 'similarity' }, { value: 'recency', label: 'recency' }, { value: 'source', label: 'source' }]} />
            </div>
          </div>

          <ResultCard dom="notes" source="obsidian/vault/projects/heimdall-graph-rag.md" section="# Pipeline architecture › ## Diff stage" version="v3" sim={0.89}
            snippet={<span>The <mark>diff stage between normalization and chunking</mark> means re-ingestion only produces new chunk versions when content actually changes. All source content is normalized to <mark>markdown</mark> before comparison, giving a stable surface for detecting meaningful changes.</span>}
            chunkHash="3f2a91ce8b14…" when="ingested 6 days ago" adapter="obsidian" parent="0c8d1e22f7a3…" normalizer="v2.1" />
          <ResultCard dom="messages" source="email.imap/work@studio · subject: 'graph rag handoff'" section="Thread · 4 of 7 messages · from morgan" version="v1" sim={0.84}
            snippet={<span>For the new pipeline, I want to <mark>preserve threading</mark> when chunking — individual messages stay atomic but reply chains carry as structured context. Then the retriever can <mark>reconstruct conversations</mark> at query time.</span>}
            chunkHash="8a14ce0c9d2f…" when="ingested 2 days ago" adapter="email" parent={null} normalizer="v1.0" />
          <ResultCard dom="notes" source="filesystem/docs/rag/lineage-design.md" section="# Adapter contract › ## Domain mapping" version="v2" sim={0.78}
            snippet={<span>Adapters are cheap to write. The interface is small and the domain layer does the heavy lifting — <mark>adapters encode access</mark>, <mark>domains encode semantics</mark>. A Gmail adapter knows how to fetch email. The Messages domain knows how to chunk conversations.</span>}
            chunkHash="c9d2f8e314a0…" when="ingested 3 weeks ago" adapter="filesystem" parent="a431f8d1ce…" normalizer="v1.8" />
          <ResultCard dom="tasks" source="apple.reminders/list 'context-library'" section="Task — done" version="v4" sim={0.71}
            snippet={<span><mark>Implement parent_chunk_hash field</mark> so the chunk table self-references its previous version. Enables version-chain queries without positional alignment. State: open → in-progress → done (2024-Q3).</span>}
            chunkHash="412a9ce8b1f0…" when="state→done · 5 weeks ago" adapter="apple.reminders" parent="3f2a91ce8b14…" normalizer="v0.7" />
          <ResultCard dom="notes" source="obsidian/daily/2024-09-12.md" section="# Standup · ## RAG followups" version="v1" sim={0.66}
            snippet={<span>Skim through the <mark>chunking strategy doc</mark>. Action: rewrite the notes-domain chunker so heading-level fluctuations don't trigger phantom diffs. Carry the breadcrumb in context_header so the embedding context survives edits.</span>}
            chunkHash="d1e22f7a3091…" when="ingested 2 months ago" adapter="obsidian" parent={null} normalizer="v1.5" />
        </div>

        <div>
          <Panel title="Facets" headerAction={<span className="eyebrow">7 hits</span>} noPadding style={{ marginBottom: 14 }}>
            <div style={{ padding: '4px 0 8px' }}>
              <FacetGroup title="DOMAIN" rows={[['notes', 3, 'notes'], ['messages', 2, 'messages'], ['tasks', 1, 'tasks'], ['events', 1, 'events']]} />
              <FacetGroup title="ADAPTER" rows={[['obsidian', 2], ['email', 2], ['filesystem', 1], ['apple.reminders', 1], ['caldav', 1]]} />
              <FacetGroup title="VERSION CHAIN" rows={[['head only', 5], ['has parent', 4], ['retired', 0]]} />
            </div>
          </Panel>

          <Panel title="Query" noPadding>
            <KVGrid rows={[
              { key: 'EMBEDDING', value: <span className="mono">all-MiniLM-L6-v2 · 384d</span> },
              { key: 'DOMAIN', value: <span className="mono">notes, messages</span> },
              { key: 'TOP K', value: <span className="mono">20</span> },
              { key: 'RERANK', value: <span className="mono">off</span> },
              { key: 'FETCH', value: <span className="mono">+ lineage, + parent</span> },
              { key: 'LATENCY', value: <span className="mono">84 ms total</span> },
            ]} />
            <div style={{ padding: '10px 12px', borderTop: '1px solid var(--cl-canvas-border)', background: 'var(--cl-canvas-bg-2)' }}>
              <div className="eyebrow" style={{ marginBottom: 6 }}>EQUIVALENT cURL</div>
              <pre style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--cl-canvas-fg-2)', lineHeight: 1.55, whiteSpace: 'pre-wrap' }}>
{`curl -X POST :8000/query \\
  -d '{"query": "graph rag…",
       "top_k": 20,
       "domain_filter": ["notes","messages"]}'`}
              </pre>
            </div>
          </Panel>
        </div>
      </div>
    </CLShell>
  );
}

window.SearchScreen = SearchScreen;
