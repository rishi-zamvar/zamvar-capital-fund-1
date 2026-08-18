"""A3 signed-move recompute + A4 cross-source dedup. Both ZERO paid API (cached daily bars / SQL).

A4: collapse (ticker,event_date,type) duplicates keeping the earliest-filed (lowest id); cascade-
    delete the redundant rows' moves/versions/sources.
A3: recompute realized_move SIGNED (close(T+2)/close(T-1)-1, no abs) from cached daily bars. The
    universe screen re-abs's so membership is unchanged; signed values feed the playbook + reporting.
    Only UPDATEs on a successful recompute (never nulls an existing value).
"""
import sqlite3
from datetime import date, timedelta
from catalyst_trader.providers.prices import get_daily_bars, _yf_daily, _nasdaq_daily_bars

FREE_DAILY = [_yf_daily, _nasdaq_daily_bars]
conn = sqlite3.connect("catalyst.db"); conn.row_factory = sqlite3.Row; q = conn.execute

# ---- A4: dedup ----
groups = q("""select ticker,event_date,catalyst_type,group_concat(id) ids, count(*) c
              from catalyst group by ticker,event_date,catalyst_type having c>1""").fetchall()
deleted = 0
for g in groups:
    ids = sorted(int(x) for x in g["ids"].split(","))
    keep, drop = ids[0], ids[1:]
    for d in drop:
        for t in ("catalyst_move", "catalyst_version", "catalyst_source"):
            conn.execute(f"DELETE FROM {t} WHERE catalyst_id=?", (d,))
        conn.execute("DELETE FROM catalyst WHERE id=?", (d,))
        deleted += 1
conn.commit()
print(f"A4 dedup: {len(groups)} dup groups collapsed, {deleted} redundant catalysts deleted", flush=True)

# ---- A3: signed recompute ----
def signed_move(ticker, event_date):
    if len(event_date) != 10: return None
    start = (date.fromisoformat(event_date) - timedelta(days=14)).isoformat()
    end = (date.fromisoformat(event_date) + timedelta(days=14)).isoformat()
    bars = get_daily_bars(ticker, start, end, providers=FREE_DAILY)
    if not bars: return None
    bars = sorted(bars, key=lambda b: b["week_end"])
    dts = [b["week_end"] for b in bars]
    t0 = next((i for i, d in enumerate(dts) if d >= event_date), None)
    if t0 is None: return None
    i_lo, i_hi = t0 - 1, t0 + 2
    if i_lo < 0 or i_hi >= len(bars): return None
    c_lo, c_hi = bars[i_lo].get("close"), bars[i_hi].get("close")
    if not c_lo or not c_hi: return None
    return c_hi / c_lo - 1.0  # SIGNED

rows = q("""select m.id mid, c.ticker tk, c.event_date ev, m.realized_move old
            from catalyst_move m join catalyst c on c.id=m.catalyst_id""").fetchall()
upd = same = miss = flipped = 0
for r in rows:
    s = signed_move(r["tk"], r["ev"])
    if s is None: miss += 1; continue
    conn.execute("UPDATE catalyst_move SET realized_move=? WHERE id=?", (s, r["mid"]))
    upd += 1
    if r["old"] is not None and s < 0: flipped += 1
conn.commit()
print(f"A3 signed: updated {upd} moves ({flipped} now negative), {miss} unrecomputable (kept)", flush=True)

# audit: direction split now realistic?
neg = q("select count(*) from catalyst_move where realized_move<0").fetchone()[0]
pos = q("select count(*) from catalyst_move where realized_move>=0").fetchone()[0]
print(f"direction split: up={pos} ({pos/(pos+neg):.0%}) down={neg} ({neg/(pos+neg):.0%})", flush=True)
open("scripts/.polish.done","w").write("done")
