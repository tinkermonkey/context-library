// Shared Heimdall shell for the Context Library refresh.
// Renders titlebar + dark sidebar + topbar + canvas slot + statusbar.
// Configured per-artboard via the `active` prop.

const NAV = [
  { id: 'overview',  group: null, label: 'Overview',      icon: 'dashboard', count: null },
  { id: 'search',    group: null, label: 'Search',        icon: 'search',    count: null },
  { id: 'sources',   group: null, label: 'Sources',       icon: 'data',      count: '4,812' },

  { id: '__domains', group: 'header', label: 'Domains' },
  { id: 'notes',     group: 'dom', label: 'Notes',     icon: 'doc',     dot: 'notes',     count: '1,284' },
  { id: 'messages',  group: 'dom', label: 'Messages',  icon: 'globe',   dot: 'messages',  count: '2,140' },
  { id: 'events',    group: 'dom', label: 'Events',    icon: 'pipeline',dot: 'events',    count: '986'   },
  { id: 'tasks',     group: 'dom', label: 'Tasks',     icon: 'check',   dot: 'tasks',     count: '142'   },
  { id: 'documents', group: 'dom', label: 'Documents', icon: 'layers',  dot: 'documents', count: '260'   },
  { id: 'people',    group: 'dom', label: 'People',    icon: 'shield',  dot: 'people',    count: '94'    },
  { id: 'location',  group: 'dom', label: 'Location',  icon: 'globe',   dot: 'location',  count: '231'   },
  { id: 'music',     group: 'dom', label: 'Music',     icon: 'zap',     dot: 'music',     count: '3,402' },
  { id: 'health',    group: 'dom', label: 'Health',    icon: 'brain',   dot: 'health',    count: '14,981'},

  { id: '__system',  group: 'header', label: 'System' },
  { id: 'pipeline',  group: null, label: 'Pipeline',  icon: 'pipeline', count: null },
  { id: 'adapters',  group: null, label: 'Adapters',  icon: 'cpu',     count: '11' },
  { id: 'admin',     group: null, label: 'Admin',     icon: 'settings', count: null },
];

function Shell({ active, breadcrumbs, statusbar, children }) {
  return (
    <div className="desktop">
      {/* Titlebar */}
      <div className="titlebar">
        <div className="lights">
          <span className="l-close"></span>
          <span className="l-min"></span>
          <span className="l-max"></span>
        </div>
        <div className="titlebar-app">
          <div className="brand-mark" style={{width:18, height:18, borderRadius:4}}><i></i></div>
          <span>context-library</span>
          <span className="titlebar-app-sep">·</span>
        </div>
        <button className="titlebar-ws">
          <Icon name="layers" size={11}/> <span>cli/wkbench</span>
        </button>
        <div className="titlebar-spacer"></div>
        <button className="titlebar-btn">
          <Icon name="refresh" size={12}/> <span>sync</span>
        </button>
        <button className="titlebar-btn">
          <span>⌘K</span>
          <span className="kbd-mini">palette</span>
        </button>
      </div>

      {/* Shell row */}
      <div className="app-shell">
        {/* Sidebar */}
        <aside className="shell-rail">
          <div className="brand-row">
            <div className="brand-mark"><i></i></div>
            <div className="brand-name">
              Context Library
              <span>versioned RAG</span>
            </div>
            <button className="rail-collapse" aria-label="collapse"><Icon name="chevLeft" size={12}/></button>
          </div>

          <nav className="nav-section">
            {NAV.map(item => {
              if (item.group === 'header') {
                return (
                  <div key={item.id} className="eyebrow-shell" style={{padding:'14px 12px 6px'}}>
                    {item.label}
                  </div>
                );
              }
              const isActive = active === item.id;
              return (
                <div key={item.id} className={'nav-item' + (isActive ? ' active' : '')}>
                  {item.dot
                    ? <span className={'dom-dot ' + item.dot} style={{width:8, height:8}}></span>
                    : <Icon name={item.icon} size={14}/>}
                  <span className="nav-label">{item.label}</span>
                  {item.count && <span className="nav-count">{item.count}</span>}
                </div>
              );
            })}
          </nav>

          <div className="rail-footer">
            <div className="rail-user">
              <div className="avatar">HM</div>
              <div className="rail-user-info">
                <div className="n">heimdall</div>
                <div className="e">localhost:8000</div>
              </div>
              <Icon name="more" size={14}/>
            </div>
          </div>
        </aside>

        {/* Workspace */}
        <div className="workspace">
          {/* Topbar */}
          <div className="topbar">
            <button className="ws-chip">
              <span className="ws-chip-dot"></span>
              <span className="ws-chip-name">localhost:8000</span>
              <Icon name="chevDown" size={11}/>
            </button>
            <div className="crumbs">
              {(breadcrumbs || []).map((c, i) => (
                <React.Fragment key={i}>
                  {i > 0 && <span className="sep">/</span>}
                  <span className={i === breadcrumbs.length - 1 ? 'last' : ''}>{c}</span>
                </React.Fragment>
              ))}
            </div>
            <button className="topbar-palette">
              <Icon name="search" size={13}/>
              <span>Search sources, chunks, adapters, run /commands…</span>
              <span className="kbd">⌘K</span>
            </button>
            <span className="env-pill"><span className="dot"></span>chroma · ok</span>
            <button className="topbar-ico"><Icon name="bell" size={15}/></button>
            <button className="topbar-ico"><Icon name="settings" size={15}/></button>
          </div>

          {/* Canvas */}
          <div className="canvas-area">
            {children}
          </div>

          {/* Statusbar */}
          <div className="statusbar">
            <div className="statusbar-group">
              <span className="sb-item"><span className="pulse sm"></span> <span className="sb-mono">graph daemon :8000</span></span>
              <span className="sb-divider"></span>
              {(statusbar?.left || [
                <span key="a" className="sb-item sb-mono">11 adapters</span>,
                <span key="b" className="sb-item sb-mono">4,812 sources</span>,
                <span key="c" className="sb-item sb-mono">18,724 chunks</span>,
              ]).map((el, i) => <React.Fragment key={i}>{el}{i < 2 && <span className="sb-divider"></span>}</React.Fragment>)}
            </div>
            <div className="statusbar-group">
              {(statusbar?.right || [
                <span key="a" className="sb-item sb-mono"><span className="pulse cyan sm"></span> embedding all-MiniLM-L6-v2</span>,
                <span key="b" className="sb-item sb-mono">queue 0</span>,
                <span key="c" className="sb-item sb-mono">v0.4.2</span>,
              ]).map((el, i) => <React.Fragment key={i}>{el}{i < 2 && <span className="sb-divider"></span>}</React.Fragment>)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

window.Shell = Shell;
