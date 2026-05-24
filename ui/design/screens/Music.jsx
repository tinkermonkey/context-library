// Music domain — listening history + top tiles
// Adapters: apple.music, apple.music_library, apple.podcasts.
// Adapter routes each play through documents/events with album, play_count, duration_minutes, genre.

function MusicScreen() {
  return (
    <Shell active="music" breadcrumbs={['domain', 'music', 'oct 2024']}>
      <div className="canvas-inner" style={{padding:'18px 22px 22px', display:'flex', flexDirection:'column', minHeight:0}}>
        <div className="page-head" style={{marginBottom:14}}>
          <div>
            <h1 style={{margin:0}}>
              Music <span className="id-tag" style={{marginLeft:10}}>3,402 listens · 312 albums</span>
            </h1>
            <div className="subtitle">
              Listening history from Apple Music + library imports. Each play batches into a daily
              chunk; the library catalog is a separate set of evergreen sources for album metadata.
            </div>
          </div>
          <div className="page-actions">
            <FDPanel label="RANGE" value="oct 2024"/>
            <FDPanel label="SOURCE" value="apple.music · library"/>
          </div>
        </div>

        <div style={{display:'grid', gridTemplateColumns:'1fr 360px', gap:14, flex:1, minHeight:0}}>
          <div style={{display:'flex', flexDirection:'column', gap:14, minHeight:0}}>
            {/* Top albums strip */}
            <div className="panel">
              <div className="panel-head" style={{padding:'10px 14px'}}>
                <div className="panel-title" style={{fontSize:13}}><Icon name="zap" size={13}/>Top albums · 30d</div>
                <span className="eyebrow">BY PLAY COUNT</span>
              </div>
              <div style={{padding:'14px 16px', display:'grid', gridTemplateColumns:'repeat(7, 1fr)', gap:10}}>
                <Album cover={['#F472B6','#EC4899']}  glyph="LP" name="Long Player"    artist="Slow Pulp"      plays={184}/>
                <Album cover={['#22D3EE','#0891B2']}  glyph="MR" name="Mirror"          artist="Porches"        plays={132}/>
                <Album cover={['#10B981','#047857']}  glyph="HC" name="Honeysuckle"     artist="Andy Shauf"     plays={118}/>
                <Album cover={['#818CF8','#4F46E5']}  glyph="NV" name="Nova"            artist="Burial"         plays={96}/>
                <Album cover={['#F59E0B','#D97706']}  glyph="SP" name="Stillpoint"      artist="Khruangbin"     plays={84}/>
                <Album cover={['#FB7185','#BE123C']}  glyph="GD" name="Garden"          artist="Adrianne Lenker" plays={78}/>
                <Album cover={['#A78BFA','#6D28D9']}  glyph="OF" name="Open Field"      artist="Floating Points" plays={72}/>
              </div>
            </div>

            {/* Daily listening chart */}
            <div className="panel" style={{flex:1, minHeight:0, display:'flex', flexDirection:'column'}}>
              <div className="panel-head" style={{padding:'10px 14px'}}>
                <div className="panel-title" style={{fontSize:13}}>
                  <Icon name="brain" size={14}/>daily listening · oct 2024
                </div>
                <div className="seg">
                  <button>minutes</button>
                  <button className="active">tracks</button>
                  <button>by genre</button>
                </div>
                <span className="eyebrow">23 DAYS · 1,128 PLAYS</span>
              </div>

              <div style={{flex:1, padding:'14px 18px 6px', minHeight:0}}>
                <DailyChart/>
              </div>

              <div style={{padding:'10px 16px', borderTop:'1px solid var(--canvas-border)',
                            background:'var(--canvas-bg-2)',
                            display:'flex', gap:14, alignItems:'center',
                            fontFamily:'var(--font-mono)', fontSize:11}}>
                <Legend color="#F472B6"  name="indie"/>
                <Legend color="#22D3EE"  name="electronic"/>
                <Legend color="#10B981"  name="jazz"/>
                <Legend color="#818CF8"  name="ambient"/>
                <Legend color="#F59E0B"  name="podcast"/>
                <span style={{flex:1}}></span>
                <span style={{color:'var(--canvas-fg-3)'}}>oct 22 · 62 tracks · 4h 12m</span>
              </div>
            </div>
          </div>

          {/* Right: now-playing + recent + selected day */}
          <div style={{display:'flex', flexDirection:'column', gap:14, minHeight:0}}>
            {/* Now playing */}
            <div className="panel">
              <div className="panel-head" style={{padding:'10px 12px'}}>
                <div className="panel-title" style={{fontSize:12.5}}>
                  <span className="pulse cyan sm"></span>
                  Now playing
                </div>
                <span className="eyebrow">apple.music</span>
              </div>
              <div style={{padding:'14px 14px', display:'flex', gap:12, alignItems:'center'}}>
                <div style={{width:48, height:48, borderRadius:6,
                               background:'linear-gradient(135deg, #F472B6, #EC4899)',
                               display:'inline-flex', alignItems:'center', justifyContent:'center',
                               color:'#fff', fontFamily:'var(--font-mono)', fontSize:14, fontWeight:700}}>
                  LP
                </div>
                <div style={{flex:1, minWidth:0}}>
                  <div style={{fontSize:13, fontWeight:600, color:'var(--canvas-fg-1)',
                                 overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>Slow Wave</div>
                  <div style={{fontSize:11.5, color:'var(--canvas-fg-3)',
                                 overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>Slow Pulp · Long Player</div>
                </div>
              </div>
              <div style={{padding:'0 14px 12px'}}>
                <div style={{height:3, background:'var(--canvas-bg-2)', borderRadius:2, overflow:'hidden'}}>
                  <div style={{height:'100%', width:'34%', background:'var(--accent-primary)'}}></div>
                </div>
                <div style={{display:'flex', justifyContent:'space-between',
                               fontFamily:'var(--font-mono)', fontSize:10, color:'var(--canvas-fg-3)',
                               marginTop:5}}>
                  <span>1:18</span>
                  <span>3:42</span>
                </div>
              </div>
            </div>

            {/* Selected day */}
            <div className="panel" style={{flex:1, minHeight:0, display:'flex', flexDirection:'column', overflow:'hidden'}}>
              <div className="panel-head" style={{padding:'10px 12px'}}>
                <div className="panel-title" style={{fontSize:12.5}}><Icon name="history" size={13}/>oct 22 · 62 plays</div>
                <span className="version-pill">v1</span>
              </div>

              <div style={{padding:'10px 14px 0', borderBottom:'1px solid var(--canvas-border)'}}>
                <div className="eyebrow" style={{marginBottom:6}}>CONTEXT_HEADER</div>
                <div style={{padding:'7px 10px', background:'rgba(251,191,36,0.04)',
                              border:'1px solid var(--canvas-border)', borderRadius:'var(--radius-md)',
                              fontFamily:'var(--font-mono)', fontSize:11, color:'var(--canvas-fg-1)',
                              marginBottom:10}}>
                  Music — 2024-10-22 (62 plays · 4h 12m)
                </div>
              </div>

              <div style={{overflow:'auto', flex:1}}>
                <Track t="07:14" title="Open Field" artist="Floating Points"     dur="6:08" genre="ambient"   first/>
                <Track t="07:21" title="Shimmer"    artist="Floating Points"     dur="4:42" genre="ambient"/>
                <Track t="07:26" title="Nova · alt" artist="Burial"              dur="5:18" genre="electronic"/>
                <Track t="07:32" title="Slow Wave"  artist="Slow Pulp"           dur="3:42" genre="indie" highlight/>
                <Track t="07:36" title="Mirror"     artist="Porches"             dur="3:54" genre="indie"/>
                <Track t="07:40" title="Honeysuckle" artist="Andy Shauf"         dur="4:12" genre="indie"/>
                <Track t="07:44" title="Stillpoint" artist="Khruangbin"          dur="5:02" genre="jazz"/>
                <Track t="09:01" title="(focus block · 2h 17m)" artist="—"        dur="—"   meta/>
                <Track t="11:18" title="Garden"     artist="Adrianne Lenker"     dur="4:48" genre="indie"/>
                <Track t="11:24" title="Long Player · side A" artist="Slow Pulp" dur="22:14" genre="indie" album/>
                <Track t="13:42" title="Mirror"     artist="Porches"             dur="3:54" genre="indie"/>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function Album({ cover, glyph, name, artist, plays }) {
  return (
    <div className="album-tile">
      <div className="cover" style={{background:`linear-gradient(135deg, ${cover[0]} 0%, ${cover[1]} 100%)`}}>
        <span className="glyph">{glyph}</span>
      </div>
      <div className="meta">
        <div className="n">{name}</div>
        <div className="a">{artist}</div>
        <div className="plays">{plays} plays</div>
      </div>
    </div>
  );
}

function Legend({ color, name }) {
  return (
    <span style={{color:'var(--canvas-fg-3)'}}>
      <span style={{display:'inline-block', width:8, height:8, background:color, verticalAlign:'middle',
                     marginRight:5, borderRadius:2}}></span>
      {name}
    </span>
  );
}

function DailyChart() {
  // 23 daily bars, stacked by genre
  const days = Array.from({length: 23}, (_, i) => i + 1);
  // synthetic stacked bars: [indie, electronic, jazz, ambient, podcast]
  const seed = [
    [12, 8, 4, 6, 2],   // 1
    [14, 6, 6, 4, 0],
    [10, 10, 2, 8, 4],
    [16, 4, 8, 6, 2],
    [8, 12, 4, 10, 0],
    [14, 6, 8, 4, 2],
    [18, 8, 6, 4, 4],
    [12, 14, 4, 8, 0],
    [10, 8, 12, 6, 2],
    [16, 6, 6, 8, 0],
    [8, 10, 4, 10, 4],
    [14, 8, 8, 4, 2],
    [20, 6, 4, 6, 0],
    [12, 12, 6, 4, 4],
    [10, 8, 10, 6, 2],
    [16, 6, 4, 8, 0],
    [12, 14, 8, 4, 2],
    [8, 8, 6, 10, 4],
    [14, 10, 6, 6, 0],
    [18, 8, 4, 8, 2],
    [20, 6, 8, 4, 0],
    [26, 14, 8, 12, 2],  // 22 — selected
    [10, 8, 4, 6, 4],
  ];
  const colors = ['#F472B6', '#22D3EE', '#10B981', '#818CF8', '#F59E0B'];
  const W = 720, H = 200;
  const padL = 28, padR = 8, padT = 8, padB = 22;
  const cw = W - padL - padR, ch = H - padT - padB;
  const max = 64; // tracks
  const bw = cw / days.length * 0.7;
  const bGap = cw / days.length * 0.3;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{width:'100%', height:'100%', display:'block'}} preserveAspectRatio="none">
      {/* y gridlines */}
      {[0, 20, 40, 60].map(t => {
        const y = padT + ch - (t / max) * ch;
        return (
          <g key={t}>
            <line x1={padL} y1={y} x2={padL + cw} y2={y}
                  stroke="var(--canvas-border)" strokeDasharray="2 4"/>
            <text x={padL - 6} y={y + 3} textAnchor="end" fontSize="9.5"
                  fontFamily="var(--font-mono)" fill="var(--canvas-fg-3)">{t}</text>
          </g>
        );
      })}
      {/* bars */}
      {days.map((d, i) => {
        const x = padL + i * (bw + bGap) + bGap/2;
        let y = padT + ch;
        const stacks = seed[i];
        const total = stacks.reduce((a, b) => a + b, 0);
        const isSelected = d === 22;
        return (
          <g key={d}>
            {stacks.map((v, j) => {
              const h = (v / max) * ch;
              y -= h;
              return (
                <rect key={j} x={x} y={y} width={bw} height={h}
                      fill={colors[j]}
                      opacity={isSelected ? 1 : 0.85}
                      stroke={isSelected && j === 0 ? 'var(--accent-primary)' : 'none'}
                      strokeWidth={isSelected ? 0 : 0}
                />
              );
            })}
            {isSelected && (
              <rect x={x - 1} y={padT + ch - (total / max) * ch - 1}
                    width={bw + 2} height={(total / max) * ch + 2}
                    fill="none" stroke="var(--accent-primary)" strokeWidth="1.5"/>
            )}
            {(d % 4 === 1 || d === 22) && (
              <text x={x + bw/2} y={H - 6} textAnchor="middle" fontSize="9.5"
                    fontFamily="var(--font-mono)"
                    fill={isSelected ? 'var(--canvas-fg-1)' : 'var(--canvas-fg-3)'}
                    fontWeight={isSelected ? 600 : 400}>{d}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

function Track({ t, title, artist, dur, genre, first, highlight, album, meta }) {
  const genreColor = { indie:'#F472B6', electronic:'#22D3EE', jazz:'#10B981', ambient:'#818CF8', podcast:'#F59E0B' }[genre];
  return (
    <div style={{
      padding:'8px 14px',
      borderBottom:'1px solid var(--canvas-border)',
      display:'grid', gridTemplateColumns:'42px 1fr auto', gap:10, alignItems:'center',
      background: highlight ? 'rgba(251,191,36,0.05)' : 'transparent',
      borderLeft: highlight ? '2px solid var(--accent-primary)' : '2px solid transparent',
      paddingLeft: highlight ? 12 : 14,
    }}>
      <span style={{fontFamily:'var(--font-mono)', fontSize:10.5, color:'var(--canvas-fg-3)'}}>{t}</span>
      <div style={{minWidth:0}}>
        <div style={{fontSize: meta ? 11.5 : 12.5, fontWeight: meta ? 400 : 500,
                       color: meta ? 'var(--canvas-fg-3)' : 'var(--canvas-fg-1)',
                       fontStyle: meta ? 'italic' : 'normal',
                       overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>
          {album && <span style={{color:'var(--canvas-fg-3)', marginRight:6, fontFamily:'var(--font-mono)', fontSize:9.5}}>ALBUM</span>}
          {title}
        </div>
        {!meta && (
          <div style={{fontSize:11, color:'var(--canvas-fg-3)',
                         overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>
            {artist}
          </div>
        )}
      </div>
      {!meta && (
        <div style={{display:'flex', flexDirection:'column', alignItems:'flex-end', gap:2}}>
          <span style={{fontFamily:'var(--font-mono)', fontSize:10.5, color:'var(--canvas-fg-3)'}}>{dur}</span>
          {genre && (
            <span style={{fontFamily:'var(--font-mono)', fontSize:9.5,
                           padding:'1px 5px', borderRadius:2,
                           background: 'rgba(0,0,0,0.04)',
                           border:'1px solid ' + (genreColor || 'var(--canvas-border)'),
                           color: genreColor}}>{genre}</span>
          )}
        </div>
      )}
    </div>
  );
}

window.MusicScreen = MusicScreen;
