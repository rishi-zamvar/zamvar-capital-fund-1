"""Live per-agent monitor for the warm-playbook extraction fan-out — DB-TRUTH edition.
Progress = REAL kb catalyst nodes in the DB per chunk (ref_id = catalyst_id), NOT transcript strings
(the prior version miscounted instruction text). Live feed = the most recently inserted nodes with
their ticker/label/move read from attrs_json. Read-only. Usage: python scripts/extraction_monitor.py --serve 8813
"""
import json, os, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from catalyst_trader import db as _db

CFG = "/private/tmp/claude-501/-Users-rishizamvar/139e5b38-0e32-487e-95f3-e82f948cbb53/scratchpad/monitor_config.json"
_START = time.time()


def _noded_refids():
    c = _db.connect("catalyst.db"); c.execute("PRAGMA busy_timeout=8000")
    ids = {int(r["ref_id"]) for r in c.execute("SELECT ref_id FROM kb_node WHERE kind='catalyst'") if r["ref_id"] is not None}
    recent = []
    for r in c.execute("SELECT id, attrs_json FROM kb_node WHERE kind='catalyst' ORDER BY id DESC LIMIT 8"):
        try:
            a = json.loads(r["attrs_json"])
            lab = None
            orow = c.execute("SELECT k.attrs_json aj FROM kb_edge e JOIN kb_node k ON k.id=e.dst_id "
                             "WHERE e.src_id=? AND e.rel='RESULTED_IN' LIMIT 1", (r["id"],)).fetchone()
            if orow:
                try: lab = json.loads(orow["aj"]).get("label")
                except Exception: pass
            recent.append({"ticker": a.get("ticker"), "type": a.get("type") or a.get("catalyst_type"),
                           "label": lab or a.get("outcome_label"), "cid": a.get("catalyst_id")})
        except Exception:
            pass
    c.close()
    return ids, recent


def data():
    cfg = json.load(open(CFG))
    noded, recent = _noded_refids()
    now = time.time()
    agents = []
    tot = done = 0
    for a in cfg:
        try:
            cids = [int(x) for x in json.load(open(a["cids"]))]
        except Exception:
            cids = []
        d = len(set(cids) & noded)
        mt = os.path.getmtime(a["out"]) if os.path.exists(a["out"]) else 0
        active = (now - mt) < 90 if mt else False
        agents.append({"wave": a["wave"], "chunk": a["chunk"], "total": len(cids),
                       "done": d, "remaining": len(cids) - d, "active": active})
        tot += len(cids); done += d
    elapsed = now - _START
    rate = done / elapsed if elapsed > 0 else 0
    eta = int((tot - done) / rate) if rate > 0 and tot > done else 0
    return {"agents": agents, "total": tot, "done": done,
            "pct": round(100 * done / tot, 1) if tot else 0,
            "elapsed": int(elapsed), "eta": eta, "recent": recent,
            "waves": sorted({a["wave"] for a in cfg})}


HTML = """<!doctype html><meta charset=utf-8><title>Playbook Extraction</title>
<style>
:root{--bg:#0f1110;--card:#171a17;--card2:#1c201c;--ink:#e9e4d5;--mut:#a09982;--faint:#7d7663;
--line:#2a2e29;--acc:#d4af6a;--pos:#5fbf87;--warn:#d8a94a;--neg:#e0736b;--mono:ui-monospace,Menlo,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px var(--mono)}
.wrap{max-width:1200px;margin:0 auto;padding:22px}
h1{font-size:16px;letter-spacing:.18em;color:var(--acc);margin:0 0 2px}
.sub{color:var(--mut);font-size:12px;margin-bottom:14px}
.bigbar{height:16px;background:var(--card2);border:1px solid var(--line);border-radius:8px;overflow:hidden;margin:8px 0}
.bigbar>i{display:block;height:100%;background:linear-gradient(90deg,var(--acc),var(--pos));width:0;transition:width .5s}
.stat{display:inline-block;margin-right:22px}.stat b{color:var(--acc);font-size:18px}
.cols{display:grid;grid-template-columns:2fr 1fr;gap:18px;margin-top:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:11px 12px}
.card.done{opacity:.6}.card .hd{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.tag{font-size:11px;color:var(--faint)}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px}
.dot.on{background:var(--pos);box-shadow:0 0 6px var(--pos)}.dot.off{background:var(--faint)}
.bar{height:9px;background:var(--card2);border:1px solid var(--line);border-radius:6px;overflow:hidden}
.bar>i{display:block;height:100%;background:var(--acc);width:0;transition:width .5s}
.nums{font-size:11px;color:var(--mut);margin-top:5px}.nums .ins{color:var(--pos)}
.side{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
.side h2{font-size:12px;letter-spacing:.1em;color:var(--acc);margin:0 0 8px}
.ri{font-size:12px;padding:4px 0;border-bottom:1px solid var(--line);color:var(--faint)}
.ri .u{color:var(--ink)}.ri .lab{color:var(--warn)}
</style>
<div class=wrap>
<h1>WARM PLAYBOOK &mdash; LIVE EXTRACTION</h1>
<div class=sub id=sub>connecting&hellip;</div>
<div class=bigbar><i id=big></i></div>
<div><span class=stat><b id=done>0</b> nodes built</span><span class=stat>of <b id=tot>0</b></span>
<span class=stat><b id=pct>0</b>%</span><span class=stat>elapsed <b id=el>0s</b></span>
<span class=stat>eta <b id=eta>&mdash;</b></span></div>
<div class=cols>
 <div><div class=grid id=grid></div></div>
 <div class=side><h2>LATEST NODES</h2><div id=recent></div></div>
</div></div>
<script>
function fmt(s){s=+s;if(!s||!isFinite(s))return'—';let m=Math.floor(s/60),x=s%60;return m?m+'m'+x+'s':x+'s'}
async function tick(){
 let d=await (await fetch('/data')).json();
 sub.textContent='waves: '+d.waves.join(' + ')+' · '+d.agents.length+' agents · DB-truth · '+new Date().toLocaleTimeString();
 done.textContent=d.done;tot.textContent=d.total;pct.textContent=d.pct;el.textContent=fmt(d.elapsed);eta.textContent=fmt(d.eta);
 big.style.width=d.pct+'%';
 grid.innerHTML=d.agents.map(a=>{let dn=a.total>0&&a.remaining==0,p=a.total?Math.round(100*a.done/a.total):0;
  return '<div class="card'+(dn?' done':'')+'"><div class=hd><span><span class="dot '+(a.active?'on':'off')+'"></span>'+a.wave+' #'+a.chunk+'</span><span class=tag>'+a.done+'/'+a.total+'</span></div>'+
   '<div class=bar><i style="width:'+p+'%"></i></div><div class=nums><span class=ins>'+a.done+' built</span> · '+a.remaining+' left</div></div>'}).join('');
 recent.innerHTML=(d.recent||[]).map(r=>'<div class=ri><span class=u>'+(r.ticker||'?')+'</span> '+(r.type||'')+' &rarr; <span class=lab>'+(r.label||'?')+'</span></div>').join('')||'<div class=ri>&hellip;</div>';
}
tick();setInterval(tick,3000);
</script>
"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        try:
            if self.path.startswith("/data"):
                body = json.dumps(data()).encode()
                ct = "application/json"
            else:
                body = HTML.encode(); ct = "text/html"
            self.send_response(200); self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(body))); self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(500); self.end_headers(); self.wfile.write(str(e).encode())


if __name__ == "__main__":
    port = int(sys.argv[sys.argv.index("--serve") + 1]) if "--serve" in sys.argv else 8813
    print(f"extraction monitor (DB-truth) on http://127.0.0.1:{port}", flush=True)
    HTTPServer(("127.0.0.1", port), H).serve_forever()
