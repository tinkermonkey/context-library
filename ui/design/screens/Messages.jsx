// Messages domain · threaded conversations (Gmail/iMessage hybrid)

function MessagesScreen() {
  return (
    <Shell active="messages" breadcrumbs={['domain', 'messages', 'email · work@studio', 'thread']}>
      <div className="canvas-inner" style={{padding:0, minWidth:0}}>
        <div style={{display:'grid', gridTemplateColumns:'240px 360px 1fr', height:'100%',
                     padding:'14px 14px', gap:14}}>
          {/* Mailboxes / adapters left rail */}
          <div className="panel" style={{display:'flex', flexDirection:'column', overflow:'hidden'}}>
            <div className="panel-head" style={{padding:'10px 12px'}}>
              <div className="panel-title" style={{fontSize:12.5}}>
                <span className="dom-dot messages"></span>Messages · 2,140
              </div>
            </div>

            <div style={{padding:'10px 4px', overflow:'auto', flex:1}}>
              <NavSection label="EMAIL · IMAP" count="1,892">
                <MboxRow label="work@studio" count={428} active/>
                <MboxRow label="personal@me" count={1042}/>
                <MboxRow label="newsletters@me" count={422}/>
              </NavSection>

              <NavSection label="APPLE · iMESSAGE" count="248">
                <MboxRow label="thread:family" count={64}/>
                <MboxRow label="thread:morgan" count={92}/>
                <MboxRow label="thread:dev-cabal" count={88}/>
                <MboxRow label="+ 4 more"/>
              </NavSection>

              <NavSection label="THREADS · ALL" count="312" tail>
                <MboxRow label="all threads" count={312}/>
                <MboxRow label="unread" count={18} pill/>
                <MboxRow label="with replies" count={224}/>
              </NavSection>
            </div>
          </div>

          {/* Thread list */}
          <div className="panel" style={{display:'flex', flexDirection:'column', overflow:'hidden'}}>
            <div className="panel-head" style={{padding:'10px 14px'}}>
              <div className="panel-title" style={{fontSize:13}}>
                <Icon name="globe" size={13}/>
                work@studio
                <span className="version-pill" style={{marginLeft:6}}>v1.0</span>
              </div>
              <div style={{display:'flex', gap:6}}>
                <button className="btn btn-ghost btn-sm" style={{padding:'3px 8px'}}>↻ poll</button>
              </div>
            </div>
            <div style={{padding:'8px 12px', borderBottom:'1px solid var(--canvas-border)'}}>
              <div className="seg" style={{width:'100%', display:'grid', gridTemplateColumns:'1fr 1fr 1fr 1fr'}}>
                <button className="active">threads</button>
                <button>messages</button>
                <button>unread <span className="mono" style={{marginLeft:4, color:'var(--canvas-fg-3)'}}>18</span></button>
                <button>flagged</button>
              </div>
            </div>

            <div style={{overflow:'auto', flex:1}}>
              <Thread selected unread sender="Morgan Cho" subject="graph rag handoff — pipeline arch + open Qs"
                      preview="For the new pipeline, I want to preserve threading when chunking — individual messages stay atomic but reply chains carry as structured context. Then…"
                      when="14 m" count={7} dom="messages"/>
              <Thread sender="Ana Patel" subject="re: chunk-hash collision proposal"
                      preview="Agreed on SHA-256 over the normalized markdown only — context_header lives outside the hash so heading edits don't invalidate."
                      when="2 h" count={4}/>
              <Thread sender="Sam Reyes" subject="reranker latency budget"
                      preview="84ms vector + 12ms rerank is fine for interactive search but the agent loop needs <40ms. Can we cache the cross-encoder?"
                      when="yesterday" count={3}/>
              <Thread unread sender="Daniela Lim" subject="apple bridge — health endpoint flakiness"
                      preview="Workouts have been timing out for 2 days. Confirmed it's not the rate limiter — looks like the helper service crashes on empty windows."
                      when="yesterday" count={2}/>
              <Thread sender="Morgan Cho" subject="dual-storage design — SQLite as source of truth"
                      preview="Liked your phrasing in the doc: 'vector store is an index, not a database'. Adopting that as the principle."
                      when="3 d" count={11}/>
              <Thread sender="Jules Park" subject="re: domain-vs-adapter split"
                      preview="Gmail adapter knows how to fetch; Messages domain knows how to chunk. They don't need to know about each other beyond the mapping."
                      when="3 d" count={6}/>
              <Thread sender="Ana Patel" subject="ChromaDB rebuild plan"
                      preview="Replay lancedb_sync_log on cold start works for me. We should add a sanity check that verifies hash-count parity before serving queries."
                      when="5 d" count={2}/>
              <Thread sender="Sam Reyes" subject="re: phantom diffs from normalizer"
                      preview="Found one: trailing newline on Apple Notes export. Filed the fix as a normalizer v2.1 bump — pinning to that."
                      when="1 w" count={5}/>
              <Thread unread sender="weekly-digest@studio" subject="this week in context-library · 38 ingests, 412 chunks"
                      preview="Active adapters: 11. Sources updated: 38. Chunks created: 412. Chunks retired: 12. Sync log drained 2× during peak."
                      when="1 w" count={1}/>
            </div>
          </div>

          {/* Thread reader */}
          <div className="panel" style={{display:'flex', flexDirection:'column', overflow:'hidden'}}>
            <div className="panel-head" style={{padding:'12px 16px'}}>
              <div style={{flex:1}}>
                <div style={{fontSize:15, fontWeight:600, color:'var(--canvas-fg-1)', letterSpacing:'-0.015em'}}>
                  graph rag handoff — pipeline arch + open Qs
                </div>
                <div style={{display:'flex', gap:10, marginTop:4, alignItems:'center', fontSize:11.5, color:'var(--canvas-fg-3)'}}>
                  <span className="mono">thread_id 3f2a91ce8b14</span>
                  <span style={{color:'var(--canvas-fg-4)'}}>·</span>
                  <span>7 messages</span>
                  <span style={{color:'var(--canvas-fg-4)'}}>·</span>
                  <span>4 participants</span>
                  <span style={{color:'var(--canvas-fg-4)'}}>·</span>
                  <span className="mono">14 chunks → embedded</span>
                </div>
              </div>
              <div style={{display:'flex', gap:6}}>
                <button className="btn btn-ghost btn-sm">view as chunks</button>
                <button className="btn btn-ghost btn-sm">provenance →</button>
              </div>
            </div>

            {/* Provenance strip */}
            <div style={{padding:'10px 16px', background:'var(--canvas-bg-2)',
                         borderBottom:'1px solid var(--canvas-border)',
                         display:'flex', gap:14, alignItems:'center'}}>
              <span className="eyebrow">LINEAGE</span>
              <div className="lineage-rail" style={{flex:1}}>
                <span className="lr-node">email.imap</span>
                <span className="lr-arrow">→</span>
                <span className="lr-node">normalize v1.0</span>
                <span className="lr-arrow">→</span>
                <span className="lr-node">messages.chunker</span>
                <span className="lr-arrow">→</span>
                <span className="lr-node head">14 chunks</span>
                <span className="lr-arrow">→</span>
                <span className="lr-node">chromadb · 384d</span>
              </div>
              <span className="version-pill">v1</span>
            </div>

            {/* Messages */}
            <div style={{overflow:'auto', flex:1, padding:'0 22px 22px'}}>
              <Msg av="M" cls="" who="Morgan Cho" addr="morgan@studio" when="Mon 9:14 AM" hash="3f2a91ce8b14…"
                   text={<>For the new pipeline, I want to <mark style={{background:'rgba(251,191,36,0.20)', padding:'0 2px'}}>preserve threading</mark> when chunking — individual messages stay atomic but reply chains carry as structured context.<br/><br/>Then the retriever can reconstruct conversations at query time. WDYT?</>}/>
              <Msg av="A" cls="av-cyan" who="Ana Patel" addr="ana@studio" when="Mon 9:31 AM" hash="8a14ce0c9d2f…"
                   text={<>+1. We should put <code>thread_id</code> in <code>domain_metadata</code> on each chunk so filters can scope to a thread without rejoining.</>}/>
              <Msg av="S" cls="av-emerald" who="Sam Reyes" addr="sam@studio" when="Mon 10:02 AM" hash="c9d2f8e314a0…"
                   text={<>Quote-stripping question: the current normalizer kills <code>&gt;</code> blocks but keeps "On … wrote:" lines. Do we want both gone? Empty-reply chunks are noise.</>}/>
              <Msg av="M" cls="" who="Morgan Cho" addr="morgan@studio" when="Mon 10:18 AM" hash="d1e22f7a3091…"
                   text={<>Yes — kill both. Filed as <code>normalize.v2.1</code>. Re-ingest will diff against existing hashes so most chunks survive; only the previously noisy ones get retired.</>}/>
              <Msg av="D" cls="av-pink" who="Daniela Lim" addr="daniela@studio" when="Mon 11:44 AM" hash="412a9ce8b1f0…"
                   text={<>Reminder that the iMessage adapter <strong>doesn't</strong> have quoted replies in the same form. The bridge ships clean text already.</>}/>
            </div>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function NavSection({ label, count, children, tail }) {
  return (
    <div style={{marginBottom: tail ? 0 : 8}}>
      <div className="eyebrow" style={{padding:'8px 12px 4px', display:'flex', justifyContent:'space-between'}}>
        <span>{label}</span>
        <span>{count}</span>
      </div>
      <div style={{display:'flex', flexDirection:'column', gap:1, padding:'0 4px'}}>
        {children}
      </div>
    </div>
  );
}

function MboxRow({ label, count, pill, active }) {
  return (
    <div style={{
      display:'flex', alignItems:'center', gap:8,
      padding:'5px 10px', borderRadius:4,
      cursor:'pointer',
      background: active ? 'rgba(251,191,36,0.06)' : 'transparent',
      borderLeft: active ? '2px solid var(--accent-primary)' : '2px solid transparent',
      paddingLeft: active ? 8 : 10,
      fontFamily:'var(--font-mono)', fontSize:11.5,
      color: active ? 'var(--canvas-fg-1)' : 'var(--canvas-fg-2)',
    }}>
      <span style={{flex:1}}>{label}</span>
      {count != null && (
        pill
          ? <span style={{background:'var(--accent-primary)', color:'#29220A', fontWeight:600, padding:'1px 6px', borderRadius:3, fontSize:10}}>{count}</span>
          : <span style={{color:'var(--canvas-fg-3)', fontSize:10.5}}>{count}</span>
      )}
    </div>
  );
}

function Thread({ sender, subject, preview, when, count, unread, selected }) {
  return (
    <div className={'thread-row' + (unread ? ' unread' : '') + (selected ? ' selected' : '')}>
      <div className="pin"></div>
      <div style={{minWidth:0}}>
        <div className="subj">{sender} — <span style={{fontWeight:'inherit', color:'var(--canvas-fg-2)'}}>{subject}</span></div>
        <div className="preview">{preview}</div>
      </div>
      <div className="meta">
        <div className="when">{when}</div>
        <div className="count">{count} msg</div>
      </div>
    </div>
  );
}

function Msg({ av, cls, who, addr, when, hash, text }) {
  return (
    <div className="msg">
      <div className={'av ' + cls}>{av}</div>
      <div className="b">
        <div className="who-row">
          <span className="who">{who}</span>
          <span className="mid">{addr}</span>
          <span className="when" style={{marginLeft:'auto'}}>{when}</span>
        </div>
        <div className="text">{text}</div>
        <div className="footer">
          <span><Icon name="link" size={10} style={{verticalAlign:'middle'}}/> chunk {hash}</span>
          <span>· embedded</span>
          <span>· 0.84 sim to query</span>
        </div>
      </div>
    </div>
  );
}

window.MessagesScreen = MessagesScreen;
