# Curated data files — HUMAN CURATION REQUIRED

These three CSVs are the phase's one **money-critical human-curation task** (Plan
01-06, Task 2). No PDUFA/AdCom **date** may originate from an LLM's memory — every
date is entered by hand from a named source with a real `source_url`. The code
(universe builder, two-source verifier, CT.gov lead-sponsor filter, curated-PDUFA
loader) is fully built and tested against fixtures. What remains is **your** data.

Status: **PENDING CURATION** — the files ship as documented templates. `seed_universe.csv`
and `ticker_sponsor_map.csv` carry labelled VRTX/REGN example rows so the pipeline
runs end-to-end; `pdufa_curated.csv` is header-only (no invented dates).

## 1. `seed_universe.csv`
Columns: `ticker,company_name,market_cap,adv_usd,therapeutic_area,delisted`

Add ~20–30 real life-science/biotech tickers with known upcoming catalysts (seed by
hand from a free source such as BiopharmaWatch's 2026 PDUFA calendar). Fill
`market_cap` (USD), `adv_usd` (avg daily $ volume) and `therapeutic_area` — FMP-live
enrichment of the numeric fields is a documented follow-up, so approximate curated
values are acceptable to start. Include a few delisted names (`delisted=1`) for
backtest realism; the builder **retains** them (survivorship-free). The two example
rows' `market_cap`/`adv_usd` are approximate placeholders — replace with FMP figures.

## 2. `ticker_sponsor_map.csv`
Columns: `ticker,legal_sponsor_name`

Each ticker's **exact** legal `leadSponsor.name` as it appears in ClinicalTrials.gov
(e.g. `VRTX -> "Vertex Pharmaceuticals Incorporated"`). Loose sponsor search pulls in
collaborator/university trials, so a study is attributed to a ticker only when its
lead sponsor matches a name here. Verify against a live CT.gov query for at least 3
names. VRTX and REGN are already filled with real legal names.

## 3. `pdufa_curated.csv`
Columns: `ticker,catalyst_type,event_date,source_name,source_url,source_type`

`catalyst_type` is `pdufa` or `adcom`. **Every row MUST carry a real `source_url`**
(company IR press release / FDA). Each row enters the same verify pipeline as the
automated feeds and starts **unverified** — a hand-typed date needs a 2nd (ideally
primary) corroborating source before it is tradeable. It is header-only until you
add real, source-cited rows (the executor must never invent a PDUFA date).

Keep this file comment-free: the structural check
`! awk -F, 'NR>1 && $5=="" {print}' data/pdufa_curated.csv | grep -q .`
must find no data row missing a `source_url`.

## Run the pipeline end-to-end after curating
```bash
.venv/bin/python -m catalyst_trader.calendar.refresh   # needs FMP_API_KEY for earnings; CT.gov + curated work without it
.venv/bin/python -c "from catalyst_trader.db import connect,migrate; from catalyst_trader.universe.build import build_snapshot; c=connect(); migrate(c); print('included:', build_snapshot(c,'2026-08-14'))"
```
Confirm the seed list is populated + sourced, and that no PDUFA row lacks a `source_url`.
