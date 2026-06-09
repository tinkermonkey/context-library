// Chunk Inspector — rebuilt on real heimdall components.
// Real DS: PageHeader, Panel, KVGrid, SegmentedControl, VersionPill, Chip, Button, Icon.
// Shipped in heimdall: LineageRail, VersionTimeline (version chain), LogStream (sync log).
// Custom: markdown body, embedded-input preview (app-level).

const { useState: useCIState } = React;

function ChainRow({ label, hash, note, when, sim, head }) {
  return (
    <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--cl-canvas-border)', display: 'flex', gap: 12, alignItems: 'flex-start' }}>
      <span style={{ flexShrink: 0, marginTop: 1 }}><VersionPill className={head ? 'deep' : ''}>{label}</VersionPill></span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="mono" style={{ fontSize: 11.5, color: 'var(--cl-canvas-fg-1)' }}>{hash}</div>
        <div style={{ fontSize: 11.5, color: 'var(--cl-canvas-fg-3)', marginTop: 2 }}>{note}</div>
      </div>
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        <div className="mono" style={{ fontSize: 10.5, color: 'var(--cl-canvas-fg-3)' }}>{when}</div>
        {sim != null && (
          <div className="mono" style={{ fontSize: 10.5, color: 'var(--cl-canvas-fg-3)', marginTop: 3, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 40, height: 3, background: 'var(--cl-canvas-bg-2)', borderRadius: 2, position: 'relative', display: 'inline-block' }}>
              <i style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: (sim * 100) + '%', background: 'var(--cl-canvas-fg-3)', borderRadius: 2 }}></i>
            </span>
            {sim.toFixed(2)}
          </div>
        )}
      </div>
    </div>
  );
}

function SyncLine({ when, op, target, state }) {
  const stateColor = state === 'ok' ? 'var(--cl-status-emerald)' : state === 'new' ? 'var(--cl-status-cyan)' : 'var(--cl-status-rose)';
  return (
    <div style={{ display: 'flex', gap: 10 }}>
      <span style={{ color: 'var(--cl-canvas-fg-4)' }}>{when}</span>
      <span style={{ color: 'var(--cl-canvas-fg-2)', fontWeight: 500, width: 50 }}>{op}</span>
      <span style={{ color: 'var(--cl-canvas-fg-3)', flex: 1 }}>{target}</span>
      <span style={{ color: stateColor, fontWeight: 500 }}>{state}</span>
    </div>
  );
}

function ChunkInspectorScreen() {
  const [view, setView] = useCIState('markdown');
  return (
    <CLShell active="sources" breadcrumbs={['sources', 'obsidian/…/heimdall-graph-rag.md', 'chunks', '3f2a91ce8b14…']}>
      <PageHeader
        eyebrow="CHUNK · NOTES DOMAIN"
        title={<span style={{ fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 10 }}>3f2a91ce8b14a09c… <VersionPill className="deep">v3 · head</VersionPill></span>}
        subtitle="SHA-256 of normalized content, never of the embedding context. Same content re-ingested from any adapter would produce this same hash. Active in 1 source · chained from 2 ancestors."
        actions={[
          <Button key="c" variant="ghost"><Icon name="link" size={12} /> Copy hash</Button>,
          <Button key="o" variant="ghost"><Icon name="file" size={12} /> Open source</Button>,
          <Button key="s" variant="accent"><Icon name="graph" size={13} /> Find similar</Button>,
        ]}
      />

      <Panel noPadding style={{ marginBottom: 14 }}>
        <div className="row gap-12" style={{ alignItems: 'center', padding: '14px 18px' }}>
          <span className="eyebrow">PROVENANCE</span>
          <div className="lineage-rail">
            <span className="lr-node"><Icon name="component" size={11} /> obsidian</span>
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
          <span className="tbb-flag shipped" style={{ marginLeft: 'auto' }}><Icon name="component" size={10} /> heimdall · LineageRail</span>
        </div>
      </Panel>

      <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: 14 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Panel noPadding
            title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}><Icon name="layout" size={13} /> context_header <Chip form="id-tag">EMBEDDED · NOT HASHED</Chip></span>}
            headerAction={<span className="eyebrow">42 TOK</span>}>
            <div style={{ padding: '12px 16px', fontFamily: 'var(--font-mono)', fontSize: 12.5, color: 'var(--cl-canvas-fg-2)', lineHeight: 1.6, background: 'rgba(251, 191, 36, 0.03)' }}>
              <span style={{ color: 'var(--cl-canvas-fg-4)' }}># </span>Pipeline architecture
              <span style={{ color: 'var(--cl-canvas-fg-4)' }}> &gt; ## </span>Diff stage
            </div>
          </Panel>

          <Panel noPadding
            title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}><Icon name="file" size={13} /> content <Chip form="id-tag">HASHED · SHA-256</Chip></span>}
            headerAction={<span className="row gap-12"><span className="eyebrow">186 TOK · 712 CHARS</span><SegmentedControl value={view} onChange={setView} options={[{ value: 'markdown', label: 'markdown' }, { value: 'normalized', label: 'normalized' }, { value: 'raw', label: 'raw' }]} /></span>}>
            <div style={{ padding: '14px 16px' }}>
              <div className="md">
                <p>Chunks are content-addressed via <code>SHA-256</code> of their normalized markdown. Comparing two versions is therefore a set operation on hash sets:</p>
                <pre><code>{`added   = curr_hashes − prev_hashes
removed = prev_hashes − curr_hashes
kept    = curr_hashes ∩ prev_hashes`}</code></pre>
                <p>No positional alignment. Reordering sections produces zero diff cost. Performance is <code>O(n + m)</code> and embedding cost falls only on <code>added</code>.</p>
              </div>
            </div>
          </Panel>

          <Panel noPadding
            title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}><Icon name="bot" size={13} /> embedded input <Chip form="id-tag">context + content</Chip></span>}
            headerAction={<span className="eyebrow">all-MiniLM-L6-v2</span>}>
            <div style={{ padding: '12px 16px', fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--cl-canvas-fg-2)', lineHeight: 1.6, maxHeight: 120, overflow: 'auto' }}>
              <span style={{ background: 'rgba(251,191,36,0.10)', padding: '1px 3px', borderRadius: 2, color: 'var(--cl-accent-primary-deep)' }}># Pipeline architecture &gt; ## Diff stage</span>
              <br /><br />
              Chunks are content-addressed via SHA-256 of their normalized markdown. Comparing two versions is therefore a set operation on hash sets: added equals curr_hashes minus prev_hashes; removed equals prev_hashes minus curr_hashes; kept equals the intersection. No positional alignment. Reordering sections produces zero diff cost. …
            </div>
            <div style={{ padding: '8px 16px', borderTop: '1px solid var(--cl-canvas-border)', background: 'var(--cl-canvas-bg-2)', display: 'flex', gap: 14, fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--cl-canvas-fg-3)' }}>
              <span>VECTOR · <span style={{ color: 'var(--cl-canvas-fg-1)' }}>[0.124, -0.038, 0.211, …, -0.073]</span></span>
              <span style={{ color: 'var(--cl-canvas-fg-4)' }}>·</span>
              <span>NORM 1.00</span>
              <span style={{ color: 'var(--cl-canvas-fg-4)' }}>·</span>
              <span>384 DIMS</span>
            </div>
          </Panel>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Panel title="Identity & lineage" noPadding>
            <KVGrid keyWidth={120} rows={[
              { key: 'CHUNK_HASH', value: <span className="mono" style={{ color: 'var(--cl-canvas-fg-1)' }}>3f2a91ce8b14a09c…</span> },
              { key: 'PARENT', value: <a className="mono" style={{ color: 'var(--cl-accent-primary-deep)' }}>a431f8d1ce0c2b…</a> },
              { key: 'SOURCE_ID', value: <span className="mono">obsidian/vault/projects/heimdall-graph-rag.md</span> },
              { key: 'SOURCE VER', value: <span><VersionPill>v3</VersionPill> <span className="muted" style={{ marginLeft: 6 }}>(head)</span></span> },
              { key: 'DOMAIN', value: <span><span className="dom-dot notes"></span> <span className="mono">notes</span> · chunk_type: <span className="mono">heading</span></span> },
              { key: 'ADAPTER', value: <span className="mono">obsidian · normalizer v2.1</span> },
              { key: 'EMBEDDING MODEL', value: <span className="mono">all-MiniLM-L6-v2</span> },
              { key: 'FIRST SEEN', value: <span className="mono">2024-10-23 14:42:18Z</span> },
              { key: 'RETIRED', value: <span className="muted">— (active)</span> },
            ]} />
          </Panel>

          <Panel title="Version chain" headerAction={<span className="row gap-12"><span className="eyebrow">3 GENERATIONS</span><span className="tbb-flag shipped"><Icon name="gitBranch" size={10} /> heimdall · VersionTimeline</span></span>} noPadding
            footer={<div className="between"><span className="eyebrow">CHAIN_SIM TO HEAD ↑</span><Button variant="ghost" size="sm">view chain →</Button></div>}>
            <ChainRow head label="v3" hash="3f2a91ce8b14a09c…" note="current — diff-stage rewrite" when="2 min ago" sim={null} />
            <ChainRow label="v2" hash="a431f8d1ce0c2b8a…" note="prior — positional-diff approach" when="4 days ago" sim={0.62} />
            <ChainRow label="v1" hash="0c8d1e22f7a31f08…" note="root — initial draft, no diff stage" when="6 days ago" sim={0.41} />
          </Panel>

          <Panel title="Sync log" headerAction={<Chip variant="emerald">in sync</Chip>} noPadding>
            <div style={{ padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 6, fontFamily: 'var(--font-mono)', fontSize: 11 }}>
              <SyncLine when="14:42:19" op="INSERT" target="chromadb" state="ok" />
              <SyncLine when="14:42:18" op="WRITE" target="sqlite" state="ok" />
              <SyncLine when="14:42:18" op="HASH" target="—" state="new" />
            </div>
          </Panel>
        </div>
      </div>
    </CLShell>
  );
}

window.ChunkInspectorScreen = ChunkInspectorScreen;
