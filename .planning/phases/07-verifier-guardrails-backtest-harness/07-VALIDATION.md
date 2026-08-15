---
phase: 7
slug: verifier-guardrails-backtest-harness
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-15
---

# Phase 7 — Validation Strategy

> Per-phase validation contract. Full per-requirement architecture in `07-RESEARCH.md ## Validation Architecture`. Money-honesty rules: pessimistic gap-open fill on held-through binaries; data-latency + point-in-time = NO look-ahead (rides the existing `<= as_of` guard); Layer B results LABELED biased-optimistic; survivorship-free event set; sample-based go/no-go; no silent truncation. Fully offline on synthetic-history fixtures; Layer B mocks `run_structured`. `.venv/bin/python -m pytest` only (bare python NOT on PATH).

---

## Test Infrastructure
| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio (`asyncio_mode=auto`) |
| **Config file** | pyproject.toml (existing) |
| **Quick run** | `.venv/bin/python -m pytest tests/test_backtest_engine.py -x` |
| **Full suite** | `.venv/bin/python -m pytest -q` |
| **Estimated runtime** | ~45 seconds (all mocked; synthetic history; no network) |

---

## Sampling Rate
- After every task commit: `.venv/bin/python -m pytest -q`
- After every wave: full suite
- Before verification: full suite green (expect ~831 baseline + new)
- Max feedback latency: ~45 seconds

---

## Per-Task Verification Map
| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| (filled by planner from `07-RESEARCH.md ## Validation Architecture` — per-req named tests: events/engine/fill/latency/layerb/gate/guardrails + performance metrics) | | | BACK-01..05, OPS-03 | unit (mocked) | `.venv/bin/python -m pytest -q` | ⬜ pending |

---

## Wave 0 Requirements
- [ ] 4 new metrics in `quant/performance.py`: `max_drawdown`, `win_rate`, `avg_win_loss`, `hedge_effectiveness` (numpy, no new deps) + `tests/test_performance.py` extensions
- [ ] `backtest/events.py` (point-in-time survivorship-free event-set builder) + `tests/test_backtest_events.py`
- [ ] `backtest/fill.py` (pessimistic gap-open + slippage knob + data-latency `effective_asof` knob) + `tests/test_backtest_fill.py` + `test_backtest_latency.py`
- [ ] `backtest/engine.py` (Layer A deterministic weekly loop) + `tests/test_backtest_engine.py`
- [ ] `backtest/layerb.py` (guarded-agentic replay + biased_optimistic label + sample/drop-log) + `tests/test_backtest_layerb.py`
- [ ] `backtest/gate.py` (sample-based go/no-go) + `tests/test_backtest_gate.py`
- [ ] `desk/guardrails.py` (thin runtime gate) + `tests/test_guardrails.py`

*Existing infra (pytest, bars_asof/universe_as_of/tradeable_catalysts, thesis_scan/size_for_survival/validate_hedge/select_book, sharpe/sortino/cumulative_return/attribution, the desk pipeline + run_structured mock seam) covers everything else.*

---

## Manual-Only Verifications
*None for the offline suite. Running the backtest on REAL historical data (vs synthetic fixtures) is a data-curation step gated on the seed universe + historical price/catalyst ingestion — it does not gate the phase's code/tests.*

---

## Validation Sign-Off
- [ ] **Layer A (BACK-02):** deterministic weekly loop re-expresses the corrected mechanics (NO LLM — reuses thesis_scan/size_for_survival/validate_hedge/select_book; catalyst-leg direction = base-rate proxy knob); entry 1-2d pre-event, SL/TP, 1-week exit; produces the baseline distribution.
- [ ] **Pessimistic fill (BACK-04):** held-through binary fills at the GAP-OPEN far-side (NOT the stop level — test); tunable slippage knob; skip only halted/delisted/zero-volume/zero-quote.
- [ ] **Data-latency + point-in-time (operator directive):** `effective_asof(class, D)` feeds the `<= as_of` functions so no data unavailable-at-decision-time leaks; look-ahead-impossible test; latency knob tunable.
- [ ] **Event set (BACK-01):** ~1yr earnings + dateable catalysts, point-in-time, INCLUDING delisted (survivorship-free — test).
- [ ] **Layer B (BACK-03):** real pipeline behind guardrails (web-free asserted, point-in-time fundamentals, outcome-blind prompts); results LABELED `biased_optimistic`; sampled with a logged drop-list (no silent caps).
- [ ] **Guardrails (OPS-03):** runtime gate enforces catalyst freshness, fact-check/provenance, WF-3 firewall, net-long/concentration caps, no-scraped-to-order — test-enforced.
- [ ] **Gate (BACK-05):** sample-based go/no-go (never calendar-based); baseline includes max-DD + hedge-effectiveness.
- [ ] All BACK-01..05 + OPS-03 covered; no live API; no new dependencies.
- [ ] `nyquist_compliant: true` on sign-off.

**Approval:** pending
