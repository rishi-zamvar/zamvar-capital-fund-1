---
status: resolved
trigger: "daemon shakedown ingested 0 ClinicalTrials.gov trial-readout catalysts (clinicaltrials absent from by_origin; only nasdaq_earnings=19). Fixable wiring bug or genuine data/timing gap?"
created: 2026-08-16
updated: 2026-08-16
---

## Current Focus

hypothesis: CONFIRMED — TWO layers. (A) The ingestion zero is a FIXABLE CONFIG BUG:
  data/ticker_sponsor_map.csv covered 0 of 21 universe tickers (only VRTX/REGN placeholders),
  so fetch_trial_readouts fired ZERO API calls and returned []. (B) A latent structural gate:
  single-source CT.gov readouts can never clear the uniform 2-source verify gate → not tradeable.
test: done — live probes + end-to-end insert/verify/tradeable
expecting: n/a
next_action: (A) FIXED + re-probed green. (B) needs operator design decision.

## Symptoms

expected: CT.gov trial-readout catalysts flow, verify, become tradeable for the 21-name universe
actual: catalysts.by_origin = {nasdaq_earnings: 19} — clinicaltrials ABSENT entirely (not even unverified); tradeable_catalyst_count=0
errors: none — silent zero
reproduction: run shakedown / daemon --once over 2025-08-22..2026-08-14; by_origin has no clinicaltrials key
started: since CT.gov provider wired (Phase 1, reused in daemon Plan 06.10)

## Eliminated

- hypothesis: CT.gov not wired into the daemon/ingest path (silently omitted like a missing slot)
  evidence: registry.build_providers wires "clinicaltrials" -> clinicaltrials.fetch_trial_readouts;
    ingest._fetch_catalysts calls providers.get("clinicaltrials"). Earnings (19) flowed through the
    SAME _fetch_catalysts loop, proving the loop runs. Wiring is complete.
  timestamp: 2026-08-16

- hypothesis: no dateable in-window readouts exist for these names (genuine data gap)
  evidence: live CT.gov probe found in-window primaryCompletionDate readouts for 16/19 operating
    names (IONS 7, INSM 5, RARE 3, MIRM 3, CLDX 3, PRAX 4, ALNY 2, NTLA 2, BBIO 3-via-subsidiaries,
    PHVS 2, RGNX 2, SRPT 1, OLMA 1, CMPS 2, TVTX 1, BCRX 1). Mix of day- and month-precision. Data
    is plentiful — it was never being requested.
  timestamp: 2026-08-16

## Evidence

- timestamp: 2026-08-16
  checked: registry.py + ingest.py (_fetch_catalysts, ingest_history) + clinicaltrials.fetch_trial_readouts
  found: CT.gov fully wired. fetch iterates tickers; for each, legal_names = sponsor_map.get(ticker, []).
    If empty, the inner "for name in legal_names" loop never runs → 0 API calls → [] for that ticker.
  implication: an empty sponsor_map for a ticker = silent zero, indistinguishable from "no data".

- timestamp: 2026-08-16
  checked: data/ticker_sponsor_map.csv vs data/seed_universe.csv (live load_sponsor_map())
  found: map contained ONLY VRTX + REGN (starter-template placeholders). 0 of the 21 universe
    tickers had an entry. Every universe fetch hit the empty-legal_names path.
  implication: ROOT CAUSE of the ingestion zero. Mirrors the PDUFA company_map question — except the
    PDUFA company_map is BUILT from seed (populated), while this sponsor_map is a curated CSV nobody
    filled for the universe.

- timestamp: 2026-08-16
  checked: LIVE CT.gov v2 query.spons for all 19 operating names, window 2025-08-22..2026-08-14
  found: exact leadSponsor.name strings (cite-or-drop, all API-returned). Subsidiary gotcha: BBIO
    trials run under "QED Therapeutics, a BridgeBio company" / "Calcilytix Therapeutics, Inc., a
    BridgeBio company" — parent "BridgeBio" is never the leadSponsor. Collaborator gotcha real
    (Univ. of Pennsylvania on an IONS study, AbbVie on RGNX) — correctly filtered by lead-sponsor rule.
    DYN/IDYA/MDGL had 0 self-sponsored readouts IN-WINDOW (canonical names captured no-date-filter for
    future windows: "Dyne Therapeutics", "IDEAYA Biosciences", "Madrigal Pharmaceuticals, Inc.").
  implication: the map is fillable from the authoritative source itself (no fabrication).

- timestamp: 2026-08-16
  checked: END-TO-END live — fetch(IONS, real name) -> store.insert_catalyst -> verify.verify_catalyst -> tradeable_catalysts
  found: 7 IONS readouts fetched + inserted; ALL 7 verify -> unverified; tradeable_catalysts = 0.
    verify_catalyst gate = `len(agreeing) >= 2 and has_primary`; a CT.gov catalyst carries exactly ONE
    (primary) source → can never reach 2 agreeing → never verified → never tradeable.
  implication: LAYER B. Even with the map fixed, a lone CT.gov readout is INGESTED-but-not-tradeable.
    Same structural 2-source gate the sibling flagged for PDUFA. CT.gov is a single authoritative
    source but is NOT treated as sufficient. (Note: earnings show the same — 19 ingested, 0 verified.)

- timestamp: 2026-08-16
  checked: date precision of live readouts + dates.classify
  found: readouts are a mix of day- and month-precision (e.g. IONS 5 day / 3 month). Month/year
    precision -> Uncertainty.window ALWAYS; day-precision single-source -> window (ESTIMATED) or soft
    (ACTUAL). Precision does NOT drop the catalyst at ingest (all 7 IONS inserted). It only affects
    the uncertainty label, which the tradeable gate does not read. So date precision is NOT the blocker;
    the 2-source gate is.
  implication: timing/precision is a non-issue for the zero. The blocker is corroboration count.

## Resolution

root_cause: |
  TWO independent layers.
  (A) INGESTION ZERO (the reported symptom — clinicaltrials absent from by_origin):
      data/ticker_sponsor_map.csv covered 0 of 21 universe tickers (only VRTX/REGN template rows).
      fetch_trial_readouts therefore fired zero CT.gov API calls for the universe and returned [] —
      a silent zero indistinguishable from "no data". CT.gov itself was correctly wired all along.
  (B) TRADEABLE ZERO (latent, shared with PDUFA): the uniform verify gate requires >=2 agreeing
      sources with >=1 primary. A CT.gov readout is a single primary source, so it is ingested as
      `unverified` and never becomes tradeable. CT.gov is authoritative but not treated as sufficient.

classification: |
  (A) = FIXABLE CONFIG BUG — fixed this session.
  (B) = GENUINE STRUCTURAL GATE / operator design decision — NOT unilaterally changed (money-path
        invariant). Identical to the sibling PDUFA finding.

fix: |
  (A) Populated data/ticker_sponsor_map.csv with the exact CT.gov leadSponsor.name for all 19
      operating universe companies (BBIO gets 2 subsidiary rows; XBI/LABD ETFs intentionally absent),
      every name verified from a live CT.gov v2 probe. Added a regression test
      (test_sponsor_map_covers_every_non_etf_universe_ticker) that fails if any operating universe
      ticker lacks a mapping — the exact check that would have caught this. Updated the CSV-load test
      for the new canonical rows + comma-quoting.
  (B) NOT changed. Requires an operator decision: either (i) treat CT.gov as authoritative-sufficient
      for trial_readout (allow a single primary source to verify), or (ii) require a 2nd corroborating
      source. This is the SAME 2-source-gate decision pending on PDUFA.
verification: |
  Re-probed through the DEFAULT path (load_sponsor_map() from the fixed CSV, no injected map):
  fetch_trial_readouts(['SRPT','IONS'], window) -> 8 trial-readout catalysts (IONS 7, SRPT 1),
  proving CT.gov catalysts now FLOW into ingestion (they will appear as by_origin.clinicaltrials).
  End-to-end confirmed they insert but remain unverified (Layer B). tests/test_clinicaltrials.py: 8 passed.
files_changed:
  - data/ticker_sponsor_map.csv (populated 19 companies / 20 sponsor rows)
  - tests/test_clinicaltrials.py (regression: universe-coverage test + updated CSV-load assertions)
