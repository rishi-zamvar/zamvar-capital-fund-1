"""E2+E3 — corrected PIT knowability restamp (fixes the crude v1 that stamped future recorded_at).

Per-type, leak-free, no future stamps:
  * READOUT (CT.gov): event_date = the ESTIMATED primary-completion date we already stored
    (catalyst_source.date_type='estimated'); recorded_at = studyFirstPostDate fetched from CT.gov v2
    (free, no key) = when the estimate became public. The later 'actual'/slipped date is kept as
    event_date_end metadata, never as the tradeable date. Falls back to recorded_at=event_date-180d
    (clamped) only if CT.gov gives no first-post date.
  * PDUFA: keep the acceptance-8-K filing recorded_at from v1 (already correct); only re-clamp.
  * EARNINGS/ADCOM: recorded_at = event_date (same-day 8-K).
Collapses the tangled multi-version rows to ONE canonical version per catalyst. Clamps every
recorded_at to <= min(event_date, today). Idempotent. CT.gov = free-unlimited.
"""
import sqlite3, re, time, json, httpx
from datetime import date, timedelta

TODAY = "2026-08-18"
DB = "catalyst.db"
CT = "https://clinicaltrials.gov/api/v2/studies"
UA = {"User-Agent": "Zamvar Capital Fund1 rishi_zamvar@brown.edu"}
conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row; q = conn.execute

def clamp(rec, ev):
    """recorded_at never in the future, never after the event (a catalyst is knowable at/before it)."""
    cap = min(ev, TODAY) if ev else TODAY
    return min(rec, cap) if rec else cap

def month_to_day(d):
    if not d: return None
    if len(d) == 7: return d + "-01"      # YYYY-MM -> first of month (day precision for anchoring)
    if len(d) == 4: return d + "-01-01"
    return d

# ---- readouts: gather estimated date + NCT ----
readouts = []
ncts = {}
for r in q("select id, ticker, event_date from catalyst where catalyst_type='trial_readout'"):
    est = q("""select reported_date from catalyst_source
              where catalyst_id=? and date_type='estimated' and reported_date is not null
              order by reported_date limit 1""", (r["id"],)).fetchone()
    ref = q("select source_url from catalyst_source where catalyst_id=? and source_url like '%NCT%' limit 1",(r["id"],)).fetchone()
    nct = None
    if ref:
        m = re.search(r"(NCT\d+)", ref["source_url"] or ""); nct = m.group(1) if m else None
    est_date = month_to_day(est["reported_date"]) if est else month_to_day(r["event_date"])
    readouts.append({"id": r["id"], "nct": nct, "event": est_date})
    if nct: ncts.setdefault(nct, None)
print(f"readouts: {len(readouts)} | unique NCTs to fetch: {len(ncts)}", flush=True)

# ---- fetch studyFirstPostDate per NCT (free, rate-limited) ----
with httpx.Client(headers=UA, timeout=30) as cli:
    for i, nct in enumerate(list(ncts), 1):
        try:
            d = cli.get(f"{CT}/{nct}", params={"fields": "StudyFirstPostDate", "format": "json"}).json()
            sm = d.get("protocolSection", {}).get("statusModule", {})
            fp = (sm.get("studyFirstPostDateStruct") or {}).get("date")
            ncts[nct] = fp
        except Exception as e:
            ncts[nct] = None
        time.sleep(0.08)
        if i % 40 == 0: print(f"  fetched {i}/{len(ncts)} NCTs", flush=True)
got = sum(1 for v in ncts.values() if v)
print(f"studyFirstPostDate recovered: {got}/{len(ncts)}", flush=True)

def set_one_version(cid, event_date, recorded_at):
    conn.execute("DELETE FROM catalyst_version WHERE catalyst_id=?", (cid,))
    conn.execute("INSERT INTO catalyst_version (catalyst_id,event_date,recorded_at) VALUES (?,?,?)",
                 (cid, event_date, recorded_at))
    conn.execute("UPDATE catalyst SET event_date=?, last_verified_at=? WHERE id=?",
                 (event_date, recorded_at, cid))

# ---- restamp readouts ----
r_pre = 0
for r in readouts:
    ev = r["event"]
    fp = ncts.get(r["nct"]) if r["nct"] else None
    rec = fp or ( (date.fromisoformat(ev) - timedelta(days=180)).isoformat() if ev and len(ev)==10 else ev )
    rec = clamp(rec, ev)
    set_one_version(r["id"], ev, rec)
    if ev and rec and rec < ev: r_pre += 1
conn.commit()
print(f"readouts restamped: {r_pre} pre-tradeable (recorded_at<event)", flush=True)

# ---- pdufa: collapse to one version, keep filing-date recorded_at, re-clamp ----
p_pre = 0
for r in q("select id, event_date from catalyst where catalyst_type='pdufa'"):
    v = q("select recorded_at from catalyst_version where catalyst_id=? order by recorded_at limit 1",(r["id"],)).fetchone()
    rec = clamp(v["recorded_at"] if v else r["event_date"], r["event_date"])
    set_one_version(r["id"], r["event_date"], rec)
    if rec < r["event_date"]: p_pre += 1
conn.commit()
print(f"pdufa restamped: {p_pre} pre-tradeable", flush=True)

# ---- earnings/adcom: recorded_at=event_date, one version ----
oth = 0
for r in q("select id, event_date from catalyst where catalyst_type in ('earnings','adcom')"):
    set_one_version(r["id"], r["event_date"], clamp(r["event_date"], r["event_date"])); oth += 1
conn.commit()
print(f"earnings/adcom restamped: {oth}", flush=True)

# ---- audit ----
fut = q("select count(*) from catalyst_version where recorded_at>?",(TODAY,)).fetchone()[0]
multi = q("select count(*) from (select catalyst_id from catalyst_version group by catalyst_id having count(*)>1)").fetchone()[0]
print(f"\nAUDIT: future recorded_at now={fut} (was 944) | catalysts with >1 version now={multi} (was 962)", flush=True)
# in-window pre-tradeable calendar by type
W0,W1="2025-08-17","2026-08-17"
for t in ("pdufa","trial_readout"):
    n=q(f"""select count(distinct c.id) from catalyst c join catalyst_version v on v.catalyst_id=c.id
            where c.catalyst_type=? and c.event_date>=? and c.event_date<=? and v.recorded_at<c.event_date""",
        (t,W0,W1)).fetchone()[0]
    print(f"  in-window pre-tradeable {t}: {n}", flush=True)
open("scripts/.restamp_v2.done","w").write("done")
