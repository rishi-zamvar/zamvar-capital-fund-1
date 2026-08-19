"""desk/builder.py (PORT-02 + HEDGE-01/04): DebateVerdict -> TradeProposal, the single-leg
estimated-move construction engine (the no-hedge case is the DEFAULT, and it is ENGINEERED —
not "size tiny and pray").

The builder ORCHESTRATES + INTERPRETS; the money math lives in the quant/risk tools (agents
never do arithmetic):
  - the payoff distribution is `quant.catalyst_move_estimate` (param-driven, cited),
  - the leg is sized on the ESTIMATED down-move via `risk.size_for_survival` (not a blanket 0.70),
  - the hold-through-vs-exit decision is `quant.hold_vs_exit` — expected-LOG-growth at the
    survival-constrained size f (Kelly-consistent), NEVER raw EV (BLOCKER-2),
  - SL/TP is `quant.adaptive_sl_tp_levels`, ADVISORY whenever the leg holds through the catalyst
    (a stop cannot fill inside an overnight gap),
  - the estimate is VETTED via `verifier.enforce_estimate` before finalize (a reject blocks it).

A candidate inverse (-1) peer is surfaced for the Risk committee to VALIDATE — the builder never
fabricates a validated hedge (TradeProposal.hedge is None out of the builder). Every builder
threshold is a loaded param; a missing builder param RAISES (no literal in the builder body).

# ponytail: flat async fn over the one run_structured seam, same shape as debate.py/risk.py — no
#           base classes, no config objects. The only narrative the LLM authors is pair_rationale;
#           every trade NUMBER is a deterministic tool output it can never inject.
"""

from statistics import median

from pydantic import BaseModel, ConfigDict

from .. import kb
from ..contracts import TradeProposal
from ..quant.events import catalyst_move_estimate, hold_vs_exit
from ..quant.field import expected_move_field
from ..quant.sizing import adaptive_sl_tp_levels
from ..quant.valuation import analyst_pt_move, pipeline_value, rnpv
from . import evidence, risk
from .assumptions_adapter import assumptions_snapshot_provider
from .options_adapter import implied_move_from_provider
from ..playbook.store import assert_embedder_consistency
from .analysts import _get
from ..playbook import tagger
from .runtime import run_structured
from .verifier import EstimateRejectedError, enforce_estimate


class BuilderNarrative(BaseModel):
    """The one narrative the LLM authors — the pair rationale. Every trade NUMBER is a
    deterministic tool output that OVERWRITES anything the model emits."""

    model_config = ConfigDict(extra="forbid")
    pair_rationale: str


def _ctype(catalyst) -> str:
    """The catalyst type as its plain string value (enum or str in -> str out), so it keys
    load_params / analog filters / enforce_estimate consistently."""
    ct = _get(catalyst, "catalyst_type")
    return getattr(ct, "value", ct)


def _candidate_peer(conn, target) -> str | None:
    """Top inverse (-1) peer ticker for the Risk committee to VALIDATE, or None. A +1 co-move
    peer is a conviction long, NEVER an idiosyncratic-hedge candidate (HEDGE-01) — filtered out.
    The builder only SURFACES the candidate; risk.validate_hedge decides if it holds THIS catalyst.

    # ponytail: top candidate only — the KB weight already ranks them; risk re-derives it anyway.
    """
    inverse = [p for p in kb.hedge_peers(conn, target) if p["payoff_direction"] == -1]
    return inverse[0]["peer"] if inverse else None


def _analog_context(verdict, ctype) -> str:
    # No ticker: retrieval must cluster on the SETUP, not the firm's identity (quick-260818-l64).
    return f"{ctype} catalyst: {verdict.thesis}"


def _split_moves(analogs) -> tuple[list[float], list[float]]:
    """Split realized analog outcome moves into up (>0) and down (|move| for <0) branches —
    the two-state gap distribution catalyst_move_estimate consumes."""
    moves = [a["outcome"]["move"] for a in analogs if a.get("outcome") and "move" in a["outcome"]]
    up_moves = [m for m in moves if m > 0]
    down_moves = [-m for m in moves if m < 0]
    return up_moves, down_moves


def _narrative_prompt(verdict, target, candidate, ctype, extra="") -> str:
    return f"""You are the TRADE BUILDER authoring the pair rationale for a single-leg biotech
catalyst trade. Explain the leg and the (candidate) hedge in prose — emit NO numbers, sizes,
stops, or targets (those are computed deterministically and will overwrite anything you write).

CATALYST         {target} — {ctype}
DIRECTION        {verdict.direction} (confidence {verdict.confidence:.2f})
THESIS           {verdict.thesis}
CANDIDATE HEDGE  {candidate or 'NONE (honest fallback — size-tiny / exit-before-event)'}
KILL CRITERIA    {'; '.join(verdict.kill_criteria)}
{extra}
Write pair_rationale: why this leg, the candidate inverse peer (pending Risk re-validation this
catalyst), and the kill criteria that would falsify the thesis.
"""


async def build(conn, embed, verdict, catalyst, *, entry: float,
                extra_context: str | None = None, as_of: str | None = None,
                options_provider=None, assumptions_provider=None) -> TradeProposal | None:
    """Turn a `DebateVerdict` into a `TradeProposal` (or None = no trade this week, HEDGE-04).

    `entry` is the current leg price (the caller — 05-07 — supplies it; the builder can't invent a
    price). Fully offline under test: the narrative + comparability calls route through run_structured.

    `extra_context` (RECON-03): a GP/DD re-trigger appended to the narrative prompt's extra= slot.
    Default None -> no suffix -> identical prompt -> identical TradeProposal (no-regression).
    # ponytail: extra_context re-reasons the NARRATIVE only; sizing/hold/SL-TP are deterministic +
    # input-driven. A sizing-related gap MUST also reach the refreshed risk_inputs/entry the work-item
    # carries (Plan 04 cascade) — text alone won't move deterministic sizing.

    FF-05 — the expected-move football field. Two injectable provider seams (both default None ->
    byte-for-byte the pre-FF behaviour: only the analog method is available, 1 < min_methods, no
    field forms, catalyst_move_estimate is called with implied_move=None):
      options_provider(ticker, event_date) -> {underlying_price, call_mid, put_mid, iv, days_to_event}
        | None  (live = RH, backtest = options_snapshot_provider(conn), tests = fake). Abstains -> omitted.
      assumptions_provider(ticker, catalyst, as_of) -> a dict of OPTIONAL keys, or {} to abstain:
        {"rnpv": {"cashflows", "discount_rate", "costs"|None, "shares_out">0},
         "sop":  {"segments":[{"cashflows","discount_rate","costs"}], "shares_out">0},
         "analyst_pt": {"price_targets":[float]}}  — the desk agent fills this LIVE per opportunity
        (CEO decision: estimate live, no static file).
    When >= min_methods assemble, the field convergence feeds sizing via the SAME
    catalyst_move_estimate implied_move prior — the deterministic sizing/hold/SL-TP contract is
    otherwise unchanged.
    # ponytail: NO-LOOK-AHEAD is a construction-time discipline, not an in-builder guard. In BACKTEST
    #   both providers MUST be built to read ONLY pre-event (as_of < event) data — the builder threads
    #   `as_of` INTO assumptions_provider so it can gate as-of; the options_snapshot backtest provider
    #   is likewise as-of-scoped. Ceiling: full enforcement is imperfect (an off-by-one snapshot slips
    #   through) — the discipline lives in the provider, not here.
    """
    target = _get(catalyst, "ticker")
    catalyst_id = _get(catalyst, "catalyst_id")
    ctype = _ctype(catalyst)
    event_date_str = _get(catalyst, "event_date")
    exit_by_date = _get(catalyst, "event_date_end") or _get(catalyst, "event_date")

    params = kb.load_params(conn, ctype)  # the frozen model-fit seam (estimator/sl_tp/builder groups)
    builder_p = params["builder"]         # a missing builder param RAISES here (no literal fallback)

    context = _analog_context(verdict, ctype)
    # Refuse to KNN a corpus populated with a DIFFERENT embedder — a mismatch is silent garbage
    # (Plan 04 stamps the embedder on every catalyst node; this is the warm-retrieval guard).
    assert_embedder_consistency(conn, embed)
    # MULTI-AXIS retrieval v2 (quick-260818-oto): inclusive UNION recall over the catalyst's OWN
    # axes (type + setups + disease_area + mechanism_class) + rarity-weighted rerank + confidence.
    # A fresh live catalyst not yet classified degrades to type+setups recall (still inclusive) —
    # a query-side LLM classifier is YAGNI (the stress test reads the re-tagged node's stored axes).
    q_setups = tagger.tag_setups({"thesis": verdict.thesis, "indication": _get(catalyst, "indication"),
                                  "modality": _get(catalyst, "modality")})
    q_disease = _get(catalyst, "disease_area")     # None -> that axis just doesn't constrain recall
    q_mech = _get(catalyst, "mechanism_class")
    res = kb.analog_query_v2(conn, embed, context, ctype=ctype, disease_area=q_disease,
                             mechanism_class=q_mech, setups=q_setups, k=5, as_of=as_of)
    analogs = res["analogs"]
    retrieval_confidence = res["retrieval_confidence"]  # captured for downstream field weighting
    candidate = _candidate_peer(conn, target)

    # 1. Estimate the catalyst payoff distribution (param-driven, cited). p_positive comes from the
    #    verdict; the estimate + sizing + hold-vs-exit + SL/TP are ALL deterministic tool outputs.
    up_moves, down_moves = _split_moves(analogs)
    p_positive = verdict.confidence if verdict.direction == "positive" else 1.0 - verdict.confidence

    # 1a. Assemble the expected-move football field (FF-05). Each method ABSTAINS independently
    #     (omitted, never entered as magnitude 0 — which would bias the field toward zero). Every
    #     weight is read from params["field"]["weights"] (a missing key RAISES — no literal here).
    analog_ref = evidence.tool_ref_for("analog_query_v2", {
        "context": context, "ctype": ctype, "disease_area": q_disease,
        "mechanism_class": q_mech, "setups": q_setups, "k": 5, "as_of": as_of})
    w = params["field"]["weights"]
    min_analogs = params["estimator"]["min_analogs"]
    methods: list[dict] = []
    if up_moves or down_moves:  # analog method: magnitude = median of |analog moves| (both are magnitudes)
        analog_mag = median(up_moves + down_moves)
        methods.append({"method": "analog", "magnitude": analog_mag,
                        "weight": w["analog_warm"] if len(analogs) >= min_analogs else w["analog_cold"],
                        "ref": analog_ref})
    if options_provider is not None:  # implied-IV via the abstaining Task-1 adapter
        im = implied_move_from_provider(target, event_date_str, options_provider)
        if im is not None:
            methods.append({"method": "implied", "magnitude": im.value,
                            "weight": w["implied_liquid"], "ref": evidence.tool_ref(im)})
    if assumptions_provider is None:  # default to the headless assumptions_snapshot cache read
        assumptions_provider = assumptions_snapshot_provider(conn)
    a = assumptions_provider(target, catalyst, as_of)  # provider abstains with {} — None-safe/byte-for-byte
    if "rnpv" in a:
        r = rnpv(a["rnpv"]["cashflows"], a["rnpv"]["discount_rate"], a["rnpv"].get("costs"))
        mag = abs(r.value / a["rnpv"]["shares_out"] - entry) / entry
        methods.append({"method": "rnpv", "magnitude": mag, "weight": w["rnpv_scenario"], "ref": evidence.tool_ref(r)})
    if "sop" in a:
        segs = [rnpv(s["cashflows"], s["discount_rate"], s.get("costs")) for s in a["sop"]["segments"]]
        pv = pipeline_value(segs)
        mag = abs(pv.value / a["sop"]["shares_out"] - entry) / entry
        methods.append({"method": "sop", "magnitude": mag, "weight": w["rnpv_scenario"], "ref": evidence.tool_ref(pv)})
    if "analyst_pt" in a:
        pt = analyst_pt_move(entry, a["analyst_pt"]["price_targets"])
        methods.append({"method": "analyst_pt", "magnitude": pt.value, "weight": w["analyst_pt"], "ref": evidence.tool_ref(pt)})

    # 1b. Form the field only when it can (>= min_methods); feed the convergence into sizing via the
    #     EXISTING implied_move prior. field_prior=None -> current behaviour EXACTLY (sizing/hold/SL-TP
    #     contract preserved); a one-method "field" never forms (expected_move_field would raise).
    field_detail = None
    field_prior = None
    if len(methods) >= params["field"]["min_methods"]:
        field = expected_move_field(methods, params)
        field_detail = field.detail
        field_prior = field.value
    est = catalyst_move_estimate(p_positive, up_moves, down_moves, params, implied_move=field_prior)
    up_move, down_move = est.detail["up_move"], est.detail["down_move"]

    # 2. Size the leg on the ESTIMATED down-move (not a blanket 0.70). Zero-trade allowed: a leg
    #    below the tradeable floor is not worth taking -> pass (no proposal).
    size = risk.size_for_survival(p_loss=1.0 - p_positive, gap=down_move)
    if size.value < builder_p["min_tradeable_size"]:
        return None

    # 3. Hold-through-vs-exit by the quant hold_vs_exit tool — expected-LOG-growth at the survival-
    #    constrained size f (Kelly-consistent), NEVER raw EV (BLOCKER-2). The exit branch captures a
    #    run-up fraction pre-event and dodges the gap.
    hold_outcomes = [(p_positive, up_move), (1.0 - p_positive, -down_move)]
    exit_outcomes = [(1.0, builder_p["runup_capture_frac"] * up_move)]
    hv = hold_vs_exit(size.value, hold_outcomes, exit_outcomes, margin=builder_p["log_growth_margin"])
    holds_through = hv.value == 1.0

    # 4. Adaptive SL/TP — advisory whenever the leg holds through the catalyst (a stop can't fill in
    #    an overnight gap); the advisory flag comes for free from the delegated sl_tp_levels.
    sl_tp = adaptive_sl_tp_levels(entry, up_move=up_move, vol_move=down_move,
                                  params=params, holds_through_catalyst=holds_through)
    sl_advisory = bool(sl_tp.detail.get("advisory"))

    # 5. VET the estimate assumptions BEFORE finalize — a reject blocks the trade (pass / no proposal).
    est_ref = evidence.tool_ref(est)
    estimate_inputs = [
        {"input": "p_positive", "ref": est_ref, "value": p_positive},
        {"input": "up_move", "ref": est_ref, "value": up_move},
        {"input": "down_move", "ref": est_ref, "value": down_move},
        {"input": "analogs", "ref": analog_ref, "value": [str(a["node_id"]) for a in analogs]},
    ]
    try:
        vetting = await enforce_estimate(
            conn, estimate_inputs, verdict=verdict, params=params,
            holds_through_catalyst=holds_through, sl_advisory=sl_advisory,
            down_move=down_move, catalyst_type=ctype, n_analogs=len(analogs),
        )
    except EstimateRejectedError:
        return None  # a rejected estimate never finalizes a trade (re-derive is a Phase-9 concern)

    # 6. Narrative (the ONLY LLM-authored field) — cite the hold-vs-exit decision for the memo.
    narrative = await run_structured(
        _narrative_prompt(verdict, target, candidate, ctype,
                          extra=f"HOLD-VS-EXIT   {hv.detail['decision']} (cite {evidence.tool_ref(hv)})"
                                + f"\nRETRIEVAL      analog confidence: {retrieval_confidence}"
                                + (f"\nMD RE-TRIGGER: {extra_context}" if extra_context else "")),
        BuilderNarrative, model="sonnet",
    )

    return TradeProposal(
        target_long=target,
        hedge=None,  # the builder NEVER validates — Risk owns validation (05-07 reconciles the object)
        pair_rationale=narrative.pair_rationale,
        entry=entry,
        exit_by_date=exit_by_date,
        stop_loss=sl_tp.detail["stop"],
        take_profit=sl_tp.detail["target"],
        size_pct=size.value,                       # the quant survival size — never an LLM number
        expected_return_pct=est.value,             # DISPLAY ONLY — never feeds size_pct (1% not a sizing input)
        kb_analogs=[str(a["node_id"]) for a in analogs],
        holds_through_catalyst=holds_through,
        catalyst_id=catalyst_id,
        direction=verdict.direction,
        estimate_vetting=vetting,
        sl_advisory=sl_advisory,
        expected_move_field=field_detail,          # FF-05 field detail (None when < min_methods)
        retrieval_confidence=retrieval_confidence,
    )
