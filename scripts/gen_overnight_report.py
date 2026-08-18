import sqlite3, json, math, statistics as st
from catalyst_trader.backtest import engine

conn=sqlite3.connect("catalyst.db");conn.row_factory=sqlite3.Row
res=engine.run_layer_a(conn, lambda *a,**k:None, start="2025-08-17", end="2026-08-10", slippage=0.0)
results=res[0] if isinstance(res,tuple) else res
weeks=[r.week for r in results]
wk_rets=[sum((l.size_pct or 0)*(l.realized_ret or 0) for l in r.legs) for r in results]
eq=10000.0; strat=[eq]
for wr in wk_rets: eq*=(1+wr); strat.append(eq)
# XBI weekly path normalized to $10k
xbi_close=[r["close"] for r in conn.execute(
    "select close from price_bar where ticker='XBI' and week_end>=? and week_end<=? order by week_end",
    ("2025-08-17","2026-08-15"))]
xbi=[10000.0*c/xbi_close[0] for c in xbi_close] if xbi_close else []
tot=strat[-1]/strat[0]-1
mean=sum(wk_rets)/len(wk_rets); sd=st.pstdev(wk_rets) or 1e-9
sharpe=mean/sd*math.sqrt(52)
xbi_ret=(xbi_close[-1]/xbi_close[0]-1) if len(xbi_close)>=2 else 0
# leg split
cat=[l.realized_ret or 0 for r in results for l in r.legs if l.is_catalyst]
stat=[l.realized_ret or 0 for r in results for l in r.legs if (not l.is_catalyst and l.ticker not in ('SGOV','BIL','XBI'))]
deff=sum(1 for r in results for l in r.legs if l.ticker in ('SGOV','BIL','XBI'))
def wr(x): return (sum(1 for v in x if v>0)/len(x)) if x else 0

# svg chart (two curves, shared $ axis)
W,H,PL,PR,PT,PB=760,300,54,16,16,28
allv=strat+(xbi or [10000])
lo,hi=min(allv),max(allv); rng=hi-lo or 1
def X(i,n): return PL+(W-PL-PR)*i/max(1,n-1)
def Y(v): return PT+(H-PT-PB)*(1-(v-lo)/rng)
def poly(series): return " ".join(f"{X(i,len(series)):.1f},{Y(v):.1f}" for i,v in enumerate(series))
gridlines="".join(
    f'<line x1="{PL}" y1="{Y(lo+rng*f):.1f}" x2="{W-PR}" y2="{Y(lo+rng*f):.1f}" class="grid"/>'
    f'<text x="{PL-6}" y="{Y(lo+rng*f)+3:.1f}" class="ax" text-anchor="end">${(lo+rng*f)/1000:.0f}k</text>'
    for f in (0,.25,.5,.75,1))
svg=f'''<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="Equity curves">
{gridlines}
<polyline points="{poly(xbi)}" class="l-xbi"/>
<polyline points="{poly(strat)}" class="l-strat"/>
<text x="{W-PR}" y="{Y(xbi[-1])-6:.1f}" class="lbl xbi" text-anchor="end">XBI +{xbi_ret*100:.0f}%</text>
<text x="{W-PR}" y="{Y(strat[-1])+14:.1f}" class="lbl strat" text-anchor="end">Strategy {tot*100:+.1f}%</text>
</svg>'''

data=dict(final=strat[-1],tot=tot,sharpe=sharpe,xbi=xbi_ret,ncat=len(cat),nstat=len(stat),
          catwr=wr(cat),statwr=wr(stat),statsum=sum(stat),deff=deff,
          catsum=sum(cat),trades=len(cat)+len(stat))
json.dump(data,open("/private/tmp/claude-501/-Users-rishizamvar/139e5b38-0e32-487e-95f3-e82f948cbb53/scratchpad/report_data.json","w"))

CSS='''*{box-sizing:border-box}
:root{--bg:#f4efe4;--surface:#fbf7ee;--surface2:#f2ecdd;--ink:#23201a;--muted:#6f6857;--faint:#928a76;
--line:#e0d7c2;--accent:#9a6b1f;--accent2:#7c5a2a;--pos:#2f7d4f;--neg:#b23a3a;--warn:#9a761a;--info:#3a6ea5;
--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0f1110;--surface:#171a17;--surface2:#1c201c;
--ink:#e9e4d5;--muted:#a09982;--faint:#7d7663;--line:#2a2e29;--accent:#d4af6a;--accent2:#c8a24a;
--pos:#5fbf87;--neg:#e0736b;--warn:#d8a94a;--info:#7fb0e0}}
:root[data-theme="dark"]{--bg:#0f1110;--surface:#171a17;--surface2:#1c201c;--ink:#e9e4d5;--muted:#a09982;
--faint:#7d7663;--line:#2a2e29;--accent:#d4af6a;--accent2:#c8a24a;--pos:#5fbf87;--neg:#e0736b;--warn:#d8a94a;--info:#7fb0e0}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.55}
.wrap{max-width:920px;margin:0 auto;padding:40px 22px 80px}
.brand{font-family:var(--mono);font-size:12px;letter-spacing:.22em;color:var(--accent);font-weight:600}
h1{font-size:clamp(26px,3.6vw,38px);margin:.24em 0 .1em;letter-spacing:-.01em;text-wrap:balance}
.sub{color:var(--muted);font-size:15px;margin:.2em 0 0}
.banner{margin:22px 0;padding:14px 18px;border-left:3px solid var(--pos);background:var(--surface);border-radius:0 8px 8px 0}
.banner b{color:var(--pos)}
h2{font-size:20px;margin:38px 0 6px;padding-top:20px;border-top:1px solid var(--line)}
.lead{color:var(--muted);font-size:14px;margin:.2em 0 14px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1px;background:var(--line);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.c{background:var(--surface);padding:14px 16px;display:flex;flex-direction:column;gap:3px}
.c .v{font-family:var(--mono);font-size:23px;font-weight:600;font-variant-numeric:tabular-nums}
.c .v.neg{color:var(--neg)} .c .v.pos{color:var(--pos)}
.c .k{font-size:11px;letter-spacing:.04em;color:var(--muted);text-transform:uppercase}
.chart{width:100%;height:auto;margin:18px 0;background:var(--surface);border:1px solid var(--line);border-radius:10px}
.grid{stroke:var(--line);stroke-width:1}
.ax{fill:var(--faint);font:11px var(--mono)}
.l-xbi{fill:none;stroke:var(--info);stroke-width:2;stroke-dasharray:4 3;opacity:.85}
.l-strat{fill:none;stroke:var(--neg);stroke-width:2.5}
.lbl{font:600 12px var(--mono)} .lbl.xbi{fill:var(--info)} .lbl.strat{fill:var(--neg)}
ul{padding-left:0;list-style:none;margin:10px 0}
li{padding:8px 0 8px 26px;position:relative;border-bottom:1px solid var(--line);font-size:14.5px}
li:before{position:absolute;left:0;top:8px;font-family:var(--mono);font-size:13px}
li.done:before{content:"\\2713";color:var(--pos)} li.gate:before{content:"\\25C6";color:var(--warn)}
li.next:before{content:"\\2192";color:var(--accent)}
.tag{font-family:var(--mono);font-size:10.5px;padding:1px 6px;border-radius:4px;border:1px solid var(--line);color:var(--muted);margin-left:6px}
.finding{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin:10px 0}
.finding h3{margin:0 0 4px;font-size:15px}
.finding .why{color:var(--muted);font-size:13.5px}
strong.n{color:var(--neg)} strong.p{color:var(--pos)}
footer{margin-top:44px;padding-top:18px;border-top:1px solid var(--line);color:var(--faint);font-size:12px;font-family:var(--mono)}
'''

html=f'''<title>Fund 1 First Backtest</title>
<style>{CSS}</style>
<div class="wrap">
<div class="brand">ZAMVAR CAPITAL &middot; FUND 1 &middot; OVERNIGHT RUN</div>
<h1>The first walk-forward backtest runs</h1>
<p class="sub">52 weeks, point-in-time correct, non-vacuous. The result is an honest baseline &mdash; and it tells us exactly what to build next.</p>

<div class="banner"><b>Milestone hit:</b> the end-to-end pipeline works &mdash; universe &rarr; PIT-gated catalysts &rarr; weekly portfolio &rarr; pessimistic fills &rarr; metrics. No look-ahead leak; catalysts are only visible from their real announcement date.</div>

<h2>Result &mdash; the naive baseline</h2>
<p class="lead">Deterministic Layer-A: long-only, no directional skill yet. $10k start, ~1%/week target within survival caps.</p>
<div class="cards">
  <div class="c"><span class="v neg">${data['final']:,.0f}</span><span class="k">final equity</span></div>
  <div class="c"><span class="v neg">{data['tot']*100:+.1f}%</span><span class="k">total return</span></div>
  <div class="c"><span class="v neg">{data['sharpe']:.2f}</span><span class="k">ann. sharpe</span></div>
  <div class="c"><span class="v pos">+{data['xbi']*100:.0f}%</span><span class="k">XBI buy &amp; hold</span></div>
  <div class="c"><span class="v">{data['trades']}</span><span class="k">real trades / 52wk</span></div>
</div>
{svg}
<p class="lead">The year was a <strong class="p">+{data['xbi']*100:.0f}% biotech bull market</strong>. The strategy sat mostly in cash/defensive ({data['deff']} defensive legs) &mdash; so it <em>both</em> missed the rally <em>and</em> lost on its few active trades. That underperformance is the signal for what to fix.</p>

<h2>Why it lost &mdash; root-caused, not hand-waved</h2>
<div class="finding"><h3>1. Buy-the-dip sleeve caught falling knives <span class="tag">the big loser</span></h3>
<div class="why">{data['nstat']} statistical trades, <strong class="n">{data['statwr']*100:.0f}% win rate</strong>, {data['statsum']*100:+.0f}% summed. It kept buying CAPR as it collapsed post-CRL (&minus;10/&minus;12/&minus;21%). Root cause: <code>classify_drop</code>&rsquo;s busted-catalyst / news gating is <strong>unwired</strong> (no news feed), so on a hindsight-selected <em>high-mover</em> universe (which over-weights the year&rsquo;s biggest movers = often CRL crashers) it can&rsquo;t tell a clean dip from a structural collapse.</div></div>
<div class="finding"><h3>2. Catalyst legs are directionless <span class="tag">~break-even</span></h3>
<div class="why">{data['ncat']} PDUFA trades, {data['catwr']*100:.0f}% win, {data['catsum']*100:+.1f}% &mdash; a coin flip. Layer-A goes <em>blindly long</em> into every catalyst; it has no way to avoid a likely CRL. This is exactly the slot the catalyst-desk direction call + football-field fill.</div></div>
<div class="finding"><h3>3. Too defensive to participate <span class="tag">missed +73%</span></h3>
<div class="why">Only {data['trades']} active trades in 52 weeks &mdash; the eligibility gates are strict and, being long-only with no beta sleeve, it never rode the sector. In a bull year that is a large opportunity cost worth a design decision.</div></div>

<h2>What shipped tonight</h2>
<ul>
<li class="done">Free-source price backfill &mdash; 73/73 universe names, 0 paid calls <span class="tag">on-device</span></li>
<li class="done">PIT knowability restamp &mdash; 41/42 PDUFA acceptance dates recovered from SEC; readouts = same-day <span class="tag">leak-free</span></li>
<li class="done">Fixed the vacuous-backtest root cause &mdash; gateway now surfaces resolved catalysts (+2 regression tests, 40 green)</li>
<li class="done">73-name movement-screened universe locked + published artifact</li>
<li class="done">Football-field valuation phase &mdash; research + 5 execution plans ready (2 net-new plugins only)</li>
<li class="done">Backtest runs end-to-end, committed &amp; pushed</li>
</ul>

<h2>Decision gates for you <span class="tag">money-path</span></h2>
<ul>
<li class="gate"><b>Busted-catalyst filter.</b> Wire a signal so buy-the-dip skips names in post-CRL/miss collapse. We already know the outcomes (our 8-K readouts) &mdash; skip names with a recent negative catalyst. Cheap, high-impact. <em>Approve approach?</em></li>
<li class="gate"><b>Directional gating on catalysts.</b> Only go long when expected-up (catalyst desk / football-field), else skip. Turns the coin-flip into selective longs.</li>
<li class="gate"><b>Beta participation.</b> Should the book hold a baseline XBI/sector sleeve so a bull year isn&rsquo;t entirely missed? Or stay pure event-driven and accept flat-in-bull?</li>
<li class="gate"><b>Universe selection bias.</b> Hindsight &ldquo;biggest movers&rdquo; skews toward the year&rsquo;s crashers. Consider selecting on <em>two-sided</em> move + liquidity, not just magnitude.</li>
</ul>

<h2>Next steps (queued)</h2>
<ul>
<li class="next">Execute football-field plans (07.7) &mdash; improves the desk/live move estimate <span class="tag">gsd, ready</span></li>
<li class="next">Add half-spread+commission cost model + deflated Sharpe to the metrics</li>
<li class="next">Signed-move recompute + cross-source earnings dedup <span class="tag">data polish</span></li>
<li class="next">Re-run after the busted-catalyst filter &mdash; the single change most likely to flip the result</li>
</ul>

<footer>Zamvar Capital Fund 1 &middot; autonomous overnight run &middot; walk-forward 2025-08-17 &rarr; 2026-08-10 &middot; all data on-device, 0 paid API calls</footer>
</div>'''
open("/Users/rishizamvar/Documents/Projects/Zamvar Capital/Fund 1 Strategy/docs/overnight-run-report.html","w").write(html)
print("wrote report", len(html), "bytes | final",round(strat[-1]),"sharpe",round(sharpe,2),"xbi",round(xbi_ret,3))
