---
phase: quick-260819-pers
plan: 01
subsystem: desk/analysts
tags: [prompts, personas, cite-or-drop, CALL-01]
requires: [analysts.build_prompt, analysts.PROMPTS]
provides: ["4 expert-persona analyst PROMPTS", "shared DEPTH DIRECTIVE (HARD RULE 6)"]
affects: [desk.analysts]
key-files:
  modified:
    - src/catalyst_trader/desk/analysts.py
    - tests/test_desk_analysts.py
decisions:
  - "Depth is defined as a deeper INTERPRETATION of already-tool-cited evidence, never a new claim — subordinate to cite-or-drop"
metrics:
  duration: ~8m
  completed: 2026-08-19
---

# Phase quick-260819-pers Plan 01: Analyst Expert Personas Summary

Rewrote the 4 generic analyst job strings into distinct named top-expert personas that reason to the WHY, and added ONE shared DEPTH DIRECTIVE (HARD RULE 6) in `build_prompt` — explicitly subordinate to cite-or-drop so depth never opens a fabrication vector. Prompt-string change only.

## The 4 New Personas (verbatim job strings)

**clinical** — physician-scientist (MD/PhD), test keyword `clinically meaningful`:
> "You are a PHYSICIAN-SCIENTIST (MD/PhD) serving as the clinical/scientific analyst. Reason from mechanistic biology upward: is the drug's mechanism of action causally plausible for this indication, and is the trial design valid — endpoint choice, statistical powering, control arm, blinding, and confounders? Decisively, judge whether the primary endpoint is clinically meaningful to patients, not merely statistically significant, and assess the causal plausibility of the efficacy signal. Weigh phase-transition odds and how mechanistically similar past readouts resolved."

**regulatory** — FDA regulatory counsel (lawyer), test keyword `regulatory counsel`:
> "You are FDA REGULATORY COUNSEL (a lawyer) serving as the regulatory analyst. Reason to the procedural WHY: what was the FDA's ACTUAL deficiency or ask, which review pathway applies and what precedent binds it, and — for any AdCom — the panel voting dynamics and what a panel vote does and does not legally bind the agency to do. Read the relevant FDA guidance and statute the way regulatory counsel would, and reason from PDUFA/AdCom precedent for this therapeutic class, prior CRLs, and the review division's posture."

**financial** — CFO, test keyword `CFO`:
> "You are a CFO serving as the financial analyst. Reason to the WHY behind the numbers: the balance-sheet and cash-runway mechanics into and past the catalyst, the STRUCTURE of any dilution or financing (ATM, shelf, convertible, warrant coverage), and — critically — what recent capital-markets moves (raises, ATM usage, insider buying or selling) SIGNAL about management's own conviction in the outcome. Judge financial resilience and the asset's risk-adjusted valuation sensitivity around the event."

**market_sentiment** — buy-side PM / microstructure specialist, test keyword `microstructure`:
> "You are a BUY-SIDE PORTFOLIO MANAGER and market-microstructure specialist serving as the market/sentiment analyst. Reason to what is already PRICED IN: decompose the options-implied move vs realized analog moves, the options skew and short-interest mechanics, and the crowding/positioning — then ask who is on the other side of this trade and why. Microstructure is the point: identify where consensus positioning is fragile or already exhausted."

## The DEPTH DIRECTIVE (new HARD RULE 6, verbatim)

> 6. DEPTH (subordinate to rule 2): reason one level deeper than consensus — every finding states the WHY behind it (the mechanism, precedent, or cause), and surface at least one non-obvious second-order insight a generalist would miss. This depth is a deeper INTERPRETATION of evidence you have already tool-cited: introduce no new uncited claim. An insight without a supporting tool evidence_ref is dropped. Cite-or-drop (rule 2) always prevails over depth.

## Guardrail Proof — depth cannot become fabrication

- **Subordination invariant** (`test_depth_directive_is_cite_or_drop_subordinate`, parametrized over all 4 dims): asserts BOTH halves of the guardrail are present in every prompt — `"no new uncited claim"` AND (`"evidence_ref"` with `"dropped"`) — plus that `"cite-or-drop"` (rule 2) and `"cited key_findings"` (rule 5) survive verbatim.
- **Schema floor** (`test_uncited_finding_rejected`, pre-existing): a citation-free payload is still rejected at the real `AnalystSignal` boundary through `run_structured`. Stays green — the string change did not touch the schema seam.

## Preserved invariants (rules 1–5 verbatim)

- Rule 1 tool mandate (`mcp__quant__` present), rule 2 cite-or-drop, rule 3 unknowns, rule 4 double-quoted `"{dimension}"` token, rule 5 grounded thesis (`cited key_findings`) — all unchanged.
- Kept-green regression tests: `test_prompt_mandates_quant_tools_and_dimension_token` (mcp__quant__ / clinical / ACME), `test_prompt_mandates_grounded_thesis` (thesis / cited key_findings), `test_desk_orchestrator.py` double-quoted dimension token.

## Backward-compat

- `git diff --name-only` = exactly `src/catalyst_trader/desk/analysts.py` + `tests/test_desk_analysts.py`.
- `AnalystSignal` schema, thesis field, money/sizing paths, and the 8 DD dimensions (`diligence.build_dimension_prompt`) untouched — prompt-string change only.

## Test counts

- Targeted (`test_desk_analysts` + orchestrator + debate + verifier): **36 passed**.
- Full `tests/`: **1769 passed, 1 xfailed** (the xfail is the pre-existing deferred `test_off_map_escalates_to_reasoning_agent` latency-sweep wiring — unrelated).
- 8 new persona/subordination asserts went RED-before-GREEN (TDD verified).

## Deviations from Plan

Path note only: plan frontmatter listed `src/catalyst_trader/desk/analysts.py`; the actual repo path matched, so no deviation. No behavioral deviations — plan executed as written.

## Known Stubs

None. No hardcoded/placeholder values introduced; change is prose-only prompt text.

## Self-Check: PASSED

- FOUND: src/catalyst_trader/desk/analysts.py, tests/test_desk_analysts.py
- FOUND: commit cb8c85e (feat(quick-260819-pers): deepen 4 analysts into distinct expert personas)
- Not pushed (per instruction — CEO will push + run the live demo).
