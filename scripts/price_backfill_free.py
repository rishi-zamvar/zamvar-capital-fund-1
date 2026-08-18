"""A1 — free-source weekly price backfill for the universe-in-play.

Populates price_bar (weekly) for every tradeable universe name using FREE-UNLIMITED
providers ONLY (yfinance / Nasdaq). Paid fallbacks (Tiingo/AV) are NOT passed, so a
free-source miss is SKIPPED, never escalated to quota. Idempotent (upsert). Reads the
universe list from data/universe_profiles.json (excludes delisted).
# ponytail: weekly bars only here — daily move-windows are pulled on-demand (cached) by
# the move-recompute + backtest via get_daily_bars; no need to pre-fetch them.
"""
import json, sqlite3, sys, time
from catalyst_trader.providers.prices import get_weekly_bars, _yf_weekly, _nasdaq_daily
from catalyst_trader import ingest

FREE = [_yf_weekly, _nasdaq_daily]                 # free-unlimited ONLY — no paid fallback
DROP = {"CMRX", "BXRXQ", "LIANY"}
START, END = "2020-01-01", "2026-08-17"
DB = "catalyst.db"

prof = json.load(open("data/universe_profiles.json"))
tickers = [r["ticker"] for r in prof if r["ticker"] not in DROP]
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row              # store.upsert_bars reads existing["id"]
have = {t for (t,) in conn.execute("select distinct ticker from price_bar")}

done, skipped, already = [], [], []
for i, tk in enumerate(tickers, 1):
    n_existing = conn.execute("select count(*) from price_bar where ticker=?", (tk,)).fetchone()[0]
    if n_existing >= 200:                          # ~4yr of weekly bars already -> skip
        already.append(tk); continue
    try:
        bars = get_weekly_bars(tk, START, END, providers=FREE) or []
    except Exception as e:
        bars = []
        print(f"[{i}/{len(tickers)}] {tk}: ERROR {e}", flush=True)
    if not bars:
        skipped.append(tk)
        print(f"[{i}/{len(tickers)}] {tk}: no free-source bars — SKIP (no quota spent)", flush=True)
        continue
    ingest._upsert_price_bars(conn, tk, bars, delisted=False)
    conn.commit()
    done.append(tk)
    print(f"[{i}/{len(tickers)}] {tk}: {len(bars)} weekly bars upserted", flush=True)

print("\n=== A1 BACKFILL DONE ===", flush=True)
print(f"upserted:{len(done)}  already-had:{len(already)}  skipped(free-miss):{len(skipped)}", flush=True)
print("skipped:", skipped, flush=True)
cov = {t for (t,) in conn.execute("select distinct ticker from price_bar")}
print(f"price_bar coverage now: {len(cov & set(tickers))}/{len(tickers)} universe names", flush=True)
open("scripts/.a1_backfill.done", "w").write(json.dumps(
    {"done": done, "already": already, "skipped": skipped, "coverage": len(cov & set(tickers)), "universe": len(tickers)}))
