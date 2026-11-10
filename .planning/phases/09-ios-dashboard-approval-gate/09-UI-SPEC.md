# Phase 9 — UI Design Contract (iOS)

Native SwiftUI, system components only (List/Section/LabeledContent/Gauge/Chart). No custom design
system — Dynamic Type, Dark Mode and VoiceOver come free from stock controls.

## Visual language
- Accent: brass `#B08D57` (matches docs/architecture-workflows.html), set as the asset AccentColor.
- Gain = `.green`, loss = `.red`, but every signed number also carries a `+`/`-` sign (never colour-only).
- Numbers: `.monospacedDigit()`; percents via `FormatStyle.Percent` with 2 fraction digits.
- Typography: system text styles only (`.headline`, `.subheadline`, `.caption`), no fixed sizes.

## Navigation
`TabView` with 5 tabs: This Week (`calendar`), History (`chart.line.uptrend.xyaxis`),
Playbook (`book`), Approvals (`checkmark.seal`, badge = pending count), MD Chat (`bubble.left.and.bubble.right`).
Settings (server URL + token) is a toolbar sheet on This Week; first launch with no token opens it.

## Screens
1. **This Week** — header: expected book return vs 1% benchmark (Gauge), Sharpe, expectancy.
   Sections: Upcoming catalysts (ticker, type, "in N days"); Open positions (ticker, entry→mark,
   unrealized P&L signed, distance to SL / TP as %, "advisory" tag when sl_advisory); for each position
   with a review: thesis, kill criteria, top pre-mortem failure factors + mitigations (accepted residuals).
2. **History** — Swift Charts LineMark equity curve + RuleMark at 1.0; KPI row (win rate, trades, Sharpe);
   calibration PointMark chart predicted vs realized with y=x reference; per-trade list;
   Attribution section shows `ContentUnavailableView("Attribution pending", …"Phase 8")` while null.
3. **Playbook** — List of playbooks grouped by scenario_type, confidence as a ProgressView + percent.
4. **Approvals** — list of pending decisions → Dossier detail: trade card (entry, size, exit-by, SL/TP
   advisory), thesis, kill criteria, pre-mortem, DD verdict + red flags + strongest disconfirming evidence,
   MD rationale + preserved dissent, evidence refs as tappable rows (copy / open URL if http).
   Bottom bar: **Reject** (bordered, destructive) and **Approve** (borderedProminent). Both open a
   `confirmationDialog` restating ticker + size; no swipe-to-approve, no default action.
5. **MD Chat** — message list + TextField; assistant reply streams in from SSE deltas.

## States (every screen)
- Loading: `ProgressView`. Error: `ContentUnavailableView` with the server message + Retry.
- Empty: explicit copy ("No pending decisions — the desk submits after a T-2 run", "No closed trades yet").
- Unauthorized (401): prompt to open Settings.

## Copy rules
- Never say "guaranteed", "stop loss protects"; SL/TP labelled "advisory" when sl_advisory (gap risk).
- Approve dialog: "Open a PAPER position in {TICKER} at {size}? Nothing opens until you confirm."
</content>
