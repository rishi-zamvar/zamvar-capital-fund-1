"""The risk desk (PORT-03 + HEDGE-01..04): survival-first sizing, honest per-catalyst
inverse-hedge validation, and a 3-way (aggressive/conservative/neutral) Risk Committee
that mirrors `debate.py`'s flat fan-out over the one `run_structured` seam.

The committee AGENTS interpret (argue p_loss / gap / hedge validity from analogs); every
money number is a DETERMINISTIC quant output the committee can never inject:
  - the size is `size_for_survival()` — the `risk_of_ruin` down-sweep is the survival cap (the
    HARD ceiling), and an optional `target_return` drives the size UP toward, but provably never
    past, that cap: `chosen = clamp(target_return/expected_move, FLOOR, survival_cap)`. With
    `target_return=None` it collapses to the pure survival cap (Phase-5 behavior). Sizing thus
    SERVES the ~1%/week objective within the ruin ceiling (PORT-03 amended / WEEK-04; PITFALLS #2/#5).
  - the hedge is `validate_hedge()` — a peer only counts if it is a -1 inverse peer that passes
    conditional_payoff + cointegration + catalyst-clean THIS catalyst; otherwise None (honest
    fallback, HEDGE-04). The validated Hedge OBJECT is carried on the RiskAssessment (BLOCKER-1).

# ponytail: flat async fan-out over run_structured, same shape as debate.py — no base classes,
#           no config objects. validate_hedge + size_for_survival are pure/deterministic; only
#           the committee views + synthesis narrative go through the LLM seam.
"""

from pydantic import BaseModel, ConfigDict, Field

from .. import kb, serving
from ..contracts import Hedge, RiskAssessment
from ..quant.pairs import cointegration, conditional_payoff
from ..quant.result import ToolResult
from ..quant.sizing import risk_of_ruin
from .runtime import run_structured

_VERSION = "1.0.0"

STEP = 0.0005  # sizing sweep granularity (5 bps)
FLOOR = STEP  # tiny non-zero floor when no size clears the ruin cap (caller sizes-tiny / exits)


def size_for_survival(
    p_loss: float,
    gap: float = 0.70,
    ruin_cap: float = 0.02,
    per_event_cap: float = 0.03,
    n_trades: int = 52,
    *,
    target_return: float | None = None,
    expected_move: float | None = None,
) -> ToolResult:
    """Size a leg to SERVE the ~1%/week target WITHIN the risk-of-ruin survival ceiling.

    The `survival_cap` — the largest size_pct whose risk_of_ruin(p_loss, size_pct, gap).value
    <= ruin_cap, also clamped to per_event_cap — is the HARD upper bound. It is found by sweeping
    size DOWNWARD from per_event_cap in fixed STEPs (risk_of_ruin rises monotonically with size,
    so the first size clearing the cap from the top is the largest one). This sweep is UNCHANGED
    from Phase 5.

    Sizing WITHIN that cap (PORT-03 amended / WEEK-04):
      - target_return=None  -> chosen = survival_cap  (EXACT Phase-5 behavior; back-compat).
      - else                -> target_implied = target_return / expected_move (needs expected_move>0,
                               else FLOOR), and chosen = clamp(target_implied, FLOOR, survival_cap).
    Because survival_cap is the clamp's upper bound, a target can raise the size TOWARD but provably
    never PAST the ruin ceiling — the cap is structurally un-crossable.

    Returns the chosen size + the risk_of_ruin snapshot AT the chosen size as its audit citation.
    No size clears the cap → the tiny FLOOR (never an error): a zero-ish position the caller turns
    into size-tiny / exit-before-event.
    """
    inputs = {
        "p_loss": p_loss,
        "gap": gap,
        "ruin_cap": ruin_cap,
        "per_event_cap": per_event_cap,
        "n_trades": n_trades,
        "target_return": target_return,
        "expected_move": expected_move,
    }
    # survival_cap = the EXISTING downward sweep result (the hard ceiling). BYTE-FOR-BYTE.
    n = int(round(per_event_cap / STEP))  # candidate sizes: n*STEP (== per_event_cap) down to STEP
    survival_cap = FLOOR
    for i in range(n, 0, -1):
        size = round(i * STEP, 10)
        ror = risk_of_ruin(p_loss, size, gap, n_trades=n_trades)
        if ror.value <= ruin_cap:
            survival_cap = size
            break

    if target_return is None:
        chosen = survival_cap
    else:
        target_implied = target_return / expected_move if expected_move and expected_move > 0 else FLOOR
        chosen = min(max(target_implied, FLOOR), survival_cap)  # survival_cap is the ceiling

    # snapshot at the CHOSEN size (recomputed so ruin_at_size reflects what we actually sized to)
    snapshot = risk_of_ruin(p_loss, chosen, gap, n_trades=n_trades)
    return ToolResult(
        tool="size_for_survival",
        tool_version=_VERSION,
        inputs=inputs,
        value=chosen,
        detail={"ruin_at_size": snapshot.value, "risk_of_ruin": dict(snapshot.detail)},
    )


def validate_hedge(
    conn, embed, target, catalyst, entry, exit_by_date, analog_gaps, prices,
    *, candidate_peer: str | None = None,
) -> Hedge | None:
    """Re-validate an inverse-payoff peer for THIS catalyst, or return None (honest fallback).

    The stored KB payoff sign is a PRIOR, never proof — a peer only becomes a hedge if, for this
    specific catalyst, it passes ALL THREE gates:
      1. it is a -1 inverse peer (a +1 co-move peer is never an idiosyncratic hedge, HEDGE-01);
      2. PAYOFF (HEDGE-02): the un-netted worst cell of conditional_payoff (from the caller's analog
         gaps) is materially better than holding the target alone, AND the peer has real downside in
         its own down branch (peer_down < 0) — no fake netting;
      3. cointegration is True (necessary-not-sufficient gate, PITFALLS #3);
      4. catalyst-clean (HEDGE-03): the peer has NO own catalyst inside the [entry, exit] hold window.

    All pass → a validated idiosyncratic Hedge OBJECT; anything else → None (size-tiny / exit,
    HEDGE-04 — never a fabricated hedge). Pure/deterministic: no run_structured here.

    `candidate_peer` (06-02, keyword-only, default None) scopes validation to a SPECIFIC promoted
    peer: when set, only that peer is considered (empty → None, an honest fallback, never a
    different peer). `candidate_peer=None` is byte-for-byte the Phase-5 behavior (top -1 peer).

    # ponytail: top -1 candidate only — the KB weight already ranks them; multi-candidate search is
    #           speculative until a real trade needs it.
    """
    peers = [p for p in kb.hedge_peers(conn, target) if p["payoff_direction"] == -1]
    if candidate_peer is not None:
        peers = [p for p in peers if p["peer"] == candidate_peer]
    if not peers:
        return None
    cand = peers[0]
    peer_ticker = cand["peer"]

    cp = conditional_payoff(
        analog_gaps["target_up"], analog_gaps["target_down"],
        analog_gaps["peer_up"], analog_gaps["peer_down"],
        analog_gaps["w_target"], analog_gaps["w_peer"],
    )
    # target-alone worst = the whole allocation in the target on its worse branch (no hedge)
    target_alone_worst = (analog_gaps["w_target"] + analog_gaps["w_peer"]) * min(
        analog_gaps["target_up"], analog_gaps["target_down"]
    )
    payoff_ok = cp.value > target_alone_worst and analog_gaps["peer_down"] < 0

    cointegrated = cointegration(prices["target"], prices["peer"]).detail["cointegrated"]

    # peer catalyst-clean check through the serving gateway at cutoff=entry (the decision date) — the
    # SAME seam the backtest uses; a peer catalyst not yet knowable at entry can't disqualify the hedge.
    peer_events = [
        c for c in serving.asof(conn, cutoff=entry).catalysts()
        if c.ticker == peer_ticker and entry <= c.event_date <= exit_by_date
    ]
    catalyst_clean = not peer_events

    if not (payoff_ok and cointegrated and catalyst_clean):
        return None

    return Hedge(
        instrument="equity_peer",
        ticker=peer_ticker,
        payoff_direction=-1,
        validated=True,
        covers="idiosyncratic",
        mechanism=cand["mechanism"],
        conditional_worst=cp.value,
    )


class CommitteeView(BaseModel):
    """One committee member's ARGUED inputs (not the size). Each member supplies its p_loss / gap
    read and its hedge opinion with citations; the deterministic tools own every money number."""

    model_config = ConfigDict(extra="forbid")
    role: str
    p_loss_estimate: float = Field(ge=0.0, le=1.0)
    gap_estimate: float
    hedge_opinion: str
    rationale: str
    evidence_refs: list[str] = []


_ROLES = ("aggressive", "conservative", "neutral")


def _committee_context(p_loss, gap, hedge_ticker, analog_gaps) -> str:
    return (
        f"Prior p_loss estimate: {p_loss:.2f}\n"
        f"Prior gap (down-move) estimate: {gap:.2f}\n"
        f"Candidate inverse-hedge peer: {hedge_ticker or 'NONE'}\n"
        f"Analog gaps (target/peer, up/down): "
        f"target_up={analog_gaps['target_up']:+.2f} target_down={analog_gaps['target_down']:+.2f} "
        f"peer_up={analog_gaps['peer_up']:+.2f} peer_down={analog_gaps['peer_down']:+.2f}\n"
    )


def _committee_prompt(role: str, ctx: str) -> str:
    return f"""You are the {role.upper()} member of a 3-way biotech Risk Committee (aggressive/conservative/neutral).
Argue this catalyst's risk from the analogs below — reason in ISOLATION, not toward a consensus.

SHARED EVIDENCE
{ctx}
Supply your ARGUED INPUTS in the CommitteeView:
  - p_loss_estimate: your probability the target LOSES on this binary catalyst (cited to an analog/base rate).
  - gap_estimate: your estimate of the down-move magnitude (the gap sizing sizes against).
  - hedge_opinion: does the inverse peer reliably RISE when the target FALLS on THIS catalyst? Argue it.
  - rationale + evidence_refs: cite every claim (tool:... / kb:...).
Do NOT emit a position size, entry, stop, or take-profit — the size is computed deterministically downstream.
"""


def _synthesis_prompt(ctx: str, views: list[CommitteeView]) -> str:
    argued = "\n".join(
        f"[{v.role}] p_loss={v.p_loss_estimate:.2f} gap={v.gap_estimate:.2f} hedge: {v.hedge_opinion}"
        for v in views
    )
    return f"""You are the RISK COMMITTEE CHAIR. Synthesize the three members' arguments into a RiskAssessment
narrative: the downside stress scenarios, liquidity, event-vol, each member's view, and residual risks.

SHARED EVIDENCE
{ctx}
COMMITTEE ARGUMENTS
{argued}

Emit the narrative fields ONLY. The recommended_size_pct, conditional_payoff_matrix, conditional_worst,
hedge, hedge_valid, and ruin_at_size are computed by deterministic tools and will OVERWRITE whatever you
put there — never let a number you write become the trade size or the hedge.
"""


async def assess(
    conn,
    embed,
    proposal,
    catalyst,
    *,
    p_loss: float,
    gap: float,
    analog_gaps: dict,
    prices: dict,
    entry: str | None = None,
    exit_by_date: str | None = None,
    ruin_cap: float = 0.02,
    per_event_cap: float = 0.03,
    target_return: float | None = None,
    expected_move: float | None = None,
) -> RiskAssessment:
    """The 3-way Risk Committee: three isolated `run_structured` views (sonnet) then an opus synthesis,
    mirroring `debate.py`'s flat fan-out over the one seam. The committee INTERPRETS; the money numbers
    are DETERMINISTIC and overwrite anything the LLM emits:
      - recommended_size_pct = size_for_survival(...).value (never an LLM number),
      - conditional_payoff_matrix / conditional_worst = conditional_payoff(...),
      - hedge = validate_hedge(...) called EXACTLY ONCE, threaded onto BOTH hedge (the object) and
        hedge_valid (BLOCKER-1),
      - ruin_at_size = risk_of_ruin at the chosen size.
    Fully offline under test — every LLM call routes through run_structured.
    """
    entry = entry or catalyst["event_date"]
    exit_by_date = exit_by_date or proposal.exit_by_date

    ctx = _committee_context(p_loss, gap, proposal.target_long, analog_gaps)
    views = [
        await run_structured(_committee_prompt(role, ctx), CommitteeView, model="sonnet")
        for role in _ROLES
    ]

    # Deterministic money + hedge — the committee can never inject any of these.
    size_res = size_for_survival(
        p_loss, gap, ruin_cap, per_event_cap,
        target_return=target_return, expected_move=expected_move,
    )
    cp = conditional_payoff(
        analog_gaps["target_up"], analog_gaps["target_down"],
        analog_gaps["peer_up"], analog_gaps["peer_down"],
        analog_gaps["w_target"], analog_gaps["w_peer"],
    )
    hedge_obj = validate_hedge(
        conn, embed, proposal.target_long, catalyst, entry, exit_by_date, analog_gaps, prices
    )  # called ONCE (BLOCKER-1)
    hedge_valid = hedge_obj is not None and hedge_obj.validated

    synthesis = await run_structured(_synthesis_prompt(ctx, views), RiskAssessment, model="opus")
    return synthesis.model_copy(update={
        "recommended_size_pct": size_res.value,
        "conditional_payoff_matrix": cp.detail["matrix"],
        "conditional_worst": cp.value,
        "hedge": hedge_obj,
        "hedge_valid": hedge_valid,
        "ruin_at_size": size_res.detail["ruin_at_size"],
    })
