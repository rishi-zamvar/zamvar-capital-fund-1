"""Risk desk (PORT-03 + HEDGE-01..04): the deterministic survival-sizing engine,
the honest per-catalyst inverse-hedge validator, and the 3-way Risk Committee.

Money-critical invariants under test:
  - size_for_survival has NO return-target parameter (1% can never be a sizing input).
  - a hedge is only validated when a -1 inverse peer passes conditional_payoff +
    cointegration + catalyst-clean THIS catalyst; every other case → None (honest fallback).
  - assess calls validate_hedge EXACTLY ONCE and threads that single result onto BOTH
    RiskAssessment.hedge (the object) AND hedge_valid (BLOCKER-1).
  - the size on the RiskAssessment is ALWAYS the size_for_survival quant output, never an LLM number.

Quant + KB run FOR REAL (deterministic); run_structured is monkeypatched → fully offline.
"""

import inspect

from catalyst_trader.desk import risk
from catalyst_trader.quant.sizing import risk_of_ruin


# ---------------------------------------------------------------------------
# Task 1 — size_for_survival
# ---------------------------------------------------------------------------


def test_no_return_target_parameter():
    """Structural anti-1%-coupling: the signature carries NO return/target/weekly param."""
    params = inspect.signature(risk.size_for_survival).parameters
    banned = ("target", "return", "weekly", "one_pct", "benchmark")
    for name in params:
        assert not any(b in name.lower() for b in banned), f"{name} couples sizing to a return target"


def test_chosen_size_is_survivable_and_is_the_largest():
    r = risk.size_for_survival(p_loss=0.45, gap=0.70, ruin_cap=0.02, per_event_cap=0.03)
    size = r.value
    # the chosen size actually clears the ruin cap
    assert risk_of_ruin(0.45, size, 0.70).value <= 0.02
    # ...and it is the LARGEST such size — one step up breaches the cap (unless clamped at the per-event cap)
    if risk.FLOOR < size < 0.03:
        assert risk_of_ruin(0.45, size + risk.STEP, 0.70).value > 0.02
    # the citation snapshot is carried for audit
    assert r.detail["ruin_at_size"] == risk_of_ruin(0.45, size, 0.70).value
    assert "risk_of_ruin" in r.detail


def test_size_clamped_to_per_event_cap():
    # a trivially safe bet (tiny p_loss) still never exceeds the per-event cap
    r = risk.size_for_survival(p_loss=0.001, gap=0.70, ruin_cap=0.02, per_event_cap=0.03)
    assert r.value <= 0.03


def test_higher_p_loss_never_increases_size():
    low = risk.size_for_survival(p_loss=0.20, gap=0.70).value
    high = risk.size_for_survival(p_loss=0.50, gap=0.70).value
    assert high <= low


def test_larger_gap_never_increases_size():
    small_gap = risk.size_for_survival(p_loss=0.40, gap=0.30).value
    big_gap = risk.size_for_survival(p_loss=0.40, gap=0.90).value
    assert big_gap <= small_gap


def test_no_size_clears_cap_returns_tiny_floor_not_error(monkeypatch):
    # Defensive fallback: when NO size clears the ruin cap (every risk_of_ruin > cap),
    # size_for_survival returns the tiny FLOOR, never raises. Stub risk_of_ruin so the
    # branch is exercised without an expensive long-horizon DP.
    from catalyst_trader.quant.result import ToolResult

    def _ruinous(*a, **k):
        return ToolResult(tool="risk_of_ruin", tool_version="1.0.0", inputs={}, value=0.99, detail={})

    monkeypatch.setattr(risk, "risk_of_ruin", _ruinous)
    r = risk.size_for_survival(p_loss=0.9, gap=0.9, ruin_cap=0.02)
    assert r.value == risk.FLOOR
    assert r.detail["ruin_at_size"] == 0.99  # snapshot is the floor's (breaching) ruin


def test_deterministic():
    a = risk.size_for_survival(p_loss=0.37, gap=0.70)
    b = risk.size_for_survival(p_loss=0.37, gap=0.70)
    assert a.value == b.value and a.detail == b.detail
