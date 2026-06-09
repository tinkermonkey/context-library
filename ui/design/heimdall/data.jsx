// =============================================================================
// Heimdall design system — data display + charts (part 1).
// Ported verbatim from @tinkermonkey/heimdall-ui (src/components/*.tsx).
// =============================================================================
const { forwardRef: fw, useId: useId_, useMemo: useMemo_, useState: uS, useRef: uR, useEffect: uE } = React;

// ---- statusColors.ts ------------------------------------------------------
const statusColorMap = {
  emerald: 'rgb(16 185 129)',
  amber: 'rgb(245 158 11)',
  rose: 'rgb(244 63 94)',
  cyan: 'rgb(34 211 238)',
  violet: 'rgb(139 92 246)',
  neutral: 'rgb(var(--canvas-fg-2))',
};

// ---- Sparkline.tsx --------------------------------------------------------
function resolveColor(color) { return color in statusColorMap ? statusColorMap[color] : color; }
function linePath(pts) { return pts.map(([x, y], i) => (i ? 'L' : 'M') + x.toFixed(2) + ',' + y.toFixed(2)).join(' '); }
const Sparkline = fw(({ data, width = 88, height = 28, color = 'emerald', area = true, label, className = '', style, ...rest }, ref) => {
  const gradId = useId_();
  const geometry = useMemo_(() => {
    if (!data || data.length < 2) return null;
    const min = Math.min(...data), max = Math.max(...data);
    const pts = data.map((v, i) => [(i / (data.length - 1)) * width, height - 2 - ((v - min) / (max - min || 1)) * (height - 4)]);
    const line = linePath(pts);
    const fill = `${line} L${width},${height} L0,${height} Z`;
    return { line, fill };
  }, [data, width, height]);
  if (!geometry) return null;
  const c = resolveColor(String(color));
  const { line, fill } = geometry;
  return (
    <svg ref={ref} role="img" aria-label={label ?? 'trend sparkline'} width={width} height={height}
      viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ display: 'block', ...style }} className={className}>
      {area && (<defs><linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={c} stopOpacity="0.22" /><stop offset="100%" stopColor={c} stopOpacity="0" />
      </linearGradient></defs>)}
      {area && <path d={fill} fill={`url(#${gradId})`} />}
      <path d={line} stroke={c} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
});
Sparkline.displayName = 'Sparkline';

// ---- StatTile.tsx ---------------------------------------------------------
const StatTile = fw(({ label = '', value = '', delta, color = 'cyan', icon, sparkData, meta, metaIcon, className = '', 'aria-label': ariaLabel, ...props }, ref) => {
  const classNames = ['stat-tile', `stat-tile--${color}`, className].filter(Boolean).join(' ');
  return (
    <div ref={ref} className={classNames} aria-label={ariaLabel ?? `${label}: ${value}`} style={props.style}>
      <div className="stat-tile__header">
        <div className="stat-tile__label">{label}</div>
        {icon && <Icon name={icon} size={14} aria-hidden="true" />}
      </div>
      <div className="stat-tile__value">{value}</div>
      {(delta || meta) && (
        <div className="stat-tile__footer">
          {delta && (
            <span className={`stat-tile__delta stat-tile__delta--${delta.direction || 'up'}`}>
              <span className="stat-tile__delta-value">{delta.direction === 'down' ? '−' : '+'}{Math.abs(delta.value)}</span>
              {delta.label && <span className="stat-tile__delta-label">{delta.label}</span>}
            </span>
          )}
          {meta && <div className="stat-tile__meta">{metaIcon && <Icon name={metaIcon} size={12} aria-hidden="true" />}<span className="stat-tile__meta-text">{meta}</span></div>}
        </div>
      )}
      {sparkData && <div className="stat-tile__sparkline"><Sparkline data={sparkData} width={88} height={28} color={color || 'cyan'} /></div>}
    </div>
  );
});
StatTile.displayName = 'StatTile';

// ---- StatGrid.tsx ---------------------------------------------------------
const StatGrid = fw(({ columns = 4, className = '', children, ...props }, ref) => {
  const classNames = ['stat-grid', `stat-grid--cols-${columns}`, className].filter(Boolean).join(' ');
  return <div ref={ref} className={classNames} style={props.style}>{children}</div>;
});
StatGrid.displayName = 'StatGrid';

// ---- ProgressBar.tsx ------------------------------------------------------
const ProgressBar = fw(({ percent, color = 'emerald', height = 6, label, className = '', ...rest }, ref) => {
  const clampedPercent = Number.isNaN(percent) ? 0 : Math.min(Math.max(percent, 0), 100);
  return (
    <div ref={ref} className={`progress-bar progress-bar--${color} ${className}`.trim()} style={{ height: `${height}px` }}
      role="progressbar" aria-valuenow={clampedPercent} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <div className="progress-bar__fill" style={{ width: `${clampedPercent}%` }} />
    </div>
  );
});
ProgressBar.displayName = 'ProgressBar';

// ---- MetricRow.tsx --------------------------------------------------------
const MetricRow = fw(({ label, value, unit, percent, sparklineData = [], color = 'emerald', progressLabel, className = '', 'aria-label': ariaLabel, ...rest }, ref) => (
  <div ref={ref} role="row" aria-label={ariaLabel ?? label} className={`metric-row ${className}`.trim()}>
    <div className="metric-row__label">{label}</div>
    <div className="metric-row__progress"><ProgressBar percent={percent} color={color} height={6} label={progressLabel ?? label} /></div>
    <div className="metric-row__sparkline"><Sparkline data={sparklineData} width={60} height={18} color={color} /></div>
    <div className="metric-row__value">{value}{unit && <span className="metric-row__unit">{unit}</span>}</div>
  </div>
));
MetricRow.displayName = 'MetricRow';

// ---- QuickAccessTile.tsx --------------------------------------------------
const QuickAccessTile = fw(({ icon, title, description, className = '', ...props }, ref) => {
  const classNames = ['quick-access-tile', className].filter(Boolean).join(' ');
  return (
    <button ref={ref} type="button" className={classNames} onClick={props.onClick}>
      <div className="quick-access-tile__icon"><Icon name={icon} size={16} /></div>
      <div className="quick-access-tile__body">
        <div className="quick-access-tile__title">{title}</div>
        {description && <div className="quick-access-tile__description">{description}</div>}
      </div>
      <Icon name="chevronRight" size={13} className="quick-access-tile__chev" />
    </button>
  );
});
QuickAccessTile.displayName = 'QuickAccessTile';

// ---- QuickAccessGrid.tsx --------------------------------------------------
const QuickAccessGrid = fw(({ tiles, onAction, columns = 4, className = '', ...props }, ref) => {
  const classNames = ['quick-access-grid', className].filter(Boolean).join(' ');
  return (
    <div ref={ref} className={classNames} style={{ '--qa-columns': columns }}>
      {tiles.map(tile => <QuickAccessTile key={tile.id} icon={tile.icon} title={tile.title} description={tile.description} onClick={() => onAction?.(tile.id)} />)}
    </div>
  );
});
QuickAccessGrid.displayName = 'QuickAccessGrid';

// ---- ActivityTimeline.tsx -------------------------------------------------
const EVENT_COLOR_MAP = { create: 'emerald', update: 'cyan', delete: 'rose', run: 'amber' };
const formatTimestamp = (timestamp) => {
  const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  if (Number.isNaN(diffMs)) return '';
  const diffMins = Math.floor(diffMs / 60000), diffHours = Math.floor(diffMs / 3600000), diffDays = Math.floor(diffMs / 86400000);
  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
};
const ActivityTimeline = fw(({ events = [], emptyState = 'No activity recorded', className = '', ...props }, ref) => {
  const classNames = ['activity-timeline', className].filter(Boolean).join(' ');
  if (events.length === 0) return <div ref={ref} className={classNames}><div className="activity-timeline__empty">{emptyState}</div></div>;
  return (
    <div ref={ref} className={classNames}>
      <div className="activity-timeline__list">
        {events.map(event => (
          <div key={event.id}
            className={['activity-timeline__event', event.onClick ? 'activity-timeline__event--clickable' : ''].filter(Boolean).join(' ')}
            {...(event.kind && { 'data-kind': event.kind })}
            {...(event.onClick && { role: 'button', tabIndex: 0, onClick: () => event.onClick(event), onKeyDown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); event.onClick(event); } } })}>
            <div className="activity-timeline__dot-container">
              {event.dotColor
                ? <div className="activity-timeline__dot--custom" style={{ backgroundColor: statusColorMap[event.dotColor] }} />
                : <Badge color={EVENT_COLOR_MAP[event.type]} className="activity-timeline__dot" />}
            </div>
            <div className="activity-timeline__content">
              <div className="activity-timeline__header">
                {event.kind && <span className="activity-timeline__kind-label">{event.kindLabel || event.kind}</span>}
                <div className="activity-timeline__subject">{event.headline || event.subject}</div>
              </div>
              {event.meta && <div className="activity-timeline__meta">{event.meta}</div>}
            </div>
            <div className="activity-timeline__timestamp">{formatTimestamp(event.timestamp)}</div>
          </div>
        ))}
      </div>
    </div>
  );
});
ActivityTimeline.displayName = 'ActivityTimeline';

// ---- PipelineCard.tsx -----------------------------------------------------
const statusChipColor = { running: 'cyan', success: 'emerald', idle: 'neutral', failed: 'rose' };
const PipelineCard = fw(({ pipeline, onRun, onCancel, onOptions, compact = false, selected = false, headerAction, footerContent, flowLayout = 'fill', className, ...props }, ref) => {
  const statusColor = statusChipColor[pipeline.status];
  return (
    <div ref={ref} className={['pipeline-card', compact && 'pipeline-card--compact', selected && 'pipeline-card--selected', className].filter(Boolean).join(' ')} style={props.style}>
      <div className="pipeline-card__head">
        <div className="pipeline-card__head-top">
          <div className="pipeline-card__title-group">
            <div className="pipeline-card__name-mono">{pipeline.name}</div>
            {pipeline.id && <div className="pipeline-card__id-mono">{pipeline.id}</div>}
          </div>
          <div className="pipeline-card__head-right">
            <div className="pipeline-card__head-chips">
              <Chip variant={statusColor}>{pipeline.status}</Chip>
              {pipeline.target && <Chip variant="neutral">{pipeline.target}</Chip>}
              {pipeline.tags && pipeline.tags.length > 0 && (
                <div className="pipeline-card__tags">{pipeline.tags.map((tag) => <Chip key={tag} variant="neutral">{tag}</Chip>)}</div>
              )}
            </div>
            <div className="pipeline-card__head-actions">
              {headerAction}
              {onRun && pipeline.status !== 'running' && <button type="button" className="pipeline-card__action-btn" onClick={onRun}>Run</button>}
              {onCancel && pipeline.status === 'running' && <button type="button" className="pipeline-card__action-btn pipeline-card__action-btn--cancel" onClick={onCancel}>Cancel</button>}
              {onOptions && <button type="button" aria-label="Pipeline options" className="pipeline-card__kebab-btn" onClick={onOptions}><Icon name="moreVertical" size={16} /></button>}
            </div>
          </div>
        </div>
        {pipeline.description && <p className="pipeline-card__description">{pipeline.description}</p>}
      </div>
      <div className="pipeline-card__flow" data-layout={flowLayout}>
        {pipeline.flow.map((node, index) => ([
          <div key={node.id} className="pipeline-card__node" data-color={node.color}>
            <div className="pipeline-card__icon-tile">{typeof node.icon === 'string' ? <Icon name={node.icon} size={16} /> : node.icon}</div>
            <div className="pipeline-card__node-content">
              <div className="pipeline-card__node-name">{node.name}</div>
              {node.label && <div className="pipeline-card__node-label">{node.label}</div>}
            </div>
          </div>,
          index < pipeline.flow.length - 1 ? <div key={node.id + '-arr'} className="pipeline-card__arrow" /> : null,
        ]))}
      </div>
      <div className="pipeline-card__foot">
        {footerContent ?? (
          <div className="pipeline-card__foot-row">
            <div className="pipeline-card__foot-col"><div className="pipeline-card__foot-label">LAST RUN</div><div className="pipeline-card__foot-value">{pipeline.lastRun || '—'}</div></div>
            <div className="pipeline-card__foot-col"><div className="pipeline-card__foot-label">INGESTED</div><div className="pipeline-card__foot-value">{pipeline.recent.ingested}</div></div>
            <div className="pipeline-card__foot-col"><div className="pipeline-card__foot-label">CREATED</div><div className="pipeline-card__foot-value">{pipeline.recent.created}</div></div>
            <div className="pipeline-card__foot-col"><div className="pipeline-card__foot-label">UPDATED</div><div className="pipeline-card__foot-value">{pipeline.recent.updated}</div></div>
            <div className={['pipeline-card__foot-col', Number(pipeline.recent.errors) > 0 && 'pipeline-card__foot-col--error'].filter(Boolean).join(' ')}><div className="pipeline-card__foot-label">ERRORS</div><div className="pipeline-card__foot-value">{pipeline.recent.errors}</div></div>
          </div>
        )}
      </div>
    </div>
  );
});
PipelineCard.displayName = 'PipelineCard';

// ---- Table.tsx ------------------------------------------------------------
const Table = fw((props, ref) => {
  const { columns, data, rowKey, selectable = false, selectedRows = [], onSelectRows, onRowClick, onSort, emptyState, className = '', ...rest } = props;
  const [sortKey, setSortKey] = uS(null);
  const [sortDirection, setSortDirection] = uS('asc');
  const selectAllRef = uR(null);
  const allSelected = data.length > 0 && selectedRows.length === data.length;
  const someSelected = selectedRows.length > 0 && selectedRows.length < data.length;
  uE(() => { if (selectAllRef.current) selectAllRef.current.indeterminate = someSelected; }, [someSelected]);
  const getRowKey = (row, index) => typeof rowKey === 'function' ? rowKey(row, index) : row[rowKey];
  const handleSelectAll = () => { if (allSelected) onSelectRows?.([]); else onSelectRows?.(data.map((row, idx) => getRowKey(row, idx))); };
  const handleSelectRow = (k) => { if (selectedRows.includes(k)) onSelectRows?.(selectedRows.filter(x => x !== k)); else onSelectRows?.([...selectedRows, k]); };
  const handleSort = (key) => {
    if (sortKey === key) {
      if (sortDirection === 'asc') { setSortDirection('desc'); onSort?.(key, 'desc'); }
      else { setSortKey(null); onSort?.(key, null); }
    } else { setSortKey(key); setSortDirection('asc'); onSort?.(key, 'asc'); }
  };
  const handleSortKeyDown = (e, key) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleSort(key); } };
  const classNames = ['table', className].filter(Boolean).join(' ');
  return (
    <table ref={ref} className={classNames}>
      <thead className="table__head">
        <tr className="table__row">
          {selectable && (
            <th className="table__header table__header--checkbox" style={{ width: '30px' }}>
              <input ref={selectAllRef} type="checkbox" className="table__checkbox" checked={allSelected} onChange={handleSelectAll} aria-label="Select all rows" />
            </th>
          )}
          {columns.map(column => {
            const colKey = String(column.key);
            const isSorted = sortKey === colKey;
            const ariaSortValue = isSorted ? (sortDirection === 'asc' ? 'ascending' : 'descending') : (column.sortable ? 'none' : undefined);
            return (
              <th key={colKey} className={`table__header ${column.sortable ? 'table__header--sortable' : ''}`} style={{ width: column.width }}
                aria-sort={ariaSortValue} tabIndex={column.sortable ? 0 : undefined}
                onClick={() => column.sortable && handleSort(colKey)} onKeyDown={column.sortable ? (e) => handleSortKeyDown(e, colKey) : undefined}>
                <div className="table__header-content">{column.label}{isSorted && <Icon name={sortDirection === 'asc' ? 'chevronUp' : 'chevronDown'} size={14} className="table__sort-icon" />}</div>
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody className="table__body">
        {data.length === 0 && emptyState ? (
          <tr className="table__row"><td className="table__cell table__cell--empty" colSpan={columns.length + (selectable ? 1 : 0)}>{emptyState}</td></tr>
        ) : data.map((row, index) => {
          const rowKeyValue = getRowKey(row, index);
          const isSelected = selectedRows.includes(rowKeyValue);
          const isClickable = !!onRowClick;
          return (
            <tr key={rowKeyValue} data-row-key={rowKeyValue}
              className={['table__row', isSelected ? 'table__row--selected' : '', isClickable ? 'table__row--clickable' : ''].filter(Boolean).join(' ')}
              onClick={isClickable ? () => onRowClick(row, rowKeyValue) : undefined}
              onKeyDown={isClickable ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onRowClick(row, rowKeyValue); } } : undefined}
              tabIndex={isClickable ? 0 : undefined}>
              {selectable && (
                <td className="table__cell table__cell--checkbox">
                  <input type="checkbox" className="table__checkbox" checked={isSelected} aria-label={`Select row ${rowKeyValue}`} onChange={() => handleSelectRow(rowKeyValue)} onClick={(e) => e.stopPropagation()} />
                </td>
              )}
              {columns.map(column => (
                <td key={`${rowKeyValue}-${String(column.key)}`} className="table__cell">
                  {column.render ? column.render(row[column.key], row, index) : row[column.key]}
                </td>
              ))}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
});
Table.displayName = 'Table';

Object.assign(window, { statusColorMap, Sparkline, StatTile, StatGrid, ProgressBar, MetricRow, QuickAccessTile, QuickAccessGrid, ActivityTimeline, PipelineCard, Table });
