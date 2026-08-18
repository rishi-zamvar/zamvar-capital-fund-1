"""Live monitor for the universe-expansion run (Phase 06.12 Plan 03) — served on a port.

A tiny stdlib HTTP server (no new deps): GET / returns the dashboard shell, GET /data returns a
fresh JSON snapshot computed per-request from the DETERMINISTIC live signals (catalyst.db counts,
raw-archive file counts, the run log's degrades/errors, the .done signal, process liveness) plus an
INSIGHTS markdown file Claude appends to. The page polls /data every POLL_S seconds and updates the
DOM in place — genuinely live, no full-page reload. Best-effort throughout: a read failure degrades
that field, never the server.

Run: `.venv/bin/python scripts/expansion_monitor.py --serve 8812`  then open http://127.0.0.1:8812
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import sqlite3
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(".planning/phases/06.12-universe-expansion")
LOG = BASE / "06.12-03-live-run.log"
DONE = BASE / "06.12-03-live-expand-report.json.done"
INSIGHTS = BASE / "monitor-insights.md"
POLL_S = 5
CATALYST_BASELINE = 65  # catalyst rows before this run began

_PREV: dict = {}  # in-process last-tick counters for the activity heartbeat / rates


def _alive() -> bool:
    try:
        return bool(subprocess.run(["pgrep", "-f", "universe_expand_live.py"],
                                   capture_output=True, text=True).stdout.strip())
    except Exception:
        return False


def _db_counts() -> dict:
    out = {"catalyst": None, "catalyst_move": None, "snapshot_today": None}
    try:
        c = sqlite3.connect("catalyst.db")
        today = _dt.date.today().isoformat()
        out["catalyst"] = c.execute("SELECT COUNT(*) FROM catalyst").fetchone()[0]
        try:
            out["catalyst_move"] = c.execute("SELECT COUNT(*) FROM catalyst_move").fetchone()[0]
        except sqlite3.OperationalError:
            out["catalyst_move"] = None
        out["snapshot_today"] = c.execute(
            "SELECT COUNT(*) FROM universe_snapshot WHERE as_of_date=?", (today,)).fetchone()[0]
        c.close()
    except Exception:
        pass
    return out


def _archive() -> dict:
    def n(*roots):
        t = 0
        for r in roots:
            try:
                t += sum(1 for f in (Path("data/raw") / r).rglob("*") if f.is_file())
            except Exception:
                pass
        return t
    return {"efts_pages": n("edgar_efts"), "exhibits_8k": n("edgar_8k"),
            "ctgov": n("ctgov_discover"), "cboe": n("cboe"), "daily": n("nasdaq_daily", "tiingo")}


def _newest_mtime() -> float | None:
    newest = None
    for r in ("edgar_efts", "edgar_8k", "ctgov_discover", "cboe", "nasdaq_daily", "tiingo"):
        p = Path("data/raw") / r
        if not p.exists():
            continue
        for f in p.rglob("*"):
            try:
                if f.is_file():
                    m = f.stat().st_mtime
                    newest = m if newest is None or m > newest else newest
            except Exception:
                continue
    return newest


def _issues():
    if not LOG.exists():
        return [], None
    try:
        lines = LOG.read_text(errors="replace").splitlines()
    except Exception:
        return [], None
    counts: dict[str, int] = {}
    for ln in lines:
        if re.search(r"degraded|error|timed out|Traceback|429|Too Many", ln, re.I):
            key = re.sub(r"for [A-Z0-9.]+", "for <ticker>", ln)
            key = re.sub(r"https?://\S+", "<url>", key).strip()[:150]
            counts[key] = counts.get(key, 0) + 1
    issues = [{"text": k, "count": c} for k, c in
              sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:8]]
    return issues, (lines[-1].strip() if lines else None)


def _parse_etime(s: str) -> int | None:
    """macOS/BSD `ps -o etime=` -> seconds. Format [[dd-]hh:]mm:ss."""
    s = s.strip()
    if not s:
        return None
    days = 0
    if "-" in s:
        d, s = s.split("-", 1)
        days = int(d)
    try:
        parts = [int(x) for x in s.split(":")]
    except ValueError:
        return None
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, sec = parts[-3], parts[-2], parts[-1]
    return days * 86400 + h * 3600 + m * 60 + sec


def _proc_elapsed() -> int | None:
    """Accurate run elapsed = the live process's own etime (survives log-path reuse across re-runs).
    None when the run process is gone (finished)."""
    try:
        pids = subprocess.run(["pgrep", "-f", "universe_expand_live.py"],
                              capture_output=True, text=True).stdout.split()
        best = None
        for pid in pids:
            r = subprocess.run(["ps", "-o", "etime=", "-p", pid],
                               capture_output=True, text=True).stdout.strip()
            e = _parse_etime(r)
            if e is not None:
                best = e if best is None or e > best else best
        return best
    except Exception:
        return None


def _insights():
    if not INSIGHTS.exists():
        return []
    try:
        raw = INSIGHTS.read_text()
    except Exception:
        return []
    out = []
    for para in raw.split("\n## ")[::-1]:
        para = para.strip().lstrip("#").strip()
        if not para:
            continue
        head, _, body = para.partition("\n")
        out.append({"head": head.strip(), "body": body.strip()})
    return out


def _phase(snap, moves, catalysts, done):
    if done:
        return "COMPLETE", "ok"
    if snap and snap > 0:
        return "Writing cohort — finishing", "ok"
    if moves and moves > 0:
        return "Computing catalyst moves (daily-bar windows)", "run"
    if catalysts and catalysts > CATALYST_BASELINE:
        return "Backfilling historical catalysts (5-yr efts)", "run"
    return "Discovery — CT.gov + efts", "run"


def _eta(phase, heartbeat, progressing):
    if phase == "COMPLETE":
        return "done"
    if progressing:  # counts are still rising -> working, even when served from cache (no new fetch)
        return {
            "Discovery — CT.gov + efts": "working — scanning filings",
            "Backfilling historical catalysts (5-yr efts)": "working — gathering events",
            "Computing catalyst moves (daily-bar windows)": "working — measuring moves (rough: a few min)",
            "Writing cohort — finishing": "< 1 min — writing the shortlist",
        }.get(phase, "working…")
    if heartbeat is not None and heartbeat > 240:
        return f"paused? no progress in {int(heartbeat)}s — check issues"
    return "working…"


# The pipeline as plain-language discrete steps the operator can follow.
_STEP_DEFS = [
    ("Scout candidate companies",
     "Searching FDA filings + the clinical-trials registry for biotech companies with big upcoming events."),
    ("Gather their event history",
     "Pulling each company's past make-or-break events (drug approvals, trial readouts)."),
    ("Measure how much each moved",
     "Checking how far the stock jumped or fell around each past event."),
    ("Keep the real movers",
     "Keeping companies whose events actually move the stock enough to trade; dropping the quiet ones."),
    ("Build the shortlist",
     "Ranking by how much they move and writing the final peer universe."),
]
# phase string -> index of the currently-active step
_PHASE_STEP = {
    "Discovery — CT.gov + efts": 0,
    "Backfilling historical catalysts (5-yr efts)": 1,
    "Computing catalyst moves (daily-bar windows)": 2,
    "Writing cohort — finishing": 3,
    "COMPLETE": 5,
}


def _steps(phase, catalysts, moves, snap, backfilled, arch):
    cur = _PHASE_STEP.get(phase, 0)
    if snap and snap > 0:
        cur = 5  # cohort written -> everything done
    details = [
        f"{arch.get('efts_pages',0)+arch.get('ctgov',0)} filings/pages scanned" if arch else "",
        f"{catalysts} events gathered" + (f" (+{backfilled} new)" if backfilled and backfilled>0 else "")
            if catalysts is not None else "",
        f"{moves} moves measured" if moves is not None else "",
        "screening the movers…" if cur == 3 else ("done" if cur > 3 else "waiting"),
        (f"{snap} companies written" if snap else "waiting"),
    ]
    out = []
    for i, (label, plain) in enumerate(_STEP_DEFS):
        status = "done" if i < cur else ("active" if i == cur else "pending")
        out.append({"n": i + 1, "label": label, "plain": plain,
                    "status": status, "detail": details[i]})
    return out


def collect() -> dict:
    now = time.time()
    db = _db_counts()
    arch = _archive()
    issues, last_line = _issues()
    hb_m = _newest_mtime()
    heartbeat = (now - hb_m) if hb_m else None
    done = DONE.exists()
    catalysts, moves, snap = db["catalyst"], db["catalyst_move"], db["snapshot_today"]
    phase, tone = _phase(snap, moves, catalysts, done)
    # progress-based liveness: counts rising = working, even when cache-served (no new fetch).
    # progressing = any DB/archive count rose in the last 120s. Cache-served compute writes NO new
    # archive files, so the fetch-heartbeat goes stale while work continues — track a rolling
    # last-progress timestamp off the DB counts so we don't false-report "paused".
    arch_total = sum(arch.values())
    now_ts = time.time()
    counts = (catalysts or 0) + (moves or 0) + arch_total
    if (not _PREV) or counts > _PREV.get("counts", -1):
        _PREV["last_progress"] = now_ts
    _PREV["counts"] = counts
    since_progress = now_ts - _PREV.get("last_progress", now_ts)
    progressing = since_progress < 120
    done_txt = ""
    if done:
        try:
            done_txt = DONE.read_text().strip()
        except Exception:
            pass
    return {
        "phase": phase, "tone": tone, "alive": _alive(), "done": done, "done_txt": done_txt,
        "elapsed_s": _proc_elapsed(),
        "heartbeat_s": int(heartbeat) if heartbeat is not None else None,
        "eta": _eta(phase, heartbeat, progressing), "progressing": progressing,
        "catalysts": catalysts, "backfilled": (catalysts - CATALYST_BASELINE) if catalysts else 0,
        "moves": moves, "snapshot_today": snap,
        "steps": _steps(phase, catalysts, moves, snap,
                        (catalysts - CATALYST_BASELINE) if catalysts else 0, arch),
        "archive": arch, "issues": issues, "last_line": last_line,
        "insights": _insights(), "updated": _dt.datetime.now().strftime("%H:%M:%S"),
        "poll_s": POLL_S,
    }


SHELL = """<!doctype html><html><head><meta charset="utf-8">
<title>Universe Expansion — Live Monitor</title>
<style>
:root{--bg:#0d0f12;--panel:#15181d;--line:#2a2f37;--ink:#e6e9ef;--muted:#8b93a1;--brass:#C8A24B}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;padding:24px}
h1{font-size:18px;margin:0 0 2px;color:var(--brass);letter-spacing:.5px}
.sub{color:var(--muted);margin:0 0 18px;font-size:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0}
.m{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px}
.mv{font-size:24px;font-weight:700}.ml{color:var(--muted);font-size:11px;margin-top:4px;text-transform:uppercase;letter-spacing:.5px}
.ms{color:var(--brass);font-size:11px;margin-top:3px}
.banner{display:flex;align-items:center;gap:12px;background:var(--panel);border:1px solid var(--line);
border-left:4px solid var(--brass);border-radius:8px;padding:14px 18px;margin-bottom:8px}
.dot{width:12px;height:12px;border-radius:50%;flex:0 0 auto}
.phase{font-size:16px;font-weight:700}.eta{color:var(--muted);font-size:12px;margin-left:auto;text-align:right}
.sec{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px;margin:14px 0}
.sec h2{font-size:12px;text-transform:uppercase;letter-spacing:1px;color:var(--brass);margin:0 0 12px}
.iss{padding:6px 0;border-bottom:1px dashed var(--line);color:#f0c9b0;font-size:12px}
.cnt{color:#FF6B6B;font-weight:700;margin-right:8px}
.ins{padding:10px 0;border-bottom:1px dashed var(--line)}.ins-h{color:var(--brass);font-weight:700;font-size:12px}
.ins-b{color:var(--ink);font-size:13px;margin-top:3px;white-space:pre-wrap}
.muted{color:var(--muted)}.foot{color:var(--muted);font-size:11px;margin-top:16px}
.last{color:var(--muted);font-size:11px;background:#0a0c0f;border:1px solid var(--line);border-radius:6px;
padding:8px 10px;margin-top:8px;overflow-x:auto;white-space:nowrap}
.done{background:#10241a;border:1px solid #1f6b46;color:#7CFC9B;border-radius:6px;padding:10px;margin:8px 0}
.off{opacity:.5}
.step{display:flex;gap:12px;align-items:flex-start;padding:11px 0;border-bottom:1px dashed var(--line)}
.step:last-child{border-bottom:0}
.step .mark{width:24px;height:24px;border-radius:50%;flex:0 0 auto;display:flex;align-items:center;
justify-content:center;font-size:12px;font-weight:700;border:1px solid var(--line);color:var(--muted)}
.step.done .mark{background:#7CFC9B;color:#06240f;border-color:#7CFC9B}
.step.active .mark{background:#F5C451;color:#2a1e00;border-color:#F5C451;animation:pulse 1.6s ease-in-out infinite}
.step.pending{opacity:.45}
.step .lab{font-weight:650;font-size:15px}
.step .pl{color:var(--muted);font-size:13px;margin-top:2px;max-width:60ch}
.step .det{font-family:ui-monospace,monospace;font-size:12px;color:var(--brass-ink);margin-top:4px}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(245,196,81,.5)}50%{box-shadow:0 0 0 7px rgba(245,196,81,0)}}
@media (prefers-reduced-motion:reduce){.step.active .mark{animation:none}}
</style></head><body>
<h1>🧬 ZAMVAR CAPITAL — UNIVERSE EXPANSION · LIVE MONITOR</h1>
<p class="sub" id="sub">connecting…</p>
<div id="doneban"></div>
<div class="banner"><div class="dot" id="dot"></div>
<div><div class="phase" id="phase">—</div><div class="muted" id="phasesub" style="font-size:12px"></div></div>
<div class="eta">ETA<br><b style="color:var(--brass)" id="eta">—</b></div></div>
<div class="sec"><h2>Steps — where we are</h2><div id="steps"></div></div>
<div class="grid" id="grid"></div>
<div class="sec"><h2>Current issues (from run log)</h2><div id="issues"></div><div id="lastline"></div></div>
<div class="sec"><h2>Claude's insights (newest first)</h2><div id="insights"></div></div>
<p class="foot">Served live on this port; the numbers poll <span id="poll">5</span>s. Deterministic panels are
computed per request from the DB + raw archive + run log. Insights are appended by Claude as milestones hit.</p>
<script>
const TONE={ok:'#7CFC9B',run:'#F5C451',err:'#FF6B6B'};
function dur(s){if(s==null)return '—';let h=Math.floor(s/3600),m=Math.floor((s%3600)/60),x=s%60;return (h?h+'h ':'')+m+'m '+x+'s';}
function esc(t){const d=document.createElement('div');d.textContent=t==null?'':String(t);return d.innerHTML;}
function metric(v,l,sub){return `<div class="m"><div class="mv">${v==null?'—':v}</div><div class="ml">${l}</div>${sub?'<div class="ms">'+sub+'</div>':''}</div>`;}
async function tick(){
 try{
  const d=await (await fetch('/data',{cache:'no-store'})).json();
  document.getElementById('poll').textContent=d.poll_s;
  document.getElementById('sub').textContent=`Phase 06.12 Wave 5 · ${d.alive?'● running':(d.done?'✓ finished':'○ process gone')} · updated ${d.updated}`;
  const dot=document.getElementById('dot');dot.style.background=TONE[d.tone]||'#F5C451';dot.style.boxShadow='0 0 12px '+(TONE[d.tone]||'#F5C451');
  document.getElementById('phase').textContent=d.phase;
  document.getElementById('phasesub').textContent=`elapsed ${dur(d.elapsed_s)} · ${d.progressing?'working ✓':(d.heartbeat_s==null?'starting…':'idle '+dur(d.heartbeat_s))}`;
  document.getElementById('eta').textContent=d.eta;
  document.getElementById('doneban').innerHTML=d.done?`<div class="done">✓ RUN COMPLETE — ${esc(d.done_txt)}</div>`:'';
  document.getElementById('steps').innerHTML=(d.steps||[]).map(s=>
    `<div class="step ${s.status}"><div class="mark">${s.status==='done'?'✓':s.n}</div>`+
    `<div><div class="lab">${esc(s.label)}</div><div class="pl">${esc(s.plain)}</div>`+
    (s.detail?`<div class="det">${esc(s.detail)}</div>`:'')+`</div></div>`).join('');
  const a=d.archive||{};
  document.getElementById('grid').innerHTML=[
   metric(d.catalysts,'Historical catalysts',d.backfilled>0?('+'+d.backfilled+' this run'):''),
   metric(d.moves,'Catalyst moves computed','past events w/ T+2 close'),
   metric(d.snapshot_today,'Cohort written (today)','names in universe_as_of'),
   metric(a.exhibits_8k,'8-K exhibits fetched','archived'),
   metric(a.ctgov,'CT.gov pages','archived'),
   metric(a.cboe,'CBOE chains','screened'),
  ].join('');
  document.getElementById('issues').innerHTML=(d.issues&&d.issues.length)?
    d.issues.map(i=>`<div class="iss"><span class="cnt">×${i.count}</span>${esc(i.text)}</div>`).join(''):
    '<p class="muted">No issues logged — clean run so far.</p>';
  document.getElementById('lastline').innerHTML=d.last_line?`<div class="last">last log line: ${esc(d.last_line)}</div>`:'';
  document.getElementById('insights').innerHTML=(d.insights&&d.insights.length)?
    d.insights.map(x=>`<div class="ins"><div class="ins-h">${esc(x.head)}</div><div class="ins-b">${esc(x.body)}</div></div>`).join(''):
    '<p class="muted">No insights yet.</p>';
  document.body.classList.remove('off');
 }catch(e){document.body.classList.add('off');document.getElementById('sub').textContent='monitor unreachable — server stopped?';}
}
tick();setInterval(tick, 5000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/data"):
            body = json.dumps(collect(), default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(SHELL.encode())

    def log_message(self, *a):  # silence access-log noise
        pass


def main() -> int:
    port = 8812
    if "--serve" in sys.argv:
        i = sys.argv.index("--serve")
        if i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print(f"universe-expansion monitor serving on http://127.0.0.1:{port}")
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
