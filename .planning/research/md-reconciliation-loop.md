# MD Reconciliation Loop — Research

**Purpose:** Design input for the Zamvar Capital MD reconciliation orchestrator — the loop where the MD integrates the catalyst call (Workflow 1), the portfolio build (Workflow 2), and independent diligence (Workflow 3), and iterates to a bounded decision.

**Sourcing note:** WebSearch budget was exhausted at task start (200/200). Sections below rest on (a) two live-fetched sources — Klein's premortem article (HBR, Sept 2007) and principles.com — and (b) established, well-documented buy-side/decision-science practice from named published works, each labeled. Anything not traceable to a named source is marked **UNVERIFIED** or omitted.

---

## Section 1 — How real hedge-fund ICs / PMs actually run this

### 1.1 What lands on the PM's desk

Real ICs are deliberately **decision-only forums**: the work product arrives finished, and the meeting spends its time interrogating it, not building it. The canonical package:

- **The IC memo / pitch.** Sonkin & Johnson's *Pitch the Perfect Investment* (Wiley, 2017) — written by a Columbia Business School adjunct and a former PM specifically about what a PM needs to hear — frames the deliverable as three claims with evidence: (1) here is the security and my estimate of value, (2) here is *why* it's mispriced (the variant perception — who's on the other side and why they're wrong), and (3) here is the **catalyst** that closes the gap, with a time window. A pitch without a catalyst is explicitly incomplete for an event-driven desk. The memo also pre-answers the PM's reflexive objections ("how do you lose money on this?") because the PM's first move is always to attack the downside.
- **The risk/sizing sheet.** In multi-manager platforms (Millennium, Citadel, Point72 — structure widely documented, e.g., in Steven Drobny's *Inside the House of Money*, 2006, and platform-fund reporting), risk arrives as a separate artifact from the thesis: gross/net exposure impact, factor exposure, drawdown-to-stopout math, and correlation to existing book. The PM never trusts sizing math embedded in an advocate's memo — the advocate has an incentive to shade it.
- **The independent review / devil's-advocate note.** Best-documented in intelligence tradecraft that buy-side firms explicitly borrowed: Heuer & Pherson, *Structured Analytic Techniques for Intelligence Analysis* (CQ Press, 2010) codify "devil's advocacy" and "premortem analysis" as formal contrarian techniques run by someone who did **not** author the thesis. The key structural property: the reviewer's independence is on their *reasoning process*, not their information — they see the same facts but are institutionally rewarded for finding the hole.

### 1.2 The best-documented real process: Bridgewater

Ray Dalio's *Principles* (Simon & Schuster, 2017) is the most detailed public account of an IC-like process at a major hedge fund:

- **Idea meritocracy + radical transparency**: disagreements are surfaced deliberately ("thoughtful disagreement"), recorded, and argued in the open. (Confirmed live on principles.com: Bridgewater is described as "an idea meritocracy that strives to achieve meaningful work and meaningful relationships through radical transparency." The operational detail below is from the book itself.)
- **Believability-weighted decision making**: when people disagree, opinions are weighted by each person's demonstrated track record *in that domain* — not by seniority and not one-person-one-vote. Crucially for our design: believability weighting is an *input* to the decision, but **the "Responsible Party" still decides** — Dalio is explicit that it is not a democracy and the decision-owner can overrule the weighted vote, provided they do it transparently and log why. This is exactly the MD-authority model: structured dissent flows up; one accountable node decides.
- **Issue log**: every error or disagreement is logged as a case, creating an audit trail that later feeds back into believability weights. This is the ancestor of our per-round reconciliation log (Section 2.4).

### 1.3 Premortems, red teams, disagree-and-commit

- **Premortem (Klein 2007).** Gary Klein, "Performing a Project Premortem," *Harvard Business Review*, September 2007 (fetched live for this research): before committing, the team *assumes the plan has already failed* and each member independently writes down why. It works through "prospective hindsight" — imagining the failure as a past fact makes causes easier to generate — and because it makes dissent psychologically safe: concerns are framed as retrospective explanations, not criticism of a colleague's live work. Klein's design detail that matters for us: the premortem is run **after** the plan exists and **before** commitment — i.e., it sits exactly at our DD/MD reconciliation stage, not earlier.
- **Red teaming.** Formalized in the U.S. Army's UFMCS *Red Team Handbook* and CIA structured-analytic practice (Heuer & Pherson, above): a standing, resourced adversarial unit whose deliverable is a written challenge, and whose findings the decision-maker must explicitly accept or rebut — not silently absorb. The buy-side import ("murder boards" for pitches) keeps one property sacred: **the red team does not acquire decision authority.** It informs the decider; it never becomes a second decider.
- **Checklists.** Atul Gawande's *The Checklist Manifesto* (2009) documents Mohnish Pabrai's investing checklist — built from *other* investors' documented mistakes — run as a final gate before capital commitment. The checklist's function is identical to our DD go/no-go: a deterministic pass over known failure modes, separate from the thesis argument.
- **Disagree and commit.** Jeff Bezos, Amazon 2016 shareholder letter: when a decision is two-way-door and the team is split, the leader says "I disagree, but I'll commit" (or asks the team to) rather than grinding to consensus — and, from the same letter, **most decisions should be made with ~70% of the information you wish you had**; waiting for 90% means you're slow. This is the philosophical basis for a *bounded* loop: the MD's job is not to eliminate residual uncertainty but to decide once uncertainty is priced.

### 1.4 How a thesis gets re-opened, and how many rounds

- **Re-opening is triggered by *material new information*, not by discomfort.** In documented IC practice (private equity ICs are the best-described: screening memo → preliminary IC → full IC with Q&A; see standard descriptions in Gilligan & Wright, *Private Equity Demystified*, ICAEW, 3rd ed. 2014), a deal that draws unresolved questions gets a **"revise and resubmit"** with the specific questions attached — the deal team goes back, does the work, and returns. The committee does not do the work in the room.
- **Typical touch count: 2–3.** The PE pattern is early-look → main IC → (if needed) final confirmatory IC. More than three round-trips is widely treated as a signal to pass — a deal you have to argue into existence four times is a pass. (**Established practice; no single canonical citation** — consistent across Gilligan & Wright and practitioner accounts.)
- **Process over outcome.** Michael Mauboussin (*Think Twice*, HBS Press 2009; and his Credit Suisse/Counterpoint research on base rates) is the standard buy-side authority for two habits our loop should encode: (1) judge the decision by the process at the time, not the result — hence the need for a complete decision record; (2) anchor probability estimates in **base rates** (reference-class data) before case-specific reasoning — which for us means the catalyst call must carry its base-rate anchor so the MD can see how far the debate drifted from it.

### 1.5 What the PM decides vs. delegates

Consistent across the platform-fund model and *Pitch the Perfect Investment*:

| PM/MD **decides** | PM/MD **delegates** (and consumes as attachments) |
|---|---|
| Enter / pass / defer | Thesis research, evidence gathering, modeling |
| Size (or ratifies proposed size within risk limits) | Sizing *math* and scenario tables |
| Timing / structure (options vs. equity, hedge legs) | Structure alternatives analysis |
| Kill criteria — and their later *enforcement* | Drafting the kill criteria |
| What gets escalated upward (to CIO / LPs) | Everything evidentiary |
| Whether dissent was adequately answered | Producing the dissent (red team / DD) |

The PM's scarce resource is judgment, not information. Every documented process above converges on the same shape: **advocacy, adversarial review, and risk math arrive as separate, finished artifacts from independent producers; one accountable person integrates and decides; the decision and its rationale are logged.** That is precisely the MD authority model we are encoding.

---

## Section 2 — Bounded iterative reconciliation (avoiding infinite loops)

### 2.1 Why real desks don't loop forever

Three structural facts keep real IC processes bounded, and all three transfer directly:

1. **The catalyst is a hard clock.** On an event desk, the trade has an expiry: the PDUFA date / readout window arrives whether or not the committee is done. Analysis time is bounded by *entry-timing decay* — every day of deliberation costs entry price and optionality. A loop cap is not a bureaucratic choice; it's the market imposing one.
2. **Decisions are made at ~70% information** (Bezos, Amazon 2016 shareholder letter, verified live: "Most decisions should probably be made with somewhere around 70% of the information you wish you had" — waiting for 90% "typically slows progress unnecessarily"). A position with kill criteria is a *reversible* (two-way-door) decision — it can be exited — which per the same letter qualifies it for a "light-weight process," not an exhaustive one. The irreversible decision isn't the entry; it's holding through the catalyst, and that gets its own later gate.
3. **Re-litigation requires new material information.** The documented "revise and resubmit" pattern (Section 1.4) only re-opens a thesis when review surfaced something the thesis didn't address. Discomfort, restated old objections, or wanting more confidence are not re-open triggers — they are inputs to the decide/pass call itself.

### 2.2 Convergence criteria — when is the thesis "solid enough"?

A round *converges* (loop exits to a decision) when ALL of:

- **DD clears**: diligence verdict is GO, or NO-GO-with-residuals where every residual is explicitly priced into sizing or covered by a kill criterion;
- **No new material issue**: the latest round surfaced nothing that changes verdict direction, sizing bucket, or structure — only refinements;
- **Internal consistency**: the three workflows agree on the shared facts (same catalyst date, same probability range, same max-loss number) — disagreement on *judgment* is fine (the MD weighs it), disagreement on *facts* is not (that forces a re-trigger);
- **MD satisfied**: every issue the MD flagged in prior rounds has an answer — which may legitimately be "unresolvable; priced as follows," not necessarily "resolved."

The loop also exits — to **PASS** — on divergence: if round N+1 surfaces a new material issue *of the same class* as one already litigated (the fix keeps un-fixing), that's oscillation, and the documented practitioner heuristic applies: a thesis you must argue into existence repeatedly is a pass.

### 2.3 The hard cap, and what "re-trigger" carries

- **Cap: 3 reconciliation rounds** (mirroring the 2–3-touch IC norm, Section 1.4). Round 1 is the initial integration; rounds 2–3 are re-triggers. At the cap the MD must choose from a closed set: **ENTER (possibly reduced size) / PASS / ESCALATE (Section 4)** — never "one more round."
- **The re-trigger carries the gap, not the answer.** This mirrors Klein's premortem discipline and the revise-and-resubmit pattern: the committee sends back *questions* ("your probability doesn't address the FDA's March CRL on the competitor — account for it"), not conclusions ("lower your probability to 45%"). The re-run agent re-reasons with the new fact in context and may legitimately come back *unmoved with a rebuttal* — that's a valid convergence outcome, and it's what preserves independence. Handing the answer down would turn the debate into a rubber stamp and destroy the only reason it exists.
- **Firewall preserved:** the re-trigger payload into Workflow 1/2 contains only the specific finding DD surfaced (a fact + why it's material), never DD's overall verdict, confidence, or recommended direction.

### 2.4 What gets logged each round (auditability)

Per Dalio's issue-log practice and Mauboussin's decision-journal recommendation (*Think Twice*, 2009 — record what you decided, why, and what you expected, *at the time*), each round appends one immutable record:

| Field | Content |
|---|---|
| `round` | 1..3 |
| `md_flags` | Each issue the MD raised: target workflow, the specific gap, materiality rationale |
| `retrigger_payload` | Exactly what was sent back (auditable proof the answer wasn't handed down) |
| `response_delta` | What changed in the re-run output vs. prior (verdict, probability, size, structure) — or "unmoved + rebuttal" |
| `convergence_check` | The 2.2 criteria, each pass/fail |
| `disposition` | continue / converged→decision / cap-hit→forced-choice / diverged→pass |

This log is what makes the eventual LP report honest: residual caveats at decision time are lifted verbatim from unresolved `md_flags`, not reconstructed after the fact.

## Section 3 — The deliverable package the MD decides on

### 3.1 The principle: decide-only, never gather

Every documented process in Section 1 converges on the same rule: the decision forum receives *finished* artifacts and spends its entire budget on judgment. If the MD has to fetch a quote, re-derive a number, or ask "what's the runway?", the packet was incomplete — that's a **packet defect**, bounced back to the producing workflow without consuming a reconciliation round.

### 3.2 The MD decision packet

Everything below already exists as a validated contract in `src/catalyst_trader/contracts/__init__.py` — the packet is an aggregation, not new research:

| Packet slot | Existing artifact | What the MD reads it for |
|---|---|---|
| **Catalyst verdict** | `DebateVerdict` (Workflow 1) | Binary direction + base-rate-anchored confidence, both sides' strongest point, `unresolved_dissent`, non-empty `kill_criteria` |
| **Portfolio build** | `StrategyDossier` (Workflow 2) | Promote/kill, reconciled `TradeProposal` (risk-committee size + validated hedge already win per BLOCKER-1), `PortfolioContext`, `residual_net_long`, `which_risk_covered` |
| **Survival math** | `RiskAssessment` (inside the dossier flow) | `recommended_size_pct` from size-for-survival, `ruin_at_size`, `conditional_worst` (un-netted worst cell), 3-way views, `residual_risks` |
| **Conditional payoff** | `RiskAssessment.conditional_payoff_matrix` | The four-cell outcome table the hedge claim rests on |
| **Independent diligence** | `DiligenceDossier` (Workflow 3) | `verdict` go/no_go, `red_flags`, `strongest_disconfirming_evidence`, `residual_risks` |
| **Pre-mortem** | `StrategyDossier.pre_mortem` (OPS-02) | Klein-style "assume it lost — why," authored separately from and before the promote/kill decision |
| **Position memo** | `StrategyDossier.position_memo` (OPS-01) | The narrative one-pager, also authored before the decision |
| **Cross-check sheet** | NEW (deterministic, no LLM) | Machine-computed consistency check across the three: same `catalyst_id`/date, DD `residual_risks` vs risk `residual_risks` diff, kill-criteria coverage of DD red flags |

The **cross-check sheet** is the only genuinely new artifact: a deterministic Python diff that pre-computes exactly the discrepancies the MD would otherwise hunt for. That's what makes the MD call a pure judgment call.

### 3.3 The MD's output record

Per Mauboussin's decision-journal discipline (record decision + rationale + expectation *at decision time*) and Dalio's transparent-overrule rule (Section 1.2), the MD emits one validated contract:

- `decision`: `enter | pass | escalate`
- `rationale`: which packet elements carried the decision; if the MD overrode any workflow's recommendation (e.g., entered over a DD residual, or killed a promoted trade), the override and its reason are **mandatory fields**, not prose
- `accepted_residuals`: each unresolved caveat the MD is knowingly accepting, with how it's priced (size reduction / kill criterion / hedge)
- `round_log`: the full Section-2.4 log embedded by reference
- `dissent_preserved`: `DebateVerdict.unresolved_dissent` + DD's `strongest_disconfirming_evidence`, carried verbatim — the losing argument survives into the record (red-team accept-or-rebut discipline, Section 1.3)

### 3.4 Honest relay to the LP

The LP-facing summary is **generated from the record, not composed fresh**: accepted residuals verbatim, the strongest disconfirming evidence verbatim, round count, and any cap-hit flag. Composing an LP narrative separately from the decision record is how caveats get laundered out; deriving it mechanically is how they don't. (Same logic as `verifier.enforce`'s source-quote-or-drop: the summary may only contain claims traceable to the record.)

---

## Section 4 — When the MD escalates to the LP (the rare genuine blocker)

### 4.1 The dividing line

The test from real practice (LPAC analogy below + Bezos two-way-door): **escalate only what the MD lacks the *authority* or the *information-in-principle* to resolve — never what is merely hard.** Difficulty, ambiguity, and residual uncertainty are the MD's job; that's what the role exists to absorb.

**The MD just decides (no escalation):**
- Residual uncertainty after the cap — price it (smaller size / tighter kill) or pass. "I'm not sure" is a PASS, not an escalation.
- Workflow disagreement on *judgment* (DD is skeptical, debate is confident) — weighing exactly that is the MD's function.
- Any situation where PASS is available and adequate. Passing costs one week's opportunity on one name; it needs no permission. This is the strongest de-escalation valve: **an MD who can always pass almost never needs to escalate.**

**Genuine blockers (escalate):**
1. **Mandate/authority boundary**: the best available action exits the agreed box — outside the ~20-name universe, above the weekly budget/heat cap, an instrument the mandate excludes (e.g., options before v1 allows them), or real-money action before the paper gate clears. The MD may not self-expand its own mandate; that's the LP's decision by construction. *(Real-world analog: PE Limited Partner Advisory Committees are consulted for conflicts of interest and investment-restriction waivers — mandate exceptions — not for deal quality; Gilligan & Wright, Private Equity Demystified, ICAEW 2014. Deal quality is the GP's job.)*
2. **Unfillable, decision-critical data gap**: a fact that determines the verdict, that no workflow can source (e.g., catalyst date cannot be two-source verified inside the trade window). Note the order of operations: an unverifiable date already *excludes* the catalyst under Phase-1 rules — so this escalates only when the human might actually hold the missing fact (e.g., a hand-curated PDUFA entry looks wrong).
3. **Irreconcilable factual conflict at the cap**: two workflows assert contradictory *facts* (not judgments) after 3 rounds — meaning an upstream data source or tool is lying, which is an infrastructure fault, not a trade question. The trade is passed AND the fault is escalated.
4. **Systemic/infrastructure failure**: verifier hard-fails (`VerdictUnsupportedError`) repeatedly, a provider is down, contract validation keeps rejecting output — the desk cannot produce trustworthy packets at all. Escalate the *outage*, pass the trades.

### 4.2 Keeping escalations rare and high-signal

- **Escalation ≠ delegation upward.** The escalation message carries the full packet, the round log, and the MD's *own recommended resolution* — the LP confirms or overrides a framed choice; they never receive an open-ended "what should I do?" (Standard staff-work discipline; same shape as the completed-staff-work doctrine long used in military/government staffing — **established practice**.)
- **Budgeted scarcity**: an escalation per week should be an anomaly worth investigating in itself. If the loop escalates twice in a month, the mandate boundaries are drawn wrong or a workflow is under-delivering — fix the system, don't normalize the pings.
- **Note the existing human gate is NOT an escalation**: the approve/reject gate on every live trade (iOS dashboard, Phase 9) is a standing mandate control that happens on every trade. Escalation is the separate, rare channel for blockers. Conflating them would train the LP to rubber-stamp.

---

## Section 5 — Scope + design recommendation for OUR build (Phase 6.7)

### 5.1 Reuse-vs-new verdict: **almost entirely reuse**

The codebase already contains every load-bearing mechanism. What Phase 6.7 adds is one orchestrator function, two small contracts, and re-trigger context plumbing.

| Need | Verdict | Where |
|---|---|---|
| Agent-call seam (offline-testable) | **REUSE** | `desk/runtime.py::run_structured` — the MD role is one more schema-bound call through the same seam |
| Bounded-loop pattern | **REUSE** | `desk/debate.py::run` already does `for _ in range(rounds)` with `MAX_ROUNDS = 2` in `desk/__init__.py`; the MD loop is the same shape one level up |
| Flat async fan-out (no SDK subagents) | **REUSE** | `orchestrator.py` pattern: plain Python composition, `asyncio.gather` where independent |
| Verifier gating | **REUSE** | `verifier.enforce` already gates every re-run verdict; nothing new |
| Firewall on DD inputs | **REUSE** | `DiligenceInput` (`extra="forbid"`) already makes Workflow-1/2 leakage a type error |
| Deliverable contracts | **REUSE** | `DebateVerdict`, `StrategyDossier`, `RiskAssessment`, `DiligenceDossier` (Section 3.2) |
| Decision journal / audit | **REUSE** | KB provenance discipline (`kb.py`) — rounds land as KB records with citations |
| Re-trigger context injection | **NEW (small)** | One optional `extra_context: str` param on `debate.run`/`builder.build` — `diligence.py::build_dimension_prompt` already models exactly this |
| `MDDecision` + `ReconciliationRound` contracts | **NEW (small)** | Two pydantic models in `contracts/`, same `extra="forbid"` style |
| Cross-check sheet | **NEW (small, deterministic)** | Pure-Python consistency diff, unit-tested, no LLM |
| MD orchestrator | **NEW** | `desk/md.py::reconcile` — the loop itself, ~150 lines by analogy with `orchestrator.py` |

### 5.2 The loop, concretely

```
async def reconcile(conn, embed, item, *, max_rounds=3) -> MDDecision:
    # round 0 artifacts already exist: verdict (run_desk), dossier (run_portfolio),
    # dd (run_diligence on DiligenceInput ONLY)
    for round_n in 1..max_rounds:
        sheet  = cross_check(verdict, dossier, dd)              # deterministic, no LLM
        review = await run_structured(md_review_prompt(packet), MDReview, model="opus")
        log_round(conn, round_n, review, sheet)                  # KB, immutable
        if review.converged (per §2.2 criteria):                 # -> decide
            break
        if review.flags target == "catalyst_call":
            verdict  = await run_desk(conn, catalyst, extra_context=gap_only(review.flags))
            dossier  = await run_portfolio(... verdict ...)      # downstream refresh
            dd       = await run_diligence(DiligenceInput(...))  # DD re-checks; inputs still firewalled
        elif review.flags target == "portfolio_build":
            dossier  = await run_portfolio(... extra_context=gap_only(review.flags))
            dd       = await run_diligence(DiligenceInput(...))
    return await run_structured(md_decide_prompt(packet, round_log), MDDecision, model="opus")
    # at cap: decision ∈ {enter, pass, escalate} — "one more round" is unrepresentable
```

Key mechanics:

- **`gap_only()` is the independence guarantee in code.** It formats each MD flag as *fact + why material* ("DD surfaced: competitor received a CRL on the same mechanism in March (evidence_ref kb:...). Your verdict does not address it.") and structurally cannot carry `direction`, `confidence`, a size, or DD's verdict — enforce with a small pydantic model for the flag (`RetriggerFlag: {finding: str, evidence_ref: str, why_material: str}`, `extra="forbid"`), mirroring how `DiligenceInput` enforces the inbound firewall. The re-run debate re-reasons and may return unmoved with a rebuttal; that counts toward convergence.
- **Re-trigger targets the workflow, then refreshes downstream.** A catalyst-call re-trigger reruns 1 → 2 → 3 in order (a changed verdict invalidates the build; a changed build deserves a DD look). A portfolio-only re-trigger reruns 2 → 3. DD itself is never "re-triggered with the answer" — it just re-runs on the new (still-firewalled) inputs.
- **Convergence check is code, not vibes**: the §2.2 criteria evaluate deterministically off the contracts (dd.verdict, flag-answered bookkeeping, cross-check sheet clean) plus one boolean from the MD review (`satisfied`). Oscillation detection: if a `RetriggerFlag.evidence_ref` repeats across rounds → forced PASS.
- **MD model tier**: `opus`, matching the existing precedent that synthesis/decision roles run on the strongest tier (debate moderator, PM pass, DD narrative are all opus).
- **Escalation surface**: `MDDecision(decision="escalate")` carries `blocker_class` (mandate | data_gap | factual_conflict | infra, per §4.1), the packet reference, and `recommended_resolution` (mandatory — completed-staff-work rule). Downstream (Phase 9) this renders as a dashboard item + push; Phase 6.7 only needs to emit the record.
- **Packet-defect bounce ≠ round.** Contract-validation failures (pydantic reject, `VerdictUnsupportedError`) are producer defects handled by the existing retry/error path — they don't consume one of the 3 reconciliation rounds.

### 5.3 Design decisions a PM must confirm

1. **Round cap = 3** (1 integration + 2 re-triggers), mirroring the 2–3-touch IC norm — or tighter (2) to hold token cost, given `MAX_ROUNDS = 2` inside the debate already bounds the inner loop?
2. **Forced-PASS on oscillation** (same-class issue resurfacing) — confirm PASS rather than escalate; §4.1 reserves escalation for *factual* conflict only.
3. **Downstream refresh scope**: after a catalyst-call re-trigger, full 1→2→3 rerun (proposed, honest but ~2x tokens) vs. rerunning 2 only when the verdict actually changed direction/confidence-bucket (cheaper; risks stale-build subtleties).
4. **Where the MD sits vs. the existing PM pass**: proposal is that `pm_decide` (Workflow 2's promote/kill) stays as-is — it is Workflow 2's *proposal* — and the MD reconciliation runs after DD, above all three. Confirm we are not collapsing the PM pass into the MD (two distinct judgment points, per the platform-fund model in §1.1).
5. **`enter` at cap with unresolved MD flags**: allowed if every flag lands in `accepted_residuals` with explicit pricing (disagree-and-commit), or forbidden (any unresolved flag at cap forces PASS)? Recommendation: allowed — otherwise the cap quietly becomes "loop until clean," which reintroduces the infinite loop by another name.
6. **Escalation transport for now**: KB record + surfaced in the weekly report until Phase 9's dashboard exists (ZeeChat ping available on the host if a live blocker warrants it). Confirm.

---

## Source list

**Fetched live for this research (2026-08-15):**
- Gary Klein, "Performing a Project Premortem," *Harvard Business Review*, September 2007 — https://hbr.org/2007/09/performing-a-project-premortem
- Jeff Bezos, Amazon 2016 Letter to Shareholders (high-velocity decisions, ~70% information, disagree-and-commit, two-way doors) — https://www.aboutamazon.com/news/company-news/2016-letter-to-shareholders
- principles.com (Bridgewater idea-meritocracy framing; operational detail from the book below)

**Established published works (not fetched; standard editions cited):**
- Ray Dalio, *Principles: Life and Work*, Simon & Schuster, 2017 — believability-weighting, Responsible Party decides, issue log
- Paul Sonkin & Paul Johnson, *Pitch the Perfect Investment*, Wiley, 2017 — pitch/memo structure, catalyst requirement, PM's downside-first lens
- Richards Heuer & Randolph Pherson, *Structured Analytic Techniques for Intelligence Analysis*, CQ Press, 2010 — devil's advocacy, premortem as formal techniques
- Michael Mauboussin, *Think Twice*, Harvard Business School Press, 2009 — process-over-outcome, base rates, decision journals
- Atul Gawande, *The Checklist Manifesto*, Metropolitan Books, 2009 — Pabrai's pre-commitment investing checklist
- John Gilligan & Mike Wright, *Private Equity Demystified*, ICAEW, 3rd ed. 2014 — IC staging, revise-and-resubmit, LPAC scope
- U.S. Army UFMCS *Red Team Handbook* — standing red-team practice
- Steven Drobny, *Inside the House of Money*, Wiley, 2006 — platform PM/analyst division of labor

**UNVERIFIED / established-practice-only (no single canonical citation):** the "2–3 IC touches then pass" norm; completed-staff-work doctrine; multi-manager risk-sheet separation as described. Each is labeled inline where used.
