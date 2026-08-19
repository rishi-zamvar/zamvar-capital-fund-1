---
phase: 07.8-live-desk-wiring-pre-paper-hardening
plan: slice2.5
type: execute
wave: 1
depends_on: [slice2]
autonomous: false
requirements: [DILIG-02, DILIG-03]
files_modified:
  - src/catalyst_trader/providers/edgar.py
  - src/catalyst_trader/desk/diligence_inputs.py
  - tests/test_providers_edgar.py
  - tests/test_desk_diligence_inputs.py
user_setup: []

must_haves:
  truths:
    - "edgar.fundamentals exposes cash_usd + monthly_burn_usd from the XBRL facts it ALREADY fetches (reusing the burn derivation _runway_months uses — no duplicated math, no second fetch)."
    - "A free EDGAR Form-4 net-insider signal (edgar.insider_net) is fetchable per ticker over a caller-supplied trailing window, degrading to None on a genuine miss (edgartools error / all filings unparseable) and returning a real 0 when the tape is simply quiet."
    - "make_diligence_inputs assembles a grounded financials dict {cash_usd, monthly_burn_usd, months_to_catalyst} when the XBRL facts exist, else OMITS the key + flags degraded (never fabricated)."
    - "make_diligence_inputs assembles the FULL ownership dict {short_interest_pct, days_to_cover, insider_net} ONLY when all three ground (FINRA + shares + insider_net); a single miss OMITS the whole key + flags — never a partial dict (which would KeyError at diligence.py:269)."
    - "The Slice-2 unconditional financials/ownership omit is gone; a real promoted candidate reaches DD with both money dims grounded, so run_diligence returns a thesis-based GO/NO-GO, not a data-gap NO-GO."
    - "Every code-task test is fully offline (fake edgartools Form-4/facts + FINRA injected); zero live network. Existing suites (test_providers_edgar, test_providers_finra, test_desk_diligence_inputs) stay green; changes are additive/backward-compatible."
  artifacts:
    - path: "src/catalyst_trader/providers/edgar.py"
      provides: "fundamentals extended (cash_usd + monthly_burn_usd) + insider_net Form-4 net fetcher"
      contains: "def insider_net"
      min_lines: 150
    - path: "src/catalyst_trader/desk/diligence_inputs.py"
      provides: "financials + ownership money-dim sourcing wired into make_diligence_inputs; unconditional omit removed"
      contains: "def make_diligence_inputs"
      min_lines: 90
    - path: "tests/test_providers_edgar.py"
      provides: "offline cash_usd/monthly_burn_usd + insider_net coverage (fake Form-4 filings, degrade paths)"
    - path: "tests/test_desk_diligence_inputs.py"
      provides: "sourced-when-present / omit+flag-on-miss for financials + ownership (fake sources)"
  key_links:
    - from: "src/catalyst_trader/desk/diligence_inputs.py"
      to: "edgar.fundamentals"
      via: "single fundamentals fetch reused for financials cash/burn AND ownership shares_outstanding"
      pattern: "fundamentals"
    - from: "src/catalyst_trader/desk/diligence_inputs.py"
      to: "edgar.insider_net"
      via: "Form-4 net over recent trailing window"
      pattern: "insider_net"
    - from: "src/catalyst_trader/desk/diligence_inputs.py"
      to: "finra.fetch"
      via: "short_interest + days_to_cover at recent_si_settlement(as_of)"
      pattern: "finra"
    - from: "src/catalyst_trader/providers/edgar.py"
      to: "edgartools Form4"
      via: "Company.get_filings(form='4', filing_date=range) -> .obj().get_ownership_summary().net_change"
      pattern: "get_ownership_summary"
---

<objective>
Source the two structurally-ungrounded DD money dimensions — **financials** (cash / burn / months-to-catalyst) and **ownership** (short-interest % / days-to-cover / net insider) — from FREE point-in-time data (SEC EDGAR XBRL + EDGAR Form-4 + FINRA), so `run_diligence` reaches a REAL thesis-based GO/NO-GO instead of the Slice-2 forced NO-GO. This slice GATES Slice-4 paper trading (which trades nothing until DD can ground these dims).

Purpose: Slice 2 wired DD→MD but left `financials` and `ownership` unconditionally omitted → every real candidate hit an ungrounded-money NO-GO → Slice-4 paper trading would be vacuous. Slice 2.5 grounds them honestly (source-or-degrade, never fabricate).

Output: extended `edgar.fundamentals` + a new free `edgar.insider_net` Form-4 fetcher, both wired into `make_diligence_inputs`; the Slice-2 omit removed; capped by ONE combined live human-verify run (the deferred Slice-2 live check + the Slice-2.5 proof in one).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/TOKEN-NOTES.md
@.planning/phases/07.8-live-desk-wiring-pre-paper-hardening/slice2/SLICE2-PLAN.md

@src/catalyst_trader/providers/edgar.py
@src/catalyst_trader/providers/finra.py
@src/catalyst_trader/desk/diligence_inputs.py
@src/catalyst_trader/desk/diligence.py
@src/catalyst_trader/providers/registry.py

<interfaces>
<!-- Verified against the installed edgartools 5.49.0 + the codebase. Executor uses these directly. -->

CONSUMER CONTRACTS (desk/diligence.py — direct-subscript, missing-key-raises):
  financials_context(raw)  needs raw {cash_usd, monthly_burn_usd, months_to_catalyst}  (diligence.py:246-257)
  ownership_context(raw)   needs raw {short_interest_pct, days_to_cover, insider_net}   (diligence.py:260-270)
    None/{} -> None -> ungrounded money dim -> synthesize_verdict forces NO-GO.
    A PARTIAL ownership dict KeyErrors at line 269 — supply ALL THREE or OMIT the whole key.

edgar.fundamentals (edgar.py:112-150) TODAY returns {shares_outstanding, cash_runway_months, provenance}.
  Internally it ALREADY fetches:
    cash = facts.get_concept("cash_and_equivalents", return_metadata=True)   # {value, period, filing_date, ...}
    ocf  = facts.get_concept("operating_cash_flow", return_metadata=True)
  and _runway_months(cash, ocf) (edgar.py:98-109) ALREADY derives `monthly_burn = -ocf / months`
  (months from _period_months on the OCF period string). REUSE that derivation — do not duplicate it.

finra.fetch(ticker, settlement_date) (finra.py:36-77) -> {short_interest:int, days_to_cover:float,
  si_settlement_date, provenance} | None. REUSE verbatim.
registry.recent_si_settlement(end_iso) -> most-recent published FINRA settlement date. REUSE for the date.

edgartools Form-4 surface (VERIFIED, offline-introspected):
  edgar.Company(ticker).get_filings(form="4", filing_date="YYYY-MM-DD:YYYY-MM-DD")  # date-range supported
     -> iterable of EntityFiling; each filing.obj() -> edgar.ownership.Form4
  Form4.get_ownership_summary() -> TransactionSummary with properties:
     .net_change  (total net shares; +buy / -sell)   <- ROBUST primary (always present)
     .net_value   (total net USD; may be None when a txn carries no price)
  Reuse edgar.py::_set_identity() (SEC UA gate) exactly as fundamentals/fetch do.

make_diligence_inputs closure signature (diligence_inputs.py:76):
  diligence_inputs(conn, ticker, catalyst, *, entry, risk_inputs, exit_by_date, pair=None, as_of)
    -> (DiligenceInput, market_data, degraded)
</interfaces>

<test_patterns>
<!-- test_providers_edgar.py monkeypatches edgar_lib.Company + edgar_lib.set_identity against fakes
     pinned to the real typed surface (_FakeCompany/_FakeFacts/_FakeFiling). Extend the SAME fakes:
       - _FakeCompany.get_filings(form=["4"], filing_date=...) -> list of _FakeFiling
       - add a .obj() to _FakeFiling returning a fake Form4 whose get_ownership_summary() returns an
         object with .net_change (and .net_value). NO network, NO real edgartools parse.
     test_desk_diligence_inputs.py injects fake sources via make_diligence_inputs(...) kwargs. -->
</test_patterns>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Provider layer — expose cash_usd/monthly_burn_usd on fundamentals + add free edgar.insider_net (Form-4)</name>
  <files>src/catalyst_trader/providers/edgar.py, tests/test_providers_edgar.py</files>
  <behavior>
    fundamentals (extend, additive — existing keys unchanged):
      - Test: fixture facts (cash 300M, OCF -90M over Q2=6mo) -> out["cash_usd"] == 300000000.0 AND
        out["monthly_burn_usd"] == pytest.approx(15000000.0) (== the burn _runway_months already derives).
      - Test: existing keys (shares_outstanding, cash_runway_months, provenance) still present + unchanged
        (backward-compat; test_fundamentals_shares_and_runway still green).
      - Test: not burning (OCF >= 0) -> monthly_burn_usd is None (never a fabricated/negative burn);
        cash_usd still emitted if cash present.
      - Test: missing cash fact -> cash_usd is None.
    insider_net(ticker, *, since, until):  (net insider Form-4 signal over [since, until], both ISO)
      - Test: two fake Form-4 filings with net_change +1000 and -3000 -> insider_net == -2000
        (net shares; negative = net selling).
      - Test: NO Form-4 filings in the window -> returns 0.0 (a quiet tape is a REAL datum, not a miss).
      - Test: edgartools raises (CompanyNotFoundError) -> None (degrade, no exception).
      - Test: every filing.obj() raises/unparseable -> None (all-fail degrade; a partial-fail SKIPS the
        bad filings and still sums the good ones).
      - Test: missing SEC UA -> RuntimeError (reuse _set_identity, matching fundamentals/fetch).
  </behavior>
  <action>
    In providers/edgar.py:
    1. Refactor the burn derivation out of _runway_months into a tiny helper `_monthly_burn(ocf_meta) -> float | None`
       ( `-ocf/months` when ocf<0 and months known, else None ), and have _runway_months CALL it (no duplicated
       arithmetic — DILIG rule: no duplication). Then in `fundamentals`, add to the returned dict:
         "cash_usd": cash.get("value") if cash else None,
         "monthly_burn_usd": _monthly_burn(ocf),
       Keep ALL existing keys byte-for-byte (shares_outstanding, cash_runway_months, provenance). Degrade rules
       unchanged (any edgartools error / no usable facts -> None; never fabricate).
    2. Add `insider_net(ticker, *, since, until) -> float | None`:
         _set_identity()                                   # SEC UA gate (raises if unset)
         try: company = edgar.Company(ticker)
              filings = company.get_filings(form="4", filing_date=f"{since}:{until}")
         except Exception: log.warning; return None        # genuine miss -> degrade
         total, parsed = 0.0, 0
         for f in filings:
             try: summary = f.obj().get_ownership_summary(); nc = summary.net_change
             except Exception: continue                    # skip a single unparseable filing
             if nc is not None: total += float(nc); parsed += 1
         if not filings: return 0.0                         # quiet tape = real 0, grounded (NOT a miss)
         return total if parsed else None                  # all-fail -> degrade
       Use `net_change` (shares) as the signal — robust (net_value can be None with no price). The trailing
       WINDOW is the caller's concern (since/until args) — NO magic literal inside the provider (window default
       lives in diligence_inputs PARAMS, Task 2).
    Addresses: the ONE new fetcher the sourcing map flags — free EDGAR Form-4 net-insider (edgartools already a dep).
    In tests/test_providers_edgar.py: extend _FakeFiling with a `.obj()` returning a fake Form4 whose
    get_ownership_summary() returns a stub with .net_change/.net_value; extend _FakeCompany.get_filings to honor
    form=["4"]/filing_date. All offline (monkeypatch edgar_lib.Company + set_identity) — no network.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_providers_edgar.py -x -q</automated>
  </verify>
  <done>fundamentals emits cash_usd + monthly_burn_usd (existing keys unchanged); insider_net sums Form-4 net_change over a window with correct quiet-tape(0)/degrade(None)/partial-skip semantics; edgar suite green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wire financials + ownership into make_diligence_inputs (source-or-omit) + remove the Slice-2 unconditional omit</name>
  <files>src/catalyst_trader/desk/diligence_inputs.py, tests/test_desk_diligence_inputs.py</files>
  <behavior>
    - Test: financials_source returns fundamentals with cash_usd/monthly_burn_usd -> md["financials"] ==
      {cash_usd, monthly_burn_usd, months_to_catalyst} with months_to_catalyst derived from (event_date - as_of).
    - Test: fundamentals present but monthly_burn_usd is None (not burning) -> "financials" OMITTED + a degrade flag
      (ungrounded, honest NO-GO). fundamentals None -> same.
    - Test: finra + shares + insider_net all present -> md["ownership"] == {short_interest_pct == si/shares,
      days_to_cover == finra days_to_cover, insider_net} (full dict).
    - Test: finra None -> "ownership" OMITTED + flag. shares None -> OMITTED + flag. insider_net None -> OMITTED + flag.
      NEVER a partial dict (a 2-key ownership would KeyError at diligence.py:269).
    - Test: insider_net == 0.0 (quiet tape) with finra+shares present -> ownership STILL GROUNDS (0 is a real datum),
      full dict emitted (0 is not a miss).
    - Test: all-sources-present happy path -> set(md) includes "financials" AND "ownership" (Slice-2's
      test_financialsAlwaysOmitted_B1 / test_ownershipAlwaysOmitted_C4 are REPLACED by these source-or-omit tests).
    - Test: existing options/liquidity/hedge/trial behavior UNCHANGED (regression).
  </behavior>
  <action>
    In desk/diligence_inputs.py:
    1. Add module PARAMS (missing-key-raises, no magic literals):
         _INPUTS_PARAMS = {"form4_lookback_days": 90, "days_per_month": 30.4375}
       (form4_lookback_days = the Form-4 trailing window; days_per_month = months_to_catalyst conversion.)
    2. Add two injectable sources to make_diligence_inputs signature (production defaults are free + cache-shaped):
         financials_source=None,  # -> edgar.fundamentals
         finra_source=None,       # -> lambda tk: finra.fetch(tk, registry.recent_si_settlement(as_of))  (bind as_of inside closure)
         insider_source=None,     # -> lambda tk, since, until: edgar.insider_net(tk, since=since, until=until)
       Default them with `or` (mirror options_source/trial_source). Import edgar, finra, registry.
    3. Inside the closure, FETCH fundamentals ONCE and REUSE it for BOTH dims (no double edgar hit — cache-first rule):
         fund = financials_source(ticker)      # {shares_outstanding, cash_usd, monthly_burn_usd, cash_runway_months, provenance} | None
       financials: if fund and fund.get("cash_usd") is not None and fund.get("monthly_burn_usd") is not None:
           months_to_catalyst = round(days_to_event / _INPUTS_PARAMS["days_per_month"], 2)
           market_data["financials"] = {"cash_usd":..., "monthly_burn_usd":..., "months_to_catalyst": months_to_catalyst}
         else: OMIT + degraded.append("financials: ... ungrounded, NO-GO").
       ownership: shares = fund.get("shares_outstanding") if fund else None
           si = finra_source(ticker)   # {short_interest, days_to_cover, ...} | None
           since = (as_of - form4_lookback_days).isoformat(); until = as_of
           net = insider_source(ticker, since, until)   # 0.0 quiet | float | None
         if si and shares and net is not None:   # note: net==0.0 GROUNDS (0 is a real datum, `is not None`)
             market_data["ownership"] = {"short_interest_pct": si["short_interest"]/shares,
                                          "days_to_cover": si["days_to_cover"], "insider_net": net}
         else: OMIT + degraded.append("ownership: ... ungrounded, NO-GO").   # whole-dict-or-omit; NEVER partial
    4. DELETE the unconditional `degraded = [_FINANCIALS_DEGRADE, _OWNERSHIP_DEGRADE]` and the two _DEGRADE
       constants; `degraded` is now built up ONLY from genuine misses (empty when both ground). Keep the honest
       Slice-2 `degraded` pattern (a flag per genuinely-missing source).
    Everything additive/backward-compatible: options/liquidity/hedge/trial code untouched. All tests offline
    (inject fake financials_source/finra_source/insider_source; NO network, NO LLM).
    In tests/test_desk_diligence_inputs.py: replace the two "always omitted" tests with source-or-omit coverage
    per <behavior>; update the module docstring's B1/C4 note (now SOURCED, was deferred to Slice 2.5).
    Addresses: un-degrade the Slice-2 omits so DD reaches a real GO/NO-GO (DILIG-02/03).
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_desk_diligence_inputs.py tests/test_desk_diligence.py tests/test_live_desk_decision.py tests/test_providers_finra.py -x -q</automated>
  </verify>
  <done>make_diligence_inputs sources financials + ownership from a single fundamentals fetch + FINRA + Form-4, whole-dict-or-omit with genuine-miss flags; the unconditional omit + _DEGRADE constants are gone; DD-inputs + diligence + live-desk + finra suites green.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <what-built>
    edgar.fundamentals now exposes cash_usd + monthly_burn_usd; edgar.insider_net sources free EDGAR Form-4 net
    insider; make_diligence_inputs grounds financials + ownership (source-or-omit); the Slice-2 unconditional
    NO-GO is removed. This is the DEFERRED Slice-2 live check + the Slice-2.5 proof combined into one run.
  </what-built>
  <how-to-verify>
    1. Pick ONE positive-leaning upcoming catalyst in the universe (a name with real XBRL financials + Form-4 history
       — a liquid mid-cap biotech, not a shell). Confirm SEC_USER_AGENT + FINRA are reachable and the daemon/cache
       is warm (API-frugality: prefer a name whose financials/finra are already cached from a recent run).
    2. Run the combined live decision:
         .venv/bin/python scripts/run_one_catalyst.py <TICKER> --live --with-dd --db catalyst.db
    3. Confirm in the printed block:
       - a DiligenceDossier prints a MEANINGFUL go/no_go — the verdict rests on the DIMENSION THESIS
         (financials + ownership per-dimension findings are populated + cited), NOT on an ungrounded-money data gap.
       - the `degraded` lines do NOT include the old financials/ownership "ungrounded, forces NO-GO (Slice 2.5)"
         flags for a name whose facts genuinely exist (a legitimately-missing source may still flag — that is honest).
       - an MDDecision (enter/pass/escalate) + reconciliation round log print.
    4. Sanity: if the name is quiet on insider tape, insider_net may be ~0 (a real datum) and ownership STILL grounds
       — the verdict should turn on thesis, not "no data". If a source is genuinely down, the dim honestly degrades
       (that is correct behavior, not a bug).
  </how-to-verify>
  <resume-signal>Type "approved" (DD reached a thesis-based GO/NO-GO on grounded money dims) or describe what degraded/failed.</resume-signal>
</task>

</tasks>

<verification>
- `edgar.fundamentals` returns cash_usd + monthly_burn_usd alongside the unchanged existing keys; `_monthly_burn` is the single burn-derivation used by both fundamentals and `_runway_months` (no duplication).
- `edgar.insider_net` sums Form-4 net_change over a caller-supplied window with quiet-tape(0) / degrade(None) / partial-skip semantics; SEC-UA gated; degrade-never-crash.
- `make_diligence_inputs` fetches fundamentals ONCE (reused for financials cash/burn AND ownership shares), assembles financials + ownership source-or-omit (whole-dict-or-omit for ownership), and the Slice-2 unconditional omit + `_DEGRADE` constants are removed.
- All code-task tests offline (fake edgartools Form-4/facts + FINRA injected); `test_providers_edgar`, `test_desk_diligence_inputs`, `test_desk_diligence`, `test_live_desk_decision`, `test_providers_finra` green.
- The combined `--live --with-dd` run produces a thesis-based GO/NO-GO on grounded money dims (human-verified).
</verification>

<success_criteria>
- A real promoted candidate reaches `run_diligence` with `financials` + `ownership` GROUNDED, so the verdict is decided on the dimension thesis — not the Slice-2 ungrounded-money forced NO-GO. (Slice-4 paper trading is now un-gated.)
- No fabrication anywhere: financials omits when facts are absent; ownership is whole-dict-or-omit (never a partial dict → KeyError, never an invented insider_net); insider_net degrades to None on a genuine miss and reports a real 0 on a quiet tape.
- No new magic numbers (Form-4 window + months conversion live in `_INPUTS_PARAMS`); no duplication (reuse `finra.fetch`, `edgar.fundamentals`' fact-fetch, `_runway_months`' burn math, `recent_si_settlement`, `make_diligence_inputs`).
- Backward-compatible + additive; the full offline suite stays green.
</success_criteria>

<output>
After completion, create `.planning/phases/07.8-live-desk-wiring-pre-paper-hardening/slice2.5/SLICE2.5-SUMMARY.md`.
Per CLAUDE.md conventions: update `.planning/TOKEN-NOTES.md` (subagent-token tally + carry the Directives forward) and generate the phase-report HTML for this slice if this closes the phase's remaining money-dim work.
</output>
