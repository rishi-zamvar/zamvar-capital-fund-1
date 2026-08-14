#!/usr/bin/env python3
"""
Live build monitor for the Zamvar Capital — Fund 1 autonomous run.
Stdlib-only (no deps). Streams state over SSE so the browser stays live without refreshing.

  python3 monitor/server.py [port]     # default 8799  ->  http://127.0.0.1:8799

Reads (read-only): git, .planning/*, the phase artifacts, this Claude Code session
transcript, and the active subagent's output — for a live window into this terminal.
"""
import http.server, socketserver, json, subprocess, os, glob, time, threading, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~")
GSD = os.path.join(HOME, ".claude/get-shit-done/bin/gsd-tools.cjs")

# rough per-stage seconds, from measured runs — used only for the phase ETA
STAGE_SECS = {"research": 400, "plan": 700, "plan_check": 230, "revision": 350,
              "executor": 460, "verify": 260, "report": 60}

STATE = {"ok": True}
_last_roadmap = {"t": 0, "v": []}


def run(cmd):
    try:
        return subprocess.check_output(cmd, cwd=ROOT, text=True, stderr=subprocess.DEVNULL, timeout=15).strip()
    except Exception:
        return ""


def git_state():
    log = run(["git", "log", "-12", "--format=%h\x1f%ct\x1f%s"])
    commits = []
    for line in log.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            commits.append({"h": parts[0], "epoch": int(parts[1]), "m": parts[2]})
    count = run(["git", "rev-list", "--count", "HEAD"])
    return {"count": int(count) if count.isdigit() else len(commits),
            "recent": commits,
            "last_epoch": commits[0]["epoch"] if commits else 0}


def roadmap_phases():
    # throttle the node call to every 5s
    now = time.time()
    if now - _last_roadmap["t"] < 5 and _last_roadmap["v"]:
        return _last_roadmap["v"]
    out = run(["node", GSD, "roadmap", "analyze"])
    phases = []
    try:
        d = json.loads(out)
        for p in d.get("phases", []):
            phases.append({"n": p.get("number"), "name": p.get("name"), "status": p.get("disk_status")})
    except Exception:
        pass
    if phases:
        _last_roadmap.update(t=now, v=phases)
    return phases


def current_phase():
    dirs = sorted(glob.glob(os.path.join(ROOT, ".planning/phases/*/")))
    if not dirs:
        return None
    d = dirs[-1]
    def has(suffix):
        return bool(glob.glob(os.path.join(d, f"*-{suffix}.md")))
    plans = glob.glob(os.path.join(d, "*-PLAN.md"))
    summaries = glob.glob(os.path.join(d, "*-SUMMARY.md"))
    stages = [("context", has("CONTEXT")), ("research", has("RESEARCH")),
              ("validation", has("VALIDATION")), ("plan", bool(plans)),
              ("execute", len(summaries) >= len(plans) and len(plans) > 0),
              ("verify", has("VERIFICATION"))]
    # phase start = oldest artifact mtime
    files = glob.glob(os.path.join(d, "*.md"))
    start = min((os.path.getmtime(f) for f in files), default=time.time())
    n_plans = len(plans) or 6
    est = (STAGE_SECS["research"] + STAGE_SECS["plan"] + STAGE_SECS["plan_check"]
           + n_plans * STAGE_SECS["executor"] + STAGE_SECS["verify"])
    elapsed = time.time() - start
    slug = os.path.basename(d.rstrip("/"))
    return {"slug": slug, "stages": stages,
            "plans_total": len(plans), "plans_done": len(summaries),
            "start": start, "elapsed": int(elapsed),
            "est_total": est, "remaining": max(0, int(est - elapsed))}


def tail_events(path, n=14, maxbytes=131072):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > maxbytes:
                f.seek(size - maxbytes)
                f.readline()  # drop partial
            data = f.read().decode("utf-8", "replace")
    except Exception:
        return []
    items = []
    for line in data.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        msg = o.get("message")
        ts = o.get("timestamp") or ""
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            bt = b.get("type")
            if bt == "text":
                t = (b.get("text") or "").strip().replace("\n", " ")
                if t:
                    items.append({"k": "text", "s": t[:160], "ts": ts})
            elif bt == "tool_use":
                name = b.get("name", "?")
                inp = b.get("input", {}) or {}
                hint = inp.get("description") or inp.get("command") or inp.get("file_path") \
                    or inp.get("skill") or inp.get("prompt") or ""
                if isinstance(hint, str):
                    hint = os.path.basename(hint) if inp.get("file_path") else hint
                    hint = hint.replace("\n", " ")[:70]
                items.append({"k": "tool", "s": f"{name}: {hint}", "ts": ts})
    return items[-n:]


def active_agent():
    outs = glob.glob("/private/tmp/claude-501/-Users-rishizamvar/*/tasks/*.output")
    # only agent transcripts (JSONL with parseable events) — skip plain-text bg outputs like this server's
    outs = sorted(outs, key=os.path.getmtime, reverse=True)
    for f in outs[:8]:
        ev = tail_events(f, n=1)
        if ev:
            age = time.time() - os.path.getmtime(f)
            return {"active": age < 25, "age": int(age), "last": ev[-1]["s"]}
    return None


def tokens_total():
    try:
        with open(os.path.join(ROOT, ".planning/TOKEN-NOTES.md")) as f:
            for line in f:
                if "Cumulative" in line:
                    digits = "".join(c for c in line.split(":")[-1] if c.isdigit())
                    if digits:
                        return int(digits)
    except Exception:
        pass
    return 0


def session_jsonl():
    files = glob.glob(os.path.join(HOME, ".claude/projects/-Users-rishizamvar/*.jsonl"))
    return max(files, key=os.path.getmtime) if files else None


def sample():
    g = git_state()
    ph = roadmap_phases()
    cp = current_phase()
    done = sum(1 for p in ph if p["status"] == "complete")
    sess = session_jsonl()
    feed = tail_events(sess, n=14) if sess else []
    return {"ok": True, "now": time.time(), "git": g, "phases": ph,
            "phases_done": done, "phases_total": len(ph) or 11,
            "current": cp, "agent": active_agent(),
            "tokens": tokens_total(), "feed": feed}


def sampler():
    while True:
        try:
            STATE.clear()
            STATE.update(sample())
        except Exception as e:
            STATE.clear()
            STATE.update({"ok": False, "err": str(e)})
        time.sleep(1.5)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/events"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                while True:
                    payload = json.dumps(STATE)
                    self.wfile.write(f"data: {payload}\n\n".encode())
                    self.wfile.flush()
                    time.sleep(1.5)
            except (BrokenPipeError, ConnectionResetError):
                return
        elif self.path.startswith("/state"):
            body = json.dumps(STATE).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        else:
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Fund 1 — Live Monitor</title>
<style>
:root{--bg:#0f1210;--panel:#171b16;--panel2:#1d221b;--ink:#e8ece4;--mut:#9aa192;--faint:#6b7365;
--bd:#2b312a;--gold:#d8b45a;--grn:#4cc585;--red:#ef7365;--blue:#6bb3e6;--vio:#b39cf0;
--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--mono);font-size:13px}
.wrap{max-width:1200px;margin:0 auto;padding:18px 18px 60px}
.top{display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #2b312a;padding-bottom:12px;margin-bottom:16px;flex-wrap:wrap;gap:10px}
h1{font-size:19px;margin:0;letter-spacing:.02em}
.ey{color:var(--gold);font-size:11px;letter-spacing:.18em;text-transform:uppercase}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--grn);margin-right:7px;animation:p 1.5s infinite}
.dot.warn{background:var(--red);animation:none}
@keyframes p{50%{opacity:.4}}
.clk{color:var(--mut);text-align:right;font-size:12px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:840px){.grid{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--bd);border-radius:9px;padding:14px}
.panel h2{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--mut);margin:0 0 10px}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}
@media(max-width:840px){.tiles{grid-template-columns:repeat(2,1fr)}}
.tile{background:var(--panel);border:1px solid var(--bd);border-radius:9px;padding:11px 13px}
.tile .k{color:var(--faint);font-size:10px;letter-spacing:.07em;text-transform:uppercase}
.tile .v{font-size:24px;font-weight:700;margin-top:3px}
.tile .v small{font-size:14px;color:var(--mut)}
.bar{height:9px;background:var(--panel2);border-radius:5px;overflow:hidden;margin-top:8px}
.bar>i{display:block;height:100%;background:var(--gold);width:0}
.phase{display:flex;align-items:center;gap:9px;padding:5px 0;border-bottom:1px solid #21261f}
.phase:last-child{border:none}
.pn{color:var(--faint);width:22px;text-align:right}
.badge{margin-left:auto;font-size:10px;padding:2px 8px;border-radius:12px;border:1px solid}
.b-complete{color:var(--grn);border-color:var(--grn)}
.b-in_progress{color:var(--gold);border-color:var(--gold)}
.b-planned,.b-no_directory{color:var(--faint);border-color:var(--bd)}
.step{display:inline-block;font-size:11px;padding:3px 8px;margin:2px;border-radius:5px;border:1px solid var(--bd);color:var(--mut)}
.step.on{color:var(--grn);border-color:var(--grn)}
#feed{height:340px;overflow-y:auto;background:#0c0f0b;border:1px solid var(--bd);border-radius:7px;padding:10px;font-size:12px;line-height:1.5}
.fi{padding:2px 0;white-space:pre-wrap;word-break:break-word}
.fi.tool{color:var(--blue)} .fi.text{color:var(--ink)}
.fi b{color:var(--gold);font-weight:600}
.agent{font-size:12px;color:var(--mut);margin-bottom:8px}
.agent .run{color:var(--grn)} .agent .idle{color:var(--faint)}
.commit{display:flex;gap:10px;padding:3px 0;font-size:12px;border-bottom:1px solid #21261f}
.commit:last-child{border:none}
.commit .h{color:var(--gold)}
.eta{font-size:12px;color:var(--mut);margin-top:6px}
.eta b{color:var(--ink)}
</style></head><body><div class="wrap">
<div class="top">
  <div><div class="ey">zamvar capital · live build monitor</div><h1>Fund 1 — Autonomous Build</h1></div>
  <div class="clk"><div><span class="dot" id="dot"></span><span id="conn">connecting…</span></div>
  <div id="now" style="margin-top:5px"></div></div>
</div>
<div class="tiles">
  <div class="tile"><div class="k">Phases</div><div class="v"><span id="tph">–</span><small id="tpht">/11</small></div></div>
  <div class="tile"><div class="k">Commits</div><div class="v" id="tc">–</div></div>
  <div class="tile"><div class="k">Tokens</div><div class="v" id="ttok">–</div></div>
  <div class="tile"><div class="k">Last commit</div><div class="v" id="tage" style="font-size:18px">–</div></div>
</div>
<div class="grid">
  <div>
    <div class="panel" style="margin-bottom:14px">
      <h2>Current phase</h2>
      <div id="curname" style="font-weight:700;margin-bottom:8px">–</div>
      <div id="steps"></div>
      <div class="bar"><i id="pbar"></i></div>
      <div class="eta" id="eta"></div>
    </div>
    <div class="panel"><h2>Phase pipeline</h2><div id="phases"></div></div>
  </div>
  <div>
    <div class="panel" style="margin-bottom:14px">
      <h2>Live terminal — this session</h2>
      <div class="agent" id="agent"></div>
      <div id="feed"></div>
    </div>
    <div class="panel"><h2>Recent commits</h2><div id="commits"></div></div>
  </div>
</div></div>
<script>
var esc=function(s){return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;")};
function fmtAge(sec){if(sec<60)return sec+"s";var m=(sec/60)|0;if(m<60)return m+"m "+(sec%60)+"s";return ((m/60)|0)+"h "+(m%60)+"m"}
function fmtEta(sec){if(sec<=0)return "~done";var m=Math.ceil(sec/60);if(m<60)return "~"+m+"m";return "~"+((m/60)|0)+"h "+(m%60)+"m"}
function render(d){
  if(!d||!d.ok){document.getElementById("conn").textContent="waiting…";return}
  document.getElementById("conn").textContent="live";
  var now=Date.now()/1000;
  document.getElementById("now").textContent=new Date().toLocaleTimeString();
  document.getElementById("tph").textContent=d.phases_done;
  document.getElementById("tpht").textContent="/"+d.phases_total;
  document.getElementById("tc").textContent=d.git.count;
  document.getElementById("ttok").textContent=d.tokens?(d.tokens/1e6).toFixed(2)+"M":"–";
  var age=d.git.last_epoch?Math.floor(now-d.git.last_epoch):0;
  var stale=age>900;
  document.getElementById("tage").textContent=fmtAge(age);
  document.getElementById("tage").style.color=stale?"var(--red)":"var(--ink)";
  document.getElementById("dot").className="dot"+(stale?" warn":"");
  // current phase
  var c=d.current;
  if(c){
    document.getElementById("curname").textContent=c.slug+"  ("+c.plans_done+"/"+c.plans_total+" plans)";
    var sh="";c.stages.forEach(function(s){sh+='<span class="step'+(s[1]?" on":"")+'">'+s[0]+(s[1]?" ✓":"")+'</span>'});
    document.getElementById("steps").innerHTML=sh;
    var pct=Math.min(100,Math.round(c.elapsed/c.est_total*100));
    document.getElementById("pbar").style.width=pct+"%";
    document.getElementById("eta").innerHTML="elapsed <b>"+fmtAge(c.elapsed)+"</b> · est remaining <b>"+fmtEta(c.remaining)+"</b> (rough)";
  }
  // agent
  var a=d.agent,ah="";
  if(a){ah=a.active?'<span class="run">● agent running</span> · '+esc(a.last):'<span class="idle">○ no agent active ('+fmtAge(a.age)+' idle)</span>'}
  document.getElementById("agent").innerHTML=ah;
  // phases
  var ph="";(d.phases||[]).forEach(function(p){
    ph+='<div class="phase"><span class="pn">'+p.n+'</span><span>'+esc(p.name)+'</span><span class="badge b-'+p.status+'">'+p.status.replace("_"," ")+'</span></div>'});
  document.getElementById("phases").innerHTML=ph;
  // feed
  var f="";(d.feed||[]).forEach(function(x){
    var s=x.k=="tool"?"🔧 "+esc(x.s):"💬 "+esc(x.s);
    f+='<div class="fi '+x.k+'">'+s+'</div>'});
  var fe=document.getElementById("feed");var atBottom=fe.scrollHeight-fe.scrollTop-fe.clientHeight<40;
  fe.innerHTML=f;if(atBottom)fe.scrollTop=fe.scrollHeight;
  // commits
  var cm="";(d.git.recent||[]).forEach(function(x){cm+='<div class="commit"><span class="h">'+x.h+'</span><span>'+esc(x.m)+'</span></div>'});
  document.getElementById("commits").innerHTML=cm;
}
var es=new EventSource("/events");
es.onmessage=function(e){try{render(JSON.parse(e.data))}catch(x){}};
es.onerror=function(){document.getElementById("conn").textContent="reconnecting…"};
// local clock tick so age feels live between pushes
setInterval(function(){var n=document.getElementById("now");if(n)n.textContent=new Date().toLocaleTimeString()},1000);
</script></body></html>"""


if __name__ == "__main__":
    threading.Thread(target=sampler, daemon=True).start()
    time.sleep(1.0)
    print(f"Fund 1 live monitor → http://127.0.0.1:{PORT}", flush=True)
    Server(("127.0.0.1", PORT), Handler).serve_forever()
