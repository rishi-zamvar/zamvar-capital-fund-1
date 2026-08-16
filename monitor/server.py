#!/usr/bin/env python3
"""
Live build monitor for the Zamvar Capital — Fund 1 autonomous run.
Stdlib-only (no deps). Streams state over SSE so the browser stays live without refreshing.

  python3 monitor/server.py [port]     # default 8799  ->  http://127.0.0.1:8799

Reads (read-only): git, .planning/*, phase artifacts, the research corpus, phase reports,
this Claude Code session transcript, and the active subagent's output.

Two writable control files let the desk surface things to the operator without them
opening Claude Code:
  .monitor/blocker.json  — {active,title,detail,options,since}  a hard decision blocker
  .monitor/review.json   — {items:[{ts,phase,title,note,kind}]} a soft "evaluate later" log
POST /action/focus-terminal brings the running iTerm/Terminal window to the front.
POST /action/ack-blocker clears the current blocker banner.
"""
import http.server, socketserver, json, subprocess, os, glob, time, threading, sys, re

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~")
GSD = os.path.join(HOME, ".claude/get-shit-done/bin/gsd-tools.cjs")
MONDIR = os.path.join(ROOT, ".monitor")
os.makedirs(MONDIR, exist_ok=True)

# rough per-stage seconds, from measured runs — used only for the phase ETA
STAGE_SECS = {"research": 400, "plan": 700, "plan_check": 230, "revision": 350,
              "executor": 460, "verify": 260, "report": 60}

STATE = {"ok": True}
_cache = {"roadmap": {"t": 0, "v": []}, "decisions": {"t": 0, "v": []},
          "research": {"t": 0, "v": []}, "deliverables": {"t": 0, "v": []}}


def run(cmd):
    try:
        return subprocess.check_output(cmd, cwd=ROOT, text=True, stderr=subprocess.DEVNULL, timeout=15).strip()
    except Exception:
        return ""


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# ------------------------------------------------------------------ git / phases

def git_state():
    log = run(["git", "log", "-14", "--format=%h\x1f%ct\x1f%s"])
    commits = []
    for line in log.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            commits.append({"h": parts[0], "epoch": int(parts[1]), "m": parts[2]})
    count = run(["git", "rev-list", "--count", "HEAD"])
    return {"count": int(count) if count.isdigit() else len(commits),
            "recent": commits, "last_epoch": commits[0]["epoch"] if commits else 0}


def roadmap_phases():
    now = time.time()
    if now - _cache["roadmap"]["t"] < 5 and _cache["roadmap"]["v"]:
        return _cache["roadmap"]["v"]
    out = run(["node", GSD, "roadmap", "analyze"])
    phases = []
    try:
        d = json.loads(out)
        for p in d.get("phases", []):
            phases.append({"n": p.get("number"), "name": p.get("name"), "status": p.get("disk_status")})
    except Exception:
        pass
    if phases:
        _cache["roadmap"].update(t=now, v=phases)
    return phases or _cache["roadmap"]["v"]


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
    files = glob.glob(os.path.join(d, "*.md"))
    start = min((os.path.getmtime(f) for f in files), default=time.time())
    n_plans = len(plans) or 6
    est = (STAGE_SECS["research"] + STAGE_SECS["plan"] + STAGE_SECS["plan_check"]
           + n_plans * STAGE_SECS["executor"] + STAGE_SECS["verify"])
    elapsed = time.time() - start
    return {"slug": os.path.basename(d.rstrip("/")), "stages": stages,
            "plans_total": len(plans), "plans_done": len(summaries),
            "start": start, "elapsed": int(elapsed),
            "est_total": est, "remaining": max(0, int(est - elapsed))}


def _phase_dir(num):
    try:
        padded = f"{int(float(num)):02d}"
    except Exception:
        padded = str(num)
    hits = glob.glob(os.path.join(ROOT, f".planning/phases/{padded}-*/"))
    return hits[0] if hits else None


def _est_total(n_plans):
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


# ------------------------------------------------------------------ live feeds

def tail_events(path, n=14, maxbytes=131072):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > maxbytes:
                f.seek(size - maxbytes)
                f.readline()
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
                    items.append({"k": "text", "s": t[:200], "ts": ts})
            elif bt == "tool_use":
                name = b.get("name", "?")
                inp = b.get("input", {}) or {}
                hint = inp.get("description") or inp.get("command") or inp.get("file_path") \
                    or inp.get("skill") or inp.get("prompt") or ""
                if isinstance(hint, str):
                    hint = os.path.basename(hint) if inp.get("file_path") else hint
                    hint = hint.replace("\n", " ")[:80]
                items.append({"k": "tool", "s": f"{name}: {hint}", "ts": ts})
    return items[-n:]


def agent_title(path):
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
    outs = sorted(outs, key=os.path.getmtime, reverse=True)
    for f in outs[:8]:
        ev = tail_events(f, n=16)
        if ev:
            mt = os.path.getmtime(f)
            age = time.time() - mt
            return {"active": age < 25, "age": int(age), "mtime": mt,
                    "last": ev[-1]["s"], "feed": ev, "title": agent_title(f)}
    return None


def session_jsonl():
    files = glob.glob(os.path.join(HOME, ".claude/projects/-Users-rishizamvar/*.jsonl"))
    return max(files, key=os.path.getmtime) if files else None


# ------------------------------------------------------------------ tokens / graphify

def tokens_total():
    # keep the LAST cumulative line (the ledger appends one per phase; latest wins)
    total = 0
    try:
        with open(os.path.join(ROOT, ".planning/TOKEN-NOTES.md")) as f:
            for line in f:
                if "Cumulative" in line:
                    m = re.search(r"([\d][\d,]{3,})", line.split(":")[-1])
                    if m:
                        total = int(m.group(1).replace(",", ""))
    except Exception:
        pass
    return total


def graphify_savings():
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


# ------------------------------------------------------------------ decisions / research / deliverables

def decisions():
    """LOCKED decisions across phase CONTEXT files + PROJECT.md key decisions."""
    now = time.time()
    if now - _cache["decisions"]["t"] < 20 and _cache["decisions"]["v"]:
        return _cache["decisions"]["v"]
    out = []
    for ctx in sorted(glob.glob(os.path.join(ROOT, ".planning/phases/*/*-CONTEXT.md"))):
        ph = os.path.basename(os.path.dirname(ctx)).split("-")[0]
        try:
            txt = open(ctx, encoding="utf-8").read()
        except Exception:
            continue
        for m in re.finditer(r"###\s*LOCKED[^\n]*?—\s*([^\n(]+)", txt):
            title = m.group(1).strip().rstrip(":")
            out.append({"phase": ph, "title": title[:90]})
    # de-dup, keep last ~12
    seen, uniq = set(), []
    for d in out:
        k = (d["phase"], d["title"])
        if k not in seen:
            seen.add(k); uniq.append(d)
    uniq = uniq[-14:]
    if uniq:
        _cache["decisions"].update(t=now, v=uniq)
    return uniq or _cache["decisions"]["v"]


def research_docs():
    now = time.time()
    if now - _cache["research"]["t"] < 30 and _cache["research"]["v"]:
        return _cache["research"]["v"]
    out = []
    for md in sorted(glob.glob(os.path.join(ROOT, ".planning/research/*.md"))):
        name = os.path.basename(md)
        # skip the settled project-scaffolding docs; surface the investigative ones
        title, summary = name.replace(".md", ""), ""
        try:
            with open(md, encoding="utf-8") as f:
                head = f.read(4000)
            hm = re.search(r"^#\s+(.+)$", head, re.M)
            if hm:
                title = hm.group(1).strip()[:80]
            for line in head.splitlines():
                s = line.strip()
                if s and not s.startswith("#") and not s.startswith(">") and len(s) > 30:
                    summary = re.sub(r"[*_`]", "", s)[:150]
                    break
        except Exception:
            pass
        out.append({"file": name, "title": title, "summary": summary,
                    "mtime": os.path.getmtime(md)})
    out.sort(key=lambda x: x["mtime"], reverse=True)
    if out:
        _cache["research"].update(t=now, v=out)
    return out or _cache["research"]["v"]


def deliverables():
    now = time.time()
    if now - _cache["deliverables"]["t"] < 30 and _cache["deliverables"]["v"]:
        return _cache["deliverables"]["v"]
    out = []
    for html in sorted(glob.glob(os.path.join(ROOT, "docs/**/*.html"), recursive=True)):
        rel = os.path.relpath(html, ROOT)
        title = os.path.basename(html).replace(".html", "").replace("-", " ")
        try:
            head = open(html, encoding="utf-8").read(2000)
            tm = re.search(r"<title>(.+?)</title>", head, re.I | re.S)
            if tm:
                title = tm.group(1).strip()[:70]
        except Exception:
            pass
        out.append({"file": rel, "title": title, "mtime": os.path.getmtime(html)})
    out.sort(key=lambda x: x["mtime"], reverse=True)
    if out:
        _cache["deliverables"].update(t=now, v=out)
    return out or _cache["deliverables"]["v"]


def roadmap_scope():
    """Parse ROADMAP.md '### Phase N:' detail blocks → goal + success criteria (for the Roadmap tab)."""
    now = time.time()
    c = _cache.setdefault("scope", {"t": 0, "v": []})
    if now - c["t"] < 30 and c["v"]:
        return c["v"]
    path = os.path.join(ROOT, ".planning/ROADMAP.md")
    out = []
    try:
        txt = open(path, encoding="utf-8").read()
    except Exception:
        return c["v"]
    blocks = re.split(r"^### Phase ", txt, flags=re.M)[1:]
    for b in blocks:
        head = b.splitlines()[0].strip()
        m = re.match(r"([\d.]+):\s*(.+)", head)
        if not m:
            continue
        num, name = m.group(1), re.sub(r"\s*\(added[^)]*\)", "", m.group(2)).strip()
        goal = ""
        gm = re.search(r"\*\*Goal\*\*:\s*(.+)", b)
        if gm:
            goal = gm.group(1).strip()
        crits = re.findall(r"^\s*\d+\.\s+(.+)$", b, flags=re.M)
        reqs = ""
        rm = re.search(r"\*\*Requirements\*\*:\s*(.+)", b)
        if rm:
            reqs = rm.group(1).strip()
        deferred = "BUILD DEFERRED" in b or "build deferred" in b
        out.append({"n": num, "name": name, "goal": goal[:300],
                    "crits": [c2[:220] for c2 in crits[:6]], "reqs": reqs[:120],
                    "deferred": deferred})
    if out:
        c.update(t=now, v=out)
    return out or c["v"]


def blocker():
    b = read_json(os.path.join(MONDIR, "blocker.json"), {})
    return b if b.get("active") else None


def review_items():
    r = read_json(os.path.join(MONDIR, "review.json"), {"items": []})
    items = r.get("items", [])
    return items[-20:]


# ------------------------------------------------------------------ data health (PIPE-07)

COVERAGE_ALERT_PCT = 80.0   # cross-check coverage below this -> alert
DIVERGENCE_ALERT = 5        # this many cross-check divergences in one cycle -> alert
_last_alert_sig = [None]    # de-dupe: only ping when the alert set CHANGES


def _ping_alerts(alerts):
    """Best-effort ZeeChat push (non-blocking, de-duped). NEVER blocks or crashes the monitor —
    a failing/absent ping script is silently ignored."""
    sig = "|".join(sorted(alerts))
    if sig == _last_alert_sig[0]:
        return
    _last_alert_sig[0] = sig
    try:
        subprocess.Popen(
            ["bash", os.path.expanduser("~/.claude/skills/zeechat/scripts/ping.sh"),
             "Fund1 data-health: " + "; ".join(alerts)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def data_health():
    """The pipeline-health snapshot the daemon writes each cycle (.monitor/data_health.json) plus a
    computed `alerts` list: a degraded source / a coverage drop / a divergence spike. Empty {} when
    the daemon has not written a cycle yet (never a crash)."""
    dh = read_json(os.path.join(MONDIR, "data_health.json"), {})
    if not dh:
        return {}
    alerts = []
    for name, s in (dh.get("sources") or {}).items():
        if s.get("degraded"):
            alerts.append("source degraded: " + name)
    cov = dh.get("coverage_pct")
    if cov is not None and cov < COVERAGE_ALERT_PCT:
        alerts.append("coverage %.0f%% (< %.0f%%)" % (cov, COVERAGE_ALERT_PCT))
    div = dh.get("divergences_this_cycle") or 0
    if div >= DIVERGENCE_ALERT:
        alerts.append("divergence spike: %d this cycle" % div)
    dh["alerts"] = alerts
    if alerts:
        _ping_alerts(alerts)
    return dh


# ------------------------------------------------------------------ sample loop

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
    feed = tail_events(sess, n=16) if sess else []
    return {"ok": True, "now": time.time(), "git": g, "phases": ph,
            "phases_done": done, "phases_total": len(ph) or 11,
            "current": cp, "agent": active_agent(),
            "tokens": tokens_total(), "graphify": graphify_savings(), "feed": feed,
            "decisions": decisions(), "research": research_docs(),
            "deliverables": deliverables(), "blocker": blocker(),
            "review": review_items(), "scope": roadmap_scope(),
            "data_health": data_health()}


def sampler():
    global STATE
    while True:
        try:
            STATE = sample()
        except Exception as e:
            STATE = {"ok": False, "err": str(e)}
        time.sleep(1.5)


# ------------------------------------------------------------------ actions

def focus_terminal():
    """Bring the terminal running this session to the front. Try iTerm2, iTerm, Terminal."""
    for app in ("iTerm2", "iTerm", "Terminal"):
        rc = subprocess.run(["osascript", "-e", f'tell application "{app}" to activate'],
                            capture_output=True, text=True)
        if rc.returncode == 0:
            return {"ok": True, "app": app}
    return {"ok": False, "err": "no terminal app responded"}


def ack_blocker():
    path = os.path.join(MONDIR, "blocker.json")
    b = read_json(path, {})
    b["active"] = False
    b["acked_at"] = time.time()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(b, f)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "err": str(e)}


# ------------------------------------------------------------------ http

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path.startswith("/action/focus-terminal"):
            self._json(focus_terminal())
        elif self.path.startswith("/action/ack-blocker"):
            self._json(ack_blocker())
        else:
            self._json({"ok": False, "err": "unknown action"}, 404)

    def do_GET(self):
        if self.path.startswith("/events"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                while True:
                    self.wfile.write(f"data: {json.dumps(STATE)}\n\n".encode())
                    self.wfile.flush()
                    time.sleep(1.5)
            except (BrokenPipeError, ConnectionResetError):
                return
        elif self.path.startswith("/state"):
            self._json(STATE)
        elif self.path.startswith("/report/"):
            # serve a phase report / deliverable html read-only
            rel = self.path[len("/report/"):].split("?")[0]
            safe = os.path.normpath(os.path.join(ROOT, rel))
            if safe.startswith(os.path.join(ROOT, "docs")) and os.path.isfile(safe):
                try:
                    body = open(safe, "rb").read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(body)
                except Exception:
                    self.send_error(500)
            else:
                self.send_error(404)
        else:
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fund 1 — Live Desk Monitor</title>
<style>
:root{
  --bg:#0e110d;--bg2:#0b0e0a;--panel:#161a14;--panel2:#1d221b;--card:#191e17;
  --ink:#eef1ea;--mut:#9aa192;--faint:#6b7365;--bd:#2a302690;--bds:#39413480;
  --gold:#d8b45a;--gold2:#f0cf82;--grn:#54cf8d;--red:#f0776a;--blue:#74b8ea;--vio:#b7a2f2;--amber:#e6b455;
  --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 26px rgba(0,0,0,.32);
}
*{box-sizing:border-box}
html,body{margin:0}
body{background:
  radial-gradient(1100px 500px at 78% -8%,rgba(216,180,90,.06),transparent 60%),
  var(--bg);color:var(--ink);font-family:var(--sans);font-size:14px;line-height:1.5}
.wrap{max-width:1320px;margin:0 auto;padding:20px 20px 80px}
a{color:var(--gold);text-decoration:none}
a:hover{text-decoration:underline}
/* header */
.top{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;
  border-bottom:1px solid var(--bds);padding-bottom:16px;margin-bottom:18px}
.ey{font-family:var(--mono);color:var(--gold);font-size:11px;letter-spacing:.22em;text-transform:uppercase;font-weight:600}
h1{font-size:23px;margin:6px 0 0;letter-spacing:-.01em}
.status{font-family:var(--mono);text-align:right;font-size:12px;color:var(--mut)}
.pill{display:inline-flex;align-items:center;gap:7px;background:var(--panel);border:1px solid var(--bd);
  border-radius:20px;padding:5px 13px;font-family:var(--mono);font-size:12px}
.dot{width:9px;height:9px;border-radius:50%;background:var(--grn);box-shadow:0 0 0 0 rgba(84,207,141,.5);animation:pulse 2s infinite}
.dot.warn{background:var(--red);animation:none} .dot.idle{background:var(--faint);animation:none}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(84,207,141,.45)}70%{box-shadow:0 0 0 7px rgba(84,207,141,0)}100%{box-shadow:0 0 0 0 rgba(84,207,141,0)}}
.status .row{margin-top:5px}
/* blocker banner */
#blocker{display:none;background:linear-gradient(180deg,#2a1512,#1e1210);border:1px solid var(--red);
  border-left:5px solid var(--red);border-radius:12px;padding:16px 18px;margin-bottom:18px;box-shadow:var(--shadow)}
#blocker.on{display:block;animation:slidein .3s ease}
@keyframes slidein{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}}
#blocker .lbl{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--red);font-weight:700}
#blocker h3{margin:6px 0 4px;font-size:17px}
#blocker p{margin:0 0 12px;color:var(--ink);font-size:14px}
#blocker .opts{font-family:var(--mono);font-size:12.5px;color:var(--mut);margin:0 0 14px;padding-left:2px}
#blocker .opts div{padding:2px 0}
.btn{display:inline-flex;align-items:center;gap:8px;background:var(--red);color:#1a0e0c;border:none;
  border-radius:8px;padding:10px 16px;font-family:var(--mono);font-size:13px;font-weight:700;cursor:pointer;transition:filter .15s}
.btn:hover{filter:brightness(1.1)} .btn.ghost{background:transparent;color:var(--mut);border:1px solid var(--bd);font-weight:500}
.btn.ghost:hover{color:var(--ink)}
/* kpi tiles */
.tiles{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:14px}
@media(max-width:900px){.tiles{grid-template-columns:repeat(2,1fr)}}
.tile{background:linear-gradient(180deg,var(--card),var(--panel));border:1px solid var(--bd);
  border-radius:12px;padding:13px 15px;box-shadow:var(--shadow)}
.tile .k{font-family:var(--mono);color:var(--faint);font-size:10px;letter-spacing:.08em;text-transform:uppercase}
.tile .v{font-family:var(--mono);font-size:25px;font-weight:700;margin-top:5px;letter-spacing:-.02em}
.tile .v small{font-size:14px;color:var(--mut);font-weight:400}
.tile .sub{font-family:var(--mono);font-size:10.5px;color:var(--faint);margin-top:3px}
#gdetail{font-family:var(--mono);font-size:11px;color:var(--faint);margin:2px 2px 16px}
/* layout */
.grid{display:grid;grid-template-columns:1.05fr 1fr;gap:14px}
@media(max-width:980px){.grid{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--bd);border-radius:12px;padding:15px 16px;
  margin-bottom:14px;box-shadow:var(--shadow)}
.panel h2{font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--mut);
  margin:0 0 12px;display:flex;align-items:center;gap:8px}
.panel h2 .cnt{margin-left:auto;color:var(--faint);font-size:10px;letter-spacing:.05em}
/* current phase */
#curname{font-family:var(--mono);font-weight:700;font-size:14px;margin-bottom:10px;color:var(--gold2)}
.steps{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
.step{font-family:var(--mono);font-size:11px;padding:4px 10px;border-radius:6px;border:1px solid var(--bd);
  color:var(--faint);background:var(--bg2)}
.step.on{color:#12241a;background:var(--grn);border-color:var(--grn);font-weight:600}
.bar{height:8px;background:var(--panel2);border-radius:5px;overflow:hidden;margin-top:4px}
.bar>i{display:block;height:100%;background:linear-gradient(90deg,var(--gold),var(--gold2));width:0;transition:width .5s}
.eta{font-family:var(--mono);font-size:12px;color:var(--mut);margin-top:9px}
.eta b{color:var(--ink)}
/* phase list */
.phase{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid #1e231c;font-size:13px}
.phase:last-child{border:none}
.pn{font-family:var(--mono);color:var(--faint);width:20px;text-align:right;flex:none}
.pname{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.peta{font-family:var(--mono);font-size:10.5px;color:var(--faint);flex:none}
.badge{font-family:var(--mono);font-size:9.5px;letter-spacing:.04em;text-transform:uppercase;padding:3px 9px;
  border-radius:20px;border:1px solid;flex:none}
.b-complete{color:var(--grn);border-color:#2e5c44;background:#12241a}
.b-in_progress{color:var(--gold2);border-color:#5c4a1e;background:#241d0f}
.b-planned,.b-no_directory{color:var(--faint);border-color:var(--bd)}
/* feeds */
.feed{max-height:280px;overflow-y:auto;background:var(--bg2);border:1px solid var(--bd);border-radius:9px;
  padding:11px 12px;font-family:var(--mono);font-size:12px;line-height:1.55}
.feed.sm{max-height:190px}
.fi{padding:2px 0;white-space:pre-wrap;word-break:break-word;display:flex;gap:7px}
.fi .ic{flex:none;opacity:.8}
.fi.tool{color:var(--blue)} .fi.text{color:var(--ink)}
.ts{color:var(--faint);flex:none}
.agent{font-family:var(--mono);font-size:12px;color:var(--mut);margin-bottom:9px;display:flex;align-items:center;gap:8px}
.agent .run{color:var(--grn)} .agent .idle{color:var(--faint)}
.mini-dot{width:7px;height:7px;border-radius:50%;background:var(--grn);animation:pulse 2s infinite;flex:none}
.mini-dot.idle{background:var(--faint);animation:none}
/* lists: decisions / research / deliverables / review */
.item{padding:8px 0;border-bottom:1px solid #1e231c}
.item:last-child{border:none}
.item .t{font-size:13px;color:var(--ink)}
.item .m{font-family:var(--mono);font-size:11px;color:var(--faint);margin-top:2px}
.tag{font-family:var(--mono);font-size:9.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--gold);
  background:#241d0f;border:1px solid #5c4a1e;border-radius:5px;padding:1px 6px;margin-right:7px}
.tag.rev{color:var(--vio);background:#1a1530;border-color:#3a2f5c}
.tag.p{color:var(--blue);background:#0f1c26;border-color:#254155}
.commit{display:flex;gap:11px;padding:4px 0;font-family:var(--mono);font-size:12px;border-bottom:1px solid #1e231c}
.commit:last-child{border:none}
.commit .h{color:var(--gold)}
.commit .m{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.crits{margin-top:6px;padding-left:2px}
.crit{font-family:var(--mono);font-size:11px;color:var(--mut);padding:2px 0 2px 14px;position:relative;line-height:1.45}
.crit::before{content:"";position:absolute;left:2px;top:8px;width:4px;height:4px;border-radius:50%;background:var(--grn)}
.empty{color:var(--faint);font-family:var(--mono);font-size:12px;padding:4px 0}
/* tabs for the right-side reference column */
.tabs{display:flex;gap:4px;margin-bottom:12px;flex-wrap:wrap}
.tab{font-family:var(--mono);font-size:11px;padding:5px 11px;border-radius:7px;border:1px solid var(--bd);
  color:var(--mut);background:var(--bg2);cursor:pointer}
.tab.on{color:var(--gold2);border-color:#5c4a1e;background:#241d0f}
.tabpane{display:none} .tabpane.on{display:block}
#toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%) translateY(20px);opacity:0;
  background:var(--panel);border:1px solid var(--bd);border-left:3px solid var(--grn);border-radius:8px;
  padding:10px 16px;font-family:var(--mono);font-size:12.5px;box-shadow:var(--shadow);transition:all .25s;pointer-events:none;z-index:50}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.foot{font-family:var(--mono);font-size:11px;color:var(--faint);margin-top:26px;padding-top:14px;border-top:1px solid var(--bds);text-align:center}
</style></head><body><div class="wrap">

<div class="top">
  <div>
    <div class="ey">zamvar capital · live desk monitor</div>
    <h1>Fund 1 — Autonomous Build</h1>
  </div>
  <div class="status">
    <span class="pill"><span class="dot" id="dot"></span><span id="conn">connecting…</span></span>
    <div class="row" id="clock"></div>
    <div class="row" id="lastact"></div>
    <div class="row" id="lastcommit"></div>
  </div>
</div>

<div id="blocker">
  <div class="lbl">⛔ decision blocker — the build is paused for you</div>
  <h3 id="bk-title">–</h3>
  <p id="bk-detail"></p>
  <div class="opts" id="bk-opts"></div>
  <button class="btn" onclick="focusTerm()">⌘ Open the terminal to decide</button>
  <button class="btn ghost" onclick="ackBlocker()" style="margin-left:8px">Dismiss banner</button>
</div>

<div class="tiles">
  <div class="tile"><div class="k">Phases complete</div><div class="v"><span id="tph">–</span><small id="tpht">/11</small></div><div class="sub" id="phsub"></div></div>
  <div class="tile"><div class="k">Tokens spent</div><div class="v" id="ttok">–</div><div class="sub">subagent build total</div></div>
  <div class="tile"><div class="k">Graphify saved</div><div class="v" id="gsaved" style="color:var(--grn)">–</div><div class="sub" id="gsub">estimate</div></div>
  <div class="tile"><div class="k">Commits</div><div class="v" id="tc">–</div><div class="sub" id="csub"></div></div>
  <div class="tile"><div class="k">Last activity</div><div class="v" id="tage" style="font-size:19px">–</div><div class="sub" id="agesub"></div></div>
</div>
<div id="gdetail"></div>

<div class="grid">
  <div>
    <div class="panel">
      <h2>◆ Current phase</h2>
      <div id="curname">–</div>
      <div class="steps" id="steps"></div>
      <div class="bar"><i id="pbar"></i></div>
      <div class="eta" id="eta"></div>
    </div>
    <div class="panel">
      <h2>Phase pipeline <span class="cnt" id="ppcnt"></span></h2>
      <div id="phases"></div>
    </div>
    <div class="panel">
      <h2>▶ Active subagent — live</h2>
      <div class="agent" id="agent"></div>
      <div class="feed" id="subfeed"></div>
    </div>
  </div>
  <div>
    <div class="panel">
      <h2>Reference — what the desk has decided &amp; found</h2>
      <div class="tabs">
        <div class="tab on" data-tab="rev">For your review</div>
        <div class="tab" data-tab="road">Roadmap</div>
        <div class="tab" data-tab="dec">Decisions</div>
        <div class="tab" data-tab="res">Research</div>
        <div class="tab" data-tab="del">Deliverables</div>
        <div class="tab" data-tab="dh">Data health</div>
      </div>
      <div class="tabpane on" id="pane-rev"></div>
      <div class="tabpane" id="pane-road"></div>
      <div class="tabpane" id="pane-dec"></div>
      <div class="tabpane" id="pane-res"></div>
      <div class="tabpane" id="pane-del"></div>
      <div class="tabpane" id="pane-dh"></div>
    </div>
    <div class="panel">
      <h2>Orchestrator — this session</h2>
      <div class="feed sm" id="feed"></div>
    </div>
    <div class="panel">
      <h2>Recent commits <span class="cnt" id="ccount"></span></h2>
      <div id="commits"></div>
    </div>
  </div>
</div>
<div class="foot">read-only window into the autonomous run · reconnects automatically · the desk sizes for survival — 1% is a measured outcome, never an input</div>
</div>
<div id="toast"></div>

<script>
var esc=function(s){return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;")};
function fmtAge(s){if(s<60)return s+"s";var m=(s/60)|0;if(m<60)return m+"m "+(s%60)+"s";return ((m/60)|0)+"h "+(m%60)+"m"}
function fmtEta(s){if(s<=0)return "~done";var m=Math.ceil(s/60);if(m<60)return "~"+m+"m";return "~"+((m/60)|0)+"h "+(m%60)+"m"}
function fmtDur(s){var m=Math.round(s/60);if(m<60)return m+"m";return ((m/60)|0)+"h "+(m%60)+"m"}
function hhmmss(ts){if(!ts)return "";var d=new Date(ts);return isNaN(d)?"":d.toLocaleTimeString([],{hour12:false})}
function phaseEta(e){if(!e)return "";if(e.kind=="done")return "took "+fmtDur(e.secs);if(e.kind=="running")return fmtEta(e.secs)+" left";return "est "+fmtDur(e.secs)}
function toast(msg,ok){var t=document.getElementById("toast");t.textContent=msg;t.style.borderLeftColor=ok?"var(--grn)":"var(--red)";t.className="show";setTimeout(function(){t.className=""},2600)}
function focusTerm(){fetch("/action/focus-terminal",{method:"POST"}).then(function(r){return r.json()}).then(function(d){toast(d.ok?("Brought "+d.app+" to the front →"):"Couldn't focus terminal",d.ok)}).catch(function(){toast("Couldn't reach monitor backend",false)})}
function ackBlocker(){fetch("/action/ack-blocker",{method:"POST"}).then(function(r){return r.json()}).then(function(){document.getElementById("blocker").className="";toast("Blocker dismissed",true)})}
// tabs
document.querySelectorAll(".tab").forEach(function(t){t.onclick=function(){
  document.querySelectorAll(".tab").forEach(function(x){x.className="tab"});
  document.querySelectorAll(".tabpane").forEach(function(x){x.className="tabpane"});
  t.className="tab on";document.getElementById("pane-"+t.dataset.tab).className="tabpane on";
}});

function render(d){
  if(!d||!d.ok){document.getElementById("conn").textContent="waiting…";return}
  var now=Date.now()/1000;
  // clocks
  document.getElementById("clock").textContent=new Date().toLocaleTimeString([],{hour12:false});
  // kpis
  document.getElementById("tph").textContent=d.phases_done;
  document.getElementById("tpht").textContent="/"+d.phases_total;
  var cp=d.current;
  document.getElementById("phsub").textContent=cp?(cp.plans_done+"/"+cp.plans_total+" plans this phase"):"";
  document.getElementById("ttok").textContent=d.tokens?(d.tokens/1e6).toFixed(2)+"M":"–";
  document.getElementById("tc").textContent=d.git.count;
  var gs=d.graphify;
  if(gs){document.getElementById("gsaved").textContent="~"+Math.round(gs.saved/1000)+"k";
    document.getElementById("gsub").textContent="−"+gs.pct+"% / "+gs.n_post+" plans";
    document.getElementById("gdetail").textContent="graphify est · executor avg "+Math.round(gs.base_avg/1000)+"k (pre) → "+Math.round(gs.post_avg/1000)+"k (live) per plan · executor-proxy estimate, not a controlled measurement";}
  else{document.getElementById("gsaved").textContent="–";document.getElementById("gdetail").textContent="";}
  // activity / stall
  var age=d.git.last_epoch?Math.floor(now-d.git.last_epoch):0;
  var a=d.agent||{};
  var lastAct=Math.max(d.git.last_epoch||0,a.mtime||0);
  var actAge=lastAct?Math.floor(now-lastAct):age;
  document.getElementById("lastcommit").textContent="last commit "+(d.git.last_epoch?fmtAge(age)+" ago":"–");
  document.getElementById("lastact").textContent="last activity "+(lastAct?fmtAge(actAge)+" ago":"–");
  document.getElementById("tage").textContent=fmtAge(actAge);
  document.getElementById("agesub").textContent=a.title?esc(a.title).slice(0,26):"";
  var working=a.active,warn=!working&&actAge>600;
  var dot=document.getElementById("dot");dot.className="dot"+(warn?" warn":(working?"":" idle"));
  document.getElementById("conn").textContent=working?"agent working":(warn?"idle — check for stall":"live");
  document.getElementById("tage").style.color=warn?"var(--red)":"var(--ink)";
  document.getElementById("csub").textContent=d.git.recent&&d.git.recent[0]?esc(d.git.recent[0].m).slice(0,22):"";
  // blocker
  var bk=d.blocker,bkEl=document.getElementById("blocker");
  if(bk&&bk.active){bkEl.className="on";
    document.getElementById("bk-title").textContent=bk.title||"A decision is needed";
    document.getElementById("bk-detail").textContent=bk.detail||"";
    var oh="";(bk.options||[]).forEach(function(o){oh+="<div>▸ "+esc(o)+"</div>"});
    document.getElementById("bk-opts").innerHTML=oh;
    if(!window._bkAlerted){window._bkAlerted=true;toast("⛔ Decision blocker — build paused",false)}
  }else{bkEl.className="";window._bkAlerted=false}
  // current phase
  if(cp){
    document.getElementById("curname").textContent=cp.slug;
    var sh="";cp.stages.forEach(function(s){sh+='<span class="step'+(s[1]?" on":"")+'">'+s[0]+(s[1]?" ✓":"")+'</span>'});
    document.getElementById("steps").innerHTML=sh;
    document.getElementById("pbar").style.width=Math.min(100,Math.round(cp.elapsed/cp.est_total*100))+"%";
    document.getElementById("eta").innerHTML="elapsed <b>"+fmtAge(cp.elapsed)+"</b> · est remaining <b>"+fmtEta(cp.remaining)+"</b>";
  }
  // active subagent
  var ah="";
  ah+=a.active?'<span class="mini-dot"></span>':'<span class="mini-dot idle"></span>';
  if(a.title)ah+='<b style="color:var(--gold2)">'+esc(a.title)+'</b>';
  ah+=a.active?'<span class="run">working ('+fmtAge(a.age||0)+')</span>':(a.feed?'<span class="idle">idle '+fmtAge(a.age||0)+'</span>':'<span class="idle">no active subagent</span>');
  document.getElementById("agent").innerHTML=ah;
  renderFeed("subfeed",a.feed,"no active subagent");
  // phases
  document.getElementById("ppcnt").textContent=d.phases_done+" / "+d.phases_total+" complete";
  var ph="";(d.phases||[]).forEach(function(p){
    ph+='<div class="phase"><span class="pn">'+p.n+'</span><span class="pname">'+esc(p.name)+'</span>'+
        '<span class="peta">'+phaseEta(p.eta)+'</span>'+
        '<span class="badge b-'+p.status+'">'+p.status.replace("_"," ")+'</span></div>'});
  document.getElementById("phases").innerHTML=ph;
  // reference panes
  var dec="";(d.decisions||[]).forEach(function(x){dec+='<div class="item"><div class="t"><span class="tag p">P'+esc(x.phase)+'</span>'+esc(x.title)+'</div></div>'});
  document.getElementById("pane-dec").innerHTML=dec||'<div class="empty">no locked decisions yet</div>';
  var res="";(d.research||[]).forEach(function(x){res+='<div class="item"><div class="t">'+esc(x.title)+'</div><div class="m">'+esc(x.summary||x.file)+'</div></div>'});
  document.getElementById("pane-res").innerHTML=res||'<div class="empty">no research docs</div>';
  var del="";(d.deliverables||[]).forEach(function(x){del+='<div class="item"><div class="t"><a href="/report/'+encodeURI(x.file)+'" target="_blank">'+esc(x.title)+' ↗</a></div><div class="m">'+esc(x.file)+'</div></div>'});
  document.getElementById("pane-del").innerHTML=del||'<div class="empty">no deliverables yet</div>';
  var rev="";(d.review||[]).slice().reverse().forEach(function(x){rev+='<div class="item"><div class="t"><span class="tag rev">'+esc(x.kind||"note")+'</span>'+esc(x.title)+'</div>'+(x.note?'<div class="m">'+esc(x.note)+'</div>':'')+'</div>'});
  document.getElementById("pane-rev").innerHTML=rev||'<div class="empty">nothing flagged for review — the desk will log one-off decisions here as it goes</div>';
  var road="";(d.scope||[]).forEach(function(x){
    var st=(d.phases||[]).filter(function(p){return String(p.n)==String(x.n)})[0];
    var badge=st?'<span class="badge b-'+st.status+'" style="margin-left:7px">'+st.status.replace("_"," ")+'</span>':'';
    road+='<div class="item"><div class="t"><span class="tag p">P'+esc(x.n)+'</span>'+esc(x.name)+(x.deferred?' <span class="tag rev">deferred</span>':'')+badge+'</div>';
    if(x.goal)road+='<div class="m">'+esc(x.goal)+'</div>';
    if(x.crits&&x.crits.length){road+='<div class="crits">';x.crits.forEach(function(c){road+='<div class="crit">✓ '+esc(c)+'</div>'});road+='</div>'}
    road+='</div>'});
  document.getElementById("pane-road").innerHTML=road||'<div class="empty">no roadmap scope parsed</div>';
  // data health
  var dh=d.data_health||{};var dhH="";
  if(!dh.updated){dhH='<div class="empty">daemon has not written a cycle yet — .monitor/data_health.json absent</div>';}
  else{
    (dh.alerts||[]).forEach(function(a){dhH+='<div class="item"><div class="t"><span class="tag rev" style="background:var(--red)">ALERT</span>'+esc(a)+'</div></div>'});
    dhH+='<div class="item"><div class="t">coverage <b>'+esc(String(dh.coverage_pct))+'%</b> · divergences this cycle <b>'+esc(String(dh.divergences_this_cycle))+'</b>'+(dh.degraded?' · <span class="tag rev">degraded</span>':'')+'</div>';
    var g=dh.gaps||{};dhH+='<div class="m">gaps: '+esc(String(g.price_weeks_missing||0))+' price-weeks · '+esc(String(g.missing_cards||0))+' cards · '+((dh.stale_sources||[]).length)+' stale sources · updated '+esc((dh.updated||"").slice(0,19))+'</div></div>';
    Object.keys(dh.sources||{}).forEach(function(nm){var s=dh.sources[nm];
      dhH+='<div class="item"><div class="t"><span class="tag p">'+esc(nm)+'</span>'+(s.degraded?'<span class="tag rev">degraded</span>':'ok')+'</div><div class="m">last success '+esc(String(s.last_success||"never"))+' · consec fail '+esc(String(s.consec_fail||0))+'</div></div>'});
  }
  document.getElementById("pane-dh").innerHTML=dhH;
  // orchestrator feed
  renderFeed("feed",d.feed,"quiet");
  // commits
  document.getElementById("ccount").textContent=(d.git.recent||[]).length+" shown";
  var cm="";(d.git.recent||[]).forEach(function(x){cm+='<div class="commit"><span class="h">'+x.h+'</span><span class="m">'+esc(x.m)+'</span></div>'});
  document.getElementById("commits").innerHTML=cm;
}
function renderFeed(id,feed,emptyMsg){
  var s="";(feed||[]).forEach(function(x){var t=hhmmss(x.ts);var tp=t?'<span class="ts">'+t+'</span>':'';
    var ic=x.k=="tool"?"🔧":"💬";s+='<div class="fi '+x.k+'">'+tp+'<span class="ic">'+ic+'</span><span>'+esc(x.s)+'</span></div>'});
  if(!s)s='<div class="empty">'+emptyMsg+'</div>';
  var el=document.getElementById(id);var atB=el.scrollHeight-el.scrollTop-el.clientHeight<40;el.innerHTML=s;if(atB)el.scrollTop=el.scrollHeight;
}
var es=new EventSource("/events");
es.onmessage=function(e){try{render(JSON.parse(e.data))}catch(x){}};
es.onerror=function(){document.getElementById("conn").textContent="reconnecting…";document.getElementById("dot").className="dot idle"};
setInterval(function(){var c=document.getElementById("clock");if(c)c.textContent=new Date().toLocaleTimeString([],{hour12:false})},1000);
</script></body></html>"""


if __name__ == "__main__":
    threading.Thread(target=sampler, daemon=True).start()
    time.sleep(1.0)
    print(f"Fund 1 live monitor → http://127.0.0.1:{PORT}", flush=True)
    Server(("127.0.0.1", PORT), Handler).serve_forever()
