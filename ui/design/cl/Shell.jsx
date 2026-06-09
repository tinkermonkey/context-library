// =============================================================================
// Context Library — shared application shell.
// Composed entirely from the real heimdall ShellLayout (Titlebar + Sidebar +
// AppTitle + Topbar + Statusbar). Per-screen config via props.
// =============================================================================
const { useState: useShellState } = React;

const CL_SECTIONS = [
  { title: 'Library', items: [
    { id: 'overview', label: 'Overview', icon: 'dashboard' },
    { id: 'search', label: 'Search', icon: 'search' },
    { id: 'sources', label: 'Sources', icon: 'data', count: '4,812' },
  ] },
  { title: 'Domains', items: [
    { id: 'notes', label: 'Notes', icon: 'file', count: '1,284' },
    { id: 'messages', label: 'Messages', icon: 'send', count: '2,140' },
    { id: 'events', label: 'Events', icon: 'calendar', count: '986' },
    { id: 'tasks', label: 'Tasks', icon: 'check', count: '142' },
    { id: 'documents', label: 'Documents', icon: 'folder', count: '260' },
    { id: 'people', label: 'People', icon: 'user', count: '94' },
    { id: 'location', label: 'Location', icon: 'tag', count: '231' },
    { id: 'music', label: 'Music', icon: 'zap', count: '3,402' },
    { id: 'health', label: 'Health', icon: 'heart', count: '14,981' },
  ] },
  { title: 'System', items: [
    { id: 'pipeline', label: 'Pipeline', icon: 'pipeline' },
    { id: 'adapters', label: 'Adapters', icon: 'component', count: '11' },
    { id: 'admin', label: 'Admin', icon: 'settings' },
  ] },
];

// Sidebar footer — workspace identity (app content in the real Sidebar footer slot)
function RailUser() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: 4 }}>
      <div style={{
        width: 28, height: 28, borderRadius: 'var(--radius-md)',
        background: 'linear-gradient(135deg, rgb(var(--accent-primary)), rgb(var(--accent-primary-deep)))',
        color: '#29220A', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, flexShrink: 0,
      }}>HM</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12.5, fontWeight: 600, color: 'rgb(var(--shell-fg-1))' }}>heimdall</div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'rgb(var(--shell-fg-3))' }}>localhost:8000</div>
      </div>
      <Icon name="moreVertical" size={14} style={{ color: 'rgb(var(--shell-fg-3))' }} />
    </div>
  );
}

// Titlebar slots ----------------------------------------------------------
function TitleLights() {
  const dot = (c) => ({ width: 12, height: 12, borderRadius: '50%', background: c });
  return (
    <div style={{ display: 'flex', gap: 8 }}>
      <span style={dot('#FF5F57')} /><span style={dot('#FEBC2E')} /><span style={dot('#28C840')} />
    </div>
  );
}

function CLShell({ active, breadcrumbs, statusLeft, statusRight, children }) {
  const [collapsed, setCollapsed] = useShellState(false);

  const titlebar = {
    left: [
      <TitleLights key="lights" />,
      <span key="name" style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'rgb(var(--shell-fg-1))', fontWeight: 500 }}>context-library</span>,
    ],
    center: (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: 6, padding: '3px 9px',
        border: '1px solid rgb(var(--shell-border-2))', borderRadius: 'var(--radius-md)',
        fontFamily: 'var(--font-mono)', fontSize: 11, color: 'rgb(var(--shell-fg-2))',
      }}>
        <Icon name="gitBranch" size={11} /> cli/wkbench
      </span>
    ),
    right: (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Button variant="ghost" size="sm"><Icon name="reload" size={12} /> sync</Button>
        <span style={{
          display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: 'var(--font-mono)',
          fontSize: 11, color: 'rgb(var(--shell-fg-3))',
        }}>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 10, padding: '1px 5px', borderRadius: 3,
            border: '1px solid rgb(var(--shell-border-2))', background: 'rgb(var(--shell-surface))', color: 'rgb(var(--shell-fg-3))',
          }}>⌘K</span> palette
        </span>
      </div>
    ),
  };

  const wsChip = (
    <button style={{
      display: 'inline-flex', alignItems: 'center', gap: 7, padding: '5px 10px',
      background: 'rgb(var(--shell-surface))', border: '1px solid rgb(var(--shell-border-2))',
      borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-mono)', fontSize: 12,
      color: 'rgb(var(--shell-fg-1))', cursor: 'pointer',
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'rgb(var(--accent-primary-deep))' }} />
      localhost:8000
      <Icon name="chevronDown" size={11} style={{ color: 'rgb(var(--shell-fg-3))' }} />
    </button>
  );

  const topbar = {
    leadingContent: wsChip,
    breadcrumbs: (breadcrumbs || []).map(label => ({ label })),
    onSearch: () => {},
    searchPlaceholder: 'Search sources, chunks, adapters, run /commands…',
    searchHint: '⌘K',
    children: [
      <Chip key="env" form="env">chroma · ok</Chip>,
      <Button key="bell" variant="ghost" size="sm" icon aria-label="Notifications"><Icon name="bell" size={15} /></Button>,
      <Button key="settings" variant="ghost" size="sm" icon aria-label="Settings"><Icon name="settings" size={15} /></Button>,
    ],
  };

  const defaultLeft = [
    { kind: 'pulse', tone: 'emerald', label: 'graph daemon :8000', mono: true },
    { kind: 'divider' },
    { kind: 'icon', icon: 'component', label: '11 adapters', mono: true },
    { kind: 'icon', icon: 'data', label: '4,812 sources', mono: true },
    { kind: 'icon', icon: 'pipeline', label: '18,724 chunks', mono: true },
  ];
  const defaultRight = [
    { kind: 'pulse', tone: 'cyan', label: 'embedding all-MiniLM-L6-v2', mono: true },
    { kind: 'divider' },
    { kind: 'icon', icon: 'gitBranch', label: 'v0.4.2', mono: true },
  ];

  return (
    <ShellLayout
      titlebar={titlebar}
      appTitle={{ title: 'Context Library', version: 'versioned RAG' }}
      sidebar={{
        sections: CL_SECTIONS,
        activeItemId: active,
        collapsed,
        onCollapse: setCollapsed,
        footer: <RailUser />,
      }}
      topbar={topbar}
      statusbar={{ left: statusLeft || defaultLeft, right: statusRight || defaultRight }}
    >
      {children}
    </ShellLayout>
  );
}

window.CLShell = CLShell;
