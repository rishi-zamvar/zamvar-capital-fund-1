# Quick 260819-p1x — Daily+Latency Backtest FINDINGS

Warm-playbook walk-forward window: **2025-08-17 → 2026-08-10**. Deterministic Layer-A (NO-LLM), point-in-time correct, over the REAL cached daily bars (no injected synthetic bars).

## 1. Weekly vs Daily distribution

| Path | Win rate | Avg win | Avg loss | Sharpe | Sortino | Max DD | Trades | Weeks |
| ---- | -------- | ------- | -------- | ------ | ------- | ------ | ------ | ----- |
| Weekly baseline | +20.37% | +35.09% | +6.52% | 1.30 | 7.91 | -3.85% | 108 | 52 |
| Daily reflex | +17.59% | +6.67% | +13.10% | -2.13 | -2.15 | -8.72% | 108 | 52 |

**Daily − Weekly delta (headline):** win_rate -2.78 pp, Sharpe -342.63 pp, max_drawdown -4.87 pp. _(This delta is the primary Task-B go/no-go input: does spending judgment at entry + reflexive intraweek exits beat the crude weekly hold?)_

## 2. Latency degradation (T+0 / T+1 / T+2)

| Delay | Win rate | Avg win | Avg loss | Sharpe | Sortino | Max DD | Trades | Weeks |
| ----- | -------- | ------- | -------- | ------ | ------- | ------ | ------ | ----- |
| T+0 | +17.59% | +6.67% | +13.10% | -2.13 | -2.15 | -8.72% | 108 | 52 |
| T+1 | +18.52% | +39.23% | +14.88% | 0.63 | 2.30 | -7.28% | 108 | 52 |
| T+2 | +14.81% | +54.15% | +14.06% | 0.72 | 2.62 | -6.90% | 108 | 52 |

_An edge visible only at T+0 (no execution lag) is fragile — read this table WITH the §6 caveat below before drawing any conclusion._

## 3. Data coverage

Daily catalyst legs FILLED / catalyst opportunities in the event set: **42 / 114 = 36.8%**.

The denominator is every catalyst opportunity `build_event_set` surfaced over the window; the numerator is the catalyst legs the daily reflex actually filled from the cache. Abstained legs are un-populated / degraded tickers or holiday-`exit_by` weeks whose bar landed inside the execution buffer.

## 4. off_map frequency

off_map legs / all daily legs: **1 / 108 = 0.9%**.

_off_map = an intraweek move no scenario-table branch covers (the Task-B escalation seam). State this number explicitly for the Task-B go/no-go — it sizes the off-map reasoning-agent workload the next step must handle._

## 5. Plain-English read

The daily reflex does not clearly beat the crude weekly hold on risk-adjusted return (win-rate delta -2.78 pp); under global exit latency it degrades to T+2. Coverage was 36.8% of catalyst opportunities and 0.9% of daily legs went off-map. Coverage caveats (abstained / holiday legs) are honest gaps, not silent zeros — an abstained leg is simply dropped, never fabricated. Read the §2 latency table strictly through the §6 caveat.

## 6. MANDATORY latency-interpretation caveat

The sweep in §2 applies `exit_latency_bars` **globally to ALL exits**. But per the execution model, on-map stop-loss / take-profit exits are **resting broker-side orders** with ~zero reasoning latency — only the **off-map** path carries reasoning latency (an agent must think before it acts). So the §2 latency table is a **pessimistic UPPER BOUND** that over-penalizes on-map resting exits by charging them a reasoning delay they would never incur live.

Per-exit-type latency (broker ≈ 0 for on-map SL/TP, reasoning-latency only for off-map) is a **Step-4 mitigation**. Therefore an edge that looks *globally erased* here must **NOT** be read as a real failure into the Step-5 go/no-go — a globally-erased edge is a **false-negative artifact** of applying reasoning latency to broker-side orders, not a real one. Read §2 against the off_map frequency in §4: the smaller §4 is, the more of §2's degradation is this artifact.
