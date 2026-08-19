---
phase: 07.8-live-desk-wiring-pre-paper-hardening
plan: slice1
type: tdd
wave: 1
depends_on: []
files_modified:
  - src/catalyst_trader/desk/catalyst_context.py
  - scripts/run_one_catalyst.py
  - tests/test_desk_catalyst_context.py
  - tests/test_run_one_catalyst.py
autonomous: false
requirements:
  - "7.8-S1"   # live catalyst_context binding + one-catalyst live-run harness (walking skeleton)

user_setup: []

must_haves:
  truths:
    - "A real catalyst_context hook returns {entry, risk_inputs} whose risk_inputs carries p_loss, gap, analog_gaps (all 6 keys), prices — every value honestly sourced from a point-in-time read or honestly degraded, NEVER fabricated."
    - "The hook degrades gracefully with no exception: price source None -> entry None-guarded; no analogs -> gap = params hard_veto_drop; no inverse peer -> analog_gaps peer branches = 0.0 + prices.peer = [] (the engine._NO_ANALOG_GAPS honest default, so risk.validate_hedge returns None = single-leg)."
    - "run_one_catalyst.py runs ONE catalyst through run_desk -> run_portfolio and prints a StrategyDossier (direction/size/hedge/rationale/portfolio_outcome); --dry-run proves the wiring offline with a fake verdict + fake context; --live is the operator-gated real LLM run."
    - "No-look-ahead holds: the hook reads only through serving.asof(conn, cutoff) at the catalyst's knowable_asof; live uses cutoff=now; never future data."
    - "Additive only: existing desk suites (weekly / risk / orchestrator) stay byte-for-byte green — the hook is a new module and run_weekly already accepts catalyst_context=."
  artifacts:
    - path: "src/catalyst_trader/desk/catalyst_context.py"
      provides: "make_catalyst_context(...) factory -> async hook (conn, ticker, catalyst, as_of) -> {entry, risk_inputs}"
      min_lines: 40
    - path: "scripts/run_one_catalyst.py"
      provides: "one-catalyst live-run harness with a testable run_one(...) core + thin __main__ (--dry-run / --live)"
      min_lines: 40
    - path: "tests/test_desk_catalyst_context.py"
      provides: "offline TDD: hook shape + values with fakes + graceful-degrade cases; NO live network/LLM"
    - path: "tests/test_run_one_catalyst.py"
      provides: "offline harness --dry-run wiring proof (fake run_desk + fake hook)"
  key_links:
    - from: "src/catalyst_trader/desk/catalyst_context.py"
      to: "serving.asof(conn, cutoff).bars(ticker, as_of)"
      via: "point-in-time entry + target price series (cache-first, frugal)"
      pattern: "serving\\.asof"
    - from: "src/catalyst_trader/desk/catalyst_context.py"
      to: "backtest.engine.resolve_direction_proxy('base_rate')"
      via: "p_positive -> p_loss = 1 - p_positive (the existing base-rate moat, not the verdict)"
      pattern: "resolve_direction_proxy|direction_proxy"
    - from: "src/catalyst_trader/desk/catalyst_context.py"
      to: "kb.analog_query / analog outcome moves"
      via: "target_up/target_down + gap (median down-move), split like builder._split_moves"
      pattern: "analog"
    - from: "scripts/run_one_catalyst.py"
      to: "desk.orchestrator.run_desk + run_portfolio"
      via: "one work-item {verdict, catalyst, entry, risk_inputs} through the live desk"
      pattern: "run_desk|run_portfolio"
---

<objective>
Build the one missing wire — a live `catalyst_context` hook — so ONE real biotech catalyst runs
through the LIVE agentic desk end-to-end (`run_desk` -> `run_portfolio`) and produces a
hand-checkable `StrategyDossier`. The desk is complete; `desk/weekly.py:115` skips every catalyst
leg "unless a `catalyst_context` price/analog feed hook is passed" — that hook is unbuilt. Build it
(production, offline-tested) + a one-catalyst live-run harness.

Purpose: retire the second load-bearing unknown of Phase 7.8 (after Slice 0 retired the live-LLM
seam) — that the desk's price/analog feed contract can be honestly satisfied from existing
point-in-time data with NO fabrication. Walking-skeleton first: one hand-checked catalyst, so a bad
assumption is caught on one hand, never compounded into a book.

Output: `desk/catalyst_context.py` (the hook factory) + `scripts/run_one_catalyst.py` (the harness),
both offline-tested; the real LIVE LLM run is an operator step (`--live`) AFTER this verifies.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/07.8-live-desk-wiring-pre-paper-hardening/PHASE-BRIEF.md
@.planning/phases/07.8-live-desk-wiring-pre-paper-hardening/SLICE0-RESULT.md

<interfaces>
<!-- All extracted + verified against source. Use directly — NO codebase exploration needed. -->

THE HOOK CONTRACT (desk/weekly.py:84,115-119 — the exact call site to satisfy):
```python
# weekly.py calls the hook like this (signature is FIXED by this call — do NOT change it):
verdict = await run_desk(conn, cat)
mc = await catalyst_context(conn, name, cat, as_of)   # -> {"entry": float, "risk_inputs": {...}}
verdicts.append({"verdict": verdict, "catalyst": cat, **mc})
# NOTE: the hook does NOT receive the verdict -> p_loss/gap must come from the KB/base-rate,
#       NOT from the builder's verdict-derived p_positive. This is correct: the Risk Committee
#       argues p_loss/gap as INDEPENDENT priors (risk.py:169-207), not the analyst's number.
```

WHAT run_portfolio CONSUMES per work item (orchestrator.py:96-98, 111-131):
```python
{"verdict": DebateVerdict, "catalyst": {...}, "entry": float,
 "risk_inputs": {"p_loss": float, "gap": float, "analog_gaps": dict, "prices": dict}}
# builder.build(conn, embed, verdict, catalyst, entry=item["entry"])  -> does its OWN analog_query
# risk.assess(conn, embed, proposal, catalyst,
#             p_loss=ri["p_loss"], gap=ri["gap"], analog_gaps=ri["analog_gaps"], prices=ri["prices"])
```

EXACT risk_inputs FIELD TYPES (verified against risk.assess + validate_hedge + conditional_payoff):
```python
p_loss: float                                  # risk.assess kwarg; committee prior + size_for_survival(p_loss=...)
gap:    float                                  # risk.assess kwarg; the down-gap size_for_survival(gap=...)
analog_gaps: dict = {                           # ALWAYS all 6 keys (conditional_payoff reads every one unconditionally)
    "target_up": float, "target_down": float,   #   target's up (>0) / down (<0) branch magnitudes
    "peer_up": float,   "peer_down": float,     #   PEER's move in each branch (see BLOCKER below)
    "w_target": float,  "w_peer": float,        #   allocation weights
}
prices: dict = {"target": list[float], "peer": list[float]}   # close series; only read inside validate_hedge->cointegration
```

THE HONEST DEGENERATE DEFAULT already shipped in backtest/engine.py:46-49 (REUSE its shape):
```python
_NO_ANALOG_GAPS = {"target_up": 0.0, "target_down": 0.0, "peer_up": 0.0, "peer_down": 0.0,
                   "w_target": 1.0, "w_peer": 0.0}
# engine._honest_hedge passes this + {"target": [], "peer": []} -> validate_hedge returns None
# (no inverse peer OR degenerate gaps) = the honest single-leg fallback. NEVER a fabricated hedge.
```

CRITICAL control-flow fact (risk.py:126-131): validate_hedge does
`peers = [p for p in kb.hedge_peers(conn, target) if p["payoff_direction"]==-1]; if not peers: return None`
— so peer_up/peer_down/prices["peer"] are ONLY read when the target HAS a stored inverse peer.
No inverse peer -> the peer branch is never touched -> the honest 0.0 defaults are sound.

SOURCES (all point-in-time, cache-first, no fabrication):
```python
# entry (cache-first, frugal): serving.asof(conn, cutoff).bars(ticker, as_of)[-1]["close"]  (== weekly._last_close)
#   optional --live override: providers.robinhood.quotes_rt([ticker])[ticker]["last"] (degrades to None)
# p_loss: side, p, ev = resolve_direction_proxy("base_rate")(ticker, as_of, view, conn, params=params)
#         -> p_loss = 1.0 - p   (run_layer_a uses this EXACT proxy at engine.py:303)
#         view = quant.weekly.as_of_view(conn, as_of)
# gap:    median(down-moves of catalyst analogs) if analogs else abs(params["weekly"]["hard_veto_drop"])
#         (== stat_gap, the SAME default the statistical sleeve + backtest use — NO new magic number)
# analog_gaps.target_up/target_down: kb.analog_query(conn, embed, ...) outcome moves, split like
#         builder._split_moves (up = >0, down = -|<0|); w_target/w_peer + peer_up/peer_down = _NO_ANALOG_GAPS
#         default UNLESS a paired peer co-move source is injected (see BLOCKER — Slice 1 degrades to no-hedge)
# prices.target: [b["close"] for b in serving.asof(conn, cutoff).bars(ticker, as_of, lookback_weeks=N)]
#         prices.peer: [] unless an inverse peer exists AND its bars are cached
```

catalyst dict shape (weekly.py:68-76 _catalyst_dict — mirror/reuse it for the harness):
```python
{"ticker": c.ticker, "catalyst_type": c.catalyst_type.value, "event_date": c.event_date,
 "catalyst_id": f"{ticker}:{c.event_date}"}
```

StrategyDossier print fields (contracts/__init__.py:214-226): decision, trade (TradeProposal:
target_long, hedge, size_pct, entry, direction, pair_rationale, expected_return_pct),
verdict_summary, residual_net_long, which_risk_covered, portfolio_context.portfolio_outcome.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: TDD the live catalyst_context hook (desk/catalyst_context.py)</name>
  <files>src/catalyst_trader/desk/catalyst_context.py, tests/test_desk_catalyst_context.py</files>
  <behavior>
    Write tests FIRST (RED), BDD-named `test_givenX_whenY_thenZ`, fully offline (fake price source +
    fake analog source + fake base-rate proxy; NO live network, NO run_structured). Assert:
    - given a fake price source returning a close and fake analogs with mixed moves, when the hook is
      awaited, then it returns {"entry": <close>, "risk_inputs": {...}} with ALL 6 analog_gaps keys,
      p_loss == 1 - p_positive (from the injected proxy), gap == median of the analog DOWN moves,
      target_up/target_down == the split analog magnitudes, prices["target"] == the fake close series.
    - given NO analogs, when awaited, then gap == abs(params["weekly"]["hard_veto_drop"]) (no crash,
      no new constant) and target_up/target_down fall back to the _NO_ANALOG_GAPS 0.0 defaults.
    - given NO inverse hedge peer for the target, when awaited, then analog_gaps peer_up/peer_down==0.0,
      w_peer==0.0, w_target==1.0 and prices["peer"]==[] (the honest single-leg default; assert the
      resulting dict, fed to risk.validate_hedge, yields None — no fabricated hedge).
    - given the price source returns None (degraded), when awaited, then entry is None-guarded per the
      degrade contract (return entry=None; the caller/harness skips the leg) — NO exception raised.
    - no-look-ahead: assert the hook reads through serving.asof at the passed cutoff (inject a spy conn
      or assert the injected proxy/price source is called with the given as_of, never a future date).
  </behavior>
  <action>
    Build `make_catalyst_context(*, price_source=None, analog_source=None, proxy_fn=None, params=None,
    lookback_weeks=None, quote_override=None) -> hook`, an INJECTABLE-PROVIDER factory mirroring the
    verify_moves bars_provider / builder options_adapter pattern. It returns the async closure
    `catalyst_context(conn, ticker, catalyst, as_of) -> {"entry", "risk_inputs"}` matching weekly.py:84
    EXACTLY. Production defaults bind: price_source -> serving.asof(conn, cutoff).bars (cache-first,
    frugal — the SAME read weekly._last_close uses); proxy_fn -> backtest.engine.resolve_direction_proxy
    ("base_rate") over quant.weekly.as_of_view(conn, as_of); analog_source -> kb.analog_query; params ->
    kb.load_params(conn, "weekly"). cutoff = as_of (backtest/knowable path) or now (live).

    Sourcing (ALL point-in-time, NO fabrication — reuse existing tools, no new magic numbers):
    - entry: last cached close via price_source; optional quote_override (providers.robinhood.quotes_rt,
      --live only) that DEGRADES-TO-None; entry<=0 or None -> return {"entry": None, ...} (caller skips).
    - p_loss = 1.0 - p_positive where (side, p_positive, ev) = proxy_fn(ticker, as_of, view, conn,
      params=params); on ValueError/KeyError (no measured cell) degrade to a params-derived default
      (do NOT invent — e.g. 1 - params default or the honest 0.5-neutral only if the proxy itself has none).
    - gap = median of the analog DOWN moves (split like builder._split_moves) if analogs else
      abs(params["weekly"]["hard_veto_drop"]) — the identical stat_gap the sleeve + backtest already use.
    - analog_gaps: start from a COPY of engine._NO_ANALOG_GAPS (import + reuse it, do NOT re-declare the
      literal); overwrite target_up/target_down from the catalyst analogs. peer_up/peer_down/w_peer stay
      the 0.0 honest default UNLESS a paired peer co-move source is supplied (NOT in Slice 1 — see the
      design-blocker note; Slice 1 is single-leg by honest degrade, matching engine._honest_hedge).
    - prices = {"target": [close series from cached bars], "peer": [] or the inverse peer's cached bars
      if kb.hedge_peers gives one AND its bars are cached}.

    # ponytail: no new money math — every number is an existing tool output or the shipped honest
    #   default. The hook only ROUTES point-in-time reads into the run_portfolio work-item shape.
    #   peer conditional gaps are NOT stored in the KB (hedge_peers carries only peer/direction/weight),
    #   so an honest paired-comove source is out of scope for the skeleton -> single-leg degrade.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_desk_catalyst_context.py -q</automated>
  </verify>
  <done>All new tests green (RED->GREEN->REFACTOR, 2-3 atomic commits). Hook returns the exact
  {entry, risk_inputs} shape run_portfolio consumes; every risk_input honestly sourced or honestly
  degraded; no exception on any degrade path; no fabricated peer/hedge.</done>
</task>

<task type="auto">
  <name>Task 2: One-catalyst live-run harness (scripts/run_one_catalyst.py)</name>
  <files>scripts/run_one_catalyst.py, tests/test_run_one_catalyst.py</files>
  <action>
    Build the harness with a TESTABLE core + a thin __main__:
    - `run_one(conn, embed, ticker, *, live, run_desk_fn=run_desk, context_hook=None) -> StrategyDossier|None`:
      pick the catalyst for `ticker` from catalyst.db via serving.asof(conn, cutoff).catalysts() at its
      knowable point-in-time (cutoff = the catalyst's knowable_asof for a backtest pick, or now for live);
      build the catalyst dict by mirroring weekly._catalyst_dict (reuse it if importable — no duplication);
      build the context via context_hook (default = make_catalyst_context(...) from Task 1); await
      `verdict = await run_desk_fn(conn, cat)`; `mc = await context_hook(conn, ticker, cat, as_of)`;
      if mc["entry"] is None -> print an honest "no entry price, leg skipped" and return None;
      else `book = await run_portfolio(conn, embed, [{"verdict": verdict, "catalyst": cat, **mc}],
      open_book=[])`; print the resulting StrategyDossier(s): decision, trade.direction,
      trade.size_pct, trade.hedge, trade.target_long, trade.pair_rationale, which_risk_covered,
      residual_net_long, and portfolio_context.portfolio_outcome. DD/MD are DEFERRED to Slice 2.
    - __main__ argparse: `ticker` (positional), `--dry-run` (default: inject a FAKE run_desk_fn
      returning a canned DebateVerdict + a fake context_hook -> pure-offline wiring proof, NO LLM/network)
      and `--live` (real run_desk + real hook + optional RH quote override — operator-gated, real LLM).
    - tests/test_run_one_catalyst.py: exercise run_one with live=False, a fake run_desk_fn, and a fake
      context_hook over an in-memory/seeded conn; assert it returns a StrategyDossier (or the honest
      None-entry skip) WITHOUT any live call. This is the Nyquist automated verify for the harness.

    # ponytail: the harness is glue — one work-item through the shipped run_desk->run_portfolio, no new
    #   selection/sizing. --dry-run exists ONLY so the wiring is testable without burning a live call.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_run_one_catalyst.py -q</automated>
  </verify>
  <done>run_one wired through run_desk->run_portfolio; --dry-run proves the harness offline (test
  green); --live is the operator step. Prints a full StrategyDossier. Existing suites untouched.</done>
</task>

</tasks>

<verification>
- `.venv/bin/python -m pytest tests/test_desk_catalyst_context.py tests/test_run_one_catalyst.py -q` all green.
- Regression (additive-only): `.venv/bin/python -m pytest tests/test_weekly_runner.py tests/test_desk_risk.py tests/test_desk_orchestrator.py tests/test_desk_builder.py -q` byte-for-byte green — the hook is a new module; run_weekly already accepts catalyst_context=; nothing existing was edited.
- Honest-degrade proof: the no-peer / no-analog / None-price cases return valid shapes with NO fabrication and NO exception (asserted in Task 1 tests).
- OPERATOR STEP (not a unit test): `.venv/bin/python scripts/run_one_catalyst.py <TICKER> --live` inside a Claude Code session (Max auth, no API key) runs ONE real catalyst -> prints a StrategyDossier for the human hand-check. This is the Slice-1 acceptance gate (checkpoint below).
</verification>

<success_criteria>
- desk/catalyst_context.py returns the exact {entry, risk_inputs} run_portfolio consumes; every field honestly sourced (serving.asof bars + base_rate proxy + kb analogs + params default) or honestly degraded to engine._NO_ANALOG_GAPS single-leg — zero fabricated numbers.
- scripts/run_one_catalyst.py runs one catalyst through the live desk and prints a hand-checkable StrategyDossier; --dry-run is offline-testable.
- No-look-ahead + frugality (cache-first) + no-duplication (reuses _catalyst_dict, resolve_direction_proxy, kb.analog_query, serving.asof, _NO_ANALOG_GAPS, params) all hold.
- All existing desk suites stay green.
</success_criteria>

<checkpoint>
<task type="checkpoint:human-verify" gate="blocking">
  <what-built>Live catalyst_context hook + one-catalyst harness. Offline tests + regression green.</what-built>
  <how-to-verify>
    Inside a Claude Code session (Max auth, ANTHROPIC_API_KEY unset — the Slice-0 runtime):
    1. Run `.venv/bin/python scripts/run_one_catalyst.py <TICKER> --live` for one upcoming catalyst.
    2. Confirm a real StrategyDossier prints: a coherent direction, a survival-capped size_pct,
       hedge (likely None = honest single-leg for Slice 1), a real pair_rationale, and the attached
       portfolio_outcome.
    3. Hand-check: does the entry price look right? is p_loss/gap plausible for that catalyst? is the
       single-leg (no-hedge) outcome the honest expected result given no stored peer conditional gaps?
  </how-to-verify>
  <resume-signal>Type "approved" (proceed to Slice 2 — attach DD + MD loop) or describe the discrepancy.</resume-signal>
</task>
</checkpoint>

<output>
After completion, create `.planning/phases/07.8-live-desk-wiring-pre-paper-hardening/slice1/07.8-slice1-SUMMARY.md`
</output>
