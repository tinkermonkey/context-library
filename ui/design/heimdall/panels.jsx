// =============================================================================
// Heimdall design system — inputs, panels, layout helpers.
// Ported verbatim from @tinkermonkey/heimdall-ui (src/components/*.tsx).
// (DOM prop-spreads and JSX fragments adapted for the in-browser runtime.)
// =============================================================================
const { forwardRef: f2, useState: us2, useRef: ur2, useCallback: uc2, createContext: cctx, useContext: uctx } = React;

// ---- TextInput.tsx --------------------------------------------------------
const TextInput = f2(({ mono = false, error = false, className = '', ...props }, ref) => {
  const classNames = ['text-input', mono && 'text-input--mono', error && 'text-input--error', className].filter(Boolean).join(' ');
  return <input type={props.type || 'text'} ref={ref} className={classNames}
    placeholder={props.placeholder} defaultValue={props.defaultValue} value={props.value}
    onChange={props.onChange} disabled={props.disabled} style={props.style} aria-label={props['aria-label']} name={props.name} />;
});
TextInput.displayName = 'TextInput';

// ---- FilterBar.tsx --------------------------------------------------------
const FilterBar = f2(({ filters = [], value, defaultValue = '', onSearchChange, onFilterRemove, onClearAll, searchPlaceholder = 'Search...', children, showingCount, totalCount, className = '', ...props }, ref) => {
  const isControlled = value !== undefined;
  const [internalValue, setInternalValue] = us2(defaultValue);
  const searchValue = isControlled ? value : internalValue;
  const handleSearchChange = (e) => { const next = e.target.value; if (!isControlled) setInternalValue(next); onSearchChange?.(next); };
  const handleClearAll = () => { if (!isControlled) setInternalValue(''); onClearAll?.(); };
  const classNames = ['filter-bar', className].filter(Boolean).join(' ');
  const hasChildren = React.Children.count(children) > 0;
  const hasCaption = showingCount !== undefined && totalCount !== undefined;
  return (
    <div ref={ref} className={classNames} style={props.style}>
      <div className="filter-bar__controls">
        <div className="filter-bar__search-wrapper" role="search">
          <Icon name="search" size={16} className="filter-bar__search-icon" />
          <input type="text" aria-label="Search" placeholder={searchPlaceholder} value={searchValue} onChange={handleSearchChange} className="filter-bar__search-input" />
        </div>
        {hasChildren && <div className="filter-bar__children">{children}</div>}
        {hasCaption && <div className="filter-bar__caption">Showing {showingCount} of {totalCount}</div>}
      </div>
      {filters.length > 0 && (
        <div className="filter-bar__chips">
          {onClearAll && <button type="button" className="filter-bar__clear-all" onClick={handleClearAll}>Clear all</button>}
          {filters.map(filter => (
            <Chip key={filter.id} variant="neutral" className="filter-bar__chip">
              <span className="filter-bar__chip-label">{filter.label}</span>
              <button type="button" className="filter-bar__chip-close" onClick={() => onFilterRemove?.(filter.id)} aria-label={`Remove ${filter.label} filter`}><Icon name="x" size={14} /></button>
            </Chip>
          ))}
        </div>
      )}
    </div>
  );
});
FilterBar.displayName = 'FilterBar';

// ---- KVGrid.tsx -----------------------------------------------------------
const KVGrid = f2(({ rows = [], keyWidth, className = '', style, ...props }, ref) => {
  const classNames = ['kv-grid', className].filter(Boolean).join(' ');
  const gridStyle = keyWidth ? { ...style, gridTemplateColumns: `${typeof keyWidth === 'number' ? `${keyWidth}px` : keyWidth} 1fr` } : style;
  return (
    <dl ref={ref} className={classNames} style={gridStyle}>
      {rows.map((row) => ([
        <dt key={row.key + '-k'} className="kv-grid__key">{row.key}</dt>,
        <dd key={row.key + '-v'} className="kv-grid__value">{row.value}</dd>,
      ]))}
    </dl>
  );
});
KVGrid.displayName = 'KVGrid';

// ---- InspectorPanel.tsx ---------------------------------------------------
const InspectorPanelContext = cctx(undefined);
const InspectorPanelSection = f2(({ title, count, actions, children, className = '' }, ref) => {
  const classNames = ['inspector-panel__section', className].filter(Boolean).join(' ');
  return (
    <div ref={ref} className={classNames}>
      <div className="inspector-panel__section-header">
        <div className="inspector-panel__section-title">
          <span>{title}</span>
          {count !== undefined && <span className="inspector-panel__section-count">· {count}</span>}
        </div>
        {actions && <div className="inspector-panel__section-actions">{actions}</div>}
      </div>
      {children && <div className="inspector-panel__section-content">{children}</div>}
    </div>
  );
});
InspectorPanelSection.displayName = 'InspectorPanel.Section';
const InspectorPanelPropertySection = f2(({ title, count, actionIcon, actionLabel, onAction, rows, className = '' }, ref) => {
  const classNames = ['inspector-panel__property-section', className].filter(Boolean).join(' ');
  return (
    <div ref={ref} className={classNames}>
      <div className="inspector-panel__property-section-header">
        <span className="inspector-panel__property-section-title">{title}</span>
        {count !== undefined && <span className="inspector-panel__property-section-count">{count}</span>}
        {onAction && <button className="inspector-panel__property-section-action" onClick={onAction} type="button" aria-label={actionLabel}>{actionIcon}</button>}
      </div>
      {rows.length > 0 && (
        <div className="inspector-panel__property-rows">
          {rows.map((row) => (
            <div key={row.key} className="inspector-panel__property-row">
              <span className="inspector-panel__property-key">{row.key}</span>
              <span className="inspector-panel__property-value">{row.value}</span>
              {row.usageCount !== undefined && <span className="inspector-panel__property-usage">used {row.usageCount}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
});
InspectorPanelPropertySection.displayName = 'InspectorPanel.PropertySection';
const InspectorPanelComponent = f2(({ eyebrow = '', title, id, version, actions, children, className = '' }, ref) => {
  const classNames = ['inspector-panel', className].filter(Boolean).join(' ');
  return (
    <InspectorPanelContext.Provider value={true}>
      <div ref={ref} className={classNames}>
        <div className="inspector-panel__head">
          {eyebrow && <div className="inspector-panel__eyebrow">{eyebrow}</div>}
          <div className="inspector-panel__title">{title}</div>
          <div className="inspector-panel__id-version">
            <span className="inspector-panel__id">{id}</span>
            {version !== undefined && <VersionPill>{version}</VersionPill>}
          </div>
          {actions && <div className="inspector-panel__actions">{actions}</div>}
        </div>
        <div className="inspector-panel__body">{children}</div>
      </div>
    </InspectorPanelContext.Provider>
  );
});
InspectorPanelComponent.displayName = 'InspectorPanel';
const InspectorPanel = Object.assign(InspectorPanelComponent, { Section: InspectorPanelSection, PropertySection: InspectorPanelPropertySection });

// ---- SplitPane.tsx --------------------------------------------------------
const SplitPane = f2(({ direction = 'horizontal', initialSplitPercent = 50, splitPercent: controlledPercent, onSplitChange, minSize = 200, maxSize = 800, first, second, dividerLabel, className = '' }, ref) => {
  const [internalPercent, setInternalPercent] = us2(initialSplitPercent);
  const containerRef = ur2(null);
  const isControlled = controlledPercent !== undefined;
  const splitPercent = isControlled ? controlledPercent : internalPercent;
  const clampPercent = uc2((rawPercent, containerSize) => {
    const minPercent = (minSize / containerSize) * 100;
    const maxPercent = (maxSize / containerSize) * 100;
    return Math.max(minPercent, Math.min(rawPercent, maxPercent));
  }, [minSize, maxSize]);
  const setSplit = uc2((newPercent) => { if (!isControlled) setInternalPercent(newPercent); onSplitChange?.(newPercent); }, [isControlled, onSplitChange]);
  const mergeRefs = uc2((refs) => (element) => { refs.forEach(r => { if (typeof r === 'function') r(element); else if (r) r.current = element; }); }, []);
  const handleMouseDown = uc2(() => {
    const handleMouseMove = (e) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const isHorizontal = direction === 'horizontal';
      const position = isHorizontal ? e.clientX - rect.left : e.clientY - rect.top;
      const size = isHorizontal ? rect.width : rect.height;
      const rawPercent = (position / size) * 100;
      setSplit(clampPercent(rawPercent, size));
    };
    const handleMouseUp = () => { document.removeEventListener('mousemove', handleMouseMove); document.removeEventListener('mouseup', handleMouseUp); };
    document.addEventListener('mousemove', handleMouseMove); document.addEventListener('mouseup', handleMouseUp);
  }, [direction, clampPercent, setSplit]);
  const handleKeyDown = uc2((e) => {
    if (!containerRef.current) return;
    const step = e.shiftKey ? 10 : 2;
    const isHorizontal = direction === 'horizontal';
    const rect = containerRef.current.getBoundingClientRect();
    const size = isHorizontal ? rect.width : rect.height;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); setSplit(clampPercent(splitPercent - step, size)); }
    else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); setSplit(clampPercent(splitPercent + step, size)); }
  }, [direction, splitPercent, clampPercent, setSplit]);
  const classNames = ['split-pane', `split-pane--${direction}`, className].filter(Boolean).join(' ');
  return (
    <div ref={mergeRefs([containerRef, ref])} className={classNames}>
      <div className="split-pane__first" style={direction === 'horizontal' ? { width: `${splitPercent}%` } : { height: `${splitPercent}%` }}>{first}</div>
      <div role="separator" aria-orientation={direction === 'horizontal' ? 'vertical' : 'horizontal'} aria-valuenow={Math.round(splitPercent)} aria-valuemin={0} aria-valuemax={100}
        aria-label={dividerLabel ?? (direction === 'horizontal' ? 'Horizontal divider' : 'Vertical divider')} tabIndex={0}
        className={`split-pane__divider split-pane__divider--${direction}`} onMouseDown={handleMouseDown} onKeyDown={handleKeyDown} />
      <div className="split-pane__second" style={direction === 'horizontal' ? { width: `${100 - splitPercent}%` } : { height: `${100 - splitPercent}%` }}>{second}</div>
    </div>
  );
});
SplitPane.displayName = 'SplitPane';

// ---- ConfigTile.tsx -------------------------------------------------------
const ConfigTile = f2(({ icon, title, description, summary = [], onClick, className = '', disabled, type = 'button' }, ref) => {
  const classNames = ['config-tile', disabled && 'config-tile--disabled', className].filter(Boolean).join(' ');
  return (
    <button ref={ref} type={type} className={classNames} onClick={onClick} disabled={disabled}>
      <div className="config-tile__icon"><Icon name={icon} size={24} /></div>
      <div className="config-tile__content">
        <div className="config-tile__title">{title}</div>
        {description && <div className="config-tile__description">{description}</div>}
        {summary.length > 0 && (
          <div className="config-tile__summary">
            {summary.map((item, index) => ([
              <div key={index + '-k'} className="config-tile__summary-key">{item.label}</div>,
              <div key={index + '-v'} className="config-tile__summary-value">{item.value}</div>,
            ]))}
          </div>
        )}
      </div>
      <div className="config-tile__chevron"><Icon name="chevronRight" size={16} /></div>
    </button>
  );
});
ConfigTile.displayName = 'ConfigTile';

// ---- TabBar.tsx -----------------------------------------------------------
const TabBar = f2(({ tabs = [], activeTabId = '', onSelectTab, className = '' }, ref) => {
  const classNames = ['tab-bar', className].filter(Boolean).join(' ');
  const tabRefs = ur2([]);
  const handleKeyDown = uc2((e, index) => {
    const enabledIndexes = tabs.map((t, i) => (t.disabled ? -1 : i)).filter(i => i !== -1);
    const posInEnabled = enabledIndexes.indexOf(index);
    let nextPos;
    if (e.key === 'ArrowRight') nextPos = enabledIndexes[(posInEnabled + 1) % enabledIndexes.length];
    else if (e.key === 'ArrowLeft') nextPos = enabledIndexes[(posInEnabled - 1 + enabledIndexes.length) % enabledIndexes.length];
    else if (e.key === 'Home') nextPos = enabledIndexes[0];
    else if (e.key === 'End') nextPos = enabledIndexes[enabledIndexes.length - 1];
    if (nextPos !== undefined) { e.preventDefault(); tabRefs.current[nextPos]?.focus(); onSelectTab?.(tabs[nextPos].id); }
  }, [tabs, onSelectTab]);
  return (
    <div ref={ref} className={classNames} role="tablist">
      <div className="tab-bar__tabs">
        {tabs.map((tab, index) => (
          <button key={tab.id} type="button" ref={el => { tabRefs.current[index] = el; }} role="tab"
            aria-selected={activeTabId === tab.id} aria-disabled={tab.disabled}
            tabIndex={tab.disabled ? -1 : activeTabId === tab.id ? 0 : -1}
            className={['tab-bar__tab', activeTabId === tab.id ? 'tab-bar__tab--active' : '', tab.disabled ? 'tab-bar__tab--disabled' : ''].filter(Boolean).join(' ')}
            onClick={() => !tab.disabled && onSelectTab?.(tab.id)} onKeyDown={e => handleKeyDown(e, index)}>
            <span className="tab-bar__tab-label">{tab.label}</span>
            {tab.count !== undefined && <Chip form="id-tag">{tab.count}</Chip>}
          </button>
        ))}
      </div>
    </div>
  );
});
TabBar.displayName = 'TabBar';

// ---- FilterDropdown.tsx (simplified interactivity for the prototype) ------
const FilterDropdownContext = cctx(undefined);
const useFilterDropdown = () => uctx(FilterDropdownContext);
const FilterDropdownComponent = f2(({ mode = 'checkbox', children, onChange, className = '', defaultValue, value, placement = 'bottom-start' }, ref) => {
  const [isOpen, setIsOpen] = us2(false);
  const isControlled = value !== undefined;
  const [internalValues, setInternalValues] = us2(new Set(defaultValue ?? []));
  const selectedValues = isControlled ? new Set(value) : internalValues;
  const rootRef = ur2(null);
  React.useEffect(() => {
    if (!isOpen) return;
    const onDoc = (e) => { if (rootRef.current && !rootRef.current.contains(e.target)) setIsOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [isOpen]);
  const onValueChange = (itemValue, selected) => {
    const next = new Set(selectedValues);
    if (selected) { if (mode === 'radio') next.clear(); next.add(itemValue); } else next.delete(itemValue);
    if (!isControlled) setInternalValues(next);
    onChange?.(Array.from(next));
    if (mode === 'radio' && selected) setIsOpen(false);
  };
  const ctx = { isOpen, onOpenChange: setIsOpen, mode, selectedValues, onValueChange, placement };
  return (
    <FilterDropdownContext.Provider value={ctx}>
      <div ref={(node) => { rootRef.current = node; if (typeof ref === 'function') ref(node); else if (ref) ref.current = node; }} className={`filter-dropdown ${className}`.trim()}>{children}</div>
    </FilterDropdownContext.Provider>
  );
});
FilterDropdownComponent.displayName = 'FilterDropdown';
function FilterDropdownTrigger({ label, summary, style }) {
  const { isOpen, onOpenChange, mode } = useFilterDropdown();
  return (
    <button type="button" className="filter-dropdown__trigger" onClick={() => onOpenChange(!isOpen)} aria-haspopup={mode === 'radio' ? 'dialog' : 'listbox'} aria-expanded={isOpen} style={style}>
      <span className="filter-dropdown__label">{label}</span>
      <span className="filter-dropdown__summary">{summary}</span>
      <Icon name="chevronDown" size={14} className={`filter-dropdown__chevron ${isOpen ? 'filter-dropdown__chevron--open' : ''}`} />
    </button>
  );
}
function FilterDropdownPanel({ children, className = '', style }) {
  const { isOpen, mode, placement } = useFilterDropdown();
  return (
    <div className={`dropdown-panel dropdown-panel--placement-${placement} filter-dropdown__panel ${className}`.trim()}
      role={mode === 'checkbox' ? 'listbox' : 'radiogroup'} aria-multiselectable={mode === 'checkbox' ? true : undefined} hidden={!isOpen} style={isOpen ? style : undefined}>
      {children}
    </div>
  );
}
function FilterDropdownSection({ title, children }) {
  return <div className="dropdown-section">{title && <div className="dropdown-section-title">{title}</div>}<div className="filter-dropdown__section-content">{children}</div></div>;
}
function FilterDropdownCheckbox({ value, label, description }) {
  const { selectedValues, onValueChange, mode } = useFilterDropdown();
  const isSelected = selectedValues.has(value);
  return (
    <button type="button" role={mode === 'checkbox' ? 'option' : undefined} aria-selected={isSelected} onClick={() => onValueChange(value, !isSelected)} className="dropdown-item">
      <span className="dropdown-item__leading"><input type="checkbox" className="dropdown-item__checkbox" checked={isSelected} readOnly tabIndex={-1} aria-hidden="true" /></span>
      <span className="dropdown-item__body"><span className="dropdown-item__label">{label}</span>{description && <span className="dropdown-item__description">{description}</span>}</span>
    </button>
  );
}
function FilterDropdownRadio({ value, label, description }) {
  const { selectedValues, onValueChange } = useFilterDropdown();
  const isSelected = selectedValues.has(value);
  return (
    <button type="button" role="radio" aria-checked={isSelected} onClick={() => onValueChange(value, true)} className="dropdown-item">
      <span className="dropdown-item__leading"><input type="radio" className="dropdown-item__radio" checked={isSelected} readOnly tabIndex={-1} aria-hidden="true" /></span>
      <span className="dropdown-item__body"><span className="dropdown-item__label">{label}</span>{description && <span className="dropdown-item__description">{description}</span>}</span>
    </button>
  );
}
const FilterDropdown = Object.assign(FilterDropdownComponent, { Trigger: FilterDropdownTrigger, Panel: FilterDropdownPanel, Section: FilterDropdownSection, Checkbox: FilterDropdownCheckbox, Radio: FilterDropdownRadio });

Object.assign(window, { TextInput, FilterBar, KVGrid, InspectorPanel, SplitPane, ConfigTile, TabBar, FilterDropdown });
