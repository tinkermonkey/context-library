// Messages domain · threaded reader — rebuilt on real heimdall components.
// Real DS: Panel, SegmentedControl, VersionPill, Button, Chip, Icon.
// Reuse: mailbox rail → Sidebar, thread reader → ChatMessage. Shipped in heimdall: LineageRail.

const { useState: useMsgState } = React;

function NavSection({ label, count, children, tail }) {
  return (
    <div style={{ marginBottom: tail ? 0 : 8 }}>
      <div className="eyebrow" style={{ padding: '8px 12px 4px', display: 'flex', justifyContent: 'space-between' }}>
        <span>{label}</span><span>{count}</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1, padding: '0 4px' }}>{children}</div>
    </div>
  );
}
function MboxRow({ label, count, pill, active }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 10px', borderRadius: 4, cursor: 'pointer', background: active ? 'rgba(251,191,36,0.06)' : 'transparent', borderLeft: active ? '2px solid rgb(var(--accent-primary))' : '2px solid transparent', paddingLeft: active ? 8 : 10, fontFamily: 'var(--font-mono)', fontSize: 11.5, color: active ? 'var(--cl-canvas-fg-1)' : 'var(--cl-canvas-fg-2)' }}>
      <span style={{ flex: 1 }}>{label}</span>
      {count != null && (pill
        ? <span style={{ background: 'rgb(var(--accent-primary))', color: '#29220A', fontWeight: 600, padding: '1px 6px', borderRadius: 3, fontSize: 10 }}>{count}</span>
        : <span style={{ color: 'var(--cl-canvas-fg-3)', fontSize: 10.5 }}>{count}</span>)}
    </div>
  );
}
function Thread({ sender, subject, preview, when, count, unread, selected }) {
  return (
    <div className={'thread-row' + (unread ? ' unread' : '') + (selected ? ' selected' : '')}>
      <div className="pin"></div>
      <div style={{ minWidth: 0 }}>
        <div className="subj">{sender} — <span style={{ fontWeight: 'inherit', color: 'var(--cl-canvas-fg-2)' }}>{subject}</span></div>
        <div className="preview">{preview}</div>
      </div>
      <div className="meta"><div className="when">{when}</div><div className="count">{count} msg</div></div>
    </div>
  );
}
function Msg({ av, cls, who, addr, when, hash, text }) {
  return (
    <div className="msg">
      <div className={'av ' + cls}>{av}</div>
      <div className="b">
        <div className="who-row"><span className="who">{who}</span><span className="mid">{addr}</span><span className="when" style={{ marginLeft: 'auto' }}>{when}</span></div>
        <div className="text">{text}</div>
        <div className="footer"><span><Icon name="link" size={10} style={{ verticalAlign: 'middle' }} /> chunk {hash}</span><span>· embedded</span><span>· 0.84 sim to query</span></div>
      </div>
    </div>
  );
}

function MessagesScreen() {
  const [view, setView] = useMsgState('threads');
  return (
    <CLShell active="messages" breadcrumbs={['domain', 'messages', 'email · work@studio', 'thread']}>
      <div className="cl-fill" style={{ display: 'grid', gridTemplateColumns: '240px 360px 1fr', gap: 14 }}>
        {/* Mailboxes rail */}
        <Panel noPadding className="cl-pane"
          title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}><span className="dom-dot messages"></span>Messages · 2,140</span>}
          headerAction={<span className="tbb-flag reuse"><Icon name="send" size={10} /> reuse · Sidebar</span>}>
          <div className="cl-scroll" style={{ padding: '10px 4px' }}>
            <NavSection label="EMAIL · IMAP" count="1,892">
              <MboxRow label="work@studio" count={428} active />
              <MboxRow label="personal@me" count={1042} />
              <MboxRow label="newsletters@me" count={422} />
            </NavSection>
            <NavSection label="APPLE · iMESSAGE" count="248">
              <MboxRow label="thread:family" count={64} />
              <MboxRow label="thread:morgan" count={92} />
              <MboxRow label="thread:dev-cabal" count={88} />
              <MboxRow label="+ 4 more" />
            </NavSection>
            <NavSection label="THREADS · ALL" count="312" tail>
              <MboxRow label="all threads" count={312} />
              <MboxRow label="unread" count={18} pill />
              <MboxRow label="with replies" count={224} />
            </NavSection>
          </div>
        </Panel>

        {/* Thread list */}
        <Panel noPadding className="cl-pane"
          title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13 }}><Icon name="send" size={13} />work@studio<VersionPill>v1.0</VersionPill></span>}
          headerAction={<Button variant="ghost" size="sm">↻ poll</Button>}>
          <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--cl-canvas-border)' }}>
            <SegmentedControl value={view} onChange={setView} options={[{ value: 'threads', label: 'threads' }, { value: 'messages', label: 'messages' }, { value: 'unread', label: 'unread 18' }, { value: 'flagged', label: 'flagged' }]} />
          </div>
          <div className="cl-scroll">
            <Thread selected unread sender="Morgan Cho" subject="graph rag handoff — pipeline arch + open Qs" preview="For the new pipeline, I want to preserve threading when chunking — individual messages stay atomic but reply chains carry as structured context. Then…" when="14 m" count={7} />
            <Thread sender="Ana Patel" subject="re: chunk-hash collision proposal" preview="Agreed on SHA-256 over the normalized markdown only — context_header lives outside the hash so heading edits don't invalidate." when="2 h" count={4} />
            <Thread sender="Sam Reyes" subject="reranker latency budget" preview="84ms vector + 12ms rerank is fine for interactive search but the agent loop needs <40ms. Can we cache the cross-encoder?" when="yesterday" count={3} />
            <Thread unread sender="Daniela Lim" subject="apple bridge — health endpoint flakiness" preview="Workouts have been timing out for 2 days. Confirmed it's not the rate limiter — looks like the helper service crashes on empty windows." when="yesterday" count={2} />
            <Thread sender="Morgan Cho" subject="dual-storage design — SQLite as source of truth" preview="Liked your phrasing in the doc: 'vector store is an index, not a database'. Adopting that as the principle." when="3 d" count={11} />
            <Thread sender="Jules Park" subject="re: domain-vs-adapter split" preview="Gmail adapter knows how to fetch; Messages domain knows how to chunk. They don't need to know about each other beyond the mapping." when="3 d" count={6} />
            <Thread sender="Ana Patel" subject="ChromaDB rebuild plan" preview="Replay lancedb_sync_log on cold start works for me. We should add a sanity check that verifies hash-count parity before serving queries." when="5 d" count={2} />
            <Thread sender="Sam Reyes" subject="re: phantom diffs from normalizer" preview="Found one: trailing newline on Apple Notes export. Filed the fix as a normalizer v2.1 bump — pinning to that." when="1 w" count={5} />
            <Thread unread sender="weekly-digest@studio" subject="this week in context-library · 38 ingests, 412 chunks" preview="Active adapters: 11. Sources updated: 38. Chunks created: 412. Chunks retired: 12. Sync log drained 2× during peak." when="1 w" count={1} />
          </div>
        </Panel>

        {/* Thread reader */}
        <Panel noPadding className="cl-pane"
          title={<div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--cl-canvas-fg-1)', letterSpacing: '-0.015em' }}>graph rag handoff — pipeline arch + open Qs</div>
            <div style={{ display: 'flex', gap: 10, marginTop: 4, alignItems: 'center', fontSize: 11.5, color: 'var(--cl-canvas-fg-3)' }}>
              <span className="mono">thread_id 3f2a91ce8b14</span><span style={{ color: 'var(--cl-canvas-fg-4)' }}>·</span><span>7 messages</span><span style={{ color: 'var(--cl-canvas-fg-4)' }}>·</span><span>4 participants</span><span style={{ color: 'var(--cl-canvas-fg-4)' }}>·</span><span className="mono">14 chunks → embedded</span>
            </div>
          </div>}
          headerAction={<span style={{ display: 'flex', gap: 6 }}><Button variant="ghost" size="sm">view as chunks</Button><Button variant="ghost" size="sm">provenance →</Button></span>}>
          <div style={{ padding: '10px 16px', background: 'var(--cl-canvas-bg-2)', borderBottom: '1px solid var(--cl-canvas-border)', display: 'flex', gap: 14, alignItems: 'center' }}>
            <span className="eyebrow">LINEAGE</span>
            <div className="lineage-rail" style={{ flex: 1 }}>
              <span className="lr-node">email.imap</span><span className="lr-arrow">→</span>
              <span className="lr-node">normalize v1.0</span><span className="lr-arrow">→</span>
              <span className="lr-node">messages.chunker</span><span className="lr-arrow">→</span>
              <span className="lr-node head">14 chunks</span><span className="lr-arrow">→</span>
              <span className="lr-node">chromadb · 384d</span>
            </div>
            <VersionPill>v1</VersionPill>
          </div>
          <div className="cl-scroll" style={{ padding: '0 22px 22px' }}>
            <Msg av="M" cls="" who="Morgan Cho" addr="morgan@studio" when="Mon 9:14 AM" hash="3f2a91ce8b14…" text={<span>For the new pipeline, I want to <mark style={{ background: 'rgba(251,191,36,0.20)', padding: '0 2px' }}>preserve threading</mark> when chunking — individual messages stay atomic but reply chains carry as structured context.<br /><br />Then the retriever can reconstruct conversations at query time. WDYT?</span>} />
            <Msg av="A" cls="av-cyan" who="Ana Patel" addr="ana@studio" when="Mon 9:31 AM" hash="8a14ce0c9d2f…" text={<span>+1. We should put <code>thread_id</code> in <code>domain_metadata</code> on each chunk so filters can scope to a thread without rejoining.</span>} />
            <Msg av="S" cls="av-emerald" who="Sam Reyes" addr="sam@studio" when="Mon 10:02 AM" hash="c9d2f8e314a0…" text={<span>Quote-stripping question: the current normalizer kills <code>&gt;</code> blocks but keeps "On … wrote:" lines. Do we want both gone? Empty-reply chunks are noise.</span>} />
            <Msg av="M" cls="" who="Morgan Cho" addr="morgan@studio" when="Mon 10:18 AM" hash="d1e22f7a3091…" text={<span>Yes — kill both. Filed as <code>normalize.v2.1</code>. Re-ingest will diff against existing hashes so most chunks survive; only the previously noisy ones get retired.</span>} />
            <Msg av="D" cls="av-pink" who="Daniela Lim" addr="daniela@studio" when="Mon 11:44 AM" hash="412a9ce8b1f0…" text={<span>Reminder that the iMessage adapter <strong>doesn't</strong> have quoted replies in the same form. The bridge ships clean text already.</span>} />
          </div>
        </Panel>
      </div>
    </CLShell>
  );
}

window.MessagesScreen = MessagesScreen;
