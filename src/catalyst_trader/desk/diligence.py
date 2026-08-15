"""The independent diligence desk (Workflow-3, DILIG-02): 8 ADVERSARIAL dimension agents
that try to KILL a promoted trade from raw sources — assume the promoting desk is wrong.

It is the analyst desk mirrored, not reused verbatim: `analysts.run_analyst` hard-refs the
4-dimension `analysts.PROMPTS`, so this module carries its own `DILIGENCE_PROMPTS` (8) + a
sibling `run_dimension`/`gather_dimensions`. The FIREWALL is the input type: every prompt is
assembled ONLY from `DiligenceInput` fields (ticker + raw catalyst facts + bare pair ticker) —
no Workflow-1/2 verdict/thesis is in scope to interpolate. Every call routes through the ONE
`run_structured` seam (monkeypatched in tests), so the whole desk runs offline.

The deterministic prep seams (options degradation, financials/ownership/trial raw-data, the
INDEPENDENT hedge re-validation) compute nothing the agent can inject — they hand raw figures /
tool results into a dimension's context; the agent interprets and cites, tools compute.

# ponytail: a dict of 8 prompts + one builder + one runner + one gather + a handful of pure prep
#           helpers. No per-dimension classes, no registry object — the firewall is a type, not a guard.
"""

import asyncio
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..contracts import AnalystSignal, DiligenceDossier, DiligenceInput
from ..quant.options import implied_move
from . import evidence, risk
from .runtime import run_structured
from .tools import build_quant_server
from .verifier import SupportCheck  # pure model reuse — the DebateVerdict-typed enforce() is NEVER called here

# The SINGLE source of diligence thresholds (BLOCKER-2). Module-level + always present, read via
# direct subscript (missing-key-raises), NEVER `.get`. It is deliberately DECOUPLED from the KB
# fitted-params seam: once fitted params are seeded, that seam returns a strategy dict {estimator,
# sl_tp, builder, fit_source} with NO `diligence` key, so it can never be the threshold source. Do
# NOT add a diligence block to the KB bootstrap default or its CSV.
DILIGENCE_PARAMS = {"diligence": {
    "options_max_spread": 0.6, "options_min_oi": 100,
    "dimension_score_floor": -0.2, "dimension_min_conf": 0.5,
}}

# The mcp__quant__* surface the dimension agents may call — the same "quant" server the analyst
# desk uses (base_rate/analog_query/query_playbooks/rnpv/cash_runway/implied_move/correlation_beta).
ALLOWED_TOOLS = [
    f"mcp__quant__{name}"
    for name in (
        "base_rate", "analog_query", "query_playbooks",
        "rnpv", "cash_runway", "implied_move", "correlation_beta",
    )
]

# Each dimension's ADVERSARIAL job. The shared rules (call tools, cite-or-drop, fill unknowns,
# emit the token) live in build_dimension_prompt so they can't drift per-dimension. Keyed by the
# LOCKED dimension keys — order/keys are frozen for the whole phase.
DILIGENCE_PROMPTS = {
    "trial_stats": (
        "You are the TRIAL-STATS diligence agent. Your job is to find why this readout FAILS from "
        "the raw ClinicalTrials.gov record — assume the promoting desk cherry-picked. Interrogate "
        "endpoint power, the pre-registered analysis plan, phase-transition base rates, and how "
        "structurally similar past readouts actually resolved."
    ),
    "regulatory": (
        "You are the REGULATORY diligence agent. Your job is to find the approval/label risk the "
        "promoting desk downplayed — PDUFA/AdCom precedent for this class, prior CRLs, review-division "
        "posture, and analog regulatory outcomes. Anchor every claim to a base rate or a KB analog."
    ),
    "financials": (
        "You are the FINANCIALS diligence agent. Your job is to find the funding/dilution risk around "
        "the event. Take the raw cash / burn / runway figures supplied and CALL mcp__quant__cash_runway "
        "to judge whether the company is funded past the catalyst — never estimate runway yourself."
    ),
    "ownership_flow": (
        "You are the OWNERSHIP/FLOW diligence agent. Your job is to find the positioning risk hidden in "
        "the ownership tape: short interest, days-to-cover, and insider net selling. Interpret the "
        "pre-computed figures supplied and cite each — a crowded or insider-dumped name is a red flag."
    ),
    "options_move": (
        "You are the OPTIONS-MOVE diligence agent. Your job is to judge whether the event is already "
        "priced in. Use the options-implied move supplied via the liquidity-gated context; when options "
        "are illiquid, emit LOW confidence and fall back to the in-house historical-gap estimate rather "
        "than trusting a junk implied vol. Prefer the model-free straddle move."
    ),
    "hedge_revalidation": (
        "You are the HEDGE-REVALIDATION diligence agent. Your job is to independently confirm the "
        "candidate peer pays off INVERSELY on THIS specific catalyst. Interpret the deterministic "
        "validate_hedge result supplied in context (a validated inverse Hedge, or none). No valid "
        "inverse hedge means size-tiny / exit — say so; never invent a hedge."
    ),
    "liquidity": (
        "You are the LIQUIDITY diligence agent. Your job is to confirm both legs can be traded at the "
        "target size. A wide-but-live quote is acceptable; ONLY a zero-liquidity leg (no bid / no volume "
        "/ no open interest) is a hard fail. Cite the quote/volume figures supplied."
    ),
    "historical_analog": (
        "You are the HISTORICAL-ANALOG diligence agent. Your job is to surface the closest past scenarios "
        "and how they resolved — CALL mcp__quant__analog_query and let the disconfirming analogs argue "
        "against the trade. Cite every analog you lean on."
    ),
}


def _get(x, key, default=""):
    """Read a field from a dict OR a model — the catalyst arrives as a raw dict on DiligenceInput."""
    if isinstance(x, dict):
        return x.get(key, default)
    return getattr(x, key, default)


def build_dimension_prompt(dimension: str, input: DiligenceInput, *, extra_context: str = "") -> str:
    """Assemble a diligence prompt from ONLY DiligenceInput fields + the shared hard rules.

    `extra_context` threads a deterministic prep result (options-liquidity tag, the independent
    hedge result, passed-in financial/ownership figures) into the agent's context. No Workflow-1/2
    concept is ever referenced — the firewall input has none to interpolate.
    """
    if dimension not in DILIGENCE_PROMPTS:
        raise ValueError(
            f"unknown diligence dimension: {dimension!r} (expected one of {list(DILIGENCE_PROMPTS)})"
        )

    ticker = input.ticker
    catalyst = input.catalyst
    company = _get(catalyst, "company_name") or ticker
    ctype = _get(catalyst, "catalyst_type")
    event_date = _get(catalyst, "event_date")
    catalyst_id = _get(catalyst, "catalyst_id")
    pair = input.pair or "NONE"

    context_block = f"\nDIMENSION CONTEXT (raw figures / deterministic results — interpret + cite):\n{extra_context}\n" if extra_context else ""

    return f"""{DILIGENCE_PROMPTS[dimension]}

TRADE UNDER DILIGENCE (raw facts only — this is an independent firewall; assume the promoting desk is wrong)
  ticker:       {ticker}
  company:      {company}
  catalyst:     {ctype}
  event date:   {event_date}
  catalyst_id:  {catalyst_id}
  candidate peer: {pair}
{context_block}
HARD RULES (a source-cited signal, never LLM arithmetic):
  1. For ANY number, base rate, runway, implied move, playbook, or historical analog, you MUST CALL the
     relevant `mcp__quant__*` tool. NEVER compute, estimate, or recall a figure from memory.
  2. Every key_finding MUST carry the exact evidence_ref the tool returned (cite-or-drop) — a finding you
     cannot cite does not go in the signal.
  3. Fill `unknowns` with the explicit gaps a tool could not close.
  4. Emit `dimension` EXACTLY as "{dimension}", with ticker "{ticker}" and catalyst_id "{catalyst_id}",
     and a score in [-1, 1] (bearish..bullish) with a calibrated confidence in [0, 1].
"""


async def run_dimension(
    dimension: str,
    input: DiligenceInput,
    *,
    mcp_servers: dict | None = None,
    allowed_tools: list[str] | None = None,
    extra_context: str = "",
    model: str = "sonnet",
) -> AnalystSignal:
    """Run one adversarial diligence dimension and return its validated, source-cited AnalystSignal.

    Sibling of `analysts.run_analyst` (which hard-refs the 4-dim analyst PROMPTS). The schema
    boundary rejects any uncited/invalid payload; runs on the cheaper sonnet tier by default.
    """
    return await run_structured(
        build_dimension_prompt(dimension, input, extra_context=extra_context),
        AnalystSignal,
        mcp_servers=mcp_servers,
        allowed_tools=allowed_tools,
        model=model,
    )


async def gather_dimensions(
    conn, input: DiligenceInput, *, dimension_context: dict[str, str] | None = None,
) -> list[AnalystSignal]:
    """Fan the 8 adversarial dimensions out through a SINGLE asyncio.gather (mirrors run_desk).

    `dimension_context` threads Task-2's prep seams (options/financials/ownership/trial/hedge) into
    each dimension's `extra_context`; default empty = a plain run. Returns 8 cited AnalystSignals.
    """
    srv = {"quant": build_quant_server(conn)}
    ctx = dimension_context or {}
    return await asyncio.gather(
        *[
            run_dimension(
                dim, input,
                mcp_servers=srv, allowed_tools=ALLOWED_TOOLS,
                extra_context=ctx.get(dim, ""),
            )
            for dim in DILIGENCE_PROMPTS
        ]
    )


# ---------------------------------------------------------------------------
# Deterministic prep seams (BLOCKER-1) — raw figures / tool results in, context out.
# Pure + independently testable; Wave 4 threads the results through gather_dimensions.
# ---------------------------------------------------------------------------


def zero_liquidity(quote: dict) -> bool:
    """The inline hard-fail signal (RESEARCH: ONLY zero-liquidity is fatal — a wide-but-live quote
    is not). No new quant tool. True iff a leg has no bid, no volume, or no open interest."""
    return quote.get("bid", 0) <= 0 or quote.get("volume", 0) == 0 or quote.get("oi", 0) == 0


def options_liquid(quote: dict, *, params: dict) -> bool:
    """The §1.9 options-liquidity gate: ATM bid > 0 on both legs, spread/mid < options_max_spread,
    combined OI >= options_min_oi, and an expiry at/after the catalyst. Direct param subscripts
    (missing-key-raises) — NO numeric literals in the body."""
    p = params["diligence"]
    if not (quote["call_bid"] > 0 and quote["put_bid"] > 0):
        return False
    call_mid = (quote["call_bid"] + quote["call_ask"]) / 2
    put_mid = (quote["put_bid"] + quote["put_ask"]) / 2
    if (quote["call_ask"] - quote["call_bid"]) / call_mid >= p["options_max_spread"]:
        return False
    if (quote["put_ask"] - quote["put_bid"]) / put_mid >= p["options_max_spread"]:
        return False
    if quote["call_oi"] + quote["put_oi"] < p["options_min_oi"]:
        return False
    return quote["expiry"] >= quote["catalyst_date"]


def options_context(quote: dict, underlying_price: float, days_to_event: int, *, params: dict) -> str:
    """Options-move context with graceful degradation. Illiquid → tagged `none/illiquid` + a LOW-
    confidence / fall-back-to-historical-gap instruction and an explicit "do NOT trust IV" — it never
    raises and never fabricates an IV. Liquid → `options_data: ok` + the straddle-preferred implied move.
    """
    if not options_liquid(quote, params=params):
        return (
            "options_data: none/illiquid — the ATM options fail the liquidity gate (bid<=0 leg / "
            "spread too wide / thin open interest / no expiry past the event). Emit LOW confidence and "
            "fall back to the in-house historical-gap estimator; do NOT trust or fabricate an IV."
        )
    call_mid = (quote["call_bid"] + quote["call_ask"]) / 2
    put_mid = (quote["put_bid"] + quote["put_ask"]) / 2
    res = implied_move(underlying_price, call_mid=call_mid, put_mid=put_mid, days_to_event=days_to_event)
    return (
        f"options_data: ok — straddle-implied move {res.value:.2%} (method={res.detail['method']}). "
        f"Re-call mcp__quant__implied_move to cite it; compare against the historical-gap distribution."
    )


def financials_context(raw: dict | None) -> str | None:
    """Financials money-dim prep. None/empty → None (the "no raw data" sentinel Wave 4 uses to force a
    NO-GO for an ungrounded money dim). Else carry the raw figures + instruct calling cash_runway.
    NO arithmetic here — the tool computes runway."""
    if not raw:
        return None
    return (
        "financials (raw figures — call the tool, do not compute):\n"
        f"  cash_usd={raw['cash_usd']} monthly_burn_usd={raw['monthly_burn_usd']} "
        f"months_to_catalyst={raw['months_to_catalyst']}\n"
        "  CALL mcp__quant__cash_runway with these and cite whether the company is funded past the catalyst."
    )


def ownership_context(raw: dict | None) -> str | None:
    """Ownership/flow money-dim prep. None/empty → None. Else carry the PRE-COMPUTED short-interest /
    days-to-cover / insider-net figures + a cite instruction (ratios are supplied pre-computed by the
    deferred fetcher — no arithmetic tool)."""
    if not raw:
        return None
    return (
        "ownership/flow (pre-computed figures — interpret + cite each):\n"
        f"  short_interest_pct={raw['short_interest_pct']} days_to_cover={raw['days_to_cover']} "
        f"insider_net={raw['insider_net']}"
    )


def trial_stats_context(study: dict | None) -> str | None:
    """Trial-stats prep (non-money; plain string builder). `study` mirrors
    providers.clinicaltrials.fetch_trial_readouts output (passed in / mocked — no live HTTP).
    Empty → None. Else carry the endpoints/phase/status/stats."""
    if not study:
        return None
    return (
        "trial record (raw ClinicalTrials.gov facts — interpret + cite):\n"
        f"  phase={_get(study, 'phase')} status={_get(study, 'status')} "
        f"primary_endpoint={_get(study, 'primary_endpoint')} enrollment={_get(study, 'enrollment')}"
    )


def hedge_context(conn, embed, input: DiligenceInput, *, entry, exit_by_date, analog_gaps, prices) -> str:
    """Hedge money-dim prep: re-run validate_hedge INDEPENDENTLY, scoped to the SPECIFIC promoted peer
    (candidate_peer=input.pair) with input.ticker as target (BLOCKER-3). Report the resulting Hedge |
    None. Deterministic — no run_structured. A None result is the HEDGE-04 fallback (size-tiny / exit)."""
    hedge = risk.validate_hedge(
        conn, embed, input.ticker, input.catalyst, entry, exit_by_date, analog_gaps, prices,
        candidate_peer=input.pair,
    )
    if hedge is None:
        return (
            "hedge_revalidation: no valid inverse hedge for this catalyst — the candidate peer does NOT "
            "reliably rise when the target falls THIS event. Fallback is size-tiny / exit-before-event (HEDGE-04)."
        )
    return (
        f"hedge_revalidation: validated inverse hedge {hedge.ticker} "
        f"(mechanism: {hedge.mechanism}, conditional_worst={hedge.conditional_worst:+.2f}). "
        "Interpret whether this coverage holds on THIS specific catalyst."
    )


# ---------------------------------------------------------------------------
# The DETERMINISTIC adversarial synthesizer (DILIG-03) — the money crux.
#
# This is the size_for_survival / validate_hedge precedent: the deterministic
# function OWNS the go/no-go, the LLM only writes narrative (see Task 2). The
# asymmetry is baked into the DEFAULT branch — every ambiguous path returns
# no_go. There is no branch that returns "go" without ALL money dims present AND
# data-backed AND liquidity non-zero.
# ---------------------------------------------------------------------------

# The money-touching dimensions (dims 3-7). A single one failing forces NO-GO.
# Equals the harness MONEY_DIMS (test_money_touching_matches_harness pins it).
MONEY_TOUCHING = frozenset({
    "financials", "ownership_flow", "options_move", "hedge_revalidation", "liquidity",
})


def dimension_passed(sig: AnalystSignal, *, params: dict) -> bool:
    """A dimension is data-backed iff it has >=1 cited key_finding AND its score is not
    below the floor AND its confidence clears the minimum. Thresholds come from `params`
    via direct subscript (missing-key-raises) — NEVER a hardcoded literal in money code.
    The >=1-cited-finding invariant is already guaranteed by the AnalystSignal validator;
    the `bool(sig.key_findings)` check is defense against a bypassed/constructed signal."""
    floor = params["diligence"]["dimension_score_floor"]
    min_conf = params["diligence"]["dimension_min_conf"]
    return bool(sig.key_findings) and sig.score >= floor and sig.confidence >= min_conf


def synthesize_verdict(
    findings: list[AnalystSignal], *, liquidity_zero: bool, params: dict,
) -> Literal["go", "no_go"]:
    """The ONLY place the diligence go/no-go is decided — a pure function the LLM cannot
    touch. Asymmetric by design ("rewards no-go"):

      1. zero-liquidity -> no_go (hard fail, regardless of everything else);
      2. the full MONEY_TOUCHING set must be PRESENT -> else no_go (a missing money dim
         is a 'tie'/gap, and ties default to no_go);
      3. any present money dim not data-backed -> no_go (ONE money-dim failure is fatal);
      4. only then GO.

    # ponytail: the asymmetry is the design, not a bug — easy to kill (any single money
    #           dim fails and the whole trade dies), hard to clear (all 5 money dims must
    #           be present AND data-backed AND liquid). Do NOT "simplify" the default to go.
    """
    if liquidity_zero:
        return "no_go"
    money = [s for s in findings if s.dimension in MONEY_TOUCHING]
    if {s.dimension for s in money} != MONEY_TOUCHING:  # full money set must be present
        return "no_go"
    if any(not dimension_passed(s, params=params) for s in money):
        return "no_go"
    return "go"


# ---------------------------------------------------------------------------
# The LLM narrative pass (verdict-IMMUTABLE) + the cite-or-drop dossier gate.
#
# The narrative model has NO verdict field, so a confident LLM literally cannot
# emit a go/no-go. assemble_dossier stamps the DETERMINISTIC verdict onto the
# dossier — exactly risk.assess's model_copy money-overwrite pattern. enforce_dossier
# MIRRORS the verifier's two-stage shape (structural resolve + gated semantic)
# and REUSES the desk.evidence primitives, but it NEVER calls the DebateVerdict-typed
# verifier gate (a DiligenceDossier has no thesis/evidence_refs/model_copy-of-refs
# shape it expects).
# ---------------------------------------------------------------------------


class DiligenceNarrative(BaseModel):
    """The LLM's synthesis of a decision it CANNOT change: prose only, structurally
    verdict-free (no `verdict` field → the go/no-go is unrepresentable here)."""

    model_config = ConfigDict(extra="forbid")
    strongest_disconfirming_evidence: str
    red_flags: list[str] = []
    residual_risks: list[str] = []


def _narrative_prompt(findings: list[AnalystSignal], verdict: str) -> str:
    lines = [
        f"  {s.dimension}: score={s.score:+.2f} conf={s.confidence:.2f} "
        f"findings={[kf.claim for kf in s.key_findings]}"
        for s in findings
    ]
    return (
        "You are the diligence SYNTHESIZER writing the narrative for an independent go/no-go "
        f"that has ALREADY been decided: the verdict is FIXED as {verdict!r} and you CANNOT change "
        "it. Do not argue the verdict; write the adversarial story of it. From the per-dimension "
        "findings below, surface the strongest DISCONFIRMING evidence, the red flags, and the "
        "residual risks. Cite only what the dimensions cited — invent nothing.\n"
        "PER-DIMENSION FINDINGS:\n" + "\n".join(lines)
    )


async def _narrative(findings: list[AnalystSignal], verdict: str, *, model: str = "opus") -> DiligenceNarrative:
    """One opus pass that writes the narrative of the ALREADY-DECIDED verdict. It returns a
    verdict-free DiligenceNarrative — it cannot flip the go/no-go (that lives in synthesize_verdict)."""
    return await run_structured(_narrative_prompt(findings, verdict), DiligenceNarrative, model=model)


def assemble_dossier(
    findings: list[AnalystSignal],
    verdict: str,
    narrative: DiligenceNarrative,
    *,
    liquidity_zero: bool,
    params: dict = DILIGENCE_PARAMS,
) -> DiligenceDossier:
    """Build the DiligenceDossier. The verdict is the DETERMINISTIC synthesize_verdict result —
    NEVER the narrative's (which has no verdict field). This is the model_copy money-overwrite
    guard: the LLM narrative supplies only red_flags / disconfirming-evidence / residual_risks."""
    per_dimension = [
        {**s.model_dump(), "passed": dimension_passed(s, params=params)}
        for s in findings
    ]
    all_refs = [kf.evidence_ref for s in findings for kf in s.key_findings]
    return DiligenceDossier(
        verdict=verdict,
        per_dimension=per_dimension,
        red_flags=narrative.red_flags,
        strongest_disconfirming_evidence=narrative.strongest_disconfirming_evidence,
        all_evidence_refs=all_refs,
        residual_risks=narrative.residual_risks,
    )


def _claim_for(ref: str, signals) -> str | None:
    """The claim text cited under `ref` (from a signal's key_findings), or None.
    Mirrors verifier._claim_for — the ref->claim table quote_supported needs."""
    for sig in signals or []:
        for kf in sig.key_findings:
            if kf.evidence_ref == ref:
                return kf.claim
    return None


def _dossier_support_prompt(ref: str, claim: str, dossier: DiligenceDossier) -> str:
    return (
        "Judge whether the cited source SUPPORTS the claim backing this diligence dossier's "
        f"go/no-go.\nVerdict: {dossier.verdict}\n"
        f"Strongest disconfirming evidence: {dossier.strongest_disconfirming_evidence}\n"
        f"Claim: {claim}\nCited evidence_ref: {ref}\n"
        "Answer supported=true only if the source substantively backs the claim."
    )


async def enforce_dossier(conn, dossier: DiligenceDossier, *, signals=None) -> DiligenceDossier:
    """Cite-or-drop over the dossier's all_evidence_refs, mirroring the verifier's two-stage
    shape and reusing evidence.resolve / quote_supported — but NEVER calling the verifier gate
    (that is DebateVerdict-typed). A NO-GO that loses ALL evidence support is surfaced as an
    audit red flag (never silently passed)."""
    # 1. STRUCTURAL — deterministic, no LLM.
    structural: list[str] = []
    for ref in dossier.all_evidence_refs:
        source = evidence.resolve(conn, ref)
        if source is None:
            continue  # unresolvable -> drop
        if ref.startswith("kb:"):
            claim = _claim_for(ref, signals)
            if not claim or not evidence.quote_supported(source, claim):
                continue  # cited quote not found in the source -> drop
        # tool: refs are resolved-by-construction: no KB lookup, no quote gate.
        structural.append(ref)

    # 2. SEMANTIC — LLM (opus), gated on the structural survivors.
    survivors: list[str] = []
    for ref in structural:
        claim = _claim_for(ref, signals) or dossier.strongest_disconfirming_evidence
        check = await run_structured(_dossier_support_prompt(ref, claim, dossier), SupportCheck, model="opus")
        if check.supported:
            survivors.append(ref)

    red_flags = list(dossier.red_flags)
    if dossier.verdict == "no_go" and not survivors:
        red_flags.append(
            "AUDIT: no_go rests on unsupported evidence — every disconfirming ref failed cite-or-drop"
        )
    return dossier.model_copy(update={"all_evidence_refs": survivors, "red_flags": red_flags})


# ---------------------------------------------------------------------------
# The firewalled orchestrator (DILIG-01/02/03) — the composed pipeline entry point.
#
# Mirrors orchestrator.run_desk: build the quant server, fan out the dimensions, run the
# DETERMINISTIC verdict, add the LLM narrative, gate through cite-or-drop. The FIREWALL is the
# signature: the ONLY trade-facts parameter is `input: DiligenceInput`, so no DebateVerdict /
# TradeProposal / StrategyDossier / thesis can enter — a leak is a type error, not a policy check.
# ---------------------------------------------------------------------------


async def run_diligence(
    conn, input: DiligenceInput, *, market_data: dict, embed=None,
) -> DiligenceDossier:
    """Run the full independent diligence desk offline and return an evidence-backed DiligenceDossier.

    `market_data` carries the raw values this phase consumes behind the prep seams (the live fetchers
    are deferred to Phase 7 — the caller/fetcher supplies these; tests mock them):
        {"options": {"quote": {...}, "underlying_price": float, "days_to_event": int},
         "financials": {"cash_usd", "monthly_burn_usd", "months_to_catalyst"},
         "ownership": {"short_interest_pct", "days_to_cover", "insider_net"},
         "trial": {...ClinicalTrials.gov record...},
         "hedge": {"entry", "exit_by_date", "analog_gaps", "prices"},
         "liquidity_quote": {"bid", "volume", "oi"}}
    EVERY money-touching dim (financials, ownership_flow, options_move, hedge_revalidation, liquidity)
    has a raw-data key here; a MISSING key is the ungrounded case that forces NO-GO below.

    Pipeline (mirrors run_desk, thin — all pieces built in Waves 1-3):
      quant server -> prep seams -> gather 8 dims -> DETERMINISTIC synthesize_verdict
      -> ungrounded-money hard NO-GO -> opus narrative (verdict-free) -> assemble -> cite-or-drop gate.

    # ponytail: a gather + a deterministic call + two awaits + a gate. No new logic — the firewall is
    #           the signature (DiligenceInput only) and the money decision lives in synthesize_verdict.
    """
    params = DILIGENCE_PARAMS  # the single, seed-proof threshold source (BLOCKER-2), NOT the KB fitted-param seam.
    md = market_data

    # Build each dimension's context from the prep seams. A money-dim prep returns None on missing raw
    # data (BLOCKER-1) — only non-None contexts are threaded in; an empty-string prompt never happens.
    prep = {
        "options_move": options_context(
            md["options"]["quote"], md["options"]["underlying_price"],
            md["options"]["days_to_event"], params=params,
        ) if md.get("options") else None,
        "financials": financials_context(md.get("financials")),
        "ownership_flow": ownership_context(md.get("ownership")),
        "trial_stats": trial_stats_context(md.get("trial")),
        "hedge_revalidation": hedge_context(conn, embed, input, **md["hedge"]) if md.get("hedge") else None,
    }
    dimension_context = {k: v for k, v in prep.items() if v}
    liquidity_zero = zero_liquidity(md["liquidity_quote"]) if md.get("liquidity_quote") else True
    # A money-touching dim with no raw-data seam value CANNOT be grounded -> force NO-GO (no false GO
    # from a hallucinated finding; mirrors the zero-liquidity hard-fail, keeps the LLM out of money).
    ungrounded_money = (
        MONEY_TOUCHING - set(dimension_context) - ({"liquidity"} if md.get("liquidity_quote") else set())
    )

    findings = await gather_dimensions(conn, input, dimension_context=dimension_context)
    verdict = synthesize_verdict(findings, liquidity_zero=liquidity_zero, params=params)
    if ungrounded_money:
        verdict = "no_go"
    narrative = await _narrative(findings, verdict)
    dossier = assemble_dossier(findings, verdict, narrative, liquidity_zero=liquidity_zero, params=params)
    return await enforce_dossier(conn, dossier, signals=findings)
