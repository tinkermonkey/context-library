// Adapters / Pipeline admin — rebuilt on real heimdall components.
// Real DS: PageHeader, SegmentedControl, FilterDropdown, PipelineCard, KVGrid,
// Panel, VersionPill, Chip, Button, Icon.
// Reuse: AdapterCard → ConfigTile. Shipped in heimdall: LogStream (recent-events log).

const { useState: useAdState } = React;

const ADAPTERS = [
  { name: 'obsidian.vault', domain: 'notes', status: 'running', version: 'v2.1', poll: 'pull · 5m', sources: 284, chunks: 5902, errors: 0, desc: 'Obsidian vault — frontmatter + wikilinks.' },
  { name: 'filesystem', domain: 'notes', status: 'ok', version: 'v1.8', poll: 'pull · 30m', sources: 142, chunks: 1284, errors: 0, desc: 'Plain markdown files under /docs.' },
  { name: 'filesystem.rich', domain: 'documents', status: 'ok', version: 'v0.4', poll: 'pull · 1h', sources: 260, chunks: 2618, errors: 0, desc: 'PDF + Office + image OCR via MarkItDown.' },
  { name: 'email.imap', domain: 'messages', status: 'ok', version: 'v1.0', poll: 'pull · 10m', sources: 1892, chunks: 6204, errors: 0, desc: 'IMAP via EmailEngine — account work@studio.' },
  { name: 'apple.imessage', domain: 'messages', status: 'ok', version: 'v0.7', poll: 'pull · 10m', sources: 248, chunks: 1914, errors: 0, desc: 'iMessage via macOS context-helpers bridge.', bridge: 'macOS' },
  { name: 'caldav', domain: 'events', status: 'ok', version: 'v1.2', poll: 'pull · 1h', sources: 86, chunks: 86, errors: 0, desc: 'CalDAV calendars from work + personal.' },
  { name: 'apple.health', domain: 'events', status: 'warn', version: 'v0.9', poll: 'pull · 15m', sources: 812, chunks: 1816, errors: 4, desc: 'HealthKit workouts + heart-rate windows.', bridge: 'macOS' },
  { name: 'apple.music', domain: 'events', status: 'ok', version: 'v0.6', poll: 'pull · 1h', sources: 88, chunks: 42, errors: 0, desc: 'Apple Music listens — batched per day.', bridge: 'macOS' },
  { name: 'apple.notes', domain: 'notes', status: 'ok', version: 'v1.1', poll: 'pull · 15m', sources: 184, chunks: 612, errors: 0, desc: 'Apple Notes via macOS context-helpers bridge.', bridge: 'macOS' },
  { name: 'apple.reminders', domain: 'tasks', status: 'ok', version: 'v0.7', poll: 'pull · 5m', sources: 86, chunks: 86, errors: 0, desc: "Apple Reminders — list 'context-library'." },
  { name: 'obsidian.tasks', domain: 'tasks', status: 'error', version: 'v0.3', poll: 'pull · 30m', sources: 56, chunks: 56, errors: 12, desc: 'Obsidian Tasks plugin — checkbox parser.' },
];
const STATUS = { ok: ['emerald', 'healthy'], running: ['cyan', 'running'], warn: ['amber', 'warn'], error: ['rose', 'error'] };

function AdapterCard({ a }) {
  const [variant, label] = STATUS[a.status];
  return (
    <div className="adapter-card">
      <div className="head">
        <div className="icon"><span className={'dom-bar ' + a.domain} style={{ width: 3, height: 22, borderRadius: 1, display: 'inline-block' }}></span></div>
        <div className="meta">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span className="name">{a.name}</span>
            <VersionPill>{a.version}</VersionPill>
            {a.bridge && <Chip form="id-tag">{a.bridge} bridge</Chip>}
          </div>
          <div className="desc">{a.desc}</div>
        </div>
        <Chip variant={variant}>{label}</Chip>
      </div>
      <div className="row gap-12" style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--cl-canvas-fg-3)' }}>
        <span><span className="dom-dot" style={{ background: 'var(--dom-' + a.domain + ')', width: 6, height: 6, display: 'inline-block', marginRight: 5, verticalAlign: 'middle' }}></span>{a.domain}</span>
        <span style={{ color: 'var(--cl-canvas-fg-4)' }}>·</span><span>{a.poll}</span>
      </div>
      <div className="stats">
        <div className="stat-mini"><div className="l">SOURCES</div><div className="v">{a.sources.toLocaleString()}</div></div>
        <div className="stat-mini"><div className="l">CHUNKS</div><div className="v">{a.chunks.toLocaleString()}</div></div>
        <div className="stat-mini"><div className="l">ERRORS 24H</div><div className="v" style={{ color: a.errors > 0 ? 'var(--cl-status-rose)' : 'var(--cl-canvas-fg-1)' }}>{a.errors}</div></div>
      </div>
    </div>
  );
}
function LogLine({ when, level, text }) {
  const colorMap = { info: 'var(--cl-canvas-fg-2)', warn: 'var(--cl-status-amber)', error: 'var(--cl-status-rose)' };
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
      <span style={{ color: 'var(--cl-canvas-fg-4)' }}>{when}</span>
      <span style={{ color: colorMap[level], textTransform: 'uppercase', fontSize: 9.5, fontWeight: 600, letterSpacing: '0.08em', width: 36 }}>{level}</span>
      <span style={{ color: 'var(--cl-canvas-fg-2)' }}>{text}</span>
    </div>
  );
}
function AdFilter({ label, value, options }) {
  return (
    <FilterDropdown mode="radio" defaultValue={[value]}>
      <FilterDropdown.Trigger label={label} summary={value} />
      <FilterDropdown.Panel><FilterDropdown.Section title={label}>{options.map(o => <FilterDropdown.Radio key={o} value={o} label={o} />)}</FilterDropdown.Section></FilterDropdown.Panel>
    </FilterDropdown>
  );
}

function AdaptersScreen() {
  const [scope, setScope] = useAdState('all');
  return (
    <CLShell active="adapters" breadcrumbs={['system', 'adapters']}>
      <PageHeader
        title="Adapters"
        idChip="11 registered"
        subtitle="Every external source the pipeline knows about. Adapters declare a domain and a normalizer version. Re-ingest is content-safe — only changed chunks re-embed."
        actions={[
          <Button key="b" variant="ghost"><Icon name="settings" size={13} /> Bulk re-poll</Button>,
          <Button key="r" variant="accent"><Icon name="plus" size={13} /> Register adapter</Button>,
        ]}
      />
      <div className="row gap-12" style={{ marginBottom: 14 }}>
        <SegmentedControl value={scope} onChange={setScope} options={[{ value: 'all', label: 'all 11' }, { value: 'healthy', label: 'healthy 8' }, { value: 'warn', label: 'warn 2' }, { value: 'error', label: 'error 1' }]} />
        <AdFilter label="DOMAIN" value="all" options={['all', 'notes', 'messages', 'events', 'tasks', 'documents']} />
        <AdFilter label="POLL" value="all" options={['all', 'pull', 'push']} />
        <span style={{ flex: 1 }}></span>
        <span className="eyebrow">SHOWING 11 OF 11</span>
      </div>

      <div className="between" style={{ marginBottom: 8 }}>
        <span className="eyebrow">REGISTERED ADAPTERS</span>
        <span className="tbb-flag reuse"><Icon name="component" size={10} /> reuse · ConfigTile</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 16 }}>
        {ADAPTERS.map(a => <AdapterCard key={a.name} a={a} />)}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.55fr 1fr', gap: 14 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <PipelineCard pipeline={{
            id: 'pl_apple_health', name: 'apple.health', status: 'running', target: 'events', tags: ['v0.9', 'warn'],
            description: 'HealthKit workouts + heart-rate windows · current run',
            flow: [
              { id: 'fetch', name: 'fetch', icon: 'download', color: 'emerald' },
              { id: 'normalize', name: 'normalize', icon: 'reload', color: 'emerald' },
              { id: 'diff', name: 'diff', icon: 'gitBranch', color: 'emerald' },
              { id: 'chunk', name: 'chunk', icon: 'component', color: 'cyan' },
              { id: 'embed', name: 'embed', icon: 'zap' },
              { id: 'store', name: 'store', icon: 'data' },
            ],
            lastRun: 'now', recent: { ingested: 812, created: '+18', updated: '−2', errors: 4 },
          }} onCancel={() => {}} onOptions={() => {}} />

          <Panel title="Recent events" headerAction={<Button variant="ghost" size="sm">view log →</Button>}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontFamily: 'var(--font-mono)', fontSize: 11 }}>
              <LogLine when="14:42:18" level="warn" text="workouts endpoint timed out (3rd time today)" />
              <LogLine when="14:42:15" level="info" text="fetched 812 sources from /workouts (window: 7d)" />
              <LogLine when="14:42:01" level="info" text="started run pipeline_apple_health" />
              <LogLine when="14:38:44" level="error" text="connection refused at step 2 (retried) — recovered" />
              <LogLine when="14:27:01" level="info" text="completed prior run · +12 chunks · 0 errors" />
            </div>
          </Panel>
        </div>

        <Panel title="Configuration" headerAction={<span className="eyebrow">apple.health</span>} noPadding
          footer={<div className="row" style={{ gap: 8 }}>
            <span className="eyebrow" style={{ flex: 1 }}>SET <span style={{ color: 'var(--cl-canvas-fg-1)' }}>CTX_APPLE_HELPER_URL</span> AT STARTUP</span>
            <Button variant="ghost" size="sm">edit env</Button>
            <Button variant="danger" size="sm">reset adapter</Button>
          </div>}>
          <KVGrid keyWidth={120} rows={[
            { key: 'ADAPTER_ID', value: <span className="mono">apple_health_001</span> },
            { key: 'DOMAIN', value: <span><span className="dom-dot events"></span> <span className="mono">events</span></span> },
            { key: 'POLL', value: <span className="mono">pull · every 15 min</span> },
            { key: 'NORMALIZER', value: <span className="mono">v0.9 <span className="muted" style={{ marginLeft: 6 }}>(2 versions behind)</span></span> },
            { key: 'BRIDGE', value: <span className="mono">macOS · http://nyx.lab.local:7123</span> },
            { key: 'API KEY', value: <span className="mono">•••••••••• <Button variant="ghost" size="sm">rotate</Button></span> },
            { key: 'EMBEDDING', value: <span className="mono">all-MiniLM-L6-v2</span> },
            { key: 'CHUNKER', value: <span className="mono">events.time_window · 1 day</span> },
          ]} />
        </Panel>
      </div>
    </CLShell>
  );
}

window.AdaptersScreen = AdaptersScreen;
