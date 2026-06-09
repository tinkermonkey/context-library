// Tasks domain · kanban + lifecycle — rebuilt on real heimdall components.
// Real DS: PageHeader, FilterDropdown, SegmentedControl, VersionPill, Chip, Button, KVGrid, Icon.
// Shipped in heimdall: KanbanBoard, VersionTimeline (state-transition list).

const { useState: useTaskState } = React;

function KanbanCol({ title, count, color, children }) {
  return (
    <div className="kanban-col">
      <div className="kanban-col-head">
        <span className="dot" style={{ background: color }}></span>
        <span className="title">{title}</span>
        <span className="count">{count}</span>
      </div>
      <div className="body">{children}</div>
    </div>
  );
}
function TaskCard({ ctx, title, due, src, v, overdue, selected, done, blocked, notes }) {
  return (
    <div className={'task-card' + (selected ? ' selected' : '')} style={done ? { opacity: 0.7 } : {}}>
      <div className="row1">
        <input type="checkbox" defaultChecked={done} style={{ margin: 0, accentColor: 'var(--cl-accent-primary-deep)' }} />
        <span className="ctx">{ctx}</span>
        <span style={{ marginLeft: 'auto' }}><VersionPill>{v}</VersionPill></span>
      </div>
      <div className="title" style={done ? { textDecoration: 'line-through', color: 'var(--cl-canvas-fg-3)' } : {}}>{title}</div>
      {notes && <div style={{ fontSize: 11, color: 'var(--cl-canvas-fg-2)', marginTop: -4, marginBottom: 6, borderLeft: '2px solid var(--cl-canvas-border-strong)', paddingLeft: 8 }}>{notes}</div>}
      {blocked && <div style={{ fontSize: 10.5, color: 'var(--cl-status-amber)', fontFamily: 'var(--font-mono)', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 4 }}><span style={{ width: 5, height: 5, borderRadius: '50%', background: 'var(--cl-status-amber)' }}></span>{blocked}</div>}
      <div className="meta">
        <span className={'due' + (overdue ? ' overdue' : '')}>{overdue && <Icon name="alert" size={10} style={{ verticalAlign: 'middle', marginRight: 3 }} />}due {due}</span>
        <span style={{ color: 'var(--cl-canvas-fg-4)' }}>·</span><span>{src}</span>
      </div>
    </div>
  );
}
function TaskVersion({ label, from, to, when, note, head }) {
  return (
    <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--cl-canvas-border)', display: 'grid', gridTemplateColumns: '40px 1fr auto', gap: 10, alignItems: 'flex-start' }}>
      <span style={{ justifySelf: 'flex-start' }}><VersionPill className={head ? 'deep' : ''}>{label}</VersionPill></span>
      <div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 3, fontFamily: 'var(--font-mono)', fontSize: 11 }}>
          <span style={{ color: 'var(--cl-canvas-fg-3)' }}>{from}</span><Icon name="arrowRight" size={10} /><span style={{ color: 'var(--cl-canvas-fg-1)', fontWeight: 600 }}>{to}</span>
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--cl-canvas-fg-2)' }}>{note}</div>
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--cl-canvas-fg-3)' }}>{when}</div>
    </div>
  );
}
function TaskFilter({ label, value, options, def }) {
  return (
    <FilterDropdown mode="radio" defaultValue={[def || value]}>
      <FilterDropdown.Trigger label={label} summary={value} />
      <FilterDropdown.Panel><FilterDropdown.Section title={label}>{options.map(o => <FilterDropdown.Radio key={o} value={o} label={o} />)}</FilterDropdown.Section></FilterDropdown.Panel>
    </FilterDropdown>
  );
}

function TasksScreen() {
  const [view, setView] = useTaskState('board');
  return (
    <CLShell active="tasks" breadcrumbs={['domain', 'tasks', 'project · context-library']}>
      <PageHeader
        title="Tasks"
        idChip="142 active · 38 done"
        subtitle="One task = one chunk. State transitions generate new chunk versions even when text doesn't change — the domain layer synthesizes a textual description of the state change for embedding."
        actions={[
          <Button key="f" variant="ghost"><Icon name="filter" size={13} /> Filters</Button>,
          <Button key="o" variant="ghost"><Icon name="file" size={13} /> Open in Obsidian</Button>,
        ]}
      />
      <div className="row gap-12" style={{ marginBottom: 12, flexWrap: 'wrap' }}>
        <TaskFilter label="PROJECT" value="context-library" options={['context-library', 'all projects']} />
        <TaskFilter label="SOURCE" value="all (2)" options={['all (2)', 'obsidian.tasks', 'apple.reminders']} />
        <TaskFilter label="DUE" value="any" options={['any', 'overdue', 'this week', 'this month']} />
        <TaskFilter label="ASSIGNEE" value="@me" options={['@me', '@morgan', 'anyone']} />
        <SegmentedControl value={view} onChange={setView} options={[{ value: 'board', label: 'board' }, { value: 'list', label: 'list' }, { value: 'timeline', label: 'timeline' }]} />
        <span style={{ flex: 1 }}></span>
        <span className="eyebrow">SHOWING 12 OF 142</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 14, height: 560 }}>
        <div style={{ position: 'relative' }}>
          <span className="tbb-flag shipped" style={{ position: 'absolute', top: -26, right: 0 }}><Icon name="layout" size={10} /> heimdall · KanbanBoard</span>
          <div className="kanban">
            <KanbanCol title="Open" count={4} color="var(--cl-canvas-fg-3)">
              <TaskCard ctx="context-library / pipeline" title="Add parent_chunk_hash backfill migration" due="—" src="obsidian.tasks" v="v1" />
              <TaskCard ctx="context-library / search" title="Hybrid retrieval flag — BM25 + dense" due="oct 31" src="apple.reminders" v="v1" />
              <TaskCard ctx="context-library / adapters" title="apple.health bridge: skip empty windows" due="oct 28" overdue src="obsidian.tasks" v="v1" />
              <TaskCard ctx="context-library / docs" title="Document chunking strategy — finalize" due="nov 5" src="obsidian.tasks" v="v1" />
            </KanbanCol>
            <KanbanCol title="In Progress" count={3} color="var(--cl-status-cyan)">
              <TaskCard ctx="context-library / pipeline" title="Diff stage rewrite — hash-set comparison" due="oct 24" src="obsidian.tasks" v="v3" selected notes="rewriting positional diff → hash-set ops" />
              <TaskCard ctx="context-library / search" title="Reranker latency profile — target <40ms" due="oct 30" src="apple.reminders" v="v2" />
              <TaskCard ctx="context-library / api" title="Provenance fetch — +lineage, +parent" due="oct 26" src="obsidian.tasks" v="v2" />
            </KanbanCol>
            <KanbanCol title="Blocked" count={2} color="var(--cl-status-amber)">
              <TaskCard ctx="context-library / adapters" title="apple.health workouts endpoint flakiness" due="—" src="obsidian.tasks" v="v2" blocked="waiting on apple bridge fix" />
              <TaskCard ctx="context-library / infra" title="ChromaDB rebuild script — sync_log replay" due="—" src="obsidian.tasks" v="v1" blocked="blocked on schema migration" />
            </KanbanCol>
            <KanbanCol title="Done" count={3} color="var(--cl-status-emerald)">
              <TaskCard ctx="context-library / pipeline" title="Implement parent_chunk_hash field" due="oct 16" done src="apple.reminders" v="v4" />
              <TaskCard ctx="context-library / api" title="POST /query — top_k + domain_filter" due="oct 14" done src="obsidian.tasks" v="v3" />
              <TaskCard ctx="context-library / adapters" title="email.imap thread reconstruction" due="oct 12" done src="apple.reminders" v="v5" />
            </KanbanCol>
          </div>
        </div>

        <Panel noPadding className="cl-pane"
          title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}><Icon name="check" size={13} />Task detail</span>}
          headerAction={<VersionPill>v3</VersionPill>}>
          <div className="cl-scroll" style={{ padding: '14px 14px' }}>
            <div className="eyebrow" style={{ marginBottom: 6 }}>CONTEXT-LIBRARY / PIPELINE</div>
            <div style={{ fontSize: 14.5, fontWeight: 600, color: 'var(--cl-canvas-fg-1)', letterSpacing: '-0.015em', marginBottom: 6, lineHeight: 1.35 }}>Diff stage rewrite — hash-set comparison</div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 14 }}>
              <Chip variant="cyan">in-progress</Chip>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--cl-canvas-fg-2)' }}>due oct 24</span>
            </div>
            <KVGrid keyWidth={92} rows={[
              { key: 'SOURCE', value: <span className="mono" style={{ fontSize: 11.5 }}>obsidian.tasks/vault/projects/heimdall.md#L42</span> },
              { key: 'ASSIGNEE', value: '@morgan' },
              { key: 'PROJECT', value: <span className="mono" style={{ fontSize: 11.5 }}>context-library</span> },
              { key: 'TAGS', value: <span style={{ display: 'inline-flex', gap: 6 }}><Chip variant="neutral">pipeline</Chip><Chip variant="neutral">diff</Chip><Chip variant="neutral">refactor</Chip></span> },
            ]} />
            <div className="eyebrow" style={{ margin: '8px 0 6px' }}>CONTEXT_HEADER</div>
            <div style={{ padding: '8px 10px', background: 'rgba(251,191,36,0.04)', border: '1px solid var(--cl-canvas-border)', borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--cl-canvas-fg-1)', marginBottom: 12 }}>Diff stage rewrite [due: 2024-10-24] [in-progress]</div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>STATE TRANSITIONS · 3 CHUNK VERSIONS</div>
            <div className="version-list" style={{ border: '1px solid var(--cl-canvas-border)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
              <TaskVersion label="v3" head from="open" to="in-progress" when="oct 21" note="rewriting positional diff → hash-set ops" />
              <TaskVersion label="v2" from="—" to="open · planned" when="oct 18" note="due-date set, assigned to @morgan" />
              <TaskVersion label="v1" from="—" to="—" when="oct 17" note="created from obsidian.tasks · L42" />
            </div>
          </div>
        </Panel>
      </div>
    </CLShell>
  );
}

window.TasksScreen = TasksScreen;
