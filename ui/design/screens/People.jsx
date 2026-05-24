// People domain — contact directory
// Adapters: vcard, apple.contacts. PeopleMetadata: display_name, organization, job_title, notes.
// Context header: "Contact: {display_name} — {organization}". Sensitive identifiers (emails/phones)
// excluded from embedded content per FR-6.3 — preserved only in domain_metadata.

function PeopleScreen() {
  return (
    <Shell active="people" breadcrumbs={['domain', 'people', 'studio', 'ana patel']}>
      <div className="canvas-inner" style={{padding:'18px 22px 22px', display:'flex', flexDirection:'column', minHeight:0}}>
        <div className="page-head" style={{marginBottom:14}}>
          <div>
            <h1 style={{margin:0}}>
              People <span className="id-tag" style={{marginLeft:10}}>94 contacts</span>
            </h1>
            <div className="subtitle">
              One contact = one chunk. Embedded prose excludes emails and phone numbers; sensitive
              identifiers stay in <span className="mono">domain_metadata</span> only.
            </div>
          </div>
          <div className="page-actions">
            <FDPanel label="ORG" value="studio · 18"/>
            <FDPanel label="TAG" value="all"/>
            <button className="btn"><Icon name="plus" size={13}/> Add contact</button>
          </div>
        </div>

        <div style={{display:'grid', gridTemplateColumns:'180px 1fr 360px', gap:14, flex:1, minHeight:0}}>
          {/* Left: alphabet + orgs */}
          <div className="panel" style={{display:'flex', flexDirection:'column', overflow:'hidden'}}>
            <div className="panel-head" style={{padding:'10px 12px'}}>
              <div className="panel-title" style={{fontSize:12.5}}>Filter</div>
            </div>
            <div style={{padding:'10px 4px', overflow:'auto', flex:1}}>
              <div className="eyebrow" style={{padding:'6px 12px 4px'}}>ALPHABET</div>
              <div style={{padding:'4px 8px', display:'grid', gridTemplateColumns:'repeat(6, 1fr)', gap:2}}>
                {'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('').map(l => (
                  <div key={l} style={{
                    padding:'4px 0', textAlign:'center',
                    fontFamily:'var(--font-mono)', fontSize:10.5,
                    color: 'PCMS'.includes(l) ? 'var(--canvas-fg-1)' : 'var(--canvas-fg-4)',
                    fontWeight: 'P'.includes(l) ? 700 : 400,
                    background: l === 'P' ? 'rgba(251,191,36,0.10)' : 'transparent',
                    borderRadius: 3,
                    cursor:'pointer',
                  }}>{l}</div>
                ))}
              </div>

              <div className="eyebrow" style={{padding:'14px 12px 4px'}}>ORG</div>
              <FacetItem label="studio"        count={18} active dot="#C084FC"/>
              <FacetItem label="acme · sales"  count={6}  dot="#94A3B8"/>
              <FacetItem label="anthropic"     count={4}  dot="#94A3B8"/>
              <FacetItem label="family"        count={12} dot="#F472B6"/>
              <FacetItem label="(no org)"      count={54} dot="#94A3B8"/>

              <div className="eyebrow" style={{padding:'14px 12px 4px'}}>SOURCE</div>
              <FacetItem label="vcard"          count={62} dot="var(--status-emerald)"/>
              <FacetItem label="apple.contacts" count={32} dot="var(--status-cyan)"/>
            </div>
          </div>

          {/* Center: contact grid */}
          <div className="panel" style={{display:'flex', flexDirection:'column', overflow:'hidden'}}>
            <div className="panel-head" style={{padding:'10px 14px'}}>
              <div className="panel-title" style={{fontSize:13}}>
                <span className="dom-dot people"></span>studio · 18 contacts
              </div>
              <div className="seg">
                <button className="active">grid</button>
                <button>list</button>
              </div>
              <div style={{display:'inline-flex', gap:6, padding:'5px 10px',
                            background:'var(--canvas-bg-2)', border:'1px solid var(--canvas-border-strong)',
                            borderRadius:'var(--radius-md)', alignItems:'center'}}>
                <Icon name="search" size={12}/>
                <input style={{border:0, outline:0, background:'transparent', fontSize:12,
                                width:180, color:'var(--canvas-fg-1)'}}
                       placeholder="search by name…" defaultValue=""/>
              </div>
            </div>

            <div style={{padding:14, overflow:'auto', flex:1,
                          display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:10, alignContent:'flex-start'}}>
              <Contact initials="AP" name="Ana Patel" title="staff eng · pipelines" org="studio" src="vcard" selected color="#22D3EE"/>
              <Contact initials="MC" name="Morgan Cho" title="director eng" org="studio" src="vcard" color="#818CF8"/>
              <Contact initials="SR" name="Sam Reyes" title="researcher · retrieval" org="studio" src="apple.contacts" color="#10B981"/>
              <Contact initials="DL" name="Daniela Lim" title="bridge eng · macOS" org="studio" src="vcard" color="#F472B6"/>
              <Contact initials="JP" name="Jules Park" title="product · context" org="studio" src="vcard" color="#FB7185"/>
              <Contact initials="KO" name="Kai Ono" title="researcher · embeddings" org="studio" src="apple.contacts" color="#F59E0B"/>
              <Contact initials="EM" name="Esme Moreau" title="design lead" org="studio" src="vcard" color="#A78BFA"/>
              <Contact initials="TW" name="Theo Walsh" title="data eng" org="studio" src="vcard" color="#22D3EE"/>
              <Contact initials="RL" name="Riley Liang" title="security · platform" org="studio" src="apple.contacts" color="#10B981"/>
              <Contact initials="NF" name="Nadia Fischer" title="ml infra" org="studio" src="vcard" color="#818CF8"/>
              <Contact initials="ZC" name="Zoe Carter" title="staff eng · search" org="studio" src="vcard" color="#FB7185"/>
              <Contact initials="OB" name="Owen Bell" title="recruiter · eng" org="studio" src="vcard" color="#F59E0B"/>
            </div>
          </div>

          {/* Right: contact detail */}
          <div className="panel" style={{display:'flex', flexDirection:'column', overflow:'hidden'}}>
            <div className="panel-head" style={{padding:'10px 12px'}}>
              <div className="panel-title" style={{fontSize:12.5}}><Icon name="shield" size={13}/>Contact</div>
              <span className="version-pill">v2</span>
            </div>

            <div style={{padding:'18px 16px 16px', borderBottom:'1px solid var(--canvas-border)',
                          display:'flex', flexDirection:'column', alignItems:'center', gap:6}}>
              <div style={{width:64, height:64, borderRadius:'50%',
                             background:'linear-gradient(135deg, #22D3EE 0%, #06B6D4 100%)',
                             display:'inline-flex', alignItems:'center', justifyContent:'center',
                             color:'#fff', fontFamily:'var(--font-mono)', fontSize:22, fontWeight:700,
                             marginBottom:6}}>AP</div>
              <div style={{fontSize:16, fontWeight:600, color:'var(--canvas-fg-1)', letterSpacing:'-0.015em'}}>Ana Patel</div>
              <div style={{fontSize:12, color:'var(--canvas-fg-2)'}}>staff engineer · pipelines</div>
              <div style={{fontFamily:'var(--font-mono)', fontSize:11, color:'var(--canvas-fg-3)'}}>studio</div>
            </div>

            <div style={{padding:'14px 16px', overflow:'auto', flex:1}}>
              <div className="eyebrow" style={{marginBottom:6}}>CONTEXT_HEADER</div>
              <div style={{padding:'8px 10px', background:'rgba(251,191,36,0.04)',
                            border:'1px solid var(--canvas-border)', borderRadius:'var(--radius-md)',
                            fontFamily:'var(--font-mono)', fontSize:11.5,
                            color:'var(--canvas-fg-1)', marginBottom:12}}>
                Contact: Ana Patel — studio
              </div>

              <div className="eyebrow" style={{marginBottom:6}}>EMBEDDED PROSE (PUBLIC ONLY)</div>
              <div style={{padding:'10px 12px', background:'var(--canvas-bg-2)',
                            border:'1px solid var(--canvas-border)', borderRadius:'var(--radius-md)',
                            fontSize:12.5, color:'var(--canvas-fg-1)', lineHeight:1.55, marginBottom:14}}>
                Ana Patel is a staff engineer at studio.<br/>
                Notes: pipelines + chunking lead. RAG retrieval domain expert. Currently co-owning
                the diff stage rewrite with morgan.
              </div>

              <div className="eyebrow" style={{marginBottom:6, display:'flex', alignItems:'center', gap:6}}>
                DOMAIN_METADATA · SENSITIVE
                <Icon name="shield" size={11}/>
              </div>
              <div className="kv-dense" style={{padding:'10px 12px',
                                                  background:'rgba(244,63,94,0.04)',
                                                  border:'1px solid rgba(244,63,94,0.20)',
                                                  borderRadius:'var(--radius-md)'}}>
                <div className="k">EMAIL</div>
                <div className="v mono" style={{fontSize:11.5}}>•••••@studio</div>
                <div className="k">PHONE</div>
                <div className="v mono" style={{fontSize:11.5}}>••• ••• ••91</div>
                <div className="k">SOURCE</div>
                <div className="v mono" style={{fontSize:11.5}}>vcard/ana-patel.vcf</div>
                <div className="k">SCOPE</div>
                <div className="v"><span className="chip rose" style={{padding:'1px 6px', fontSize:10}}>not embedded</span></div>
              </div>

              <div className="eyebrow" style={{marginTop:14, marginBottom:6}}>MENTIONS · 47 OCCURRENCES</div>
              <Mention dom="messages" what="email thread · 'graph rag handoff'" when="14m"/>
              <Mention dom="messages" what="email · 'chunk-hash collision proposal'" when="2h"/>
              <Mention dom="notes"    what="daily/2024-10-21.md · '## Pairing'" when="2d"/>
              <Mention dom="tasks"    what="diff stage rewrite (co-owner)" when="5d"/>
              <Mention dom="events"   what="standup · oct 23 14:00" when="2h"/>
            </div>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function Contact({ initials, name, title, org, src, selected, color }) {
  return (
    <div className={'contact-card' + (selected ? ' selected' : '')}>
      <div className="avatar" style={{background:'linear-gradient(135deg, '+color+' 0%, '+darken(color)+' 100%)'}}>
        {initials}
      </div>
      <div className="name">{name}</div>
      <div className="title">{title}</div>
      <div className="org"><span className="dom-dot people"></span> {org}</div>
      <div className="src">via {src}</div>
    </div>
  );
}

function darken(hex) {
  // tiny helper — drop into hsl darker variant
  return hex; // visual gradient handled by base; keep simple
}

function Mention({ dom, what, when }) {
  return (
    <div style={{padding:'6px 10px', margin:'2px 0',
                  background:'var(--canvas-bg-2)',
                  border:'1px solid var(--canvas-border)',
                  borderRadius:'var(--radius-md)',
                  display:'flex', alignItems:'center', gap:8}}>
      <span className={'dom-dot ' + dom}></span>
      <span style={{fontFamily:'var(--font-mono)', fontSize:9.5, color:'var(--canvas-fg-4)',
                     textTransform:'uppercase', letterSpacing:'0.06em', width:64}}>{dom}</span>
      <span style={{fontSize:11.5, color:'var(--canvas-fg-1)', flex:1, overflow:'hidden',
                     textOverflow:'ellipsis', whiteSpace:'nowrap'}}>{what}</span>
      <span style={{fontFamily:'var(--font-mono)', fontSize:10.5, color:'var(--canvas-fg-3)'}}>{when}</span>
    </div>
  );
}

window.PeopleScreen = PeopleScreen;
