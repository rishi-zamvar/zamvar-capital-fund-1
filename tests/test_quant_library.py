"""Library-wide reproducibility invariant (QUANT-03, Pitfall 6) + import-surface check.

One parametrized test enforces the reproducibility contract across EVERY tool in the library
at once: each tool returns a `ToolResult` whose `inputs` is a verbatim snapshot of the exact
call kwargs, carries a non-empty `tool_version`, and is immutable. This is the cheapest
library-wide guarantee that any number the desk emits can be reproduced from its snapshot —
adding a new tool without wiring it into `HAPPY_PATH` here leaves the library provably
un-covered by the invariant, which is the point.
"""

import math

import pytest
from pydantic import ValidationError

import catalyst_trader.quant as quant
from catalyst_trader.quant import (
    ToolResult,
    attribution,
    avg_win_loss,
    base_rate,
    cash_runway,
    cointegration,
    concentration,
    conditional_payoff,
    correlation_beta,
    cumulative_return,
    exposure,
    fractional_kelly,
    hedge_effectiveness,
    implied_move,
    iv_crush,
    kelly,
    load_base_rates,
    load_weights,
    max_drawdown,
    rnpv,
    risk_of_ruin,
    score_rubric,
    sharpe,
    sl_tp_levels,
    sortino,
    win_rate,
)

# Two deterministic, finite, varied price series for the statsmodels cointegration path.
_PB = [100.0 + i * 0.5 + math.sin(i) for i in range(40)]
_PA = [2.0 * b + math.cos(i) * 0.3 for i, b in enumerate(_PB)]

# (tool_callable, happy_path_kwargs) — kwargs are authored to equal the tool's inputs snapshot
# exactly (every field the tool records, including ones left at their default), so the
# inputs==kwargs assertion below is a true reproducibility check, not an approximation.
HAPPY_PATH = [
    (rnpv, {"cashflows": [(1.0, 100.0, 0.5)], "discount_rate": 0.1, "costs": [(0.0, 10.0, 0.9)]}),
    (cash_runway, {"cash_usd": 1000.0, "monthly_burn_usd": 100.0, "months_to_catalyst": 6.0}),
    (kelly, {"p_win": 0.4, "win_frac": 2.0, "loss_frac": 0.7}),
    (fractional_kelly, {"kelly_fraction": 0.2, "fraction": 0.25}),
    (risk_of_ruin, {"p_loss": 0.6, "size_pct": 0.02, "gap": 0.7, "ruin_drawdown": 0.5, "n_trades": 52}),
    (sl_tp_levels, {"entry": 10.0, "sl_pct": 0.1, "tp_pct": 0.2, "holds_through_catalyst": True}),
    (cointegration, {"price_a": _PA, "price_b": _PB, "method": "engle_granger", "significance": 0.05}),
    (correlation_beta, {"asset_returns": [0.01, 0.02, -0.01, 0.03], "market_returns": [0.02, 0.01, 0.0, 0.025]}),
    (
        conditional_payoff,
        {"target_up": 0.3, "target_down": -0.7, "peer_up": 0.1, "peer_down": -0.2, "w_target": 0.6, "w_peer": 0.4},
    ),
    (implied_move, {"underlying_price": 10.0, "call_mid": 1.0, "put_mid": 1.2, "iv": None, "days_to_event": None}),
    (iv_crush, {"pre_event_iv": 2.5, "post_event_iv": 0.8, "baseline_iv": None}),
    (sharpe, {"returns": [0.01, 0.02, -0.01, 0.03], "periods_per_year": 52, "risk_free": 0.0}),
    (sortino, {"returns": [0.01, 0.02, -0.01, 0.03], "periods_per_year": 52, "mar": 0.0, "risk_free": 0.0}),
    (cumulative_return, {"returns": [0.01, 0.02, -0.01, 0.03]}),
    (attribution, {"components": {"alpha": 0.6, "beta": 0.4}, "total": 1.0}),
    (max_drawdown, {"returns": [0.01, 0.02, -0.05, 0.03]}),
    (win_rate, {"trade_returns": [0.01, -0.02, 0.03, -0.01]}),
    (avg_win_loss, {"trade_returns": [0.01, -0.02, 0.03, -0.01]}),
    (hedge_effectiveness, {"target_legs": [-0.1, 0.2, -0.05], "hedge_legs": [0.08, -0.01, 0.04]}),
    (concentration, {"weights": [0.6, 0.4]}),
    (exposure, {"weights": [0.6, 0.4]}),
    (
        score_rubric,
        {
            "factor_scores": {
                "pos": 5.0,
                "cash_runway": 6.0,
                "trial_design": 7.0,
                "endpoint_credibility": 8.0,
                "regulatory_precedent": 4.0,
                "pipeline_concentration": 3.0,
                "management": 9.0,
                "commercial": 5.0,
            }
        },
    ),
]

_IDS = [tool.__name__ for tool, _ in HAPPY_PATH]


@pytest.mark.parametrize("tool, kwargs", HAPPY_PATH, ids=_IDS)
def test_given_valid_inputs_when_tool_called_then_result_snapshots_inputs_verbatim(tool, kwargs):
    result = tool(**kwargs)

    # (a) every tool speaks the same reproducibility contract
    assert isinstance(result, ToolResult)
    # (b) inputs is a verbatim snapshot of the exact call kwargs (QUANT-03 / Pitfall 6)
    assert result.inputs == kwargs
    # (c) the formula is versioned (QUANT-01)
    assert isinstance(result.tool_version, str) and result.tool_version
    # tool name is self-identifying
    assert result.tool == tool.__name__


@pytest.mark.parametrize("tool, kwargs", HAPPY_PATH, ids=_IDS)
def test_given_a_result_when_a_field_is_reassigned_then_it_raises(tool, kwargs):
    result = tool(**kwargs)
    with pytest.raises(ValidationError):
        result.value = 999.0  # frozen=True — auditable numbers can't be silently rewritten


def test_given_the_package_when_imported_then_every_declared_name_is_present():
    for name in quant.__all__:
        assert hasattr(quant, name), f"{name} in __all__ but not importable from catalyst_trader.quant"


def test_the_two_loaders_are_reachable_from_the_one_surface():
    # loaders return raw data, not a ToolResult, but must live on the same import surface
    assert callable(load_weights) and callable(load_base_rates) and callable(base_rate)
