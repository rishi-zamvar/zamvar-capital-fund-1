"""Data-latency knob (operator directive): effective_asof makes look-ahead through delayed
free-data classes impossible. The lag sits in config beside the slippage knob and is tunable.
"""

import pytest

from catalyst_trader.backtest.fill import effective_asof
from catalyst_trader.store import bars_asof
from tests.synth_history import seed_history, week_ends

_CFG = {"options": 3, "short_interest": 14, "eod": 7}  # per-class lag in DAYS


def test_effective_asof_subtracts_per_class_lag():
    assert effective_asof("options", "2024-01-15", _CFG) == "2024-01-12"
    assert effective_asof("short_interest", "2024-01-15", _CFG) == "2024-01-01"


def test_latency_makes_lookahead_impossible(db):
    # A datum published only AFTER (effective_asof, decision_date] must never be read. Mirrors
    # test_bars_asof_never_returns_a_future_bar, but the shift comes from the latency knob.
    wk = seed_history(db, tickers=["AAAA"], weeks=4)  # W0..W3 Mondays from 2024-01-01
    decision = wk[2]                                   # 2024-01-15
    eff = effective_asof("eod", decision, _CFG)        # 2024-01-08 (W1)
    got = bars_asof(db, "AAAA", eff)
    weeks_seen = {b["week_end"] for b in got}
    assert wk[2] not in weeks_seen                     # the W2 datum was not yet available
    assert weeks_seen == {wk[0], wk[1]}


def test_effective_asof_missing_class_raises():
    # No silent 0-lag: an unconfigured data class is a hard error, not a look-ahead-by-default.
    with pytest.raises((KeyError, ValueError)):
        effective_asof("unknown_class", "2024-01-15", _CFG)
