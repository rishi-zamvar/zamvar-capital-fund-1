# Phase 7.9 — Structured Analyst & Diligence Reports

**Added 2026-08-19.** CEO decisions: **full structured schema** (faithful to the guideline) + **both the 4 researchers AND the 8 diligence dimensions**.

## Why
The current analyst output (`AnalystSignal` = score/confidence/thesis/key_findings/unknowns) is a jargon-dense paragraph. The CEO wants each researcher (and each DD dimension) to emit a **structured, data-rich, plain-language one-pager** following a fixed per-lens format — deeper "so what," more data points, no undefined jargon — which also makes outputs far more legible to the downstream debate/DD/MD agents.

## Spec
`.planning/research/analyst-report-guideline.md` — the approved design. It defines, per lens: (A) ordered section headers, (B) a quantitative data-point checklist + source of each, (C) the judgment framework, a leading BOTTOM LINE + number, the Plain-Language Standard (§5), the roll-up (§6), and the full JSON schema (§7). Numbers default to null — never fabricate; an empty slot is a finding.

## ARCHITECTURE UPDATE 2026-08-20 (CEO) — shared Research Bundle substrate
CEO insight: the analysts, builder, and DD were each independently re-fetching/re-deriving the SAME facts (4× analog_query, DD re-sourcing market_data, builder its own analogs). Generalize into ONE shared, cited **Catalyst Research Bundle** (the "research nodes") computed once and fed to the desk AND the DD firewall. Win: frugality (each free source hit once) + consistency (identical ground truth everywhere). **FIREWALL LINE (non-negotiable):** the bundle carries only cited FACTS (evidence_ref-tagged), NEVER the desk's interpretations (analyst scores/theses, debate verdict, builder dossier). DD reads the same FACTS but forms its verdict INDEPENDENTLY — this preserves (and strengthens) the independent-diligence firewall (a DD-vs-desk disagreement becomes pure judgment, not a data artifact). Cite-or-drop preserved: agents cite the bundle's refs.

## Waves (each its own GSD plan → plan-check → execute → verify)
- **Plan 1 — the 4 researcher lens reports.** DONE (commits 8905a48/31f713e/777b638, suite 1801). 4 lens contracts + one-pager prompts + plain-language rule 7 + no-fabrication invariant; DD half untouched (schema split clean). CALL-01 NOT closed (spans Plan 2/3).
- **Plan 1.5 (NEW) — the Catalyst Research Bundle.** A deterministic research pass computing every cited fact once (KB analogs, base rates, financials via edgar.fundamentals, trial stats via CT.gov, options-implied via CBOE, ownership via Form-4/FINRA, price/positioning) → a structured, evidence_ref-tagged substrate. FACTS ONLY (firewall line). Feeds analysts + builder + DD. Absorbs/replaces `make_diligence_inputs` sourcing. This is the input-layer consolidation.
- **Plan 2 (RE-SCOPED) — the 8 diligence-dimension reports, reading the bundle.** Give the 8 DD dims their own structured report format (bottom-line + checklist + verdict per dim), plain-language — and source their facts from the Plan-1.5 bundle instead of re-fetching. OPEN DECISION (surface at Plan 2): does DD ALSO keep an independent re-pull as a belt-and-suspenders data-integrity cross-check, or read the shared bundle only? (CEO leaned consolidation.)
- **Plan 3 — roll-up + consumers.** The single-thesis roll-up (guideline §6: fundamental P vs market-implied P → edge; payoff map; solvency gate; expression). Wire debate/verifier/MD to consume the richer structured reports. Plain-language rendering for the artifacts.

## Guardrails (from the guideline + CLAUDE.md)
- Plain-Language Standard is a HARD RULE (define terms inline; every number gets context; lead with the so-what).
- Cite-or-drop stays absolute; depth = deeper interpretation of cited facts; numbers default null, NEVER fabricated (an empty slot is an honest finding).
- Money/sizing math untouched (this is a narrative/structure change — agents still don't do arithmetic).
- TDD; offline tests; update every construction site (AnalystSignal is used across analysts + DD + many test fixtures — enumerate exhaustively per plan, as prior slices showed the grep undercounts dict-builders/fixtures).

## Live proof (per plan)
Re-run the relevant agents live on CAPR + rebuild the artifact in the new one-pager format so the CEO sees the richer, plain-language output.
