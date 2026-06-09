// Sources Browser — rebuilt on real heimdall components.
// Real DS: PageHeader, TabBar, FilterBar, FilterDropdown, SegmentedControl,
// Table (with render columns), VersionPill, Chip, Button, Panel, Icon.

const { useState: useSourcesState } = React;

const SOURCE_ROWS = [
  { id: 'obsidian/vault/projects/heimdall-graph-rag.md', dom: 'notes', adapter: 'obsidian', ver: 3, chunks: 28, when: '2 min ago', status: 'ok' },
  { id: 'obsidian/vault/daily/2024-q4-review.md', dom: 'notes', adapter: 'obsidian', ver: 2, chunks: 14, when: '2 min ago', status: 'updated' },
  { id: 'email.imap/work@studio/INBOX/12842', dom: 'messages', adapter: 'email', ver: 1, chunks: 6, when: '14 min ago', status: 'ok' },
  { id: 'email.imap/work@studio/INBOX/12841', dom: 'messages', adapter: 'email', ver: 1, chunks: 4, when: '14 min ago', status: 'ok' },
  { id: 'filesystem/docs/rag/lineage-design.md', dom: 'notes', adapter: 'filesystem', ver: 2, chunks: 11, when: '3 weeks ago', status: 'ok' },
  { id: 'apple.reminders/list:context-library/T-2024-09-12-a', dom: 'tasks', adapter: 'apple.reminders', ver: 4, chunks: 1, when: '5 weeks ago', status: 'done' },
  { id: 'caldav/cal:work/2024-10-22T14:00:00Z', dom: 'events', adapter: 'caldav', ver: 1, chunks: 1, when: '2 hours ago', status: 'ok' },
  { id: 'apple.notes/folder:research/idea-graph-rag', dom: 'notes', adapter: 'apple.notes', ver: 1, chunks: 4, when: '38 min ago', status: 'new' },
  { id: 'obsidian/vault/projects/2024-q4-followups.md', dom: 'notes', adapter: 'obsidian', ver: 5, chunks: 22, when: '1 hour ago', status: 'ok' },
  { id: 'apple.health/workout/2024-10-21', dom: 'events', adapter: 'apple.health', ver: 1, chunks: 1, when: '1 day ago', status: 'ok' },
  { id: 'filesystem.rich/papers/lewis-rag-2020.pdf', dom: 'documents', adapter: 'filesystem.rich', ver: 1, chunks: 42, when: '2 weeks ago', status: 'ok' },
  { id: 'apple.imessage/thread:family/m-4812', dom: 'messages', adapter: 'apple.imessage', ver: 2, chunks: 1, when: '3 hours ago', status: 'ok' },
  { id: 'obsidian.tasks/vault/projects/heimdall.md#L42', dom: 'tasks', adapter: 'obsidian.tasks', ver: 3, chunks: 1, when: '1 day ago', status: 'in-progress' },
  { id: 'obsidian/vault/daily/2024-10-21.md', dom: 'notes', adapter: 'obsidian', ver: 1, chunks: 9, when: '2 days ago', status: 'ok' },
];

const STATUS_VARIANT = { ok: 'neutral', updated: 'cyan', new: 'emerald', done: 'emerald', 'in-progress': 'amber' };

function SourcesScreen() {
  const [tab, setTab] = useSourcesState('sources');
  const [scope, setScope] = useSourcesState('all');

  const columns = [
    { key: 'dom', label: '', width: '24px', render: (v) => <span className={'dom-bar ' + v} style={{ display: 'inline-block', width: 3, height: 14, borderRadius: 1, verticalAlign: 'middle' }}></span> },
    { key: 'id', label: 'source_id', render: (v) => <span className="mono" style={{ fontSize: 12 }}>{v}</span> },
    { key: 'domain', label: 'domain', render: (_v, row) => <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span className={'dom-dot ' + row.dom}></span><span className="mono" style={{ fontSize: 11.5, color: 'var(--cl-canvas-fg-2)' }}>{row.dom}</span></span> },
    { key: 'adapter', label: 'adapter', render: (v) => <span className="mono">{v}</span> },
    { key: 'ver', label: 'ver', width: '70px', render: (v) => <VersionPill>v{v}</VersionPill> },
    { key: 'chunks', label: 'chunks', width: '80px', render: (v) => <span className="mono" style={{ fontVariantNumeric: 'tabular-nums' }}>{v}</span> },
    { key: 'when', label: 'last fetched', render: (v) => <span className="mono" style={{ fontSize: 11.5, color: 'var(--cl-canvas-fg-3)' }}>{v}</span> },
    { key: 'status', label: 'state', render: (v) => <Chip variant={STATUS_VARIANT[v]}>{v}</Chip> },
    { key: '_a', label: '', width: '40px', render: () => <Button variant="ghost" size="sm" icon aria-label="Row actions"><Icon name="moreVertical" size={14} /></Button> },
  ];

  return (
    <CLShell active="sources" breadcrumbs={['workspace', 'sources']}>
      <PageHeader
        title="Sources"
        idChip="4,812 total"
        subtitle="Every external thing the pipeline has ingested. Click a row for version history, chunk-set, and origin-ref. Filter by domain or adapter to narrow."
        actions={[
          <Button key="f" variant="ghost"><Icon name="filter" size={13} /> Filters · 2</Button>,
          <Button key="e" variant="ghost"><Icon name="download" size={13} /> Export CSV</Button>,
        ]}
      />

      <div style={{ marginBottom: 14 }}>
        <TabBar activeTabId={tab} onSelectTab={setTab} tabs={[
          { id: 'sources', label: 'Sources', count: '4,812' },
          { id: 'chunks', label: 'Chunks', count: '18,724' },
          { id: 'versions', label: 'Versions', count: '2,406' },
          { id: 'retired', label: 'Retired', count: '221' },
        ]} />
      </div>

      <FilterBar searchPlaceholder="filter by source_id, origin_ref…" showingCount={14} totalCount={4812} style={{ marginBottom: 14 }}
        filters={[{ id: 'd', label: 'domain: notes, messages' }, { id: 'a', label: 'adapter: obsidian' }]} onClearAll={() => {}}>
        <FilterDropdown mode="radio" defaultValue={['any']}>
          <FilterDropdown.Trigger label="VERSIONS" summary="any" />
          <FilterDropdown.Panel><FilterDropdown.Section title="Version count">
            {['any', '1 only', '2+', '5+'].map(o => <FilterDropdown.Radio key={o} value={o} label={o} />)}
          </FilterDropdown.Section></FilterDropdown.Panel>
        </FilterDropdown>
        <SegmentedControl value={scope} onChange={setScope} options={[{ value: 'all', label: 'all' }, { value: 'active', label: 'active' }, { value: 'retired', label: 'retired' }]} />
      </FilterBar>

      <Panel noPadding footer={
        <div className="between">
          <div className="eyebrow">14 OF 4,812 · 1 SELECTED</div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <Button variant="ghost" size="sm" icon disabled aria-label="Previous page"><Icon name="chevronLeft" size={11} /></Button>
            <span className="mono" style={{ fontSize: 11, color: 'var(--cl-canvas-fg-2)' }}>page 1 / 344</span>
            <Button variant="ghost" size="sm" icon aria-label="Next page"><Icon name="chevronRight" size={11} /></Button>
          </div>
        </div>
      }>
        <Table columns={columns} data={SOURCE_ROWS} rowKey="id" onRowClick={() => {}} selectedRows={['obsidian/vault/projects/heimdall-graph-rag.md']} />
      </Panel>
    </CLShell>
  );
}

window.SourcesScreen = SourcesScreen;
