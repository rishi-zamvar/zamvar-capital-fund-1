---
status: diagnosed
trigger: "live data shakedowns ingest ZERO tradeable catalysts (tradeable_catalyst_count = 0) — PDUFA/AdCom = 0 entirely. Fixable wiring bug vs genuine free-data gap?"
created: 2026-08-16
updated: 2026-08-16
---

## Current Focus

hypothesis: CONFIRMED — the immediate zero is a genuine free-data gap (B): FR carries no PDUFA dates + no in-universe AdComs in-window; RTTNews scraper dead; curated CSV empty. Three latent design bugs (A) would block 2-source PDUFA even with data.
test: done — see Evidence
expecting: n/a
next_action: report classification to operator; latent A-bugs need operator design decision before curation can yield a tradeable catalyst

## Symptoms

expected: at least some 2-source PDUFA/AdCom catalysts flow, verify, become tradeable
actual: catalysts total=19 (ALL nasdaq_earnings), PDUFA/AdCom=0 entirely, verified=0, two_source=0
errors: none — silent zero
reproduction: run scripts/daemon.py --once or shakedown; catalysts.by_origin only nasdaq_earnings
started: since PDUFA provider added (Plan 06.9-05)

## Eliminated

- hypothesis: company_map empty/unwired in ingest path
  evidence: ingest.ingest_history builds company_map={ticker:[company_name]} from seed; registry wires pdufa lambda with company_map kwarg; _fetch_catalysts passes it. All present.
  timestamp: 2026-08-16

## Evidence

- timestamp: 2026-08-16
  checked: registry.build_providers + ingest.ingest_history + pdufa.fetch source
  found: wiring complete. FR query uses conditions[term]="advisory committee" + agency FDA. _attribute matches company/drug names ONLY against doc title.
  implication: attribution depends on drug/company name appearing in FR notice TITLE — needs live verification.

- timestamp: 2026-08-16
  checked: LIVE FR API, exact provider query, window 2025-08-22..2026-08-14
  found: 46 FDA AdCom notices in-window (155 over 2.6yr). Modern titles DO carry company+drug (e.g. "From Replimune, Inc. for Vusolimogene"), but ZERO of the 21 universe companies appear in ANY AdCom title over 2.6 years. FR publishes AdCom notices only — NOT PDUFA action dates (those are private FDA/company comms, never in the Federal Register).
  implication: FR structurally cannot supply a PDUFA date; and no in-universe AdCom exists in-window. FR contribution = 0, correctly.

- timestamp: 2026-08-16
  checked: LIVE RTTNews https://www.rttnews.com/corpinfo/fdacalendar.aspx
  found: HTTP 200, 143KB, but ZERO <table>/<tr>/<td> tags — the FDA calendar is now JS/AJAX-rendered. _parse_rttnews(html) finds 0 rows for any ticker. Scraper is dead (page changed since the 2026-08-15 research verification).
  implication: RTTNews contribution = 0 regardless of universe. The YELLOW half of the 2-source pair is broken.

- timestamp: 2026-08-16
  checked: data/pdufa_curated.csv + who loads it
  found: CSV is empty (header only). load_curated_pdufa is wired into calendar/refresh.py main() ONLY — NOT into scripts/daemon.py run_cycle (the shakedown path). Daemon never loads curated PDUFA at all.
  implication: curated path is both empty AND not on the daemon path.

- timestamp: 2026-08-16
  checked: store.insert_catalyst dedup + pdufa merge key + load_curated_pdufa external_ref
  found: (a) merge key is (ticker, event_date); FR event_date = AdCom MEETING date, RTTNews = PDUFA ACTION date — different dates for same drug → never merge → two 1-source catalysts. (b) attribution matches full legal company_name ("BridgeBio Pharma") against FR title format ("From BridgeBio, Inc. for <Drug>") — won't match; drug names not in company_map at all. (c) curated rows use external_ref=curated:tk:type:date, live pdufa uses pdufa:tk:date — different refs; insert_catalyst DELETE+replaces sources on same ref, so two curated rows for one event overwrite each other → curated can NEVER reach the >=2-agreeing gate.
  implication: even WITH data, the 2-source PDUFA design has 3 latent bugs that block verification.

## Resolution

root_cause: |
  IMMEDIATE ZERO = genuine free-data gap. Over the shakedown window there are
  literally no free-data 2-source PDUFA/AdCom events for the 21 names:
  (1) FedRegister publishes AdCom notices only, not PDUFA action dates, and none
  of the 21 companies had an AdCom in-window (0/155 over 2.6yr);
  (2) RTTNews scraper is dead — page is now JS-rendered, 0 parseable rows;
  (3) pdufa_curated.csv is empty and isn't even loaded on the daemon path.
  The prime suspect (empty/unwired company_map) was DISPROVEN — the map is built
  from seed and correctly threaded through.
fix: |
  NOT IMPLEMENTED (correctly). Cannot fix (B) without fabricating operator-owned
  dates. The 3 latent design bugs (merge-key mismatch, title-attribution weakness,
  curated-can't-reach-2-source) require an operator schema/design decision and
  cannot be verified end-to-end without real curated data. Specified for a planned
  fix below.
verification: |
  Live-probed all three free sources against the exact provider query + universe.
  FR=0 in-universe (2.6yr), RTTNews=0 rows (dead), curated=empty. Reproducible.
files_changed: []
