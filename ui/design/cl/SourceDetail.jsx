// Source Detail · Versions + Diff — rebuilt on real heimdall components.
// Real DS: PageHeader, Panel, KVGrid, SegmentedControl, FilterDropdown,
// VersionPill, Chip, Button, Icon.
// Shipped in heimdall: VersionTimeline, DiffViewer (HashSetDiff + SideBySideDiff).

const { useState: useSDState } = React;

function VersionRow({ label, headline, summary, adds, removes, keeps, when, active, head }) {
  return (
    <div className={'version-row' + (active ? ' active' : '') + (head ? ' head' : '')}>
      <div className="vmark"><div className="dot"></div></div>
      <div className="vbody">
        <div className="title">
          <VersionPill>{label}</VersionPill>
          {head && <Chip variant="emerald">head</Chip>}
          <span className="name">{headline}</span>
        </div>
        <div className="summary">{summary}</div>
        <div className="stats">
          {adds > 0 && <span className="stat-add">+{adds}</span>}
          {removes > 0 && <span className="stat-remove">−{removes}</span>}
          <span className="stat-kept">∩ {keeps}</span>
        </div>
      </div>
      <div className="when">{when}</div>
    </div>
  );
}

function DiffPick({ label, value, options }) {
  return (
    <FilterDropdown mode="radio" defaultValue={[value]}>
      <FilterDropdown.Trigger label={label} summary={value} />
      <FilterDropdown.Panel><FilterDropdown.Section title="Version">
        {options.map(o => <FilterDropdown.Radio key={o} value={o} label={o} />)}
      </FilterDropdown.Section></FilterDropdown.Panel>
    </FilterDropdown>
  );
}

function HashRow({ sha, pos }) {
  return (
    <div className="hash-row">
      <Icon name="link" size={10} />
      <span className="sha">{sha}</span>
      <span className="pos">{pos}</span>
    </div>
  );
}

function SourceDetailScreen() {
  const [view, setView] = useSDState('hash');
  return (
    <CLShell active="sources" breadcrumbs={['sources', 'obsidian', 'projects', 'heimdall-graph-rag.md', 'v2 → v3']}>
      <PageHeader
        eyebrow="NOTES / OBSIDIAN"
        title={<span style={{ fontFamily: 'var(--font-mono)', fontSize: 20, fontWeight: 600 }}>obsidian/vault/projects/heimdall-graph-rag.md</span>}
        subtitle={<span>3 versions over 6 days · 28 active chunks · 7 retired · diff stage skipped 4 re-ingests with no content change. Origin file: <span className="mono">/Users/heimdall/vault/projects/heimdall-graph-rag.md</span></span>}
        actions={[
          <Button key="rp" variant="ghost"><Icon name="reload" size={13} /> Re-poll source</Button>,
          <Button key="ob" variant="ghost"><Icon name="file" size={13} /> Open in Obsidian</Button>,
          <Button key="re" variant="accent"><Icon name="zap" size={12} /> Reprocess</Button>,
        ]}
      />

      <Panel noPadding style={{ marginBottom: 14 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0, padding: '4px 4px' }}>
          <KVGrid keyWidth={120} rows={[
            { key: 'SOURCE_ID', value: <span className="mono" style={{ fontSize: 12 }}>src_8a14ce0c9d2f</span> },
            { key: 'ADAPTER', value: <span><span className="mono" style={{ fontSize: 12 }}>obsidian</span> · <span className="muted" style={{ fontSize: 11.5 }}>normalizer v2.1</span></span> },
            { key: 'POLL', value: <span className="mono" style={{ fontSize: 12 }}>pull · every 5 min</span> },
          ]} />
          <KVGrid keyWidth={120} rows={[
            { key: 'CURRENT VER', value: <span><VersionPill className="deep">v3</VersionPill> · <span className="muted" style={{ fontSize: 11.5 }}>head</span></span> },
            { key: 'CHUNKS', value: <span className="mono" style={{ fontSize: 12 }}>28 active · 7 retired</span> },
            { key: 'LAST FETCHED', value: <span className="mono" style={{ fontSize: 12 }}>2 min ago · <span className="muted">2024-10-23 14:42:18Z</span></span> },
          ]} />
        </div>
      </Panel>

      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 14 }}>
        <Panel title="Versions" headerAction={<span className="tbb-flag shipped"><Icon name="gitBranch" size={10} /> heimdall · VersionTimeline</span>} noPadding>
          <div className="version-list">
            <VersionRow head active label="v3" headline="Diff stage rewrite" summary="Replaced positional diff with hash-set comparison. Reworked normalize→diff sequence." adds={6} removes={2} keeps={22} when="2 min ago" />
            <VersionRow label="v2" headline="Add cross-references" summary="Linked to lineage-design.md and chunking-strategy.md in 4 sections." adds={3} removes={0} keeps={19} when="4 days ago" />
            <VersionRow label="v1" headline="Initial draft" summary="First export from research notebook. Sections: intro, model, adapter contract, retrieval." adds={19} removes={0} keeps={0} when="6 days ago" />
            <div style={{ padding: '10px 16px', borderTop: '1px solid var(--cl-canvas-border)', background: 'var(--cl-canvas-bg-2)', fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--cl-canvas-fg-3)' }}>
              4 re-ingests since v3 · no content change · skipped diff stage
            </div>
          </div>
        </Panel>

        <div>
          <div className="row gap-12" style={{ marginBottom: 12 }}>
            <div className="eyebrow">COMPARING</div>
            <DiffPick label="FROM" value="v2" options={['v1', 'v2', 'v3 (head)']} />
            <span style={{ color: 'var(--cl-canvas-fg-3)', fontFamily: 'var(--font-mono)' }}>→</span>
            <DiffPick label="TO" value="v3 (head)" options={['v1', 'v2', 'v3 (head)']} />
            <span style={{ marginLeft: 'auto' }}>
              <SegmentedControl value={view} onChange={setView} options={[{ value: 'hash', label: 'hash diff' }, { value: 'content', label: 'content diff' }, { value: 'raw', label: 'raw markdown' }]} />
            </span>
          </div>

          <div className="between" style={{ marginBottom: 8 }}>
            <span className="eyebrow">HASH-SET COMPARISON</span>
            <span className="tbb-flag shipped"><Icon name="component" size={10} /> heimdall · HashSetDiff</span>
          </div>
          <div className="hash-diff-grid" style={{ marginBottom: 14 }}>
            <div className="hash-set added">
              <div className="h"><div className="label">+ ADDED</div><div className="count">6</div></div>
              <div className="body">
                <HashRow sha="3f2a91ce8b14…" pos="ch_04 · ## Diff stage" />
                <HashRow sha="8a14ce0c9d2f…" pos="ch_05 · ## Hash-set ops" />
                <HashRow sha="c9d2f8e314a0…" pos="ch_06 · code: differ.py" />
                <HashRow sha="d1e22f7a3091…" pos="ch_11 · ## Normalizer rules" />
                <HashRow sha="412a9ce8b1f0…" pos="ch_17 · ## Phantom diffs" />
                <HashRow sha="0c8d1e22f7a3…" pos="ch_24 · ## Recovery" />
              </div>
            </div>
            <div className="hash-set removed">
              <div className="h"><div className="label">− RETIRED</div><div className="count">2</div></div>
              <div className="body">
                <HashRow sha="a431f8d1ce…" pos="ch_04 · positional diff (v2)" />
                <HashRow sha="b821f0c43e…" pos="ch_05 · code: old differ" />
              </div>
            </div>
            <div className="hash-set kept">
              <div className="h"><div className="label">∩ UNCHANGED</div><div className="count">22</div></div>
              <div className="body" style={{ maxHeight: 124 }}>
                <HashRow sha="7e3a91ff21…" pos="ch_01 · # Pipeline" />
                <HashRow sha="5a01f93c8…" pos="ch_02 · ## Sources" />
                <HashRow sha="b3f29c4a18…" pos="ch_03 · ## Normalize" />
                <HashRow sha="c14f08e21…" pos="ch_07 · ## Chunking" />
                <div style={{ padding: '6px 10px', fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--cl-canvas-fg-4)' }}>… 18 more carried forward (no re-embed)</div>
              </div>
            </div>
          </div>

          <Panel noPadding
            title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}><Icon name="file" size={13} /> ## Diff stage · content diff <VersionPill>v2 → v3</VersionPill></span>}
            headerAction={<span className="row" style={{ gap: 10 }}><span className="eyebrow">2 HUNKS · +24 −9 LINES</span><span className="tbb-flag shipped"><Icon name="component" size={10} /> heimdall · SideBySideDiff</span></span>}>
            <div className="diff-grid" style={{ border: 0, borderRadius: 0 }}>
              <div className="diff-col">
                <div className="diff-col-head">
                  <span className="lab"><VersionPill className="rose">v2</VersionPill> a431f8d1ce…</span>
                  <span className="eyebrow">9 LINES</span>
                </div>
                <div className="diff-col-body">
                  <div className="diff-hunk">@@ ch_04 · ## Diff stage @@</div>
                  <div className="diff-line removed"><span className="ln">42</span>The differ uses a longest-common-subsequence pass over chunk arrays.</div>
                  <div className="diff-line removed"><span className="ln">43</span>This requires positional alignment across versions, which is fragile</div>
                  <div className="diff-line removed"><span className="ln">44</span>when sections are reordered or merged.</div>
                  <div className="diff-line context"><span className="ln">45</span></div>
                  <div className="diff-line removed"><span className="ln">46</span>Performance: O(n*m) per source — needs windowing for large notes.</div>
                  <div className="diff-line context"><span className="ln">47</span>{' '}</div>
                  <div className="diff-hunk">@@ ch_05 · removed @@</div>
                  <div className="diff-line removed"><span className="ln">58</span>```python</div>
                  <div className="diff-line removed"><span className="ln">59</span>def diff(prev, curr):</div>
                  <div className="diff-line removed"><span className="ln">60</span>    return lcs(prev.chunks, curr.chunks)</div>
                </div>
              </div>
              <div className="diff-col">
                <div className="diff-col-head">
                  <span className="lab"><VersionPill className="green">v3</VersionPill> 3f2a91ce8b14… <span style={{ marginLeft: 6, color: 'var(--cl-canvas-fg-3)' }}>← head</span></span>
                  <span className="eyebrow">24 LINES</span>
                </div>
                <div className="diff-col-body">
                  <div className="diff-hunk">@@ ch_04 · ## Diff stage @@</div>
                  <div className="diff-line added"><span className="ln">42</span>Chunks are content-addressed via SHA-256 of their normalized markdown.</div>
                  <div className="diff-line added"><span className="ln">43</span>Comparing two versions is therefore a set operation on hash sets:</div>
                  <div className="diff-line added"><span className="ln">44</span></div>
                  <div className="diff-line added"><span className="ln">45</span>  added   = curr_hashes − prev_hashes</div>
                  <div className="diff-line added"><span className="ln">46</span>  removed = prev_hashes − curr_hashes</div>
                  <div className="diff-line added"><span className="ln">47</span>  kept    = curr_hashes ∩ prev_hashes</div>
                  <div className="diff-line context"><span className="ln">48</span>{' '}</div>
                  <div className="diff-line added"><span className="ln">49</span>No positional alignment. Reordering sections produces zero diff cost.</div>
                  <div className="diff-hunk">@@ ch_05 · added @@</div>
                  <div className="diff-line added"><span className="ln">60</span>Performance: O(n + m). Embedding cost only on `added`.</div>
                </div>
              </div>
            </div>
          </Panel>
        </div>
      </div>
    </CLShell>
  );
}

window.SourceDetailScreen = SourceDetailScreen;
