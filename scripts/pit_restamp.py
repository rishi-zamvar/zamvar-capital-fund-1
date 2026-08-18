"""PIT knowability restamp — makes the bitemporal walk-forward correct (non-vacuous, leak-free).

The serving gateway resolves catalysts by catalyst_version.recorded_at <= cutoff. Backward discovery
stamped recorded_at = discovery wall-clock (Aug 2026) -> every catalyst invisible at any past cutoff
-> vacuous backtest. This restamps recorded_at (and catalyst.last_verified_at) to the true KNOWABILITY
date:

  * readout / earnings / adcom : recorded_at = event_date. For 8-K-announced readouts the filing IS the
    event day, so it is knowable same-day (correctly NOT pre-tradeable; feeds the statistical sleeve).
  * pdufa : recorded_at = the ACCEPTANCE 8-K filing date (< event_date) recovered from data.sec.gov,
    so the PDUFA is pre-tradeable from acceptance onward. Fallback = event_date if unrecoverable
    (SAFE: never a leak, just misses that pre-event trade).

Objective, no judgment. data.sec.gov = free-unlimited (UA required). Idempotent.
"""
import sqlite3, re, time, json
import httpx
from catalyst_trader.config import settings

UA = {"User-Agent": settings.sec_user_agent}
DB = "catalyst.db"
conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row; q = conn.execute

# 1) collect PDUFA accession -> (cik, accession_nodash) and unique CIKs
pdufa = []
ciks = set()
for r in q("select id, event_date, external_ref from catalyst where catalyst_type='pdufa'"):
    m = re.search(r"/data/(\d+)/(\d{18})/", r["external_ref"] or "")
    if m:
        pdufa.append((r["id"], r["event_date"], m.group(1), m.group(2)))
        ciks.add(m.group(1))
    else:
        pdufa.append((r["id"], r["event_date"], None, None))
print(f"pdufa rows: {len(pdufa)} | unique CIKs to fetch: {len(ciks)}", flush=True)

# 2) fetch filingDate map from data.sec.gov submissions (free, rate-limited)
acc_to_date = {}
with httpx.Client(headers=UA, timeout=30) as cli:
    for i, cik in enumerate(sorted(ciks), 1):
        url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
        try:
            d = cli.get(url).json()
            rec = d.get("filings", {}).get("recent", {})
            accs = rec.get("accessionNumber", []); dts = rec.get("filingDate", [])
            for a, dt in zip(accs, dts):
                acc_to_date[a.replace("-", "")] = dt
            # older filings overflow
            for extra in d.get("filings", {}).get("files", []):
                try:
                    d2 = cli.get(f"https://data.sec.gov/submissions/{extra['name']}").json()
                    for a, dt in zip(d2.get("accessionNumber", []), d2.get("filingDate", [])):
                        acc_to_date[a.replace("-", "")] = dt
                except Exception:
                    pass
        except Exception as e:
            print(f"  CIK {cik}: fetch err {e}", flush=True)
        time.sleep(0.15)  # SEC courtesy (<10 req/s)
        if i % 10 == 0: print(f"  fetched {i}/{len(ciks)} CIKs, {len(acc_to_date)} accessions mapped", flush=True)
print(f"accession->filingDate map: {len(acc_to_date)} entries", flush=True)

# 3) restamp. one catalyst_version per catalyst (latest wins); update recorded_at + last_verified_at.
def set_recorded(cid, dt):
    conn.execute("UPDATE catalyst_version SET recorded_at=? WHERE catalyst_id=?", (dt, cid))
    conn.execute("UPDATE catalyst SET last_verified_at=? WHERE id=?", (dt, cid))

pdufa_pre, pdufa_fb, other = 0, 0, 0
# pdufa
for cid, ev, cik, acc in pdufa:
    fd = acc_to_date.get(acc) if acc else None
    if fd:
        set_recorded(cid, fd); pdufa_pre += (1 if fd < ev else 0); pdufa_fb += (0 if fd < ev else 1)
    else:
        set_recorded(cid, ev); pdufa_fb += 1
# readout / earnings / adcom = event_date
for r in q("select id, event_date from catalyst where catalyst_type in ('trial_readout','earnings','adcom')"):
    set_recorded(r["id"], r["event_date"]); other += 1
conn.commit()
print(f"restamped: pdufa pre-tradeable(filing<event)={pdufa_pre}  pdufa fallback(=event)={pdufa_fb}  other(=event)={other}", flush=True)

# 4) audit: how many in-window pdufa are now pre-tradeable (recorded_at < event_date)
W0, W1 = "2025-08-17", "2026-08-17"
rows = q("""select cat.catalyst_type ct, cat.event_date ev, v.recorded_at rd
            from catalyst cat join catalyst_version v on v.catalyst_id=cat.id
            where cat.event_date>=? and cat.event_date<=? and cat.catalyst_type in ('pdufa','trial_readout','adcom')""",
         (W0, W1)).fetchall()
pre = [r for r in rows if r["rd"] and r["rd"][:10] < r["ev"]]
print(f"\nIN-WINDOW: {len(rows)} tradeable-type catalysts | pre-tradeable (recorded_at<event): {len(pre)}", flush=True)
from collections import Counter
print("pre-tradeable by type:", dict(Counter(r["ct"] for r in pre)), flush=True)
open("scripts/.pit_restamp.done", "w").write(json.dumps(
    {"pdufa_pre": pdufa_pre, "pdufa_fb": pdufa_fb, "other": other, "inwin_pre": len(pre)}))
print("DONE", flush=True)
