// People domain · contact directory — rebuilt on real heimdall components.
// Real DS: PageHeader, FilterDropdown, SegmentedControl, KVGrid, VersionPill, Chip, Button, Icon.
// Custom (flagged): alphabet/org filter rail, contact grid, mentions list.

const { useState: usePeopleState } = React;

function PFacetItem({ label, count, dot, active }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 10px', margin: '0 4px', borderRadius: 3, background: active ? 'rgba(251,191,36,0.06)' : 'transparent', borderLeft: active ? '2px solid rgb(var(--accent-primary))' : '2px solid transparent', paddingLeft: active ? 8 : 10, cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 11.5, color: active ? 'var(--cl-canvas-fg-1)' : 'var(--cl-canvas-fg-2)' }}>
      {dot && <span style={{ width: 7, height: 7, borderRadius: 2, background: dot }}></span>}
      <span style={{ flex: 1 }}>{label}</span>
      <span style={{ color: 'var(--cl-canvas-fg-3)', fontSize: 10.5 }}>{count}</span>
    </div>
  );
}
function Contact({ initials, name, title, org, src, selected, color }) {
  return (
    <div className={'contact-card' + (selected ? ' selected' : '')}>
      <div className="avatar" style={{ background: 'linear-gradient(135deg, ' + color + ' 0%, ' + color + ' 100%)' }}>{initials}</div>
      <div className="name">{name}</div>
      <div className="title">{title}</div>
      <div className="org"><span className="dom-dot people"></span> {org}</div>
      <div className="src">via {src}</div>
    </div>
  );
}
function Mention({ dom, what, when }) {
  return (
    <div style={{ padding: '6px 10px', margin: '2px 0', background: 'var(--cl-canvas-bg-2)', border: '1px solid var(--cl-canvas-border)', borderRadius: 'var(--radius-md)', display: 'flex', alignItems: 'center', gap: 8 }}>
      <span className={'dom-dot ' + dom}></span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9.5, color: 'var(--cl-canvas-fg-4)', textTransform: 'uppercase', letterSpacing: '0.06em', width: 64 }}>{dom}</span>
      <span style={{ fontSize: 11.5, color: 'var(--cl-canvas-fg-1)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{what}</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--cl-canvas-fg-3)' }}>{when}</span>
    </div>
  );
}
function PFilter({ label, value, options }) {
  return (
    <FilterDropdown mode="radio" defaultValue={[value]}>
      <FilterDropdown.Trigger label={label} summary={value} />
      <FilterDropdown.Panel><FilterDropdown.Section title={label}>{options.map(o => <FilterDropdown.Radio key={o} value={o} label={o} />)}</FilterDropdown.Section></FilterDropdown.Panel>
    </FilterDropdown>
  );
}

const CONTACTS = [
  ['AP', 'Ana Patel', 'staff eng · pipelines', 'vcard', '#22D3EE', true],
  ['MC', 'Morgan Cho', 'director eng', 'vcard', '#818CF8'],
  ['SR', 'Sam Reyes', 'researcher · retrieval', 'apple.contacts', '#10B981'],
  ['DL', 'Daniela Lim', 'bridge eng · macOS', 'vcard', '#F472B6'],
  ['JP', 'Jules Park', 'product · context', 'vcard', '#FB7185'],
  ['KO', 'Kai Ono', 'researcher · embeddings', 'apple.contacts', '#F59E0B'],
  ['EM', 'Esme Moreau', 'design lead', 'vcard', '#A78BFA'],
  ['TW', 'Theo Walsh', 'data eng', 'vcard', '#22D3EE'],
  ['RL', 'Riley Liang', 'security · platform', 'apple.contacts', '#10B981'],
  ['NF', 'Nadia Fischer', 'ml infra', 'vcard', '#818CF8'],
  ['ZC', 'Zoe Carter', 'staff eng · search', 'vcard', '#FB7185'],
  ['OB', 'Owen Bell', 'recruiter · eng', 'vcard', '#F59E0B'],
];

function PeopleScreen() {
  const [layout, setLayout] = usePeopleState('grid');
  return (
    <CLShell active="people" breadcrumbs={['domain', 'people', 'studio', 'ana patel']}>
      <PageHeader
        title="People"
        idChip="94 contacts"
        subtitle={<span>One contact = one chunk. Embedded prose excludes emails and phone numbers; sensitive identifiers stay in <span className="mono">domain_metadata</span> only.</span>}
        actions={[
          <PFilter key="o" label="ORG" value="studio · 18" options={['studio · 18', 'acme · 6', 'family · 12', 'all orgs']} />,
          <PFilter key="t" label="TAG" value="all" options={['all', 'colleague', 'family', 'vendor']} />,
          <Button key="a" variant="accent"><Icon name="plus" size={13} /> Add contact</Button>,
        ]}
      />
      <div style={{ display: 'grid', gridTemplateColumns: '180px 1fr 360px', gap: 14, height: 560 }}>
        {/* Filter rail */}
        <Panel noPadding className="cl-pane" title="Filter" headerAction={<span className="tbb-flag">custom</span>}>
          <div className="cl-scroll" style={{ padding: '10px 4px' }}>
            <div className="eyebrow" style={{ padding: '6px 12px 4px' }}>ALPHABET</div>
            <div style={{ padding: '4px 8px', display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 2 }}>
              {'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('').map(l => (
                <div key={l} style={{ padding: '4px 0', textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'PCMS'.includes(l) ? 'var(--cl-canvas-fg-1)' : 'var(--cl-canvas-fg-4)', fontWeight: l === 'P' ? 700 : 400, background: l === 'P' ? 'rgba(251,191,36,0.10)' : 'transparent', borderRadius: 3, cursor: 'pointer' }}>{l}</div>
              ))}
            </div>
            <div className="eyebrow" style={{ padding: '14px 12px 4px' }}>ORG</div>
            <PFacetItem label="studio" count={18} active dot="#C084FC" />
            <PFacetItem label="acme · sales" count={6} dot="#94A3B8" />
            <PFacetItem label="anthropic" count={4} dot="#94A3B8" />
            <PFacetItem label="family" count={12} dot="#F472B6" />
            <PFacetItem label="(no org)" count={54} dot="#94A3B8" />
            <div className="eyebrow" style={{ padding: '14px 12px 4px' }}>SOURCE</div>
            <PFacetItem label="vcard" count={62} dot="var(--cl-status-emerald)" />
            <PFacetItem label="apple.contacts" count={32} dot="var(--cl-status-cyan)" />
          </div>
        </Panel>

        {/* Contact grid */}
        <Panel noPadding className="cl-pane"
          title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13 }}><span className="dom-dot people"></span>studio · 18 contacts</span>}
          headerAction={<span className="row" style={{ gap: 8 }}><span className="tbb-flag"><Icon name="user" size={10} /> custom · ContactGrid</span><SegmentedControl value={layout} onChange={setLayout} options={[{ value: 'grid', label: 'grid' }, { value: 'list', label: 'list' }]} /></span>}>
          <div className="cl-scroll" style={{ padding: 14, display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, alignContent: 'flex-start' }}>
            {CONTACTS.map(c => <Contact key={c[1]} initials={c[0]} name={c[1]} title={c[2]} org="studio" src={c[3]} color={c[4]} selected={c[5]} />)}
          </div>
        </Panel>

        {/* Contact detail */}
        <Panel noPadding className="cl-pane"
          title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}><Icon name="lock" size={13} />Contact</span>}
          headerAction={<VersionPill>v2</VersionPill>}>
          <div style={{ padding: '18px 16px 16px', borderBottom: '1px solid var(--cl-canvas-border)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
            <div style={{ width: 64, height: 64, borderRadius: '50%', background: 'linear-gradient(135deg, #22D3EE 0%, #06B6D4 100%)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 700, marginBottom: 6 }}>AP</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--cl-canvas-fg-1)', letterSpacing: '-0.015em' }}>Ana Patel</div>
            <div style={{ fontSize: 12, color: 'var(--cl-canvas-fg-2)' }}>staff engineer · pipelines</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--cl-canvas-fg-3)' }}>studio</div>
          </div>
          <div className="cl-scroll" style={{ padding: '14px 16px' }}>
            <div className="eyebrow" style={{ marginBottom: 6 }}>CONTEXT_HEADER</div>
            <div style={{ padding: '8px 10px', background: 'rgba(251,191,36,0.04)', border: '1px solid var(--cl-canvas-border)', borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--cl-canvas-fg-1)', marginBottom: 12 }}>Contact: Ana Patel — studio</div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>EMBEDDED PROSE (PUBLIC ONLY)</div>
            <div style={{ padding: '10px 12px', background: 'var(--cl-canvas-bg-2)', border: '1px solid var(--cl-canvas-border)', borderRadius: 'var(--radius-md)', fontSize: 12.5, color: 'var(--cl-canvas-fg-1)', lineHeight: 1.55, marginBottom: 14 }}>
              Ana Patel is a staff engineer at studio.<br />Notes: pipelines + chunking lead. RAG retrieval domain expert. Currently co-owning the diff stage rewrite with morgan.
            </div>
            <div className="eyebrow" style={{ marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>DOMAIN_METADATA · SENSITIVE <Icon name="lock" size={11} /></div>
            <div style={{ background: 'rgba(244,63,94,0.04)', border: '1px solid rgba(244,63,94,0.20)', borderRadius: 'var(--radius-md)' }}>
              <KVGrid keyWidth={92} rows={[
                { key: 'EMAIL', value: <span className="mono" style={{ fontSize: 11.5 }}>•••••@studio</span> },
                { key: 'PHONE', value: <span className="mono" style={{ fontSize: 11.5 }}>••• ••• ••91</span> },
                { key: 'SOURCE', value: <span className="mono" style={{ fontSize: 11.5 }}>vcard/ana-patel.vcf</span> },
                { key: 'SCOPE', value: <Chip variant="rose">not embedded</Chip> },
              ]} />
            </div>
            <div className="eyebrow" style={{ marginTop: 14, marginBottom: 6 }}>MENTIONS · 47 OCCURRENCES</div>
            <Mention dom="messages" what="email thread · 'graph rag handoff'" when="14m" />
            <Mention dom="messages" what="email · 'chunk-hash collision proposal'" when="2h" />
            <Mention dom="notes" what="daily/2024-10-21.md · '## Pairing'" when="2d" />
            <Mention dom="tasks" what="diff stage rewrite (co-owner)" when="5d" />
            <Mention dom="events" what="standup · oct 23 14:00" when="2h" />
          </div>
        </Panel>
      </div>
    </CLShell>
  );
}

window.PeopleScreen = PeopleScreen;
