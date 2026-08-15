"""The risk desk (PORT-03 + HEDGE-01..04): survival-first sizing, honest per-catalyst
inverse-hedge validation, and a 3-way (aggressive/conservative/neutral) Risk Committee
that mirrors `debate.py`'s flat fan-out over the one `run_structured` seam.

The committee AGENTS interpret (argue p_loss / gap / hedge validity from analogs); every
money number is a DETERMINISTIC quant output the committee can never inject:
  - the size is `size_for_survival()` — swept from `risk_of_ruin`, with NO return-target
    parameter, so sizing is structurally decoupled from the 1%/week objective (PITFALLS #2/#5).
  - the hedge is `validate_hedge()` — a peer only counts if it is a -1 inverse peer that passes
    conditional_payoff + cointegration + catalyst-clean THIS catalyst; otherwise None (honest
    fallback, HEDGE-04). The validated Hedge OBJECT is carried on the RiskAssessment (BLOCKER-1).

# ponytail: flat async fan-out over run_structured, same shape as debate.py — no base classes,
#           no config objects. validate_hedge + size_for_survival are pure/deterministic; only
#           the committee views + synthesis narrative go through the LLM seam.
"""

from pydantic import BaseModel, ConfigDict, Field

from .. import kb, store
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
) -> ToolResult:
    """Largest size_pct whose risk_of_ruin(p_loss, size_pct, gap).value <= ruin_cap, also clamped
    to per_event_cap. Sweep size DOWNWARD from per_event_cap in fixed STEPs; risk_of_ruin rises
    monotonically with size, so the first size that clears the cap from the top is the largest one.

    There is deliberately NO return / target / weekly parameter — sizing mirrors risk_of_ruin's own
    omission (the structural anti-1%-coupling). Returns the chosen size + the risk_of_ruin snapshot
    at that size as its audit citation. No size clears → the tiny FLOOR (never an error): a zero-ish
    position the caller turns into size-tiny / exit-before-event.
    """
    inputs = {
        "p_loss": p_loss,
        "gap": gap,
        "ruin_cap": ruin_cap,
        "per_event_cap": per_event_cap,
        "n_trades": n_trades,
    }
    n = int(round(per_event_cap / STEP))  # candidate sizes: n*STEP (== per_event_cap) down to STEP
    chosen = FLOOR
    snapshot = risk_of_ruin(p_loss, FLOOR, gap, n_trades=n_trades)
    for i in range(n, 0, -1):
        size = round(i * STEP, 10)
        ror = risk_of_ruin(p_loss, size, gap, n_trades=n_trades)
        if ror.value <= ruin_cap:
            chosen, snapshot = size, ror
            break

    return ToolResult(
        tool="size_for_survival",
        tool_version=_VERSION,
        inputs=inputs,
        value=chosen,
        detail={"ruin_at_size": snapshot.value, "risk_of_ruin": dict(snapshot.detail)},
    )
