"""Catalyst-event quant tools — the move estimator + the Kelly-consistent hold-vs-exit decision.

`catalyst_move_estimate` is a two-state up/down mixture over historical analog gaps: it produces
the SIGNED expected move plus the SEPARATE up/down magnitudes every downstream tool consumes
(sizing's down_move → risk_of_ruin gap, the TP anchor, the hold-vs-exit branches). It works
OFFLINE from analogs alone — `implied_move` is a pluggable MAGNITUDE prior/clamp, NEVER a
directional signal (PITFALLS #10): magnitudes are blended, the sign comes only from p_positive.

`expected_log_growth` / `hold_vs_exit` implement the LOCKED <model_forms> hold-through-vs-exit
rule: decide by expected-LOG-growth at the survival-constrained size f (Kelly-consistent), NOT
raw EV. The log penalizes the fat down-tail, so a positive-EV hold can still be rejected in
favor of exiting before the event (single-leg-microstructure.md §3.2, BLOCKER-2).

Pure-python (stdlib `math`/`statistics` only). Every threshold is read from a params dict — a
missing key RAISES; no numeric literal fallback in any tool body. Same params + inputs in →
identical frozen ToolResult out (deterministic, offline, no DB).
"""

from math import log
from statistics import median

from .result import ToolResult
from .sizing import _finite, _prob

_VERSION = "1.0.0"


def _branch_magnitude(
    moves: list[float], implied_move: float | None, blend: float | None, side: str
) -> tuple[float, bool]:
    """Central magnitude for one analog branch. Returns (magnitude, used_fallback).

    Non-empty branch → median (blended with |implied_move| when a prior is supplied).
    Empty branch → |implied_move| fallback if present, else RAISE (no silent default).
    Blending is magnitude-only: it can never flip the sign of the mixture.
    """
    if moves:
        m = median(moves)
        if implied_move is not None:
            # blend read + validated by the caller (missing key already raised there)
            return (1.0 - blend) * m + blend * abs(implied_move), False
        return m, False
    if implied_move is not None:
        return abs(implied_move), True
    raise ValueError(
        f"{side} branch is empty and no implied_move fallback was supplied "
        "(no silent default — supply analogs or an implied_move prior)"
    )


def catalyst_move_estimate(
    p_positive: float,
    up_moves: list[float],
    down_moves: list[float],
    params: dict,
    implied_move: float | None = None,
) -> ToolResult:
    """Two-state up/down mixture of historical analog gaps → signed expected move + magnitudes.

    value = p_positive·up_move − (1−p_positive)·down_move. `up_move`/`down_move` are the robust
    (median) central estimates of the positive/negative analog branches; pass |move| for the
    down branch. `implied_move` is a MAGNITUDE prior blended per params["estimator"]["implied_blend"]
    — it never sets the sign. Every threshold comes from `params`; a missing key raises.
    """
    _prob(p_positive, "p_positive")
    for x in up_moves:
        _finite(x, "up_move")
    for x in down_moves:
        _finite(x, "down_move")

    est = params["estimator"]  # missing block → KeyError (no literal fallback)
    method = est["method"]
    min_analogs = est["min_analogs"]
    if method != "median":
        raise ValueError(f"unsupported estimator method {method!r} (only 'median')")

    blend: float | None = None
    if implied_move is not None:
        _finite(implied_move, "implied_move")
        blend = _prob(est["implied_blend"], "implied_blend")  # required when prior used

    up_move, up_fb = _branch_magnitude(up_moves, implied_move, blend, "up")
    down_move, down_fb = _branch_magnitude(down_moves, implied_move, blend, "down")

    expected_move = p_positive * up_move - (1.0 - p_positive) * down_move
    n_up, n_down = len(up_moves), len(down_moves)
    source = "implied_fallback" if (up_fb or down_fb) else "analogs"
    cold_start = (n_up + n_down) < min_analogs

    return ToolResult(
        tool="catalyst_move_estimate",
        tool_version=_VERSION,
        inputs={
            "p_positive": p_positive,
            "up_moves": up_moves,
            "down_moves": down_moves,
            "params": params,
            "implied_move": implied_move,
        },
        value=expected_move,
        detail={
            "up_move": up_move,
            "down_move": down_move,
            "p_positive": p_positive,
            "n_up": n_up,
            "n_down": n_down,
            "implied_move": implied_move,
            "source": source,
            "cold_start": cold_start,
        },
    )


def expected_log_growth(f: float, outcomes: list[tuple[float, float]]) -> ToolResult:
    """E[log(1 + f·R)] over outcomes=[(prob, ret), ...] — the Kelly/growth-optimal objective.

    The right criterion for a hold-through-vs-exit decision (single-leg-microstructure.md §3.2):
    the log penalizes the fat down-tail, so it can reject a positive-EV bet. Money-critical —
    RAISES if f<=0, if probs do not sum to ~1, or if any (1 + f·ret) <= 0 (a non-survivable size
    is a sizing bug, NEVER a silent -inf).
    """
    _finite(f, "f")
    if f <= 0:
        raise ValueError("f must be > 0")

    p_sum = 0.0
    contributions: list[float] = []
    for prob, ret in outcomes:
        _prob(prob, "prob")
        _finite(ret, "ret")
        p_sum += prob
        wealth = 1.0 + f * ret
        if wealth <= 0:
            raise ValueError(
                f"non-survivable size: 1 + f·ret = {wealth!r} <= 0 (size f={f!r} ruins on "
                f"ret={ret!r}) — never a silent -inf"
            )
        contributions.append(prob * log(wealth))
    if abs(p_sum - 1.0) >= 1e-9:
        raise ValueError(f"outcome probabilities must sum to 1 (got {p_sum!r})")

    return ToolResult(
        tool="expected_log_growth",
        tool_version=_VERSION,
        inputs={"f": f, "outcomes": outcomes},
        value=sum(contributions),
        detail={"contributions": contributions},
    )


def hold_vs_exit(
    f: float,
    hold_outcomes: list[tuple[float, float]],
    exit_outcomes: list[tuple[float, float]],
    margin: float = 0.0,
) -> ToolResult:
    """Hold through ⇔ E[log(1+f·R_hold)] > E[log(1+f·R_exit)] + margin (research §3.2).

    value = 1.0 (hold) / 0.0 (exit); both branches are evaluated by expected_log_growth at the
    SAME survival-constrained f — Kelly-consistent, NOT raw EV. `margin` is a param the builder
    supplies (params["builder"]["log_growth_margin"]); the 0.0 default is the neutral value, not
    a hidden threshold. Deterministic, no DB.
    """
    _finite(margin, "margin")
    g_hold = expected_log_growth(f, hold_outcomes).value
    g_exit = expected_log_growth(f, exit_outcomes).value
    hold = g_hold > g_exit + margin
    return ToolResult(
        tool="hold_vs_exit",
        tool_version=_VERSION,
        inputs={
            "f": f,
            "hold_outcomes": hold_outcomes,
            "exit_outcomes": exit_outcomes,
            "margin": margin,
        },
        value=1.0 if hold else 0.0,
        detail={
            "g_hold": g_hold,
            "g_exit": g_exit,
            "decision": "hold" if hold else "exit",
            "margin": margin,
        },
    )
