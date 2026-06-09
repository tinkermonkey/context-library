// Health domain · time-series dashboard — rebuilt on real heimdall components.
// Real DS: PageHeader, FilterDropdown, StatTile, LineChart, ProgressBar,
// Panel, SegmentedControl, KVGrid, VersionPill, Chip, Button, Icon.
// Reuse: per-source breakdown rows → MetricRow (ProgressBar-based).

const { useState: useHealthState } = React;

const RESTING = [62, 60, 61, 59, 62, 64, 61, 60, 58, 57, 59, 60, 62, 61, 60, 58, 58, 57, 59, 60, 61, 60, 58, 57, 58, 59, 58, 57, 58, 58];
const OURA = [61, 60, 60, 59, 61, 62, 61, 60, 59, 58, 59, 60, 61, 60, 59, 58, 58, 58, 59, 59, 60, 59, 58, 58, 58, 58, 58, 57, 58, 57];

function HealthFilter({ label, value, options }) {
  return (
    <FilterDropdown mode="radio" defaultValue={[value]}>
      <FilterDropdown.Trigger label={label} summary={value} />
      <FilterDropdown.Panel><FilterDropdown.Section title={label}>{options.map(o => <FilterDropdown.Radio key={o} value={o} label={o} />)}</FilterDropdown.Section></FilterDropdown.Panel>
    </FilterDropdown>
  );
}

function SourceBar({ name, detail, pct, count, color }) {
  return (
    <div style={{ padding: '7px 0', borderBottom: '1px dashed var(--cl-canvas-border)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--cl-canvas-fg-1)', fontWeight: 500, flex: 1 }}>{name}</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--cl-canvas-fg-3)' }}>{count}</span>
      </div>
      <div style={{ fontSize: 10.5, color: 'var(--cl-canvas-fg-3)', marginBottom: 4 }}>{detail}</div>
      <ProgressBar percent={pct} color={color} height={4} />
    </div>
  );
}

function HealthScreen() {
  const [range, setRange] = useHealthState('30d');
  return (
    <CLShell active="health" breadcrumbs={['domain', 'health', 'oct 2024']}>
      <PageHeader
        title="Health"
        idChip="14,981 windows · 7 metrics"
        subtitle="Adapter-windowed time-series. Apple Health groups heart-rate samples into hourly windows; Oura emits one window per night. Each window becomes one source → one chunk."
        actions={[
          <HealthFilter key="r" label="RANGE" value="oct 2024 · 23 d" options={['oct 2024 · 23 d', 'last 7 days', 'last 90 days', 'this year']} />,
          <HealthFilter key="s" label="SOURCE" value="apple.health, oura" options={['apple.health, oura', 'apple.health', 'oura']} />,
          <Button key="e" variant="ghost"><Icon name="download" size={12} /> Export</Button>,
        ]}
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 14 }}>
        <StatTile label="RESTING HR · BPM" value="58" color="emerald" delta={{ value: 3, direction: 'down', label: 'vs 30d' }} sparkData={[62, 61, 60, 59, 58, 59, 58, 58]} />
        <StatTile label="HRV · MS" value="62" color="cyan" delta={{ value: 8, direction: 'up', label: 'vs 30d' }} sparkData={[54, 56, 55, 58, 60, 59, 61, 62]} />
        <StatTile label="SLEEP · HRS" value="7.4" color="violet" meta="92% efficiency" sparkData={[6.8, 7.1, 7.0, 7.3, 7.2, 7.5, 7.4, 7.4]} />
        <StatTile label="STEPS · DAILY" value="8,412" color="amber" meta="goal 10k" sparkData={[7, 8, 6, 9, 8, 10, 9, 8]} />
        <StatTile label="WORKOUTS · WK" value="4" color="rose" meta="60 min avg" sparkData={[2, 3, 3, 4, 3, 4, 4, 4]} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 14 }}>
        <Panel noPadding
          title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13 }}><Icon name="heart" size={14} />resting heart rate · daily</span>}
          headerAction={<SegmentedControl value={range} onChange={setRange} options={[{ value: '7d', label: '7d' }, { value: '30d', label: '30d' }, { value: '90d', label: '90d' }, { value: '1y', label: '1y' }]} />}
          footer={<div className="row" style={{ gap: 14, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--cl-canvas-fg-3)' }}>
            <span><span style={{ display: 'inline-block', width: 8, height: 8, background: 'var(--cl-status-emerald)', verticalAlign: 'middle', marginRight: 6, borderRadius: 2 }}></span>resting (apple.health)</span>
            <span><span style={{ display: 'inline-block', width: 8, height: 8, background: 'var(--cl-status-cyan)', verticalAlign: 'middle', marginRight: 6, borderRadius: 2 }}></span>oura · daily</span>
            <span style={{ flex: 1 }}></span>
            <span>720 hourly chunks · 24 nightly chunks · 384d</span>
          </div>}>
          <div style={{ padding: '18px 18px 8px' }}>
            <LineChart
              series={[RESTING, OURA]}
              colors={['#10B981', '#22D3EE']}
              xLabels={['oct 1', '', '', '', '', '', 'oct 7', '', '', '', '', '', '', 'oct 14', '', '', '', '', '', '', 'oct 21', '', '', '', '', '', '', '', 'oct 29', '']}
              width={760} height={260} area axes grid tooltip
              threshold={{ value: 60, label: '30d avg' }}
              markers={[{ x: 21, label: 'oct 22' }]}
              style={{ width: '100%', height: 'auto' }}
            />
          </div>
        </Panel>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Panel title="Sources" headerAction={<span className="tbb-flag reuse"><Icon name="component" size={10} /> reuse · MetricRow</span>}>
            <SourceBar name="apple.health" detail="hourly windows · 7 types" pct={68} count="10,224" color="rose" />
            <SourceBar name="oura · sleep" detail="nightly windows · 1 type" pct={18} count="2,706" color="cyan" />
            <SourceBar name="oura · readiness" detail="daily windows · 1 type" pct={12} count="1,803" color="violet" />
            <SourceBar name="apple.health workouts" detail="per-workout · 1 type" pct={2} count="248" color="amber" />
          </Panel>

          <Panel noPadding
            title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}><Icon name="link" size={13} />Window · Oct 22 · 14:00</span>}
            headerAction={<VersionPill>v1</VersionPill>}>
            <div style={{ padding: '12px 14px' }}>
              <div className="eyebrow" style={{ marginBottom: 6 }}>CONTEXT_HEADER</div>
              <div style={{ padding: '8px 10px', background: 'rgba(251,191,36,0.04)', border: '1px solid var(--cl-canvas-border)', borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--cl-canvas-fg-1)', marginBottom: 12 }}>resting_heart_rate — 2024-10-22T14:00:00Z</div>
              <div className="eyebrow" style={{ marginBottom: 6 }}>WINDOW SUMMARY (EMBEDDED)</div>
              <div style={{ padding: '10px 12px', background: 'var(--cl-canvas-bg-2)', border: '1px solid var(--cl-canvas-border)', borderRadius: 'var(--radius-md)', fontSize: 12.5, color: 'var(--cl-canvas-fg-1)', lineHeight: 1.5, marginBottom: 12 }}>
                Resting heart rate during 14:00–15:00: avg 62 bpm (min 58, max 68), 42 samples. Steady reading consistent with afternoon focus block. No elevated periods detected.
              </div>
              <div className="eyebrow" style={{ marginBottom: 2 }}>METRICS</div>
              <KVGrid keyWidth={120} rows={[
                { key: 'SAMPLES', value: <span className="mono">42</span> },
                { key: 'AVG / MIN / MAX', value: <span className="mono">62 / 58 / 68 bpm</span> },
                { key: 'SOURCE', value: <span className="mono" style={{ fontSize: 11.5 }}>apple.health/hrv/2024-10-22T14:00:00Z</span> },
                { key: 'CHUNK_HASH', value: <span className="mono" style={{ fontSize: 11.5 }}>d72ac0148b91…</span> },
              ]} />
            </div>
          </Panel>
        </div>
      </div>
    </CLShell>
  );
}

window.HealthScreen = HealthScreen;
