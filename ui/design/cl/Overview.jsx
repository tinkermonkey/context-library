// Overview / Dashboard — rebuilt on real heimdall components.
// Real DS: PageHeader, StatGrid/StatTile, Panel, MetricRow, QuickAccessGrid,
// PipelineCard, ActivityTimeline, Button, Chip, VersionPill.
// Custom (flagged): the Domains domain-shape tiles.

const DOMAINS = [
  { d: 'notes', name: 'Notes', count: '1,284', meta: '4 adapters · 5,902 chunks', adapters: ['obsidian', 'filesystem', 'filesystem.rich', 'apple.notes'] },
  { d: 'messages', name: 'Messages', count: '2,140', meta: '2 adapters · 8,118 chunks', adapters: ['email', 'apple.imessage'] },
  { d: 'events', name: 'Events', count: '986', meta: '3 adapters · 1,944 chunks', adapters: ['caldav', 'apple.health', 'apple.music'] },
  { d: 'tasks', name: 'Tasks', count: '142', meta: '2 adapters · 142 chunks', adapters: ['obsidian.tasks', 'apple.reminders'] },
  { d: 'documents', name: 'Documents', count: '260', meta: '1 adapter · 2,618 chunks', adapters: ['filesystem.rich'] },
  { d: 'people', name: 'People', count: '94', meta: 'derived · 0 chunks', adapters: ['(derived)'] },
];

const PIPE_FLOW = (running) => ([
  { id: 'fetch', name: 'fetch', icon: 'download', color: 'emerald' },
  { id: 'normalize', name: 'normalize', icon: 'reload', color: 'emerald' },
  { id: 'diff', name: 'diff', icon: 'gitBranch', color: running >= 2 ? (running === 2 ? 'cyan' : 'emerald') : undefined },
  { id: 'chunk', name: 'chunk', icon: 'component', color: running > 3 ? 'emerald' : undefined },
  { id: 'embed', name: 'embed', icon: 'zap', color: running > 4 ? 'emerald' : undefined },
  { id: 'store', name: 'store', icon: 'data', color: running > 5 ? 'emerald' : undefined },
]);

function OverviewScreen() {
  return (
    <CLShell active="overview" breadcrumbs={['workspace', 'overview']}>
      <PageHeader
        eyebrow={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
          <Chip variant="emerald">pipeline healthy</Chip>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--cl-canvas-fg-3)' }}>last ingest 2 min ago</span>
        </span>}
        title="Overview"
        idChip="localhost:8000"
        subtitle="Versioned RAG over 11 adapters across 9 domains. Source-of-truth in SQLite, semantic index in ChromaDB. All sync queues drained."
        actions={[
          <Button key="repoll" variant="ghost"><Icon name="reload" size={13} /> Re-poll all</Button>,
          <Button key="add" variant="accent"><Icon name="plus" size={13} /> Add adapter</Button>,
        ]}
      />

      <StatGrid columns={4} style={{ marginBottom: 16 }}>
        <StatTile label="SOURCES" value="4,812" color="amber" delta={{ value: 38, label: '24h', direction: 'up' }} sparkData={[20, 24, 22, 30, 28, 36, 34, 42]} />
        <StatTile label="CHUNKS · ACTIVE" value="18,724" color="emerald" meta="221 retired · 0.18 GB index" />
        <StatTile label="EMBEDDINGS · 384 dim" value="18,724" color="cyan" meta="all-MiniLM-L6-v2 · 1 model" />
        <StatTile label="VERSIONS · 30d" value="2,406" color="violet" meta="avg 1.4 / source" />
      </StatGrid>

      <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: 16, marginBottom: 16 }}>
        <Panel
          title="Domains"
          headerAction={<span className="tbb-flag"><Icon name="component" size={10} /> custom · DomainTile</span>}
          noPadding
        >
          <div style={{ padding: 14, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {DOMAINS.map(t => (
              <div key={t.d} className="dom-tile">
                <div className={'bar dom-bar ' + t.d}></div>
                <div className="body">
                  <div className="name"><span className={'dom-dot ' + t.d}></span> {t.name}</div>
                  <div className="num">{t.count}</div>
                  <div className="meta">{t.meta}</div>
                  <div className="adapters">{t.adapters.map(a => <span key={a} className="pill">{a}</span>)}</div>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Panel title="Quick actions" noPadding>
            <div style={{ padding: 12 }}>
              <QuickAccessGrid columns={1} tiles={[
                { id: 'q', icon: 'search', title: 'Run a semantic query', description: 'POST /query — search with provenance' },
                { id: 'a', icon: 'plus', title: 'Register adapter', description: 'POST /adapters — new ingestion source' },
                { id: 'e', icon: 'reload', title: 'Re-embed model', description: 'Swap embedder, replay sync log' },
              ]} />
            </div>
          </Panel>
          <Panel title="Storage" headerAction={<span className="eyebrow">DUAL-STORE</span>}>
            <MetricRow label="SQLite · sources" value="412 MB" percent={42} color="amber" sparklineData={[2, 3, 3, 4, 4, 5, 6, 7]} />
            <MetricRow label="ChromaDB · vectors" value="184 MB" percent={28} color="cyan" sparklineData={[1, 2, 2, 3, 3, 3, 4, 5]} />
            <MetricRow label="Sync log" value="2 ops" percent={2} color="emerald" sparklineData={[1, 0, 1, 2, 1, 0, 1, 2]} />
          </Panel>
        </div>
      </div>

      <Panel title="Active pipelines" headerAction={<Button variant="ghost" size="sm">view all <Icon name="chevronRight" size={11} /></Button>} noPadding style={{ marginBottom: 16 }}>
        <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <PipelineCard pipeline={{
            id: 'pl_obsidian', name: 'obsidian.vault', status: 'running', target: 'notes',
            description: 'diffing 412 of 1,182 notes', tags: ['v2.1'],
            flow: PIPE_FLOW(2), lastRun: 'now',
            recent: { ingested: '1,182', created: 412, updated: 38, errors: 0 },
          }} onCancel={() => {}} onOptions={() => {}} />
          <PipelineCard pipeline={{
            id: 'pl_email', name: 'email.imap', status: 'idle', target: 'messages',
            description: 'last run 14 min ago · +18 chunks', tags: ['v1.0'],
            flow: PIPE_FLOW(6), lastRun: '14m ago',
            recent: { ingested: 62, created: 18, updated: 4, errors: 0 },
          }} onRun={() => {}} onOptions={() => {}} />
        </div>
      </Panel>

      <Panel title="Recent ingests" headerAction={<span className="eyebrow">LAST 24 HOURS</span>} noPadding>
        <ActivityTimeline events={[
          { id: '1', type: 'create', kind: 'version', timestamp: new Date(Date.now() - 2 * 60000), headline: <span>Ingested <b>obsidian/vault/notes/2024-q4-review.md</b></span>, subject: 'Ingested note', meta: '+12 chunks · v1 → v2 · obsidian @ normalizer 2.1' },
          { id: '2', type: 'update', kind: 'embed', timestamp: new Date(Date.now() - 14 * 60000), headline: <span>Re-embed batch finished</span>, subject: 'Re-embed batch', meta: '412 chunks · all-MiniLM-L6-v2 · obsidian.vault' },
          { id: '3', type: 'run', kind: 'poll', timestamp: new Date(Date.now() - 22 * 60000), headline: <span>Polled <b>email.imap</b> account <span className="mono">work@studio</span></span>, subject: 'Polled email', meta: '62 messages fetched · 18 new chunks · 4 retired' },
          { id: '4', type: 'create', kind: 'source', timestamp: new Date(Date.now() - 38 * 60000), headline: <span>Created new source <b>apple.notes/idea-graph-rag</b></span>, subject: 'Created source', meta: 'domain=notes · 4 chunks · 1 version' },
          { id: '5', type: 'delete', kind: 'error', timestamp: new Date(Date.now() - 60 * 60000), headline: <span>Skipped <b>apple.health</b> · workouts endpoint</span>, subject: 'Skipped', meta: 'connection refused at step 2 · retry in 8m' },
        ]} />
      </Panel>
    </CLShell>
  );
}

window.OverviewScreen = OverviewScreen;
