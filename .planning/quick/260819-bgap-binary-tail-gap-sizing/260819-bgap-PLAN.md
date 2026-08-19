---
phase: quick-260819-bgap
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - src/catalyst_trader/quant/sizing.py
  - src/catalyst_trader/kb.py
  - src/catalyst_trader/desk/catalyst_context.py
  - tests/test_sizing.py
  - tests/test_desk_catalyst_context.py
autonomous: true
requirements: [BGAP-01]
must_haves:
  truths:
    - "A BINARY catalyst (pdufa/adcom/trial_readout) sizes against the TAIL of analog down-moves, not the median"
    - "Thin/empty analog coverage falls back to a conservative binary-gap default, never a too-small median"
    - "The binary gap is never below the canonical binary prior (max(tail, default))"
    - "A binary catalyst produces a SMALLER, survivable size than the median-gap sizing did (a -60% tail is survivable within ruin_cap)"
    - "The non-binary (earnings/conference) gap path is byte-for-byte unchanged"
  artifacts:
    - path: "src/catalyst_trader/quant/sizing.py"
      provides: "binary_survival_gap(down_moves, *, percentile, default) pure tail-gap selector"
      contains: "def binary_survival_gap"
    - path: "src/catalyst_trader/kb.py"
      provides: "params: binary_catalyst_types + binary_gap_percentile + binary_gap_default in the weekly block"
      contains: "binary_gap_default"
    - path: "src/catalyst_trader/desk/catalyst_context.py"
      provides: "binary-branch gap wiring into risk_inputs['gap']"
      contains: "binary_survival_gap"
  key_links:
    - from: "src/catalyst_trader/desk/catalyst_context.py"
      to: "src/catalyst_trader/quant/sizing.py::binary_survival_gap"
      via: "binary branch on catalyst_type in params binary_catalyst_types"
      pattern: "binary_survival_gap"
    - from: "risk_inputs['gap']"
      to: "size_for_survival"
      via: "run_portfolio work-item -> risk.assess -> size_for_survival(gap=...)"
      pattern: "size_for_survival"
---

<objective>
Fix a money-critical under-estimate of the survival gap for BINARY catalysts. Today
`catalyst_context.py:116` sets `gap = median(down_moves)` for EVERY catalyst. For a binary
catalyst (PDUFA / AdCom / trial readout) the real adverse move is a TAIL event — a CRL or trial
miss gaps the stock 30-70% down — but the median analog down-move is ~8.5% (observed on CAPR).
Sizing for an 8.5% gap when the true downside is -60% oversizes the position ~7x → RUIN on a bad
binary. This bug did not bite (CAPR never traded) but MUST be fixed before real paper positions.

Purpose: make BINARY catalysts size against the tail down-move, honest-degrade to a conservative
binary prior on thin analog coverage, and leave the non-binary path byte-for-byte unchanged.

Output: a pure `binary_survival_gap` selector in the money module, three new PARAMS values (no
magic literals), and the wire in `catalyst_context.py`'s gap computation.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md

<investigation>
The bug — `src/catalyst_trader/desk/catalyst_context.py:113-119`:
```python
analogs = analog_source(conn, ticker, catalyst, as_of)
up_moves, down_moves = _split_moves(analogs)
gap = median(down_moves) if down_moves else abs(p["weekly"]["hard_veto_drop"])  # <-- median = the bug
analog_gaps = dict(_NO_ANALOG_GAPS)
analog_gaps["target_up"] = median(up_moves) if up_moves else 0.0
analog_gaps["target_down"] = -median(down_moves) if down_moves else 0.0
```
`down_moves` are POSITIVE magnitudes of the analogs' negative realized moves (`desk/builder.py::_split_moves`:
`down_moves = [-m for m in moves if m < 0]`). `gap` flows via `risk_inputs["gap"]` → the run_portfolio
work-item → `risk.assess(gap=...)` → `size_for_survival(p_loss, gap, ...)` → `risk_of_ruin(...)`.
Confirmed direction: LARGER gap → SMALLER survival size (the downward sweep in
`desk/risk.py:74-82` finds the largest size whose `risk_of_ruin` ≤ ruin_cap; `risk_of_ruin`'s
`factor = 1 - size_pct*gap` shrinks faster with a bigger gap → ruin clears only at a smaller size).

catalyst_type enum — `src/catalyst_trader/models.py::CatalystType`:
`pdufa, adcom, trial_readout, earnings, conference`. BINARY = {pdufa, adcom, trial_readout}
(FDA/trial all-or-nothing). NON-binary = {earnings, conference}. ("statistical" is a *thesis_type*,
NOT a catalyst_type — statistical legs never route through catalyst_context, so no change reaches them.)

Percentile machinery — ALREADY in stdlib and used at `src/catalyst_trader/quant/valuation.py:137`:
`from statistics import quantiles; q1,_,q3 = quantiles(moves, n=4, method="inclusive")`.
Reuse it (ladder rung 3). `quantiles` needs ≥2 points else raises StatisticsError.

CRL base-rate move — DOES NOT EXIST honestly. `data/base_rates.csv` has
`crl_penalty,-0.28 = "prior CRL reduces approval PROBABILITY ~28%"` — a PROBABILITY reduction,
NOT a stock down-move magnitude. Using it as a gap is fabrication (violates cite-or-drop). So the
conservative default is NOT a base-rate CRL move — it is the codebase's already-canonical binary
down-gap belief: `size_for_survival(gap=0.70)` + `risk_of_ruin(gap=0.70)` defaults, and
`quant/sizing.py:184` "size for -70%, not stop distance". We promote that implicit 0.70 into params.
</investigation>

<interfaces>
From src/catalyst_trader/quant/sizing.py:
```python
def risk_of_ruin(p_loss, size_pct, gap=0.70, ruin_drawdown=0.5, n_trades=52) -> ToolResult
    # validates 0 < gap <= 1 (RAISES otherwise); larger gap -> ruin clears only at smaller size
```
From src/catalyst_trader/desk/risk.py:
```python
def size_for_survival(p_loss, gap=0.70, ruin_cap=0.02, per_event_cap=0.03, n_trades=52,
                      *, target_return=None, expected_move=None) -> ToolResult  # value = chosen size_pct
```
From src/catalyst_trader/kb.py (BOOTSTRAP_DEFAULT["weekly"], the block to extend):
```python
"weekly": { ..., "hard_veto_drop": -0.15, "statistical_sleeve_cap": 0.5 }
def load_params(conn, catalyst_type) -> dict   # returns the strategy dict; params["weekly"] is the block
```
From src/catalyst_trader/models.py:
```python
class CatalystType(str, Enum): pdufa; adcom; trial_readout; earnings; conference
# catalyst["catalyst_type"] is the string value (e.g. "pdufa")
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: binary_survival_gap selector + PARAMS values</name>
  <files>src/catalyst_trader/quant/sizing.py, src/catalyst_trader/kb.py, tests/test_sizing.py</files>
  <behavior>
    New pure fn `binary_survival_gap(down_moves, *, percentile, default) -> float` in sizing.py:
    - Test: wide down-tail e.g. [0.05,0.08,0.10,0.60] with percentile=90 -> returns the ~90th
      pctile of the magnitudes (>> the 0.09 median), computed via statistics.quantiles(n=100,
      method="inclusive")[percentile-1]. Never the median.
    - Test: the returned value is max(tail, default) — a computed tail BELOW default is floored to
      default; a computed tail ABOVE default (genuinely worse observed history) is kept.
    - Test: thin coverage — len(down_moves) < 2 (0 or 1 point) -> returns default (quantiles can't
      run on <2). Empty list -> default. Never raises on thin input.
    - Test: result is always in (0, 1] (safe for risk_of_ruin's gap validator) given fractional
      inputs and a default in (0,1].
    - Test: it is a PURE function of its args (no kb/db/network); percentile & default are passed in,
      no literal inside the body except structural (n=100).
    PARAMS (kb.py BOOTSTRAP_DEFAULT["weekly"]): add
      "binary_catalyst_types": ["pdufa", "adcom", "trial_readout"],
      "binary_gap_percentile": 90,
      "binary_gap_default": 0.70,   # canonical binary down-gap (matches sizing.py -70% + gap=0.70 defaults)
    - Test (kb): load_params(conn,"weekly")["weekly"] exposes all three keys with these values.
  </behavior>
  <action>
    In src/catalyst_trader/quant/sizing.py add `from statistics import quantiles` and:
    ```python
    def binary_survival_gap(down_moves, *, percentile: float, default: float) -> float:
        """The TAIL adverse down-move a BINARY catalyst must survive (BGAP-01), NOT the median.

        A CRL / trial miss is a tail event (~30-70% gap-down); the median analog down-move (~8.5%)
        drastically UNDER-sizes the survival gap. Returns max(high-percentile of analog down-move
        MAGNITUDES, `default`): rich history with a genuinely worse tail can push the gap ABOVE the
        prior, but thin/optimistic history can NEVER pull it below it. `default` is the honest
        conservative binary prior (kb binary_gap_default) — NOT base_rates crl_penalty, which is a
        probability reduction, not a price move (cite-or-drop). Pure: percentile+default injected.
        """
        tail = default
        if len(down_moves) >= 2:  # quantiles needs >=2 points
            tail = quantiles(down_moves, n=100, method="inclusive")[int(percentile) - 1]
        return max(tail, default)
    ```
    In src/catalyst_trader/kb.py add the three keys to BOOTSTRAP_DEFAULT["weekly"] (next to
    hard_veto_drop / statistical_sleeve_cap), each with an inline comment citing the source of the
    number (binary_gap_default cites sizing.py -70% + the gap=0.70 tool defaults).
    Write tests in tests/test_sizing.py FIRST (RED), then implement (GREEN). No magic literals in
    the fn body beyond n=100 (the percentile-resolution of quantiles).
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_sizing.py -x -q</automated>
  </verify>
  <done>binary_survival_gap returns tail-not-median on wide input, floors to default on thin input,
  is max(tail,default), stays in (0,1]; the three params keys load. test_sizing.py green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: wire binary tail-gap into catalyst_context; non-binary unchanged</name>
  <files>src/catalyst_trader/desk/catalyst_context.py, tests/test_desk_catalyst_context.py</files>
  <behavior>
    In catalyst_context's gap computation, branch on whether catalyst["catalyst_type"] is in
    params["weekly"]["binary_catalyst_types"]:
    - Test: BINARY catalyst (catalyst_type="pdufa") with down-tail analogs
      [-0.05,-0.08,-0.10,-0.60] -> risk_inputs["gap"] == binary_survival_gap([0.05,0.08,0.10,0.60],
      percentile=90, default=0.70) (the tail/prior, NOT median 0.09).
    - Test: BINARY + thin/empty analogs -> risk_inputs["gap"] == 0.70 (binary_gap_default), NOT
      abs(hard_veto_drop)=0.15 and NOT a median. Conservative, never too-small.
    - Test (byte-for-byte non-binary): catalyst_type="earnings" with the SAME analogs ->
      risk_inputs["gap"] == median(down_moves) (existing behavior); empty analogs ->
      abs(p["weekly"]["hard_veto_drop"]). The earnings branch equals the pre-fix code exactly.
    - Test (analog_gaps untouched): target_up/target_down still the median split for BOTH branches
      (only `gap` changes on the binary path; analog_gaps semantics unchanged).
    - Test (end-to-end survivability): feed the binary gap into size_for_survival(p_loss=0.5,
      gap=risk_inputs["gap"]) and assert the chosen size is SMALLER than size_for_survival with the
      median gap; and that risk_of_ruin at the chosen size with a -0.60 gap is <= ruin_cap
      (0.02) — a -60% tail is survivable within the ruin cap.
    - All tests fully offline (injected analog_source/proxy_fn/price_source; no network/LLM).
  </behavior>
  <action>
    Import binary_survival_gap from ..quant.sizing. Replace catalyst_context.py:116
    `gap = median(down_moves) if down_moves else abs(p["weekly"]["hard_veto_drop"])` with:
    ```python
    w = p["weekly"]
    if catalyst["catalyst_type"] in w["binary_catalyst_types"]:
        gap = binary_survival_gap(down_moves, percentile=w["binary_gap_percentile"],
                                  default=w["binary_gap_default"])
    else:
        gap = median(down_moves) if down_moves else abs(w["hard_veto_drop"])
    ```
    Leave the analog_gaps target_up/target_down lines exactly as-is. Update the module docstring's
    `gap:` bullet to state the binary-vs-not split. Missing params key RAISES (no literal fallback).
    Write the new tests in tests/test_desk_catalyst_context.py FIRST (RED) — including flipping the
    existing default-catalyst fixture where needed so the earnings/non-binary path is asserted
    byte-for-byte — then wire (GREEN). Existing tests that used a pdufa catalyst expecting the median
    gap must be updated to the new binary expectation (they encoded the bug).
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_desk_catalyst_context.py tests/test_desk_risk.py tests/test_desk_book_risk.py tests/test_sizing.py -q</automated>
  </verify>
  <done>Binary catalyst gap = tail/prior (not median); thin coverage = 0.70 default; earnings path
  byte-for-byte unchanged; the binary gap yields a smaller, -60%-survivable size. Named suites green.</done>
</task>

</tasks>

<verification>
Full suite stays green (backward-compat — only the binary catalyst gap changes):
```
.venv/bin/python -m pytest -q
```
No new magic numbers: percentile + default + binary type set all live in kb params
(missing-key raises). No new data source invented (reuses analog down-moves + stdlib quantiles).
No fabrication: the conservative default cites the existing 0.70/-70% codebase prior, NOT the
misusable base_rates crl_penalty.
</verification>

<success_criteria>
- BINARY catalysts size against the tail (or the 0.70 prior), never the ~8.5% median.
- A -60% binary tail produces a size whose risk_of_ruin <= ruin_cap (survivable).
- earnings/conference (non-binary) gap path is byte-for-byte identical to pre-fix.
- Percentile, default, and the binary type set are PARAMS (no literals); full suite green.
</success_criteria>

<output>
After completion, create `.planning/quick/260819-bgap-binary-tail-gap-sizing/260819-bgap-SUMMARY.md`
</output>
