# Quick 260819-p1x — Daily+Latency Backtest FINDINGS

Warm-playbook walk-forward window: **2025-08-17 → 2026-08-10**. Deterministic Layer-A (NO-LLM), point-in-time correct, over the REAL cached daily bars (no injected synthetic bars).

## 1. Paired covered-subset comparison (PRIMARY go/no-go)

Paired covered legs (filled on BOTH paths, same week+ticker): **42**. Daily reflex vs weekly hold, apples-to-apples on the identical legs:

| Path | Win rate | Avg win | Avg loss | Mean ret | Sum ret |
| ---- | -------- | ------- | -------- | -------- | ------- |
| Daily reflex | +40.48% | +49.71% | -20.93% | +7.67% | +321.95% |
| Weekly hold  | +50.00% | +36.72% | -6.09% | +15.31% | +643.16% |

**Weekly − daily (headline):** mean +7.65 pp, sum +3.21. Per-leg the reflex HURT (weekly better by >0.5pp) **25**, HELPED **17**, ~same **0**. Under M1 a hold-through leg holds to the time barrier, so the daily paired path should now converge to the weekly baseline (edge restored).

**Mandatory caveats (read WITH the number, per the adversarial vet):**

- **(i) IN-SAMPLE HEALTH WARNING:** this is the same history the playbook was built on — a tiny ~48-leg / 7-winner set whose weekly edge is dominated by ~7 legs at mean +107%. Trust the RANKING and DIRECTION (is the reflex net-harmful?), NOT the magnitude. The forward paper month is the real proof.
- **(ii) ENTRY-BASIS CAVEAT:** the weekly leg enters at the decision-week CLOSE; the daily leg enters at the next tradeable daily OPEN. The raw paired delta therefore conflates exit-timing with an entry-basis difference — it is NOT a pure exit-only isolation (no re-basis is attempted; the caveat IS the mitigation the vet mandated).
- **(iii) POST-FIX off_map RE-EMIT:** this run's off_map = **0/108 (0.0%)**, re-measured on the FIXED (post-M1) band. The pre-fix 1/48 (~2%) is PROVISIONAL — it was measured under the broken band; the Task-B off-map go/no-go must re-decide on this fixed number.

## 2. Weekly vs Daily distribution

| Path | Win rate | Avg win | Avg loss | Sharpe | Sortino | Max DD | Trades | Weeks |
| ---- | -------- | ------- | -------- | ------ | ------- | ------ | ------ | ----- |
| Weekly baseline | +20.37% | +35.09% | +6.52% | 1.30 | 7.91 | -3.85% | 108 | 52 |
| Daily reflex | +16.67% | +47.00% | +17.71% | 0.50 | 1.54 | -10.34% | 108 | 52 |

**Daily − Weekly delta:** win_rate -3.70 pp, Sharpe -79.87 pp, max_drawdown -6.49 pp. _(Whole-book distributions differ in trade MIX from §1's paired subset; §1 is the fair apples-to-apples go/no-go.)_

## 3. Latency degradation (T+0 / T+1 / T+2)

| Delay | Win rate | Avg win | Avg loss | Sharpe | Sortino | Max DD | Trades | Weeks |
| ----- | -------- | ------- | -------- | ------ | ------- | ------ | ------ | ----- |
| T+0 | +16.67% | +47.00% | +17.71% | 0.50 | 1.54 | -10.34% | 108 | 52 |
| T+1 | +15.74% | +54.17% | +17.13% | 0.60 | 2.00 | -9.58% | 108 | 52 |
| T+2 | +16.67% | +53.00% | +17.07% | 0.70 | 2.36 | -8.88% | 108 | 52 |

_An edge visible only at T+0 (no execution lag) is fragile — read this table WITH the §7 caveat below before drawing any conclusion._

## 4. Data coverage

Daily catalyst legs FILLED / catalyst opportunities in the event set: **42 / 114 = 36.8%**.

The denominator is every catalyst opportunity `build_event_set` surfaced over the window; the numerator is the catalyst legs the daily reflex actually filled from the cache. Abstained legs are un-populated / degraded tickers or holiday-`exit_by` weeks whose bar landed inside the execution buffer.

## 5. off_map frequency

off_map legs / all daily legs: **0 / 108 = 0.0%**.

_off_map = an intraweek move no scenario-table branch covers (the Task-B escalation seam). Post-M1 a hold-through catalyst leg can surface off_map ONLY via a halt roll (band-excess off_map is suppressed for hold-through legs). State this number explicitly for the Task-B go/no-go — it sizes the off-map reasoning-agent workload the next step must handle._

## 6. Plain-English read

The daily reflex does not clearly beat the crude weekly hold on risk-adjusted return (win-rate delta -3.70 pp); under global exit latency it degrades to T+2. Coverage was 36.8% of catalyst opportunities and 0.0% of daily legs went off-map. Coverage caveats (abstained / holiday legs) are honest gaps, not silent zeros — an abstained leg is simply dropped, never fabricated. Read the §3 latency table strictly through the §7 caveat, and the §1 paired subset as the fair go/no-go.

## 7. MANDATORY latency-interpretation caveat

The sweep in §3 applies `exit_latency_bars` **globally to ALL exits**. But per the execution model, on-map stop-loss / take-profit exits are **resting broker-side orders** with ~zero reasoning latency — only the **off-map** path carries reasoning latency (an agent must think before it acts). So the §3 latency table is a **pessimistic UPPER BOUND** that over-penalizes on-map resting exits by charging them a reasoning delay they would never incur live.

Per-exit-type latency (broker ≈ 0 for on-map SL/TP, reasoning-latency only for off-map) is a **Step-4 mitigation**. Therefore an edge that looks *globally erased* here must **NOT** be read as a real failure into the Step-5 go/no-go — a globally-erased edge is a **false-negative artifact** of applying reasoning latency to broker-side orders, not a real one. Read §3 against the off_map frequency in §5: the smaller §5 is, the more of §3's degradation is this artifact.
