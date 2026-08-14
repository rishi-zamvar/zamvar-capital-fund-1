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


def agent_title(path):
    """Best-effort human label from the subagent's prompt (first user message)."""
    import re
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for _ in range(6):
                line = fh.readline()
                if not line:
                    break
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                msg = o.get("message")
                if isinstance(msg, dict) and msg.get("role") == "user":
                    c = msg.get("content")
                    if isinstance(c, list):
                        txt = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
                    else:
                        txt = c or ""
                    m = re.search(r"(Execute plan \S+|Research .*?Phase \d+|Plan Phase \d+|Revise .*?plans|Verify [^\n]{0,40}|Synthesize [^\n]{0,40})", txt)
                    if m:
                        return m.group(1).strip()[:72]
                    for l in txt.splitlines():
                        if l.strip():
                            return l.strip()[:72]
    except Exception:
        pass
    return ""


def active_agent():
    outs = glob.glob("/private/tmp/claude-501/-Users-rishizamvar/*/tasks/*.output")
    # only agent transcripts (JSONL with parseable events) — skip plain-text bg outputs like this server's
    outs = sorted(outs, key=os.path.getmtime, reverse=True)
    for f in outs[:8]:
        ev = tail_events(f, n=16)
        if ev:
            mt = os.path.getmtime(f)
            age = time.time() - mt
            return {"active": age < 25, "age": int(age), "mtime": mt,
                    "last": ev[-1]["s"], "feed": ev, "title": agent_title(f)}
    return None


def tokens_total():
    import re
    try:
        with open(os.path.join(ROOT, ".planning/TOKEN-NOTES.md")) as f:
            for line in f:
                if "Cumulative" in line:
                    m = re.search(r"([\d][\d,]{3,})", line.split(":")[-1])  # first number after the colon
                    if m:
                        return int(m.group(1).replace(",", ""))
    except Exception:
        pass
    return 0


def graphify_savings():
    """Estimate tokens saved by Graphify using executor-level tokens as the proxy.

    Baseline = Phase 1 executors (Graphify was NOT live). Post = Phase 2+ executors (Graphify live).
    Executors are where codebase-reading happens, so their per-plan token delta is the most
    Graphify-attributable signal. Honest label: an estimate, not a controlled measurement.
    """
    import re
    path = os.path.join(ROOT, ".planning/TOKEN-NOTES.md")
    base, post = [], []
    try:
        with open(path) as f:
            for line in f:
                m = re.search(r"Executor\s+(\d+)-\d+\s*\|\s*\**\s*([\d,]+)", line)
                if m:
                    phase = m.group(1)
                    tok = int(m.group(2).replace(",", ""))
                    (base if phase == "01" else post).append(tok)
    except Exception:
        return None
    if not base or not post:
        return None
    base_avg = sum(base) / len(base)
    post_avg = sum(post) / len(post)
    saved = int(sum(max(0, base_avg - t) for t in post))
    pct = int(round((1 - post_avg / base_avg) * 100)) if base_avg else 0
    return {"base_avg": int(base_avg), "post_avg": int(post_avg),
            "saved": saved, "pct": pct, "n_post": len(post)}


def session_jsonl():
    files = glob.glob(os.path.join(HOME, ".claude/projects/-Users-rishizamvar/*.jsonl"))
    return max(files, key=os.path.getmtime) if files else None


def _phase_dir(num):
    try:
        padded = f"{int(float(num)):02d}"
    except Exception:
        padded = str(num)
    hits = glob.glob(os.path.join(ROOT, f".planning/phases/{padded}-*/"))
    return hits[0] if hits else None


def _est_total(n_plans):
    # research + plan + plan_check + verify + revision buffer + plans*executor
    return 1590 + 350 + max(1, n_plans) * STAGE_SECS["executor"]


def phase_eta(p):
    d = _phase_dir(p["n"])
    st = p["status"]
    mt, plans = [], 5
    if d:
        md = glob.glob(os.path.join(d, "*.md"))
        mt = [os.path.getmtime(f) for f in md]
        plans = len(glob.glob(os.path.join(d, "*-PLAN.md"))) or 5
    if st == "complete" and mt:
        return {"kind": "done", "secs": int(max(mt) - min(mt))}
    if st == "in_progress" and mt:
        elapsed = time.time() - min(mt)
        return {"kind": "running", "secs": max(0, int(_est_total(plans) - elapsed)), "elapsed": int(elapsed)}
    return {"kind": "est", "secs": _est_total(plans)}


def sample():
    g = git_state()
    ph = roadmap_phases()
    for p in ph:
        try:
            p["eta"] = phase_eta(p)
        except Exception:
            p["eta"] = {"kind": "est", "secs": 0}
    cp = current_phase()
    done = sum(1 for p in ph if p["status"] == "complete")
    sess = session_jsonl()
    feed = tail_events(sess, n=14) if sess else []
    return {"ok": True, "now": time.time(), "git": g, "phases": ph,
            "phases_done": done, "phases_total": len(ph) or 11,
            "current": cp, "agent": active_agent(),
            "tokens": tokens_total(), "graphify": graphify_savings(), "feed": feed}


def sampler():
    global STATE
    while True:
        try:
            STATE = sample()  # atomic pointer swap — no partial-state race for readers
        except Exception as e:
            STATE = {"ok": False, "err": str(e)}
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
#subfeed{height:300px;overflow-y:auto;background:#0c0f0b;border:1px solid var(--bd);border-radius:7px;padding:10px;font-size:12px;line-height:1.5}
#feed{height:200px;overflow-y:auto;background:#0c0f0b;border:1px solid var(--bd);border-radius:7px;padding:10px;font-size:12px;line-height:1.5}
.fi{padding:2px 0;white-space:pre-wrap;word-break:break-word}
.fi.tool{color:var(--blue)} .fi.text{color:var(--ink)}
.ts{color:var(--faint);font-size:11px}
.petastr{color:var(--faint);font-size:11px}
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
  <div id="now" style="margin-top:5px"></div>
  <div id="lastact" style="margin-top:2px"></div>
  <div id="lastcommit"></div></div>
</div>
<div class="tiles">
  <div class="tile"><div class="k">Phases</div><div class="v"><span id="tph">–</span><small id="tpht">/11</small></div></div>
  <div class="tile"><div class="k">Commits</div><div class="v" id="tc">–</div></div>
  <div class="tile"><div class="k">Tokens</div><div class="v" id="ttok">–</div></div>
  <div class="tile"><div class="k">Graphify saved (est.)</div><div class="v" id="gsaved" style="color:var(--grn)">–</div></div>
  <div class="tile"><div class="k">Last commit</div><div class="v" id="tage" style="font-size:18px">–</div></div>
</div>
<div id="gdetail" style="font-family:var(--mono);font-size:11.5px;color:var(--faint);margin:-6px 0 16px"></div>
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
      <h2>Active subagent — what it's doing now</h2>
      <div class="agent" id="agent"></div>
      <div id="subfeed"></div>
    </div>
    <div class="panel" style="margin-bottom:14px">
      <h2>Orchestrator — this session</h2>
      <div id="feed"></div>
    </div>
    <div class="panel"><h2>Recent commits</h2><div id="commits"></div></div>
  </div>
</div></div>
<script>
var esc=function(s){return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;")};
function fmtAge(sec){if(sec<60)return sec+"s";var m=(sec/60)|0;if(m<60)return m+"m "+(sec%60)+"s";return ((m/60)|0)+"h "+(m%60)+"m"}
function fmtEta(sec){if(sec<=0)return "~done";var m=Math.ceil(sec/60);if(m<60)return "~"+m+"m";return "~"+((m/60)|0)+"h "+(m%60)+"m"}
function fmtDur(sec){var m=Math.round(sec/60);if(m<60)return m+"m";return ((m/60)|0)+"h "+(m%60)+"m"}
function hhmmss(ts){if(!ts)return "";var dt=new Date(ts);return isNaN(dt)?"":dt.toLocaleTimeString([], {hour12:false})}
function phaseEta(e){if(!e)return "";if(e.kind=="done")return "took "+fmtDur(e.secs);if(e.kind=="running")return fmtEta(e.secs)+" left";return "est "+fmtDur(e.secs)}
function render(d){
  if(!d||!d.ok){document.getElementById("conn").textContent="waiting…";return}
  document.getElementById("conn").textContent="live";
  var now=Date.now()/1000;
  document.getElementById("now").textContent=new Date().toLocaleTimeString();
  document.getElementById("tph").textContent=d.phases_done;
  document.getElementById("tpht").textContent="/"+d.phases_total;
  document.getElementById("tc").textContent=d.git.count;
  document.getElementById("ttok").textContent=d.tokens?(d.tokens/1e6).toFixed(2)+"M":"–";
  var gs=d.graphify;
  if(gs){
    document.getElementById("gsaved").textContent="~"+Math.round(gs.saved/1000)+"k";
    document.getElementById("gdetail").textContent="graphify est: executors "+Math.round(gs.base_avg/1000)+"k (pre) → "+Math.round(gs.post_avg/1000)+"k (live) avg per plan · −"+gs.pct+"% over "+gs.n_post+" plans (executor-proxy estimate)";
  } else {
    document.getElementById("gsaved").textContent="–";
    document.getElementById("gdetail").textContent="graphify savings measured once Phase 2+ executors complete (baseline = Phase 1 executors)";
  }
  var age=d.git.last_epoch?Math.floor(now-d.git.last_epoch):0;
  var stale=age>900;
  document.getElementById("tage").textContent=fmtAge(age);
  document.getElementById("tage").style.color=stale?"var(--red)":"var(--ink)";
  // absolute timestamps
  var a=d.agent||{};
  var lastAct=Math.max(d.git.last_epoch||0, a.mtime||0);
  document.getElementById("lastcommit").textContent="last commit "+(d.git.last_epoch?new Date(d.git.last_epoch*1000).toLocaleTimeString([],{hour12:false})+" ("+fmtAge(age)+" ago)":"–");
  var actAge=lastAct?Math.floor(now-lastAct):age;
  document.getElementById("lastact").textContent="last activity "+(lastAct?new Date(lastAct*1000).toLocaleTimeString([],{hour12:false})+" ("+fmtAge(actAge)+" ago)":"–");
  // smarter stall signal: agent actively writing = working (even between commits)
  var working=a.active, warn=!working && actAge>600;
  document.getElementById("dot").className="dot"+(warn?" warn":"");
  document.getElementById("conn").textContent=working?"agent working":(warn?"idle "+fmtAge(actAge)+" — check for stall":"live");
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
  // active subagent — title + status + its own live feed
  var ag=d.agent||{};
  var ah="";
  if(ag.title)ah='<b>'+esc(ag.title)+'</b> · ';
  ah+=ag.active?'<span class="run">● working ('+fmtAge(ag.age||0)+')</span>':(ag.feed?'<span class="idle">○ idle '+fmtAge(ag.age||0)+' (last subagent)</span>':'<span class="idle">○ no subagent</span>');
  document.getElementById("agent").innerHTML=ah;
  var sf="";(ag.feed||[]).forEach(function(x){var t=hhmmss(x.ts);var tp=t?'<span class="ts">'+t+'</span> ':'';var s=x.k=="tool"?"🔧 "+esc(x.s):"💬 "+esc(x.s);sf+='<div class="fi '+x.k+'">'+tp+s+'</div>'});
  if(!sf)sf='<div class="fi" style="color:var(--faint)">no active subagent</div>';
  var sfe=document.getElementById("subfeed");var atB=sfe.scrollHeight-sfe.scrollTop-sfe.clientHeight<40;sfe.innerHTML=sf;if(atB)sfe.scrollTop=sfe.scrollHeight;
  // phases
  var ph="";(d.phases||[]).forEach(function(p){
    var eta=phaseEta(p.eta);
    ph+='<div class="phase"><span class="pn">'+p.n+'</span><span>'+esc(p.name)+
        '<span class="petastr"> · '+eta+'</span></span>'+
        '<span class="badge b-'+p.status+'">'+p.status.replace("_"," ")+'</span></div>'});
  document.getElementById("phases").innerHTML=ph;
  // feed (with timestamps)
  var f="";(d.feed||[]).forEach(function(x){
    var t=hhmmss(x.ts);var tp=t?'<span class="ts">'+t+'</span> ':'';
    var s=x.k=="tool"?"🔧 "+esc(x.s):"💬 "+esc(x.s);
    f+='<div class="fi '+x.k+'">'+tp+s+'</div>'});
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
