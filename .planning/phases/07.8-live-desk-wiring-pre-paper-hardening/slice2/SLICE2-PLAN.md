---
phase: 07.8-live-desk-wiring-pre-paper-hardening
plan: slice2
type: execute
wave: 1
depends_on: [slice1]
autonomous: false
requirements: [DILIG-01, DILIG-02, DILIG-03, RECON-01, RECON-05, RECON-07]
files_modified:
  - src/catalyst_trader/desk/diligence_inputs.py
  - src/catalyst_trader/desk/live_desk.py
  - scripts/run_one_catalyst.py
  - tests/test_desk_diligence_inputs.py
  - tests/test_live_desk_decision.py
user_setup: []

must_haves:
  truths:
    - "Given a promoted StrategyDossier, the desk produces a DiligenceDossier (go/no_go) via run_diligence."
    - "The desk produces an MDDecision (enter/pass/escalate) with a reconciliation round log via md.reconcile."
    - "market_data + DiligenceInput are sourced from free/cached point-in-time data; any unsourceable field honestly degrades or is flagged, never fabricated."
    - "The zero-trade case (no promoted dossier) short-circuits to a valid no-DD/no-MD pass with no exception."
    - "The whole offline path runs with zero LLM/network (every LLM seam injected/monkeypatched)."
    - "The --live run is operator-gated (not a unit test)."
  artifacts:
    - path: "src/catalyst_trader/desk/diligence_inputs.py"
      provides: "make_diligence_inputs — the (DiligenceInput, market_data) live-binding factory"
      contains: "def make_diligence_inputs"
      min_lines: 60
    - path: "src/catalyst_trader/desk/live_desk.py"
      provides: "run_one_catalyst_decision — end-to-end catalyst -> MDDecision chain"
      contains: "def run_one_catalyst_decision"
      min_lines: 50
    - path: "scripts/run_one_catalyst.py"
      provides: "--with-dd path printing DiligenceDossier + MDDecision + rounds"
      contains: "with-dd"
    - path: "tests/test_desk_diligence_inputs.py"
      provides: "offline coverage of every md field source + honest degrade"
    - path: "tests/test_live_desk_decision.py"
      provides: "offline coverage of the chain, item assembly, and zero-trade short-circuit"
  key_links:
    - from: "src/catalyst_trader/desk/live_desk.py"
      to: "src/catalyst_trader/desk/diligence_inputs.py"
      via: "make_diligence_inputs -> (dd_input, market_data)"
      pattern: "make_diligence_inputs"
    - from: "src/catalyst_trader/desk/live_desk.py"
      to: "desk.diligence.run_diligence"
      via: "dd = run_diligence(dd_input, market_data=...)"
      pattern: "run_diligence"
    - from: "src/catalyst_trader/desk/live_desk.py"
      to: "desk.md.reconcile"
      via: "item{verdict,dossier,dd,catalyst,dd_input,market_data,open_book,entry,risk_inputs} -> reconcile"
      pattern: "reconcile"
    - from: "src/catalyst_trader/desk/diligence_inputs.py"
      to: "desk.catalyst_context risk_inputs"
      via: "market_data['hedge'] reuses {entry, analog_gaps, prices} + exit_by_date"
      pattern: "hedge"
---

<objective>
Wire the ORPHANED independent diligence + MD reconciliation loop onto the Slice-1 dossier so one
real catalyst produces an approvable go/no-go **decision** (an `MDDecision`: enter/pass/escalate +
round log), not just a `StrategyDossier`. `md.reconcile` + `run_diligence` are already built and
unit-tested but called from nowhere outside tests; Slice 2 builds the two missing live bindings
(`make_diligence_inputs`) and the end-to-end desk function that chains them, then extends the Slice-1
harness with a `--with-dd` path gated behind a live operator hand-check.

Purpose: close the last wire Phase 8 (paper ledger) + Phase 9 (approval gate) assume exists — a desk
that emits a reconciled decision, walking-skeleton first, so a bad DD/MD integration assumption is
caught on one hand-checked positive-leaning catalyst instead of compounded into a book.

Output: `desk/diligence_inputs.py` (the DiligenceInput + market_data live binding), `desk/live_desk.py`
(`run_one_catalyst_decision`), an extended `scripts/run_one_catalyst.py --with-dd`, and one live
`MDDecision` + reconciliation round log hand-checked at the blocking checkpoint.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/07.8-live-desk-wiring-pre-paper-hardening/PHASE-BRIEF.md
@.planning/phases/07.8-live-desk-wiring-pre-paper-hardening/slice1/SLICE1-SUMMARY.md
@src/catalyst_trader/desk/diligence.py
@src/catalyst_trader/desk/md.py
@src/catalyst_trader/desk/catalyst_context.py
@scripts/run_one_catalyst.py
@tests/test_desk_md.py

<interfaces>
<!-- Verified against code 2026-08-19. Executor: use these directly — no exploration needed. -->

# The two contracts Slice 2 must satisfy (diligence.py:495, md.py:302)

run_diligence(conn, input: DiligenceInput, *, market_data: dict, embed=None) -> DiligenceDossier

  DiligenceInput (contracts/__init__.py:238, extra="forbid" FIREWALL):
    ticker: str
    catalyst: dict          # minimal raw facts: {catalyst_id, catalyst_type, event_date, company_name?}
    pair: str | None = None # hedge peer TICKER only (Slice-1 ships single-leg -> None)

  market_data dict — EVERY money dim (financials, ownership, options_move, hedge, liquidity) needs a
  raw-data key; a MISSING money key = the ungrounded case that FORCES a NO-GO (diligence.py:549-558).
  Shapes (exact keys, direct-subscript — missing raises):
    "options":    {"quote": {call_bid,call_ask,put_bid,put_ask,call_oi,put_oi,expiry,catalyst_date},
                   "underlying_price": float, "days_to_event": int}
    "financials": {"cash_usd", "monthly_burn_usd", "months_to_catalyst"}
    "ownership":  {"short_interest_pct", "days_to_cover", "insider_net"}   # ALL THREE direct-subscript
    "trial":      {...ClinicalTrials.gov record...}   # non-money; None is fine (no NO-GO)
    "hedge":      {"entry", "exit_by_date", "analog_gaps", "prices"}       # hedge_context(**md["hedge"])
    "liquidity_quote": {"bid", "volume", "oi"}         # zero_liquidity: all three must be > 0

reconcile(conn, embed, item, *, max_rounds=3, blocker_path=".monitor/blocker.json") -> MDDecision

  item keys consumed (md.py:311-368 + _workitem md.py:279-299):
    item["verdict"]        # DebateVerdict (Slice-1 run_desk)
    item["dossier"]        # StrategyDossier (Slice-1 run_portfolio, the PROMOTED one)
    item["dd"]             # DiligenceDossier (Slice-2 run_diligence)  <-- NEW
    item["catalyst"]       # dict with ["catalyst_id"] AND ["catalyst_type"] (from _catalyst_dict)
    item["dd_input"]       # DiligenceInput  <-- NEW (cascade re-runs run_diligence with it)
    item["market_data"]    # dict           <-- NEW (cascade re-runs run_diligence with it)
    item["open_book"]      # list (one-catalyst run = [])
    item["entry"]          # from catalyst_context (cascade _workitem reads it)
    item["risk_inputs"]    # from catalyst_context (cascade _workitem reads it)
    item.get("incoming_flags", [])   # optional -> []

# Slice-1 outputs already available (catalyst_context.py):
#   catalyst_context(conn, ticker, catalyst, as_of) -> {"entry": float|None,
#     "risk_inputs": {"p_loss","gap","analog_gaps","prices":{"target":[...],"peer":[]}}}
#   entry=None => leg skipped (no dossier promoted => Slice-2 zero-trade short-circuit).
#   weekly._catalyst_dict(book, ticker, as_of) -> {ticker,catalyst_type,event_date,catalyst_id} | None

# Free providers to SOURCE market_data from (cache-first, per CLAUDE.md frugality ladder):
#   providers/options_cboe.fetch(ticker) -> {call_bid,call_ask,put_bid,put_ask,call_oi,put_oi,expiry,
#       underlying_quote:{bid,volume,oi}} | None   (FREE CBOE delayed quotes; exact seam shape)
#   providers/edgar.fetch(ticker) -> {...cash + operating burn + runway...} | None   (FREE SEC XBRL)
#   providers/finra.fetch(ticker, settlement_date?) -> {short_interest, days_to_cover, ...} | None (FREE)
#   providers/clinicaltrials.fetch* -> trial record | None   (FREE)
#   NO FREE insider_net source — EDGAR Form-4 ownership is explicitly DEFERRED (edgar.py:9). SEE RISK.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: make_diligence_inputs — the (DiligenceInput, market_data) live binding</name>
  <files>src/catalyst_trader/desk/diligence_inputs.py, tests/test_desk_diligence_inputs.py</files>
  <behavior>
    Mirror Slice-1's `make_catalyst_context` injectable-provider-factory pattern EXACTLY. Factory
    `make_diligence_inputs(*, options_source=..., financials_source=..., ownership_source=...,
    trial_source=...)` returns a closure
    `diligence_inputs(conn, ticker, catalyst, *, entry, risk_inputs, exit_by_date, pair=None,
    as_of) -> (DiligenceInput, market_data)`. Defaults capture the free providers; tests inject fakes.

    Tests (offline, in-memory, fakes only — NO network/LLM). One per source + per degrade:
    - test_givenAllSources_buildsFullMarketData: all five money keys present, correct shapes,
      DiligenceInput(ticker, catalyst, pair) validates.
    - test_hedgeReusesCatalystContext: market_data["hedge"] == {"entry": entry, "exit_by_date":
      exit_by_date, "analog_gaps": risk_inputs["analog_gaps"], "prices": risk_inputs["prices"]}
      (reuse, no recompute). Feed the produced hedge dict to risk.validate_hedge with pair=None and
      assert None (honest single-leg, mirrors Slice-1 test_givenNoInversePeer).
    - test_optionsFromCboe: options_source returns the CBOE seam -> market_data["options"]["quote"]
      carries call_bid/.../expiry + catalyst_date=event_date; underlying_price=entry;
      days_to_event = (event_date - as_of).days.
    - test_optionsDegradeToSentinel: options_source returns None -> a SENTINEL illiquid quote
      (call_bid=0/put_bid=0) so run_diligence's options_context uses the historical-gap fallback and
      options_move stays GROUNDED (never a fabricated IV). Assert options_liquid(quote)==False.
    - test_liquidityFromUnderlyingQuote: liquidity_quote = {bid,volume,oi} from CBOE underlying_quote
      (oi = combined option OI); CBOE None -> oi=0 (conservative zero-liquidity -> NO-GO, honest).
    - test_financialsFromEdgar: {cash_usd, monthly_burn_usd, months_to_catalyst}; months_to_catalyst
      computed from event_date - as_of (no new magic number). edgar None -> market_data has NO
      "financials" key (the ungrounded -> NO-GO path; assert key absent, NOT a fabricated zero).
    - test_ownershipInsiderGap: ownership_source lacks insider_net -> market_data has NO "ownership"
      key (honest degrade to ungrounded, NEVER a fabricated insider_net) AND a flag is surfaced on
      the returned structure (e.g. a `flags`/`degraded` list carrying "ownership: insider_net
      unavailable (EDGAR Form-4 deferred) — dim ungrounded, forces NO-GO"). SEE PLAN RISK.
    - test_noLookAhead: sources are read at the passed `as_of` (assert the fake received as_of).

    NO fabrication rule tested throughout: any field not honestly sourceable is absent or sentinel-
    honest (call_bid=0 = "no options bid observed"; oi=0 = "liquidity unconfirmed"), never invented.
  </behavior>
  <action>
    Write tests FIRST (RED), then the module (GREEN). Reuse, do not rebuild:
    - Reuse Slice-1 catalyst_context outputs for market_data["hedge"] — copy {entry, analog_gaps,
      prices} straight from `risk_inputs`, add exit_by_date (the caller's one-week hold end, same as
      weekly._weekly_exit). NO recompute of analog gaps or price series.
    - Reuse providers/options_cboe.fetch, providers/edgar.fetch, providers/finra.fetch,
      providers/clinicaltrials.fetch as the DEFAULT injected sources (captured at factory build, the
      Slice-1 `_default_analog_source(embed)` closure pattern). All are cache-first per CLAUDE.md.
    - Build DiligenceInput(ticker=ticker, catalyst=catalyst, pair=pair). Slice-1 is single-leg =>
      pair=None => hedge_context re-runs validate_hedge(candidate_peer=None) => None => HEDGE-04
      fallback text (grounded, honest — the hedge dim does NOT force NO-GO).
    - options: if source returns the CBOE dict, assemble quote {call_bid,call_ask,put_bid,put_ask,
      call_oi,put_oi,expiry, catalyst_date=event_date}, underlying_price=entry, days_to_event=
      (date(event_date)-date(as_of)).days. If source None -> sentinel {call_bid:0,call_ask:0,
      put_bid:0,put_ask:0,call_oi:0,put_oi:0,expiry:event_date,catalyst_date:event_date} (trips
      options_liquid=False -> honest fallback), still underlying_price=entry.
    - liquidity_quote: {bid,volume,oi} from CBOE underlying_quote (oi = call_oi+put_oi combined), else
      {bid:0,volume:0,oi:0}.
    - financials: edgar {cash_usd, monthly_burn_usd} + months_to_catalyst computed; OMIT the key
      entirely on edgar None (ungrounded -> NO-GO; never a fabricated cash figure).
    - ownership: OMIT the key + append a degrade flag whenever insider_net is unavailable (the honest
      NO-GO path — see Risk). short_interest_pct = finra short_interest / shares_outstanding when a
      float is cheaply available (edgar/robinhood), else omit ownership too.
    - trial: clinicaltrials record or None (non-money; None is fine).
    Return `(dd_input, market_data)` and, per test, a `degraded: list[str]` flag channel (return a
    small tuple/namedtuple or attach flags to a wrapper — pick the shape the tests assert).
    # ponytail: a factory + one closure + six field builders + honest degrade. No per-provider class,
    #           no registry — reuse the existing free providers, don't re-wrap them.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_desk_diligence_inputs.py -x -q</automated>
  </verify>
  <done>All Task-1 tests green; every money field either honestly sourced or absent/sentinel with a
  surfaced degrade flag; hedge dict reuses catalyst_context; no fabricated numbers; existing suites
  untouched.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: run_one_catalyst_decision — the end-to-end catalyst -> MDDecision chain</name>
  <files>src/catalyst_trader/desk/live_desk.py, tests/test_live_desk_decision.py</files>
  <behavior>
    `run_one_catalyst_decision(conn, embed, ticker, *, as_of, live=False, run_desk_fn=run_desk,
    context_hook=None, run_portfolio_fn=run_portfolio, dd_inputs_fn=None, run_diligence_fn=
    run_diligence, reconcile_fn=md.reconcile, open_book=None) -> result` chains:
      catalyst pick (_catalyst_dict) -> run_desk -> catalyst_context -> run_portfolio
      -> IF a dossier promoted: make_diligence_inputs -> run_diligence -> assemble reconcile item
         -> md.reconcile -> MDDecision
      -> ELSE (zero-trade): short-circuit to a valid no-DD/no-MD pass (no exception).

    Tests (offline — monkeypatch ALL LLM seams per tests/test_desk_md.py::_install pattern):
    - test_promotedTrade_producesMDDecision: fakes yield a promoted StrategyDossier + a canned
      DiligenceDossier + a canned MDDecision; assert result carries the DiligenceDossier and the
      MDDecision (decision in {enter,pass,escalate}) + round_log.
    - test_itemAssembledForReconcile: capture the item passed to reconcile_fn; assert it has EVERY
      key reconcile consumes: verdict, dossier, dd, catalyst (with catalyst_id + catalyst_type),
      dd_input, market_data, open_book, entry, risk_inputs. (Guards the md.py:311-368 contract.)
    - test_zeroTrade_shortCircuits: run_portfolio_fn promotes NOTHING (entry=None OR empty book) ->
      NO run_diligence, NO reconcile called; result is an honest "no trade / pass" with a reason.
      Assert run_diligence_fn + reconcile_fn were NOT called.
    - test_noCatalyst_returnsCleanly: _catalyst_dict None -> clean no-op result, no exception.
    - test_fullyOffline: assert zero real run_structured (all seams injected) — mirrors S1 --dry-run.
    - test_ddInputCarriesPair: single-leg -> dd_input.pair is None (Slice-1 honest degrade).
  </behavior>
  <action>
    Tests FIRST (RED), then the module (GREEN). Reuse everything; add no new decision logic:
    - Reuse weekly._catalyst_dict for the knowability-gated pick (Slice-1 pattern), catalyst_context
      / make_catalyst_context for {entry, risk_inputs}, run_desk + run_portfolio for verdict + dossier
      (Slice-1 already does this — factor the shared head or import run_one's pieces; do NOT duplicate
      the desk chain).
    - "Promoted?" = run_portfolio returned a non-empty dossier book for this leg AND entry is not None.
      Zero-trade (negative verdict long-only can't express, e.g. CAPR) => the honest pass: return a
      result with dossier=None, dd=None, decision=None, reason="no trade promoted (…)". This is a
      CORRECT outcome, not an error (Slice-1 hand-check proved CAPR was rightly no-trade).
    - When promoted: call dd_inputs_fn (default make_diligence_inputs(...) with the free sources) with
      the same entry/risk_inputs/exit_by_date/as_of the dossier used -> (dd_input, market_data);
      run_diligence_fn(conn, dd_input, market_data=market_data, embed=embed) -> dd; assemble the item
      (all keys above; open_book=open_book or []; incoming_flags=[]); reconcile_fn(conn, embed, item)
      -> MDDecision. Return {dossier, dd, decision, rounds, degraded_flags}.
    - Injectable seams so the whole thing is offline-testable (mirror Slice-1's run_desk_fn/
      context_hook/run_portfolio_fn surface + add dd_inputs_fn/run_diligence_fn/reconcile_fn).
    - No-look-ahead: everything reads at `as_of`; frugality: sources cache-first; live path is the
      only network + LLM and is operator-gated (Task 3).
    # ponytail: a linear chain + one promoted/zero-trade branch + item assembly. No orchestration
    #           class — the seams are function params, exactly like Slice-1's run_one.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_live_desk_decision.py -x -q</automated>
  </verify>
  <done>All Task-2 tests green; item assembled with the full reconcile contract; zero-trade honestly
  short-circuits without calling DD/MD; fully offline; MDDecision returned on the promoted path.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: extend scripts/run_one_catalyst.py with the --with-dd MDDecision path</name>
  <files>scripts/run_one_catalyst.py, tests/test_live_desk_decision.py</files>
  <behavior>
    Add a `--with-dd` flag that routes through run_one_catalyst_decision and PRINTS: the
    DiligenceDossier go/no-go (+ per-dimension verdict + red flags + degraded flags), the MDDecision
    (enter/pass/escalate) + reconciliation round count/dispositions, and — on zero-trade — the honest
    "no trade promoted" reason. `--dry-run` (default) stays fully offline (fake LLM seams, canned
    dossier/DD/MDDecision); `--live` is operator-gated (real run_desk/context/run_portfolio/
    run_diligence/reconcile, real free providers, optional RH entry override). `--with-dd` composes
    with both. Existing Slice-1 dossier-only path (no --with-dd) is unchanged (backward-compat).

    Tests (offline): extend test_live_desk_decision.py with a harness test that runs the --dry-run
    --with-dd path via the testable core with all seams faked and asserts the printed/returned block
    contains the DiligenceDossier verdict + the MDDecision + round count, and a zero-trade dry-run
    prints the no-trade reason. No live call in any unit test.
  </behavior>
  <action>
    Tests FIRST for the new offline path, then wire the flag (GREEN). Reuse Slice-1's argparse + the
    _fake_desk_and_context offline-seam pattern; extend it with fake dd_inputs_fn / run_diligence_fn /
    reconcile_fn returning canned artifacts so --dry-run --with-dd is pure-offline. Add
    `ap.add_argument("--with-dd", action="store_true", help="run DD + MD reconciliation -> MDDecision")`.
    Add a `_print_decision(result)` helper (sibling of _print_dossiers). Keep the money/decision logic
    entirely in live_desk.py — the harness only selects seams + prints.
    # ponytail: one flag + one print helper + fake-seam extension. No new run mode object.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_live_desk_decision.py tests/test_run_one_catalyst.py -q && .venv/bin/python -m scripts.run_one_catalyst CAPR --with-dd --dry-run</automated>
  </verify>
  <done>--with-dd --dry-run prints a DiligenceDossier + MDDecision + round log fully offline; Slice-1
  dossier-only path unchanged; existing harness tests green.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <what-built>
    The full live wire: catalyst -> run_desk -> catalyst_context -> run_portfolio -> (promoted?) ->
    make_diligence_inputs -> run_diligence -> md.reconcile -> MDDecision, exposed via
    `scripts/run_one_catalyst.py --with-dd --live`. All offline tests green; this is the FIRST real
    LLM run of the orphaned DD + MD loop end-to-end (Slice-0 proved the run_structured seam; Slice-1
    proved run_desk/run_portfolio live; this proves DD + reconcile live).
  </what-built>
  <how-to-verify>
    Inside a Claude Code session (Max auth, ANTHROPIC_API_KEY UNSET — the Slice-0 runtime), pick a
    POSITIVE-leaning upcoming catalyst that will actually PROMOTE a trade (so DD/MD have something to
    reconcile — CAPR was correctly no-trade in Slice 1, so choose a name with a bullish base-rate
    prior + cached price bars; confirm a promoted dossier first with `--live` sans `--with-dd`). Then:

      1. .venv/bin/python -m scripts.run_one_catalyst <TICKER> --live            # confirm a dossier promotes
      2. .venv/bin/python -m scripts.run_one_catalyst <TICKER> --live --with-dd  # the full decision

    Hand-check the printed output:
      - DiligenceDossier: is the go/no_go plausible? Are the money-dim NO-GO reasons DATA-GAP
        (ownership insider_net unavailable — see Risk; a degraded flag should say so) vs a genuine
        adversarial NO-GO? A NO-GO that rests ONLY on the ownership data gap is a wiring success but a
        DATA gap, not a thesis verdict — note it.
      - MDDecision: enter / pass / escalate — does it follow sensibly from verdict + dossier + DD?
        Round log: how many reconciliation rounds, what dispositions (converged / diverged_pass /
        cap_hit)? On escalate, confirm .monitor/blocker.json was written.
      - Cost/latency: note calls + wall-clock (several opus in reconcile + narrative — the Slice-0
        cost estimate applies).
  </how-to-verify>
  <resume-signal>Type "approved" (Slice 2 wire verified — one real MDDecision + round log
  hand-checked) or describe issues / the data-gap decision to carry forward.</resume-signal>
</task>

</tasks>

<verification>
- Offline: `.venv/bin/python -m pytest tests/test_desk_diligence_inputs.py tests/test_live_desk_decision.py tests/test_run_one_catalyst.py -q` all green.
- Regression: `.venv/bin/python -m pytest tests/test_desk_md.py tests/test_desk_diligence.py tests/test_desk_catalyst_context.py -q` byte-for-byte green (no reuse target mutated).
- Full offline wire: `--with-dd --dry-run` prints DiligenceDossier + MDDecision + rounds with zero LLM/network.
- Live (operator, checkpoint): one real MDDecision + reconciliation round log on a promoted candidate.
</verification>

<success_criteria>
- run_one_catalyst_decision emits an MDDecision (enter/pass/escalate) + round log on a promoted candidate, and an honest no-trade pass on the zero-trade case — both offline-tested.
- make_diligence_inputs sources every market_data field from free/cached point-in-time data or honestly degrades/flags it; hedge reuses catalyst_context; NO fabricated numbers.
- The reconcile item carries the full contract (verdict, dossier, dd, catalyst, dd_input, market_data, open_book, entry, risk_inputs).
- --with-dd extends the harness additively; Slice-1 path + all existing suites unchanged.
- Live checkpoint hand-checked: one real MDDecision + round log verified; the ownership insider_net data-gap decision is recorded.
</success_criteria>

<output>
After completion, create `.planning/phases/07.8-live-desk-wiring-pre-paper-hardening/slice2/SLICE2-SUMMARY.md`
(mirror SLICE1-SUMMARY.md: what shipped, the market_data sourcing map with honest-degrade column, the
insider_net data-gap decision + carry-forward, plan-check resolutions, no-look-ahead + frugality note,
the live hand-check command + result).
</output>
