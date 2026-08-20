"""The analyst layer (CALL-01): four dimension-specific ONE-PAGER prompts + one run_analyst().

Each of the four catalyst-call analysts (clinical/regulatory/financial/market_sentiment)
INTERPRETS tool output and emits a lens-specific structured report (guideline §7) — a
data-rich, plain-language one-pager — never a computed or recalled figure. Every number,
base rate, or analog MUST come from a `mcp__quant__*` tool call and be cited by the
evidence_ref the tool returns; a number that cannot be sourced is left null (an empty slot
is a finding, never a fabrication). The one quant MCP server (built in desk.tools, name
"quant") wraps BOTH the quant AND KB tools, so every tool is quant-namespaced.

run_analyst maps the dimension to its lens report class via REPORT_FOR and binds THAT class
at the run_structured seam — so the schema boundary rejects any uncited / malformed / wrong-
shape payload before it reaches the debate. The thin shared analyst contract is no longer
bound here; the 8 DD dimensions keep it (in diligence.py) until Plan 2.

# ponytail: still 4 job strings + 1 prompt builder + 1 seam call. The only new moving part
#           is REPORT_FOR (a dict). No per-dimension class hierarchy in this module.
"""

from ..contracts import (
    AnalystReportBase,
    ClinicalReport,
    FinancialReport,
    MarketReport,
    RegulatoryReport,
)
from .runtime import run_structured

# dimension -> the lens report class bound at the seam (the schema split).
REPORT_FOR = {
    "clinical": ClinicalReport,
    "regulatory": RegulatoryReport,
    "financial": FinancialReport,
    "market_sentiment": MarketReport,
}

# Each analyst's one-pager job: the guideline §1-4 (A) ordered section headers to fill, a cue
# to the (B) data-point checklist ("cite a tool number or leave it null"), and the (C)
# framework heuristic. The shared rules (call tools, cite, plain-language, thesis) live in
# build_prompt so they cannot drift per-dimension.
PROMPTS = {
    "clinical": (
        "You are a PHYSICIAN-SCIENTIST (MD/PhD) serving as the clinical/scientific analyst. "
        "Judge whether the primary endpoint is clinically meaningful to patients, not merely "
        "statistically significant, and assess the causal plausibility of the efficacy signal. "
        '"Met its primary endpoint" can describe a practice-changing result OR a significant '
        "sliver no payer reimburses — telling them apart is the whole job.\n\n"
        "Fill this ONE-PAGER, sections IN ORDER (cite each number to a tool or leave it null):\n"
        "  1. Bottom Line (your thesis: is the science real + strong enough to approve, and the key risk)\n"
        "  2. Disease & Unmet Need (prevalence, standard of care and its benchmark numbers, severity)\n"
        "  3. Mechanism of Action (target, modality, genetic validation, selection biomarker)\n"
        "  4. Trial Design (n, randomization, control placebo-vs-SoC, blinding, alpha/power, powered effect)\n"
        "  5. Endpoints (primary + its ladder rung OS>PFS>ORR, surrogate status, any change vs registration)\n"
        "  6. Efficacy — effect size WITH CONTEXT (point estimate + 95% CI + p; HR + absolute gain; "
        "ARR/RRR/NNT for binary outcomes; always vs the field benchmark)\n"
        "  7. Safety (AE-discontinuation %, SAE %, deaths, grade 3-4 %, boxed-warning risk)\n"
        "  8. Prior-Data Consistency (does Phase 3 match or shrink from Phase 2)\n"
        "  9. Key Scientific Risk & Probability of Success (the single biggest reason this fails; a "
        "base-rate-anchored PoS estimate WITH its tool source)\n"
        "Framework: statistical vs clinical significance; the OS>PFS>ORR endpoint ladder; distrust "
        "post-hoc subgroups; flag RRR-without-ARR/NNT spin."
    ),
    "regulatory": (
        "You are FDA regulatory counsel (a lawyer) serving as the regulatory analyst. The AdCom vote "
        "is advisory, the letter is binary, and the label is where an approval can still be a loss — "
        "handicap THREE outcomes: clean approval, approval crippled by a boxed warning / REMS / narrow "
        "label, and a Complete Response Letter (CRL = the FDA's formal 'not in this form' rejection).\n\n"
        "Fill this ONE-PAGER, sections IN ORDER (cite each number to a tool or leave it null):\n"
        "  1. Bottom Line (your thesis + the numeric Probability of Approval)\n"
        "  2. Application Mechanics (BLA vs NDA, priority-6mo vs standard-10mo review, PDUFA date, "
        "resubmission class if post-CRL, expedited tags)\n"
        "  3. Review Division & Posture (which division owns it, its CRL/AdCom track record)\n"
        "  4. The Regulatory Question (the benefit-risk issue; prior CRL deficiency + whether addressed)\n"
        "  5. AdCom Analysis (is one scheduled, committee, exact voting-question wording, briefing-doc tone)\n"
        "  6. Label / REMS / Post-Marketing Risk (boxed warning, REMS, narrower label, confirmatory trial)\n"
        "  7. Precedent & Base Rates (nearest approved AND nearest CRL'd analog in the division)\n"
        "  8. Probability of Approval (a numeric PoA WITH its tool source + a scenario map: "
        "clean-approve / approve-restricted / CRL)\n"
        "Framework: anchor on a designation base rate, apply modifiers (prior CRL, AdCom on a "
        "controversial file, briefing-doc tone), cross-check the nearest same-division precedent, and "
        "flag the 2025 regime shift (the FDA overrides its AdCom far more often now)."
    ),
    "financial": (
        "You are a CFO serving as the financial analyst. Answer two questions: can the company survive "
        "TO and PAST the event without a gun-to-head raise, and what is the risk-adjusted value of the "
        "asset the event de-risks? Counter-intuitive core: MORE cash is not always a good sign — "
        "raising a big cushion into a catalyst can signal low internal confidence.\n\n"
        "Fill this ONE-PAGER, sections IN ORDER (cite each number to a tool or leave it null):\n"
        "  1. Bottom Line (your thesis: solvency through the catalyst + rNPV vs current market cap)\n"
        "  2. Balance Sheet & Liquidity (cash, securities, total liquidity, debt + covenants)\n"
        "  3. Burn Rate & Cash Runway (quarterly net burn, runway months, does it clear the catalyst, "
        "cushion months — the Runway-vs-Catalyst test)\n"
        "  4. Capital Structure & Dilution (basic + fully-diluted shares, warrant overhang, annual dilution)\n"
        "  5. Financing History (each raise: vehicle ATM/follow-on/PIPE/convert, gross, discount, investors)\n"
        "  6. Insider & Institutional Activity (net direction; discretionary open-market BUYS = high signal; "
        "pre-scheduled 10b5-1 SALES = low signal; specialist 13F change)\n"
        "  7. Asset Valuation — rNPV build (rNPV WITH its tool source; peak sales, PoS, net price, "
        "addressable pop, penetration, LoE date, discount rate)\n"
        "  8. Scenario Value & Signal Synthesis (cross the runway test with financing structure + insider "
        "direction)\n"
        "Framework: clinical risk lives in the PoS multiplier, not the discount rate; a deep-discount PIPE "
        "with warrant coverage announced late is a weak hand; insider BUYING into a catalyst is the "
        "cleanest positive tell."
    ),
    "market_sentiment": (
        "You are a BUY-SIDE PORTFOLIO MANAGER and market-microstructure specialist serving as the "
        "market/sentiment analyst. The current price is a probability-weighted blend of the two "
        "post-event scenarios: extract the market's implied odds, compare to the fundamental odds, and "
        "judge whether the setup is skewed — and whether POSITIONING (flows) or FUNDAMENTALS (the "
        "outcome) will drive the move.\n\n"
        "Fill this ONE-PAGER, sections IN ORDER (cite each number to a tool or leave it null):\n"
        "  1. Bottom Line (your thesis: what's priced in vs our view + the asymmetry call)\n"
        "  2. Pre-Event Price Action / run-up (4w/8w move, vs XBI, short-covering component)\n"
        "  3. Options-Implied / Expected Move (ATM straddle, expected-move %, current IV, post-event IV)\n"
        "  4. Implied Probability decomposition (approval target Z, CRL target Y, price X -> implied P)\n"
        "  5. Short Interest & Squeeze (SI % of float, days-to-cover, cost-to-borrow, squeeze setup)\n"
        "  6. Float & Ownership (float %, institutional %, top-10 concentration)\n"
        "  7. Sell-Side Sentiment (Buy/Hold/Sell counts, target dispersion, revision trend)\n"
        "  8. Historical Analogs (implied move going in vs realized move, outcome)\n"
        "  9. Asymmetry Synthesis (EV % WITH its tool source; position-size %, positioning-vs-fundamentals "
        "driver, the expression)\n"
        "Framework: implied P = (X-Y)/(Z-Y); IV crush means being right on direction can still lose; if "
        "the stock has run and implied P already exceeds your fundamental P, the move is positioning-driven "
        "and priced in."
    ),
}


def _get(catalyst, key, default=""):
    """Read a field from a Catalyst model OR a plain dict — orchestrator supplies either."""
    if isinstance(catalyst, dict):
        return catalyst.get(key, default)
    return getattr(catalyst, key, default)


def build_prompt(dimension: str, catalyst) -> str:
    """Assemble the full one-pager prompt: lens job + hard tool-use/citation/plain-language
    rules + catalyst context."""
    if dimension not in PROMPTS:
        raise ValueError(f"unknown analyst dimension: {dimension!r} (expected one of {list(PROMPTS)})")

    ticker = _get(catalyst, "ticker")
    company = _get(catalyst, "company_name") or ticker
    ctype = _get(catalyst, "catalyst_type")
    event_date = _get(catalyst, "event_date")
    catalyst_id = _get(catalyst, "catalyst_id")

    return f"""{PROMPTS[dimension]}

CATALYST UNDER ANALYSIS
  ticker:       {ticker}
  company:      {company}
  catalyst:     {ctype}
  event date:   {event_date}
  catalyst_id:  {catalyst_id}

HARD RULES (a source-cited one-pager, never LLM arithmetic):
  1. For ANY number, base rate, rNPV, runway, implied move, playbook, or historical analog,
     you MUST CALL the relevant `mcp__quant__*` tool (e.g. mcp__quant__base_rate,
     mcp__quant__rnpv, mcp__quant__cash_runway, mcp__quant__implied_move,
     mcp__quant__analog_query, mcp__quant__query_playbooks). NEVER compute, estimate, or
     recall a figure from memory — the quant/KB tools are the only source of numbers and analogs.
  2. Every key_finding MUST carry the exact evidence_ref the tool returned. A finding you
     cannot cite from a tool result does not go in the report (cite-or-drop).
  3. Fill `unknowns` with the explicit gaps a tool could not close — an empty unknowns list
     means you did not look hard enough.
  4. Emit `dimension` EXACTLY as "{dimension}", with ticker "{ticker}" and catalyst_id
     "{catalyst_id}", and a score in [-1, 1] (bearish..bullish) with a calibrated confidence in [0, 1].
  5. LEAD with a `thesis`: 1-3 sentences stating your dimension-specific BOTTOM LINE
     ("here is my read"), consistent with your score/confidence. It MUST be a SYNTHESIS of your own
     cited key_findings — introduce NO claim that is not already in a cited finding (the thesis
     inherits their grounding; it is not a new uncited assertion).
  6. DEPTH (subordinate to rule 2): reason one level deeper than consensus — every finding states
     the WHY behind it (the mechanism, precedent, or cause), and surface at least one non-obvious
     second-order insight a generalist would miss. This depth is a deeper INTERPRETATION of evidence
     you have already tool-cited: introduce no new uncited claim. An insight without a supporting
     tool evidence_ref is dropped. Cite-or-drop (rule 2) always prevails over depth.
  7. PLAIN-LANGUAGE STANDARD (the one-pager is read by a human; non-jargon is the product):
     (a) DEFINE every technical term inline the first time it appears — e.g. "hazard ratio (the
         risk of the bad event in the treated group divided by the control group; below 1.0 =
         benefit)", never a bare acronym.
     (b) Every number GETS CONTEXT — good or bad, and vs WHICH BENCHMARK; never a bare number.
     (c) LEAD WITH THE BOTTOM LINE (your thesis), then the supporting evidence — the conclusion
         first, the data under it.
     Any structured data point you cannot source from a tool, LEAVE as null — never fabricate a
     number to fill the slot. An empty slot is a finding, not a gap to paper over.
  8. Fill the lens sections of your one-pager IN THE ORDER listed above, populating each numeric
     slot with a tool-cited value or null per rule 7.
"""


async def run_analyst(
    dimension: str,
    catalyst,
    *,
    mcp_servers: dict | None = None,
    allowed_tools: list[str] | None = None,
    model: str = "sonnet",
) -> AnalystReportBase:
    """Run one dimension analyst and return its validated, source-cited lens report.

    Maps the dimension to its lens report class (REPORT_FOR) and binds THAT class at the
    run_structured seam — the schema split. The caller (orchestrator) injects the quant MCP
    server + allowed `mcp__quant__*` tool names; this module never imports desk.tools. Runs
    on the cheaper `sonnet` tier by default. Raises pydantic.ValidationError if the model
    returns an uncited/invalid/wrong-shape payload.
    """
    report_cls = REPORT_FOR[dimension]
    prompt = build_prompt(dimension, catalyst)
    return await run_structured(
        prompt,
        report_cls,
        mcp_servers=mcp_servers,
        allowed_tools=allowed_tools,
        model=model,
    )
