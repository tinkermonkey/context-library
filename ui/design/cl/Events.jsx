// Events domain · calendar — rebuilt on real heimdall components.
// Real DS: Panel, SegmentedControl, VersionPill, Chip, Button, KVGrid, Icon.
// Shipped in heimdall: Calendar (month grid), MiniCalendar. Reuse: filters → FilterDropdown.

const { useState: useEvState } = React;

function MiniCal() {
  const days = [];
  days.push({ d: 30, out: true });
  for (let i = 1; i <= 31; i++) days.push({ d: i, out: false });
  for (let i = 1; i <= 3; i++) days.push({ d: i, out: true });
  const hasEvent = new Set([2, 4, 7, 9, 11, 14, 16, 18, 21, 23, 25, 28]);
  const today = 23;
  return (
    <div className="cal-mini">
      {['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((h, i) => <div key={i} className="h">{h}</div>)}
      {days.map((x, i) => <div key={i} className={'d' + (x.out ? ' out' : '') + (!x.out && hasEvent.has(x.d) ? ' has' : '') + (!x.out && x.d === today ? ' today' : '')}>{x.d}</div>)}
    </div>
  );
}
function CalCheck({ name, color, count, muted }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0', opacity: muted ? 0.65 : 1 }}>
      <span style={{ width: 10, height: 10, borderRadius: 2, background: color, border: '1px solid rgba(0,0,0,0.15)' }}></span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--cl-canvas-fg-1)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--cl-canvas-fg-3)' }}>{count}</span>
    </div>
  );
}
function SourceRow2({ name, v, status }) {
  const bg = status === 'ok' ? 'var(--cl-status-emerald)' : status === 'warn' ? 'var(--cl-status-amber)' : 'var(--cl-status-rose)';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: bg }}></span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--cl-canvas-fg-1)', flex: 1 }}>{name}</span>
      <VersionPill>{v}</VersionPill>
    </div>
  );
}
function buildMonthCells() {
  const cells = [];
  cells.push({ day: 30, outside: true });
  for (let d = 1; d <= 31; d++) cells.push({ day: d, outside: false });
  for (let d = 1; d <= 3; d++) cells.push({ day: d, outside: true });
  const eventsByDay = {
    2: [{ t: '09:00', l: 'standup', c: 'cal-event' }, { t: '14:00', l: '1:1 morgan', c: 'cal-personal' }],
    4: [{ t: '08:00', l: 'long run', c: 'cal-gym' }],
    7: [{ t: '10:30', l: 'pipeline review', c: 'cal-event' }, { t: '15:00', l: 'focus · diff', c: 'cal-focus' }],
    9: [{ t: '08:30', l: 'gym · upper', c: 'cal-gym' }, { t: '09:00', l: 'standup', c: 'cal-event' }],
    11: [{ t: '13:00', l: 'design crit', c: 'cal-event' }, { t: '18:00', l: 'family dinner', c: 'cal-personal' }],
    14: [{ t: '10:00', l: 'rag survey readout', c: 'cal-event' }],
    16: [{ t: '08:30', l: 'gym · lower', c: 'cal-gym' }, { t: '14:00', l: 'pairing · ana', c: 'cal-personal' }],
    18: [{ t: '13:00', l: 'focus · normalize', c: 'cal-focus' }],
    21: [{ t: '09:00', l: 'standup', c: 'cal-event' }, { t: '17:00', l: 'gym · upper', c: 'cal-gym' }],
    23: [{ t: '09:00', l: 'standup', c: 'cal-event' }, { t: '14:00', l: 'graph rag handoff', c: 'cal-event selected' }, { t: '16:30', l: 'focus · diff', c: 'cal-focus' }],
    25: [{ t: '10:00', l: 'reranker spike', c: 'cal-event' }, { t: '18:30', l: 'dinner · m+a', c: 'cal-personal' }],
    28: [{ t: '09:00', l: 'standup', c: 'cal-event' }, { t: '13:00', l: 'q4 review', c: 'cal-event' }],
    30: [{ t: '14:00', l: 'oura sync', c: 'cal-gym' }],
  };
  return cells.map((c, i) => (
    <div key={i} className={'cal-cell' + (c.outside ? ' outside' : '') + (c.day === 23 && !c.outside ? ' today' : '')}>
      <span className="day">{c.day}</span>
      {!c.outside && (eventsByDay[c.day] || []).map((ev, j) => (
        <div key={j} className={'cal-event ' + ev.c.replace('cal-event ', '')}>
          <span className="time">{ev.t}</span>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{ev.l}</span>
        </div>
      ))}
    </div>
  ));
}

function EventsScreen() {
  const [view, setView] = useEvState('month');
  return (
    <CLShell active="events" breadcrumbs={['domain', 'events', 'oct 2024', 'graph rag handoff sync']}>
      <div className="cl-fill" style={{ display: 'grid', gridTemplateColumns: '260px 1fr 340px', gap: 14 }}>
        {/* Left: mini cal + filters */}
        <Panel noPadding className="cl-pane"
          title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}><span className="dom-dot events"></span>Events · 986</span>}
          headerAction={<span className="tbb-flag shipped"><Icon name="calendar" size={10} /> heimdall · Calendar</span>}>
          <div className="cl-scroll">
            <div style={{ padding: '12px 12px 4px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <Button variant="ghost" size="sm" icon aria-label="Prev"><Icon name="chevronLeft" size={11} /></Button>
                <span className="mono" style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--cl-canvas-fg-1)' }}>OCTOBER 2024</span>
                <Button variant="ghost" size="sm" icon aria-label="Next"><Icon name="chevronRight" size={11} /></Button>
              </div>
              <MiniCal />
            </div>
            <div style={{ padding: '8px 12px', borderTop: '1px solid var(--cl-canvas-border)' }}>
              <div className="eyebrow" style={{ marginBottom: 8 }}>CALENDARS · 5</div>
              <CalCheck name="work · studio" color="var(--dom-events)" count={42} />
              <CalCheck name="personal" color="var(--dom-messages)" count={28} />
              <CalCheck name="gym · workouts" color="var(--dom-health)" count={18} />
              <CalCheck name="focus blocks" color="var(--dom-notes)" count={12} />
              <CalCheck name="apple.health (derived)" color="var(--dom-health)" count={812} muted />
            </div>
            <div style={{ padding: '10px 12px', borderTop: '1px solid var(--cl-canvas-border)' }}>
              <div className="eyebrow" style={{ marginBottom: 8 }}>SOURCES</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <SourceRow2 name="caldav" v="v1.2" status="ok" />
                <SourceRow2 name="apple.calendar" v="v0.9" status="ok" />
                <SourceRow2 name="apple.health" v="v0.9" status="warn" />
                <SourceRow2 name="apple.music" v="v0.6" status="ok" />
              </div>
            </div>
          </div>
        </Panel>

        {/* Center: calendar grid */}
        <Panel noPadding className="cl-pane"
          title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13 }}><Icon name="calendar" size={14} />October 2024</span>}
          headerAction={<span className="row" style={{ gap: 8 }}><SegmentedControl value={view} onChange={setView} options={[{ value: 'day', label: 'day' }, { value: 'week', label: 'week' }, { value: 'month', label: 'month' }, { value: 'agenda', label: 'agenda' }]} /><Button variant="ghost" size="sm">today</Button></span>}>
          <div className="cl-scroll" style={{ padding: 14 }}>
            <div className="cal-head"><div>MON</div><div>TUE</div><div>WED</div><div>THU</div><div>FRI</div><div>SAT</div><div>SUN</div></div>
            <div className="cal-grid" style={{ borderTop: 0, borderTopLeftRadius: 0, borderTopRightRadius: 0 }}>{buildMonthCells()}</div>
          </div>
        </Panel>

        {/* Right: event detail */}
        <Panel noPadding className="cl-pane"
          title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}><Icon name="file" size={13} />Event</span>}
          headerAction={<VersionPill>v1</VersionPill>}>
          <div className="cl-scroll" style={{ padding: '16px 14px' }}>
            <div className="eyebrow" style={{ marginBottom: 6 }}>WED · 23 OCT</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--cl-canvas-fg-1)', letterSpacing: '-0.01em', marginBottom: 6 }}>Graph RAG handoff sync</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--cl-canvas-fg-3)', marginBottom: 14 }}>14:00 → 14:45 · 45 min · zoom</div>
            <KVGrid keyWidth={92} rows={[
              { key: 'CALENDAR', value: <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: 'var(--dom-events)', verticalAlign: 'middle', marginRight: 6 }}></span>work · studio</span> },
              { key: 'ATTENDEES', value: 'morgan, ana, sam, daniela' },
              { key: 'LOCATION', value: <span className="mono" style={{ fontSize: 11.5 }}>zoom.us/j/8472901138</span> },
              { key: 'SOURCE', value: <span className="mono" style={{ fontSize: 11.5 }}>caldav/cal:work/2024-10-23T14:00:00Z</span> },
            ]} />
            <div className="eyebrow" style={{ margin: '8px 0 6px' }}>CONTEXT_HEADER</div>
            <div style={{ padding: '8px 10px', background: 'rgba(251,191,36,0.04)', border: '1px solid var(--cl-canvas-border)', borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--cl-canvas-fg-1)', marginBottom: 12 }}>Graph RAG handoff sync — 2024-10-23</div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>DESCRIPTION · CHUNK 1 OF 1</div>
            <div style={{ padding: '10px 12px', background: 'var(--cl-canvas-bg-2)', border: '1px solid var(--cl-canvas-border)', borderRadius: 'var(--radius-md)', fontSize: 12.5, color: 'var(--cl-canvas-fg-1)', lineHeight: 1.55, marginBottom: 14 }}>
              Walk through the v3 pipeline arch. Topics:<br />• diff stage rewrite (hash-set ops)<br />• normalizer v2.1 — quote stripping<br />• thread_id in domain_metadata<br />• reranker latency budget<br /><br />Pre-read: heimdall-graph-rag.md v3
            </div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>LINEAGE</div>
            <div className="lineage-rail">
              <span className="lr-node">caldav</span><span className="lr-arrow">→</span>
              <span className="lr-node">events.time_window</span><span className="lr-arrow">→</span>
              <span className="lr-node head">1 chunk</span><span className="lr-arrow">→</span>
              <span className="lr-node">embedded</span>
            </div>
          </div>
        </Panel>
      </div>
    </CLShell>
  );
}

window.EventsScreen = EventsScreen;
