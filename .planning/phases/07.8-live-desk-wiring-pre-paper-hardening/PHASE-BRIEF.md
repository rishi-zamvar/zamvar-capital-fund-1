# Phase 7.8 — Live Desk Wiring & Pre-Paper Hardening

**Added:** 2026-08-19 · **Status:** in progress · **Runtime decision (CEO):** Max subscription, agents run inside Claude Code, NO API key.

## Why this phase exists
Scoping (2026-08-19) corrected the premise: the agentic desk is **architecturally complete and genuinely LLM-driven** — 4 catalyst analysts, bull/bear/moderator debate, cite-or-drop verifier, trade builder, 3-view risk committee, 8-dim independent diligence, opus MD reconciliation — all real `run_structured` calls (`desk/runtime.py`, Claude Agent SDK). Money math stays deterministic (correct invariant). But it is a **brain in a jar**:
- It has **never run against a live model** — every test mocks the LLM seam; `ANTHROPIC_API_KEY` is off (built to run inside Claude Code). Live behavior of SDK `query()` + json_schema structured output + in-process MCP tool-calling is UNVERIFIED. **This is the single load-bearing unknown.**
- **DD + MD reconciliation are orphaned** — unit-tested but called from nowhere outside tests; `run_weekly` stops at a dossier.
- **No live `catalyst_context`** (entry price + analog feed) is wired into the desk in any runner.

Phase 8 (paper ledger), 9 (approval gate), 11 (execution) already exist in the roadmap and assume this wire exists. This phase builds the missing wire, walking-skeleton first, so a bad assumption is caught on one hand-checked catalyst — never compounded into a book.

## Principle (CEO): future-facing, errors don't compound
Each slice runs ONE real catalyst end-to-end and is independently verified before the next is built. De-risk the biggest unknown first. Nothing executes without the human gate; paper before live.

## Slices (gated)
- **Slice 0 — Live-LLM smoke test (de-risk FIRST).** Run `run_structured` for real: one tiny prompt + pydantic schema + one `mcp__quant__*` tool, under Max/inside-CC. Confirm: does the SDK inherit Max auth (no key)? does json_schema structured output validate on v0.2.139? does the in-process quant MCP server get invoked? measure per-call latency + a per-catalyst cost estimate. **Verifiable:** one real structured response validates; open runtime questions answered with evidence.
- **Followup 1 — Hedge-profile coverage backfill.** Free weekly-bar pull for the 82 skipped tickers → stamp profiles → near-full universe coverage.
- **Followup 2 — Portfolio what-if engine into weekly assembly.** Wire `build_portfolio` so a candidate weekly book is risk-checked (exposure/corr-adjusted vol/scenario/ruin) inside `run_portfolio`/`run_weekly`.
- **Slice 1 — One catalyst → dossier (live).** Bind a live `catalyst_context` (RH read adapter entry price + KB analogs); pick one upcoming catalyst from `calendar.refresh`; run `run_desk` → `run_portfolio` live. **Verifiable:** a real `StrategyDossier`, hand-checked.
- **Slice 2 — Attach DD + MD loop.** Wire `run_diligence` + `md.reconcile` after the dossier (they exist, just unconnected). **Verifiable:** one `MDDecision` (enter/pass/escalate) + round log on one real candidate.

## Downstream (already roadmapped — this phase feeds them)
- Slice 3 (human gate) → **Phase 9**. Slice 4 (paper ledger + paper fills) → **Phase 8**. Slice 5 (T-2 trigger + weekly scheduler) → folds into Phase 8/8.5. Slice 6 (live execution) → **Phase 11** (strictly last, after a clean paper month).

## Biggest risks
1. Live-LLM seam divergence from the mocks (Slice 0 resolves). 2. Cost/latency: ~30-40 calls/catalyst, several opus (measure in Slice 0). 3. Orphaned DD/MD integration untested end-to-end (Slice 2). 4. `biased_optimistic` — only the forward paper month validates the desk; the backtest cannot. 5. Prompt duplication `desk/*.py` (source of truth) vs `.claude/agents/*.md` (parity docs) — drift risk.

## Progress
- 2026-08-19 **Slice 0 PASS** (SLICE0-RESULT.md): live LLM seam validated under Max/inside-CC, no API key — structured output + in-process quant MCP tool-calling both work (full-precision match), ~10-11s/call. Load-bearing unknown retired. Commit 048cef2.
- 2026-08-19 **Followup 1 DONE**: free weekly-bar backfill (price_backfill_free) → 73/76 tradeable-universe names now hedge-profiled (3 gaps = delisted BXRXQ/CMRX/LIANY, honest skip). Data-only, reused existing tooling.
- 2026-08-19 **Followup 2 DONE** (quick-pf2, 3/3, suite 1658): book_to_portfolio_inputs adapter + auto-attach whole-book PortfolioOutcome (target-leg risk read) onto promoted dossiers via PortfolioContext.portfolio_outcome; conn-guard keeps offline suites green; money path byte-for-byte. Commit 309bf69.
- 2026-08-19 **Slice 1 DONE + live hand-check PASS** (commits a4e0d42/ec3ac95/894b884): `desk/catalyst_context.py` live hook (entry + risk_inputs, point-in-time, honest single-leg degrade) + `scripts/run_one_catalyst.py` harness (11 tests). LIVE CAPR run: full desk ran end-to-end, verdict=NEGATIVE conf 0.62 — caught the 3-9 AdCom vote (post-HOPE-3), flagged its own analysts' stale pre-AdCom signals, read the +79% as short-covering, honest about the missing FDA/AdCom concordance base rate. Zero-trade = CORRECT (negative thesis, long-only can't express). The brain works, high quality.
  - FOLLOW-UP (real, tracked): `gap` for binary catalysts is the MEDIAN analog move (~8.5%), far too small vs binary tails (30-70%) — survival-sizing off a median would under-price the tail on an actual trade. Binary catalysts need the TAIL/adverse gap, not median. Pre-existing desk behavior; fix before real trades.
  - Not yet seen live: a PROMOTED-trade dossier (CAPR was no-trade) — capture in Slice 2's live check on a positive-leaning catalyst.
- NEXT: **Slice 2** — attach the orphaned run_diligence + md.reconcile after the dossier (→ MDDecision enter/pass/escalate).

## Reuse (do not rebuild)
`desk/runtime.run_structured`, `desk/orchestrator.run_desk/run_portfolio`, `desk/diligence.run_diligence`, `desk/md.reconcile`, `calendar/refresh`, `serving.asof`, `providers/robinhood` (read-only), `desk/portfolio_builder.build_portfolio`, `kb.hedge_profile`.
