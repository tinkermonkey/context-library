// =============================================================================
// Heimdall design system — shell / layout + Panel + PageHeader.
// Ported verbatim from @tinkermonkey/heimdall-ui (src/components/*.tsx).
// =============================================================================
const { forwardRef: fwd, useState: useS, Fragment } = React;

// ---- AppTitle.tsx ---------------------------------------------------------
const AppTitle = fwd(({ title, version, collapsed = false, action, className = '', 'aria-label': ariaLabel, ...props }, ref) => {
  const classNames = ['app-title', collapsed && 'app-title--collapsed', className].filter(Boolean).join(' ');
  const computedLabel = ariaLabel ?? (version ? `${title} ${version}` : title);
  return (
    <div ref={ref} className={classNames} aria-label={computedLabel} role="banner">
      <div className="app-title__mark" aria-hidden="true" />
      {!collapsed && (
        <div className="app-title__text">
          <div className="app-title__name">{title}</div>
          {version && <span className="app-title__version">{version}</span>}
        </div>
      )}
      {action && <div className="app-title__action">{action}</div>}
    </div>
  );
});
AppTitle.displayName = 'AppTitle';

// ---- Titlebar.tsx ---------------------------------------------------------
const Titlebar = fwd(({ left, center, right, className = '', role = 'banner', 'aria-label': ariaLabel = 'Application titlebar', ...props }, ref) => {
  const classNames = ['titlebar', className].filter(Boolean).join(' ');
  return (
    <div ref={ref} className={classNames} role={role} aria-label={ariaLabel}>
      {left && <div className="titlebar__slot titlebar__slot--left">{left}</div>}
      {center && <div className="titlebar__slot titlebar__slot--center">{center}</div>}
      {right && <div className="titlebar__slot titlebar__slot--right">{right}</div>}
    </div>
  );
});
Titlebar.displayName = 'Titlebar';

// ---- NavItem.tsx ----------------------------------------------------------
const NavItem = fwd(({ icon, label, count, active = false, depth = 0, onClick, className = '', type = 'button', ...props }, ref) => {
  const classNames = ['nav-item', active && 'nav-item--active', depth === 1 && 'nav-item--depth-1', className].filter(Boolean).join(' ');
  return (
    <button ref={ref} type={type} className={classNames} onClick={onClick} aria-current={active ? 'page' : undefined}>
      {depth === 0 && icon && <Icon name={icon} size={16} className="nav-item__icon" />}
      <span className="nav-item__label">{label}</span>
      {count !== undefined && <span className="nav-item__count">{count}</span>}
    </button>
  );
});
NavItem.displayName = 'NavItem';

// ---- Sidebar.tsx ----------------------------------------------------------
const Sidebar = fwd(({ sections, activeItemId, collapsed = false, onCollapse, onSelectItem, defaultExpandedIds, expandedIds, onExpandedChange, showCollapseToggle = true, appTitle, footer, className = '', ...props }, ref) => {
  const isControlled = expandedIds !== undefined;
  const [internalExpanded, setInternalExpanded] = useS(() => new Set(defaultExpandedIds));
  const expandedItems = isControlled ? new Set(expandedIds) : internalExpanded;
  const toggleExpanded = (id) => {
    const next = new Set(expandedItems);
    if (next.has(id)) next.delete(id); else next.add(id);
    if (!isControlled) setInternalExpanded(next);
    onExpandedChange?.(Array.from(next));
  };
  const classNames = ['sidebar', collapsed && 'sidebar--collapsed', className].filter(Boolean).join(' ');
  const collapseButton = (
    <button type="button" className="sidebar__toggle" onClick={() => onCollapse?.(!collapsed)} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
      <Icon name={collapsed ? 'chevronRight' : 'chevronLeft'} size={16} />
    </button>
  );
  return (
    <div ref={ref} className={classNames}>
      {appTitle ? (
        <>
          <AppTitle {...appTitle} collapsed={collapsed} action={collapsed ? appTitle.action : (appTitle.action ?? collapseButton)} />
          {collapsed && collapseButton}
        </>
      ) : (showCollapseToggle && collapseButton)}
      <nav className="sidebar__nav" aria-label="Sidebar navigation">
        {sections.map(section => (
          <div key={section.title} className="sidebar__section">
            {!collapsed && <div className="sidebar__section-title">{section.title}</div>}
            <div className="sidebar__items">
              {section.items.map(item => {
                const hasChildren = item.children && item.children.length > 0;
                const isExpanded = expandedItems.has(item.id);
                const isActive = activeItemId === item.id;
                const childButtons = (!collapsed && hasChildren && isExpanded)
                  ? item.children.map(child => (
                      <button key={child.id} type="button" className={`sidebar__item sidebar__item--child ${activeItemId === child.id ? 'sidebar__item--active' : ''}`}
                        onClick={() => onSelectItem?.(child.id)} aria-current={activeItemId === child.id ? 'page' : undefined}>
                        <span className="sidebar__item-label">{child.label}</span>
                        {child.count !== undefined && <span className="sidebar__item-count">{child.count}</span>}
                      </button>
                    ))
                  : [];
                return [
                  <button key={item.id} type="button" className={`sidebar__item ${isActive ? 'sidebar__item--active' : ''}`}
                    onClick={() => { if (hasChildren) toggleExpanded(item.id); else onSelectItem?.(item.id); }}
                    title={collapsed ? item.label : undefined} aria-current={isActive ? 'page' : undefined}
                    aria-expanded={hasChildren ? isExpanded : undefined}>
                    {item.icon && <Icon name={item.icon} size={18} className="sidebar__item-icon" />}
                    {!collapsed && <span className="sidebar__item-label">{item.label}</span>}
                    {!collapsed && item.count !== undefined && <span className="sidebar__item-count">{item.count}</span>}
                    {!collapsed && hasChildren && <Icon name="chevronRight" size={14} className={`sidebar__item-chevron ${isExpanded ? 'sidebar__item-chevron--open' : ''}`} />}
                  </button>,
                  ...childButtons,
                ];
              })}
            </div>
          </div>
        ))}
      </nav>
      {footer && <div className="sidebar__footer">{footer}</div>}
    </div>
  );
});
Sidebar.displayName = 'Sidebar';

// ---- Topbar.tsx -----------------------------------------------------------
const Topbar = fwd(({ breadcrumbs, searchPlaceholder = 'Search…', onSearch, leadingContent, searchHint, children, className = '', ...props }, ref) => {
  const classNames = ['topbar', className].filter(Boolean).join(' ');
  const lastIndex = breadcrumbs ? breadcrumbs.length - 1 : -1;
  return (
    <div ref={ref} className={classNames}>
      {leadingContent && <div className="topbar__leading">{leadingContent}</div>}
      <div className="topbar__breadcrumbs">
        {breadcrumbs && breadcrumbs.length > 0 && (
          <nav className="breadcrumbs" aria-label="Breadcrumb">
            {breadcrumbs.map((crumb, index) => ([
              index > 0 ? <span key={`sep${index}`} className="breadcrumbs__separator" aria-hidden="true">/</span> : null,
              crumb.href ? (
                <a key={`c${index}`} href={crumb.href} className="breadcrumbs__link" aria-current={index === lastIndex ? 'page' : undefined}>{crumb.label}</a>
              ) : crumb.onClick ? (
                <button key={`c${index}`} type="button" className="breadcrumbs__link breadcrumbs__link--button" onClick={crumb.onClick} aria-current={index === lastIndex ? 'page' : undefined}>{crumb.label}</button>
              ) : (
                <span key={`c${index}`} className="breadcrumbs__link breadcrumbs__link--static" aria-current={index === lastIndex ? 'page' : undefined}>{crumb.label}</span>
              ),
            ]))}
          </nav>
        )}
      </div>
      <div className="topbar__actions">
        {onSearch && (
          <div className="topbar__search-wrap">
            <input type="search" placeholder={searchPlaceholder} aria-label={searchPlaceholder} className="topbar__search" onChange={e => onSearch(e.target.value)} />
            {searchHint && <span className="topbar__search-hint">{searchHint}</span>}
          </div>
        )}
        {children}
      </div>
    </div>
  );
});
Topbar.displayName = 'Topbar';

// ---- Statusbar.tsx --------------------------------------------------------
const isStatusbarItem = (item) => typeof item === 'object' && item !== null && 'kind' in item;
const renderStatusbarItems = (items) => items.map((item, index) => {
  switch (item.kind) {
    case 'divider': return <div key={index} className="statusbar__divider" />;
    case 'pulse': return (
      <div key={index} className="statusbar__item statusbar__item--pulse">
        <div className={`statusbar__pulse statusbar__pulse--${item.tone}`} />
        {item.mono ? <span className="statusbar__label statusbar__label--mono">{item.label}</span> : <span className="statusbar__label">{item.label}</span>}
      </div>
    );
    case 'icon': return (
      <div key={index} className={`statusbar__item ${item.mono ? 'statusbar__item--mono' : ''}`} aria-label={item.label}>
        <Icon name={item.icon} size={14} />
        {item.label && <span className="statusbar__label">{item.label}</span>}
      </div>
    );
    default: return null;
  }
});
const Statusbar = fwd(({ left, center, right, className = '', ...props }, ref) => {
  const classNames = ['statusbar', className].filter(Boolean).join(' ');
  const renderSlot = (content) => {
    if (!content) return null;
    if (Array.isArray(content) && content.length > 0 && isStatusbarItem(content[0])) return renderStatusbarItems(content);
    return content;
  };
  return (
    <div ref={ref} role="status" className={classNames}>
      {left && <div className="statusbar__slot statusbar__slot--left statusbar__left">{renderSlot(left)}</div>}
      {center && <div className="statusbar__slot statusbar__slot--center">{renderSlot(center)}</div>}
      {right && <div className="statusbar__slot statusbar__slot--right statusbar__right">{renderSlot(right)}</div>}
    </div>
  );
});
Statusbar.displayName = 'Statusbar';

// ---- ShellLayout.tsx ------------------------------------------------------
const ShellLayout = fwd(({ titlebar, appTitle, topbar, sidebar, statusbar, children, className = '', ...props }, ref) => {
  const classNames = ['shell-layout', className].filter(Boolean).join(' ');
  const { hide: _t, ...titlebarProps } = titlebar ?? {};
  const renderTitlebar = titlebar && !titlebar.hide;
  const { hide: _a, ...appTitleProps } = appTitle ?? {};
  const renderAppTitle = appTitle && !appTitle.hide;
  const { hide: _tb, ...topbarProps } = topbar ?? {};
  const renderTopbar = topbar && !topbar.hide;
  const { hide: _s, ...sidebarProps } = sidebar ?? {};
  const renderSidebar = sidebar && !sidebar.hide;
  const { hide: _sb, ...statusbarProps } = statusbar ?? {};
  const renderStatusbar = statusbar && !statusbar.hide;
  return (
    <div ref={ref} className={classNames}>
      {renderTitlebar && <Titlebar {...titlebarProps} />}
      <div className="shell-layout__main">
        {renderSidebar ? (
          <div className="shell-layout__sidebar-col">
            <Sidebar {...sidebarProps} appTitle={renderAppTitle ? appTitleProps : sidebarProps.appTitle} />
          </div>
        ) : renderAppTitle ? <AppTitle {...appTitleProps} /> : null}
        <div className="shell-layout__content">
          {renderTopbar && <Topbar {...topbarProps} />}
          <main className="shell-layout__canvas">{children}</main>
        </div>
      </div>
      {renderStatusbar && <Statusbar {...statusbarProps} />}
    </div>
  );
});
ShellLayout.displayName = 'ShellLayout';

// ---- Panel.tsx ------------------------------------------------------------
const Panel = fwd(({ title, subtitle, headerAction, footer, bordered = true, noPadding = false, className = '', children, ...props }, ref) => {
  const classNames = ['panel', !bordered && 'panel--no-border', className].filter(Boolean).join(' ');
  return (
    <div ref={ref} className={classNames} style={props.style}>
      {(title || subtitle || headerAction) && (
        <div className="panel__header">
          <div className="panel__header-left">
            {title && <div className="panel__title">{title}</div>}
            {subtitle && <div className="panel__subtitle">{subtitle}</div>}
          </div>
          {headerAction && <div className="panel__header-action">{headerAction}</div>}
        </div>
      )}
      {children != null && <div className={noPadding ? 'panel__body panel__body--no-padding' : 'panel__body'}>{children}</div>}
      {footer && <div className="panel__footer">{footer}</div>}
    </div>
  );
});
Panel.displayName = 'Panel';

// ---- PageHeader.tsx -------------------------------------------------------
const PageHeader = fwd(({ eyebrow, title, idChip, subtitle, actions, className = '', ...props }, ref) => {
  const classNames = ['page-header', className].filter(Boolean).join(' ');
  return (
    <div ref={ref} className={classNames} role="banner" style={props.style}>
      <div className="page-header__text">
        {eyebrow && <div className="page-header__eyebrow">{eyebrow}</div>}
        <h1 className="page-header__title">
          {title}
          {idChip && <Chip form="id-tag" className="page-header__id-chip">{idChip}</Chip>}
        </h1>
        {subtitle && <div className="page-header__subtitle">{subtitle}</div>}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </div>
  );
});
PageHeader.displayName = 'PageHeader';

Object.assign(window, { AppTitle, Titlebar, NavItem, Sidebar, Topbar, Statusbar, ShellLayout, Panel, PageHeader });
