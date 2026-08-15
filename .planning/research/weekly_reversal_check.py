"""Sanity check: measured weekly reversal/continuation base rates, liquid biotech cohort.

P(next week up | last week ret <= -X%), raw and idio (beta-vs-XBI adjusted trigger).
Weekly = W-FRI close-to-close. 2016-01-01..2026-08-01 via yfinance.
"""
import warnings
warnings.filterwarnings("ignore")
import pandas as pd
import yfinance as yf

TICKERS = ["VRTX","REGN","ALNY","SRPT","BMRN","IONS","NBIX","INCY","EXEL","UTHR",
           "RARE","ACAD","MRNA","JAZZ","HALO","CYTK","INSM","APLS","AXSM","KRTX"]
BENCH = "XBI"

px = yf.download(TICKERS + [BENCH], start="2016-01-01", end="2026-08-01",
                 auto_adjust=True, progress=False)["Close"]
wk = px.resample("W-FRI").last()
ret = wk.pct_change()

bench = ret[BENCH]
rows = []
for thresh in (-0.05, -0.10, -0.15):
    for mode in ("raw", "idio", "sector"):
        nxt_all, cnt = [], 0
        for t in TICKERS:
            r = ret[t].dropna()
            b = bench.reindex(r.index)
            beta = r.cov(b) / b.var()  # full-sample beta (sanity check only)
            idio = r - beta * b
            if mode == "raw":
                trig = r <= thresh
            elif mode == "idio":  # drop mostly the stock's own move
                trig = (r <= thresh) & (idio <= thresh * 0.5)
            else:  # sector: stock dropped but idio move small -> beta-driven drop
                trig = (r <= thresh) & (idio.abs() < 0.5 * abs(thresh))
            nxt = r.shift(-1)[trig].dropna()
            nxt_all.append(nxt)
            cnt += int(trig.sum())
        nxt = pd.concat(nxt_all)
        rows.append(dict(thresh=thresh, mode=mode, n=len(nxt),
                         p_up=round((nxt > 0).mean(), 3),
                         mean_next=round(nxt.mean(), 4),
                         med_next=round(nxt.median(), 4)))

# continuation: up-week follow-through, raw + big-up
for thresh in (0.05, 0.10):
    nxt_all = []
    for t in TICKERS:
        r = ret[t].dropna()
        nxt_all.append(r.shift(-1)[r >= thresh].dropna())
    nxt = pd.concat(nxt_all)
    rows.append(dict(thresh=thresh, mode="up-raw", n=len(nxt),
                     p_up=round((nxt > 0).mean(), 3),
                     mean_next=round(nxt.mean(), 4), med_next=round(nxt.median(), 4)))

# unconditional baseline
allr = pd.concat([ret[t].dropna() for t in TICKERS])
rows.append(dict(thresh=None, mode="uncond", n=len(allr),
                 p_up=round((allr > 0).mean(), 3),
                 mean_next=round(allr.mean(), 4), med_next=round(allr.median(), 4)))

print(pd.DataFrame(rows).to_string(index=False))
