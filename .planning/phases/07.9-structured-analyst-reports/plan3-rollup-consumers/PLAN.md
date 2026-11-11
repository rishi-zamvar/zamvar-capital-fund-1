---
phase: 07.9-structured-analyst-reports
plan: 3
type: tdd
wave: 2
depends_on: ["01", "1.5", "02"]
files_modified:
  - src/catalyst_trader/contracts/__init__.py
  - src/catalyst_trader/desk/rollup.py
  - src/catalyst_trader/desk/debate.py
  - src/catalyst_trader/desk/verifier.py
  - src/catalyst_trader/desk/diligence.py
  - src/catalyst_trader/desk/md.py
  - tests/test_rollup.py
  - tests/test_desk_debate.py
  - tests/test_desk_verifier.py
  - tests/test_desk_md.py
autonomous: true
requirements: [CALL-01]
must_haves:
  truths:
    - "A deterministic roll-up (guideline §6) is computed from the 4 lens reports: fundamental P(approval) reconciled from Clinical pos_estimate + Regulatory poa.point (disagreement beyond a tolerance is flagged — the disagreement is itself the finding), market-implied P from Lens-4 X/Z/Y (p=(X-Y)/(Z-Y), computed in code, never by the agent), edge = fundamental - implied, the Lens-3 solvency gate (runway.clears_catalyst), and the Lens-4 expression/driver."
    - "Every roll-up number is null when any input is null — never fabricated, never defaulted to 0."
    - "The debate's shared evidence context carries each report's structured, non-null data points + its headline number/source AND the roll-up block (both sides + moderator see the richer reports)."
    - "The verifier (and the DD cite-or-drop gate, which now reuses the same helper) maps a cited headline *_source ref to a precise '<field>=<value>' claim instead of falling back to the verdict thesis."
    - "The MD review prompt renders the DD per-dimension headline numbers from dossier.per_dimension (tolerates the thin raw dicts other tests build)."
    - "Money/sizing math untouched: no size_pct / conviction-to-size in the roll-up (sizing stays in risk.py); synthesize_verdict/dimension_passed/size paths unchanged. DD firewall intact: DD never sees the roll-up or the lens reports."
---

<objective>
Close Phase 7.9: the single-thesis roll-up (§6) + wire debate / verifier / MD to consume the
structured reports. Deterministic, null-propagating, offline.

Deliberate cuts (YAGNI, noted):
- `size_pct` / `conviction` from §7 rollup: OMITTED — they are sizing, and sizing lives in risk.py
  (money math untouched). Add only if the CEO wants a non-binding display label.
- Payoff map (upside/downside vs rNPV and market cap): OMITTED. It needs market cap plus a cited rNPV, and
  rNPV is a qualitative, agent-sourced number (C5). Add it once the bundle has a deterministic market cap.
- Analyst tool-backing (`build_quant_tools` via bundle `fact_for`), deferred here by Plan 2, is still
  deferred. It only changes whether data is precomputed or fetched live, not the report shape, and
  it is a separate TDD slice.
</objective>

<tasks>
<task type="auto" tdd="true">
  <name>Task 1: Rollup contract + desk/rollup.py (headline map, roll-up, structured renderer)</name>
  <behavior>
    tests/test_rollup.py: full lens set -> fundamental=mean(pos, poa), implied=(X-Y)/(Z-Y), edge;
    disagreement flag over tolerance; any null input -> null output; implied out of [0,1] or Z==Y -> null;
    solvency gate + expression passthrough; missing lens -> nulls; headline() reads models AND dicts;
    render lists only non-null leaves + headline with source.
  </behavior>
</task>
<task type="auto" tdd="true">
  <name>Task 2: Consumers — debate context, verifier/DD claim_for, MD DD-headline block</name>
  <behavior>
    debate _evidence_context includes structured data points + ROLL-UP; verifier _claim_for maps a
    headline source ref to '<field>=<value>'; diligence reuses verifier._claim_for; MD review prompt
    lists DD headline numbers and tolerates raw per_dimension dicts. Full suite green.
  </behavior>
</task>
</tasks>

<output>.planning/phases/07.9-structured-analyst-reports/plan3-rollup-consumers/07.9-3-SUMMARY.md</output>
