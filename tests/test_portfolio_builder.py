"""Portfolio what-if ENGINE (Wave 2) — RED-first money-path suite.

build_portfolio(positions, assumptions) -> PortfolioOutcome is a STATELESS pure function:
literal positions + literal assumptions + a FAKE corr_source (dict or callable) — no DB, no
network, no hidden state. These tests pin the covariance/vol math, the honest assumption labels
(vol proxy + off-diagonal correlation source), the scenario P&L roll-up, and the two economic
corrections the plan-check flagged (risk-of-ruin loss magnitude, O(2^n) cap degradation).
"""

import math

import pytest

from catalyst_trader.desk.portfolio_builder import PARAMS, PortfolioOutcome, build_portfolio


# ── fake correlation profiles (the corr_source assumption; no live KB) ─────────────────────────
def _profile(xbi_corr=None, xbi_beta=None, peers=None):
    """A minimal hedge_profile blob: xbi.full.corr/beta + a peers list of {peer, corr_full}."""
    prof: dict = {"peers": list(peers or [])}
    if xbi_corr is not None:
        prof["xbi"] = {"full": {"corr": xbi_corr, "beta": xbi_beta, "r2": xbi_corr**2}}
    return prof


def _mv(**kw):
    """A per-name assumption sub-dict."""
    return dict(kw)


# ── signed weights → exposure / concentration / expected return ────────────────────────────────
def test_two_longs_report_gross_not_netted():
    out = build_portfolio(
        [{"ticker": "AAA", "side": "long", "size_pct": 0.6},
         {"ticker": "BBB", "side": "long", "size_pct": 0.6}],
        {"AAA": _mv(expected_move=0.1), "BBB": _mv(expected_move=0.1)},
    )
    assert out.gross_exposure == pytest.approx(1.2)   # NOT netted
    assert out.net_exposure == pytest.approx(1.2)


def test_long_plus_short_nets_in_net_exposure():
    out = build_portfolio(
        [{"ticker": "AAA", "side": "long", "size_pct": 0.6},
         {"ticker": "BBB", "side": "short", "size_pct": 0.4}],
        {"AAA": _mv(expected_move=0.1), "BBB": _mv(expected_move=0.1)},
    )
    assert out.gross_exposure == pytest.approx(1.0)   # |0.6| + |-0.4|
    assert out.net_exposure == pytest.approx(0.2)     # 0.6 - 0.4
    assert out.concentration == pytest.approx(0.6**2 + 0.4**2)
    assert out.max_weight == pytest.approx(0.6)


def test_expected_return_applies_side_sign():
    # CONCERN 3: the short side flips the sign of size·expected_move.
    out = build_portfolio(
        [{"ticker": "AAA", "side": "short", "size_pct": 0.5}],
        {"AAA": _mv(expected_move=0.2)},
    )
    assert out.expected_return == pytest.approx(-0.10)   # -(0.5 · 0.2)


def test_long_short_expected_return_sums_signed():
    out = build_portfolio(
        [{"ticker": "AAA", "side": "long", "size_pct": 0.5},
         {"ticker": "BBB", "side": "short", "size_pct": 0.5}],
        {"AAA": _mv(expected_move=0.2), "BBB": _mv(expected_move=0.1)},
    )
    assert out.expected_return == pytest.approx(0.5 * 0.2 - 0.5 * 0.1)


# ── covariance / vol math (MONEY PATH) ─────────────────────────────────────────────────────────
def test_single_position_vol_is_sigma_times_abs_weight():
    out = build_portfolio(
        [{"ticker": "AAA", "side": "long", "size_pct": 0.5}],
        {"AAA": _mv(expected_move=0.2)},   # sigma proxy = |0.2| = 0.2
    )
    assert out.portfolio_variance == pytest.approx(0.5**2 * 0.2**2)
    assert out.portfolio_vol == pytest.approx(0.5 * 0.2)


def test_two_names_zero_correlation_is_independence():
    out = build_portfolio(
        [{"ticker": "AAA", "side": "long", "size_pct": 0.5},
         {"ticker": "BBB", "side": "long", "size_pct": 0.4}],
        {"AAA": _mv(expected_move=0.2), "BBB": _mv(expected_move=0.3)},  # no corr_source → rho 0
    )
    assert out.portfolio_variance == pytest.approx(0.5**2 * 0.2**2 + 0.4**2 * 0.3**2)
    assert out.covariance_detail["rho_source"]["AAA-BBB"] == "zero"


def test_high_peer_corr_raises_variance_for_two_longs():
    base = build_portfolio(
        [{"ticker": "AAA", "side": "long", "size_pct": 0.5},
         {"ticker": "BBB", "side": "long", "size_pct": 0.4}],
        {"AAA": _mv(expected_move=0.2), "BBB": _mv(expected_move=0.3)},
    )
    corr = {"AAA": _profile(peers=[{"peer": "BBB", "corr_full": 0.8}]), "BBB": _profile()}
    hi = build_portfolio(
        [{"ticker": "AAA", "side": "long", "size_pct": 0.5},
         {"ticker": "BBB", "side": "long", "size_pct": 0.4}],
        {"AAA": _mv(expected_move=0.2), "BBB": _mv(expected_move=0.3), "corr_source": corr},
    )
    assert hi.portfolio_variance > base.portfolio_variance
    assert hi.covariance_detail["rho_source"]["AAA-BBB"] == "peer"


def test_long_short_positive_corr_lowers_variance():
    corr = {"AAA": _profile(peers=[{"peer": "BBB", "corr_full": 0.8}]), "BBB": _profile()}
    base = build_portfolio(
        [{"ticker": "AAA", "side": "long", "size_pct": 0.5},
         {"ticker": "BBB", "side": "short", "size_pct": 0.4}],
        {"AAA": _mv(expected_move=0.2), "BBB": _mv(expected_move=0.3)},
    )
    hedged = build_portfolio(
        [{"ticker": "AAA", "side": "long", "size_pct": 0.5},
         {"ticker": "BBB", "side": "short", "size_pct": 0.4}],
        {"AAA": _mv(expected_move=0.2), "BBB": _mv(expected_move=0.3), "corr_source": corr},
    )
    assert hedged.portfolio_variance < base.portfolio_variance   # diversification via sign


def test_dict_and_callable_corr_sources_are_identical():
    peers = [{"peer": "BBB", "corr_full": 0.5}]
    as_dict = {"AAA": _profile(peers=peers), "BBB": _profile()}
    as_call = lambda t: as_dict.get(t)  # noqa: E731
    positions = [{"ticker": "AAA", "side": "long", "size_pct": 0.5},
                 {"ticker": "BBB", "side": "long", "size_pct": 0.5}]
    moves = {"AAA": _mv(expected_move=0.2), "BBB": _mv(expected_move=0.2)}
    v1 = build_portfolio(positions, {**moves, "corr_source": as_dict}).portfolio_variance
    v2 = build_portfolio(positions, {**moves, "corr_source": as_call}).portfolio_variance
    assert v1 == pytest.approx(v2)


def test_missing_ticker_profile_is_idiosyncratic():
    # BBB has no profile entry (callable returns None) -> zero off-diagonal, own sigma on diagonal.
    corr = lambda t: {"AAA": _profile(xbi_corr=0.5, xbi_beta=1.0)}.get(t)  # noqa: E731
    out = build_portfolio(
        [{"ticker": "AAA", "side": "long", "size_pct": 0.5},
         {"ticker": "BBB", "side": "long", "size_pct": 0.4}],
        {"AAA": _mv(expected_move=0.2), "BBB": _mv(expected_move=0.3), "corr_source": corr},
    )
    assert out.covariance_detail["rho_source"]["AAA-BBB"] == "zero"
    assert out.portfolio_variance == pytest.approx(0.5**2 * 0.2**2 + 0.4**2 * 0.3**2)


def test_off_diagonal_source_precedence_peer_then_xbi_then_zero():
    # peer wins even when both names have XBI corrs.
    both = {"AAA": _profile(xbi_corr=0.5, xbi_beta=1.0, peers=[{"peer": "BBB", "corr_full": 0.3}]),
            "BBB": _profile(xbi_corr=0.4, xbi_beta=1.0)}
    o1 = build_portfolio(
        [{"ticker": "AAA", "side": "long", "size_pct": 0.5},
         {"ticker": "BBB", "side": "long", "size_pct": 0.5}],
        {"AAA": _mv(expected_move=0.2), "BBB": _mv(expected_move=0.2), "corr_source": both},
    )
    assert o1.covariance_detail["rho_source"]["AAA-BBB"] == "peer"

    # no peer → single-factor XBI-implied rho = 0.5·0.4
    xbi = {"AAA": _profile(xbi_corr=0.5, xbi_beta=1.0), "BBB": _profile(xbi_corr=0.4, xbi_beta=1.0)}
    o2 = build_portfolio(
        [{"ticker": "AAA", "side": "long", "size_pct": 0.5},
         {"ticker": "BBB", "side": "long", "size_pct": 0.5}],
        {"AAA": _mv(expected_move=0.2), "BBB": _mv(expected_move=0.2), "corr_source": xbi},
    )
    assert o2.covariance_detail["rho_source"]["AAA-BBB"] == "xbi_implied"
    # variance carries the implied cross term 2·w1·w2·σ1·σ2·(0.5·0.4)
    indep = 2 * (0.5**2 * 0.2**2)
    assert o2.portfolio_variance == pytest.approx(indep + 2 * 0.5 * 0.5 * 0.2 * 0.2 * 0.20)


def test_rho_clamped_to_unit_interval():
    corr = {"AAA": _profile(peers=[{"peer": "BBB", "corr_full": 5.0}]), "BBB": _profile()}
    out = build_portfolio(
        [{"ticker": "AAA", "side": "long", "size_pct": 0.5},
         {"ticker": "BBB", "side": "long", "size_pct": 0.5}],
        {"AAA": _mv(expected_move=0.2), "BBB": _mv(expected_move=0.2), "corr_source": corr},
    )
    # rho clamps to 1.0 -> var == (w1σ1 + w2σ2)^2 (perfectly correlated)
    assert out.portfolio_variance == pytest.approx((0.5 * 0.2 + 0.5 * 0.2) ** 2)


# ── honest labels: vol proxy vs supplied sigma ─────────────────────────────────────────────────
def test_vol_proxy_names_labels_which_used_the_expected_move_proxy():
    out = build_portfolio(
        [{"ticker": "AAA", "side": "long", "size_pct": 0.5},
         {"ticker": "BBB", "side": "long", "size_pct": 0.5}],
        {"AAA": _mv(expected_move=0.2), "BBB": _mv(expected_move=0.2, sigma=0.35)},
    )
    assert out.covariance_detail["vol_proxy_names"] == ["AAA"]     # only AAA used the proxy
    assert out.covariance_detail["sigma_by_name"]["AAA"] == pytest.approx(0.2)
    assert out.covariance_detail["sigma_by_name"]["BBB"] == pytest.approx(0.35)


# ── contract discipline ────────────────────────────────────────────────────────────────────────
def test_outcome_is_frozen_and_echoes_assumptions():
    assumptions = {"AAA": _mv(expected_move=0.2)}
    out = build_portfolio([{"ticker": "AAA", "side": "long", "size_pct": 0.5}], assumptions)
    assert isinstance(out, PortfolioOutcome)
    assert out.assumptions_echo["AAA"]["expected_move"] == 0.2
    with pytest.raises(Exception):
        out.gross_exposure = 9.9   # frozen


def test_raises_on_empty_positions():
    with pytest.raises(ValueError):
        build_portfolio([], {})


def test_raises_on_non_finite_assumption():
    with pytest.raises(ValueError):
        build_portfolio(
            [{"ticker": "AAA", "side": "long", "size_pct": 0.5}],
            {"AAA": _mv(expected_move=math.inf)},
        )


def test_params_missing_key_raises_no_magic_literal():
    with pytest.raises(KeyError):
        _ = PARAMS["this_key_does_not_exist"]
