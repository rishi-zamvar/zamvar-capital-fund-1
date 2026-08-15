"""Sizing tools — Kelly / fractional-Kelly, deterministic risk-of-ruin, SL/TP (QUANT-02).

The single most money-critical module. Pure-python (stdlib `math` only). The arithmetic IS
the guardrail: Kelly on a -70% binary returns an honestly tiny fraction and risk_of_ruin has
NO return-target parameter, so sizing can never be coupled to the 1%/week target — the 1% is a
measured outcome, not a sizing input (PITFALLS #5, #2). Every tool validates at the boundary
and RAISES rather than emitting inf/NaN (Pattern 2), returning a ToolResult that snapshots its
verbatim inputs (QUANT-03). risk_of_ruin is an EXACT streak-probability DP over n_trades — no
Monte Carlo — so results are reproducible and testable.
"""

import math

from .result import ToolResult

_VERSION = "1.0.0"


def _finite(x: float, name: str) -> float:
    if not math.isfinite(x):
        raise ValueError(f"{name} must be finite (got {x!r})")
    return x


def _prob(p: float, name: str) -> float:
    _finite(p, name)
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"{name} must be in [0, 1] (got {p!r})")
    return p


def kelly(p_win: float, win_frac: float, loss_frac: float) -> ToolResult:
    """Asymmetric two-outcome Kelly fraction.

    f* = p_win/loss_frac − (1−p_win)/win_frac ; clamp f*<0 → 0 (no edge = no bet).
    win_frac/loss_frac are the win/loss size as a fraction of stake; both must be > 0.
    On a -70% binary with poor odds f* is negative and clamps to 0 — the tool never inflates
    toward a return target (PITFALLS #5).
    """
    _prob(p_win, "p_win")
    _finite(win_frac, "win_frac")
    _finite(loss_frac, "loss_frac")
    if win_frac <= 0:
        raise ValueError("win_frac must be > 0")
    if loss_frac <= 0:
        raise ValueError("loss_frac must be > 0 (div-by-zero)")

    f_star = p_win / loss_frac - (1.0 - p_win) / win_frac
    f_star = max(f_star, 0.0)  # no edge = no bet

    return ToolResult(
        tool="kelly",
        tool_version=_VERSION,
        inputs={"p_win": p_win, "win_frac": win_frac, "loss_frac": loss_frac},
        value=f_star,
    )


def fractional_kelly(kelly_fraction: float, fraction: float = 0.25) -> ToolResult:
    """Scale a full-Kelly fraction down (default quarter-Kelly). value = fraction · kelly_fraction."""
    _finite(kelly_fraction, "kelly_fraction")
    _finite(fraction, "fraction")
    if fraction < 0:
        raise ValueError("fraction must be >= 0")

    return ToolResult(
        tool="fractional_kelly",
        tool_version=_VERSION,
        inputs={"kelly_fraction": kelly_fraction, "fraction": fraction},
        value=fraction * kelly_fraction,
    )


def risk_of_ruin(
    p_loss: float,
    size_pct: float,
    gap: float = 0.70,
    ruin_drawdown: float = 0.5,
    n_trades: int = 52,
) -> ToolResult:
    """Deterministic probability of ruin over n_trades (NO RNG, NO return-target input).

    Step 1: max_survivable = how many consecutive (−gap × size_pct) hits the bankroll takes
    before cumulative drawdown ≥ ruin_drawdown (iterate bankroll *= (1 − size_pct·gap)).
    Step 2: P(a losing streak of length ≥ max_survivable+1 occurs within n_trades Bernoulli(p_loss)
    trials), computed by an exact DP over trials tracking the current streak length.

    Sizing must never be coupled to the 1%/week target — that is why there is deliberately no
    return-target parameter here (PITFALLS #2, #5).
    """
    _prob(p_loss, "p_loss")
    _finite(size_pct, "size_pct")
    _finite(gap, "gap")
    _finite(ruin_drawdown, "ruin_drawdown")
    if not 0.0 < size_pct <= 1.0:
        raise ValueError("size_pct must be in (0, 1]")
    if not 0.0 < gap <= 1.0:
        raise ValueError("gap must be in (0, 1]")
    if not 0.0 < ruin_drawdown <= 1.0:
        raise ValueError("ruin_drawdown must be in (0, 1]")
    if n_trades <= 0:
        raise ValueError("n_trades must be > 0")

    # Step 1: consecutive losses to ruin (loss_length). max_survivable = loss_length − 1.
    factor = 1.0 - size_pct * gap  # < 1 since size_pct>0, gap>0
    threshold = 1.0 - ruin_drawdown
    bankroll = 1.0
    loss_length = 0
    while bankroll > threshold:
        bankroll *= factor
        loss_length += 1
        if loss_length > n_trades:
            # a ruinous streak cannot fit in n_trades → ruin impossible over the horizon
            break
    max_survivable = loss_length - 1

    # Step 2: exact DP — P(run of losses of length ≥ loss_length within n_trades).
    if loss_length > n_trades:
        value = 0.0
    else:
        # dp[s] = prob of a current trailing loss-streak of exactly s with no ruin yet.
        dp = [0.0] * loss_length
        dp[0] = 1.0
        ruined = 0.0
        for _ in range(n_trades):
            new_dp = [0.0] * loss_length
            for s, prob in enumerate(dp):
                if prob == 0.0:
                    continue
                # a loss extends the streak
                if s + 1 >= loss_length:
                    ruined += prob * p_loss
                else:
                    new_dp[s + 1] += prob * p_loss
                # a win resets the streak
                new_dp[0] += prob * (1.0 - p_loss)
            dp = new_dp
        value = ruined

    return ToolResult(
        tool="risk_of_ruin",
        tool_version=_VERSION,
        inputs={
            "p_loss": p_loss,
            "size_pct": size_pct,
            "gap": gap,
            "ruin_drawdown": ruin_drawdown,
            "n_trades": n_trades,
        },
        value=value,
        detail={"max_survivable_consecutive_losses": max_survivable},
    )


def sl_tp_levels(
    entry: float,
    sl_pct: float,
    tp_pct: float,
    holds_through_catalyst: bool = False,
) -> ToolResult:
    """Stop-loss / take-profit levels and reward:risk ratio.

    stop = entry·(1−sl_pct); target = entry·(1+tp_pct); reward_risk = tp_pct/sl_pct.
    When the hold window spans a binary catalyst the stop is ADVISORY only — the gap jumps it,
    so the dossier must never display a fictitious bounded loss (PITFALLS #2).
    """
    _finite(entry, "entry")
    _finite(sl_pct, "sl_pct")
    _finite(tp_pct, "tp_pct")
    if entry <= 0:
        raise ValueError("entry must be > 0")
    if sl_pct <= 0:
        raise ValueError("sl_pct must be > 0 (R:R undefined / div-by-zero)")
    if tp_pct < 0:
        raise ValueError("tp_pct must be >= 0")

    detail: dict = {
        "stop": entry * (1.0 - sl_pct),
        "target": entry * (1.0 + tp_pct),
    }
    if holds_through_catalyst:
        detail["advisory"] = True
        detail["reason"] = (
            "gap jumps stop on binary event — size for -70%, not stop distance"
        )

    return ToolResult(
        tool="sl_tp_levels",
        tool_version=_VERSION,
        inputs={
            "entry": entry,
            "sl_pct": sl_pct,
            "tp_pct": tp_pct,
            "holds_through_catalyst": holds_through_catalyst,
        },
        value=tp_pct / sl_pct,
        detail=detail,
    )


def adaptive_sl_tp_levels(
    entry: float,
    up_move: float,
    vol_move: float,
    params: dict,
    holds_through_catalyst: bool = False,
) -> ToolResult:
    """Derive SL/TP from the catalyst move estimate, then DELEGATE to sl_tp_levels.

    sl_pct = params["sl_tp"]["sl_vol_mult"]·vol_move (vol proxy: estimator down_move or
    implied_move); tp_pct = params["sl_tp"]["tp_frac"]·up_move (the estimator TP anchor).
    Delegation keeps the gap-exposed advisory gate in ONE place (PITFALLS #2) — the advisory
    flag + reason come for free from sl_tp_levels. NO magic numbers: sl_vol_mult and tp_frac
    are read from params and a missing key RAISES.
    """
    _finite(entry, "entry")
    _finite(up_move, "up_move")
    _finite(vol_move, "vol_move")
    if vol_move <= 0:
        raise ValueError("vol_move must be > 0 (sl_pct must stay > 0)")
    if up_move < 0:
        raise ValueError("up_move must be >= 0")

    sltp = params["sl_tp"]  # missing block → KeyError (no literal fallback)
    sl_pct = sltp["sl_vol_mult"] * vol_move
    tp_pct = sltp["tp_frac"] * up_move

    return sl_tp_levels(entry, sl_pct, tp_pct, holds_through_catalyst)
