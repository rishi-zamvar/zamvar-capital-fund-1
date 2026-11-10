# Phase 9: iOS Dashboard + Approval Gate - Context

**Gathered:** 2026-11-10
**Status:** Ready for planning
**Source:** PRD Express Path (operator brief; discuss-phase --auto unavailable in this session, decisions taken at recommended defaults)

<domain>
## Phase Boundary

Two deliverables:
(a) A Python FastAPI + SSE serving shim over the existing paper ledger / KB: read-only views of the week,
    positions + P&L, history, playbook, and the diligence dossier, plus approve/reject endpoints that
    route to the EXISTING gate (`paper_ledger.approve_pending` / `reject_pending`), and an MD chat
    endpoint (SSE) behind the existing mocked LLM seam (`desk.runtime.run_structured`).
(b) A SwiftUI iOS 17+ app (`ios/`, Swift Charts, zero third-party deps) with five tabs: This Week,
    History, Playbook, Dossier review (approve/reject), MD chat. Built for the simulator via xcodebuild;
    unit tests on decoding + view-models.

Out of scope: live broker execution (Phase 11), Phase 8 attribution math (built in parallel — empty
state here), push notifications, a server-push event stream (pull-to-refresh is enough for a weekly book).
</domain>

<decisions>
## Implementation Decisions

### The gate (inviolable)
- The ONLY write endpoints are `POST /api/v1/decisions/{id}/approve|reject`. They call
  `paper_ledger.approve_pending` / `reject_pending` verbatim — no new opener, no position insert.
- Approve of an absent id -> 404; of a rejected id -> 409; re-approve -> idempotent (same position id).
  Reject of an already-resolved id -> 409 (never silently flips an approved record).
- Chat has NO tools (`allowed_tools=[]`), so the MD can explain but never approve.
- The app shows a confirmation dialog before approve; there is no auto-approve path anywhere.
- No live-broker module is imported by the shim (asserted by a grep test).

### Persisting the review snapshot
- `paper_pending` only stores position params today; the dossier (thesis, kill criteria, pre-mortem,
  SL/TP, DD verdict, MD rationale) is lost after submit. Migration 017 adds a nullable
  `paper_pending.review` JSON column; `submit_for_approval(conn, params, review=None)` stores it;
  `paper_run.submit_decision` passes `review_snapshot(result)`. Additive — older rows show an empty state.

### Transport (IOS-06)
- ZeeChat precedent: HTTP + SSE over Tailscale, app polls/pulls. Bearer shared-secret token
  (`DASHBOARD_TOKEN`, >= 16 chars, constant-time compare) on every `/api/v1/*` route except `/health`.
- Bind guard: the launcher refuses any host that is not loopback or inside Tailscale CGNAT 100.64.0.0/10
  (no 0.0.0.0, no LAN/public). Default 127.0.0.1.
- Chat: `POST /api/v1/chat` returns `text/event-stream` (`event: delta` chunks, then `event: done`).

### Metrics
- Reuse `quant.performance` (sharpe periods_per_year=52, win_rate, cumulative_return); a metric that
  raises on too-few points is served as `null` (honest empty state, never a fabricated 0).
- Book return per closed trade = size_pct * realized_ret; equity curve compounds by close date.
- Benchmark = 1%/week (`BENCHMARK_WEEKLY = 0.01`).
- Attribution: `null` + `attribution_status: "pending_phase_8"`; app renders an explicit empty state.
- Calibration: per closed trade predicted `expected_return_pct` (from the review snapshot) vs realized.

### iOS
- XcodeGen `project.yml` (user's WorkoutCoach precedent), generated `.xcodeproj` committed.
- `@Observable` view-models over an `APIClient` protocol (stub in tests). Token in Keychain.
- ATS: arbitrary loads allowed (Tailscale http, internal app — matches WorkoutCoach precedent).

### Claude's Discretion
- Module name `catalyst_trader/dashboard_api.py` (serving.py is the PIT databook, not HTTP — reuse it
  for reads where point-in-time matters, i.e. bars via `serving.asof`).
- Launcher `scripts/serve_dashboard.py`.
</decisions>

<canonical_refs>
## Canonical References
- `src/catalyst_trader/paper_ledger.py` — the gate + lifecycle (approve_pending is the sole opener)
- `scripts/paper_run.py` — submit_decision (the submit path to extend with the review snapshot)
- `scripts/weekly_cycle.py` — status() query shapes for open/pending/upcoming
- `src/catalyst_trader/migrations/015_paper_ledger.sql` — paper_position / paper_mark / paper_pending
- `src/catalyst_trader/contracts/__init__.py` — StrategyDossier, TradeProposal, DiligenceDossier, MDDecision
- `src/catalyst_trader/desk/runtime.py` — run_structured (the single mocked LLM seam)
- `src/catalyst_trader/quant/performance.py` — sharpe / win_rate / cumulative_return
- `src/catalyst_trader/kb.py` — kb_node kind='playbook' (confidence first-class)
- `/Users/rishizamvar/Documents/Projects/WorkoutCoach-iOS/project.yml` — XcodeGen precedent
</canonical_refs>

<deferred>
## Deferred Ideas
- Server-push `/events` SSE stream for pending-approval notifications (add when polling proves too slow).
- Real Phase 8 attribution decomposition (catalyst vs beta vs hedge vs sizing) — wire when Phase 8 lands.
- Per-leg hedge P&L: the paper ledger is single-leg today (hedge peer carries no size); the app shows the
  hedge ticker from the review snapshot and the target-leg live P&L.
</deferred>
</content>
