# Universe Expansion — Claude's Insight Log

## Monitor started — what to expect
This run does the whole pipeline on live data: discovery (CT.gov + 5-yr efts) → backfill each name's historical catalysts + compute the realized T-1→T+2 price move around each → screen names by median catalyst move (≥10% default) → rank by move → write the cohort. The long tail is the backfill: hundreds of 8-K exhibits + a daily-bar fetch per past catalyst, all rate-limited (accuracy over speed). Watch "Historical catalysts" climb, then "Catalyst moves", then "Cohort written" jumps at the end. Graceful `degraded`/timeout lines are EXPECTED and handled (never fatal) — only a stalled heartbeat (no new fetch for minutes) is a real concern.

## Backfill big, moves phase reached
The 5-yr efts backfill persisted ~779 historical catalysts (from 65) — far more breadth than the 1-yr window (20 names). CBOE screening is running (300+ chains pulled). Now computing per-catalyst realized moves (T-1→T+2). Most efts catalysts are FUTURE-dated PDUFAs → their move is None (not yet knowable) and won't get a catalyst_move row — so expect "moves computed" to be much smaller than total catalysts; that's correct, not a stall. The cohort write is the final step after the move-screen ranks names.

## Daily-bar blocker fixed — re-run launched
Root cause of the 0-admit run found: the daily providers couldn't serve historical windows (Tiingo needs a key, Nasdaq free daily is recent-only), so only 1 of 779 catalyst moves computed → the move-screen rejected all 256 candidates. Fixed by adding yfinance DAILY to the daily set (verified: BBIO 2024 moves now compute). Re-running now — this pass should actually populate catalyst_move and admit a movement-screened cohort. 1180 tests green.

## Frugality pass, then re-run
Locked in the API-call rule: only call when data is genuinely unavailable cheaper. Price cascade is now FREE-UNLIMITED ONLY (yfinance + Nasdaq — a zero-quota 2-source cross-check); Tiingo/Alpha Vantage are fallback-only (AV's 25/day is never touched on a bulk sweep). Added a persistent read-through over the raw archive so this re-run REUSES today's already-fetched SEC filings + price bars instead of re-calling them. FRED (the one genuine unlock — macro regime) is ready but not part of the universe build. Re-running now, free + cache-served.

## Direction fix: build the universe BACKWARD
The first cohort came back thin (4 names) — and the real reason isn't the names, it's the direction. We were finding companies by their UPCOMING events, then trying to measure their PAST moves — but 568 of 779 events are in the future, so there was almost nothing to measure. Pivoting: pull ALL PDUFA decisions from the last 5 years, measure how each name's stock actually moved on those PAST decisions, rank by that proven volatility, and cut the calmest names until we have a tradeable universe. Membership by history, not by hope. Also relaxing the options check (it was wrongly rejecting clearly-liquid names like INSM on junk after-hours spread data). Re-planning now → will re-run once checked.
