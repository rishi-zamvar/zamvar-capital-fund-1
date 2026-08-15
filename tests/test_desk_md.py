"""cross_check — the MD/GP deterministic consistency sheet (RECON-01/04).

cross_check is a PURE diff across the three workflow artifacts (catalyst verdict /
portfolio dossier / diligence dossier) plus two threaded values (the authoritative
catalyst_id — DebateVerdict carries none — and the builder's min_tradeable_size floor).
No LLM, no conn/kb: it pre-computes every inter-workflow inconsistency so the MD only
interprets flags and Plan 04's convergence loop gets a deterministic `clean` boolean.

Each inconsistency is exercised in ISOLATION off a mutually-consistent baseline (money-
critical, OPS-04 exhaustive edges): flip exactly one thing, assert exactly that flag fires
and `clean is False`; the all-consistent baseline is `clean is True`.
"""

from catalyst_trader.contracts import (
    DebateVerdict,
    DiligenceDossier,
    EstimateVetting,
    Hedge,
    PortfolioContext,
    StrategyDossier,
    TradeProposal,
)
from catalyst_trader.desk.md import cross_check

_UNSET = object()


# --- baseline builders: everything mutually consistent unless an override flips it ---


def _verdict(direction="positive"):
    return DebateVerdict(
        thesis="endpoint likely met",
        direction=direction,
        confidence=0.6,
        bull_strongest_point="strong phase-2 read",
        bear_strongest_point="regulatory precedent thin",
        kill_criteria=["trade fails if the primary endpoint is missed"],
    )


def _hedge(covers="idiosyncratic", validated=True, payoff_direction=-1,
           mechanism="peer rises when the target's drug fails (same indication)"):
    return Hedge(
        instrument="equity_peer",
        ticker="PEER",
        payoff_direction=payoff_direction,
        validated=validated,
        covers=covers,
        mechanism=mechanism,
        conditional_worst=-0.02,
    )


def _trade(catalyst_id="cat-1", direction="positive", size_pct=0.05,
           holds_through_catalyst=True, hedge=_UNSET):
    if hedge is _UNSET:
        hedge = _hedge()
    return TradeProposal(
        target_long="ACME",
        hedge=hedge,
        pair_rationale="inverse peer on the same indication",
        entry=10.0,
        exit_by_date="2026-12-05",
        stop_loss=9.0,
        take_profit=12.0,
        size_pct=size_pct,
        expected_return_pct=0.01,
        holds_through_catalyst=holds_through_catalyst,
        catalyst_id=catalyst_id,
        direction=direction,
        estimate_vetting=EstimateVetting(
            verdict="endorse", input_refs=["tool:x#1"], reasons=["ok"]
        ),
        sl_advisory=True,
    )


def _dossier(decision="promote", trade=_UNSET, which_risk_covered="idiosyncratic",
             kill_criteria=_UNSET, dissent_log=_UNSET):
    if trade is _UNSET:
        trade = _trade()
    if kill_criteria is _UNSET:
        kill_criteria = ["trade fails if the primary endpoint is missed"]
    if dissent_log is _UNSET:
        dissent_log = []
    return StrategyDossier(
        decision=decision,
        trade=trade,
        portfolio_context=PortfolioContext(
            concentration=0.2, corr_to_open_positions=[0.1], weekly_budget_remaining=0.5
        ),
        verdict_summary="promote on strong read",
        dissent_log=dissent_log,
        all_evidence_refs=[],
        residual_net_long=0.0,
        which_risk_covered=which_risk_covered,
        position_memo="memo",
        pre_mortem=["assume it lost — endpoint missed"],
        kill_criteria=kill_criteria,
    )


def _dd(verdict="go", catalyst_id="cat-1", red_flags=_UNSET, residual_risks=_UNSET):
    if red_flags is _UNSET:
        red_flags = []
    if residual_risks is _UNSET:
        residual_risks = []
    return DiligenceDossier(
        verdict=verdict,
        per_dimension=[
            {"dimension": "clinical", "catalyst_id": catalyst_id},
            {"dimension": "regulatory", "catalyst_id": catalyst_id},
        ],
        red_flags=red_flags,
        strongest_disconfirming_evidence="thin regulatory precedent",
        all_evidence_refs=[],
        residual_risks=residual_risks,
    )


# --- Task 1: id / direction / DD-vs-portfolio consistency ---


def test_cross_check_clean():
    out = cross_check(
        _verdict(), _dossier(), _dd(),
        catalyst_id="cat-1", min_tradeable_size=0.01,
    )
    assert out["clean"] is True
    assert out["catalyst_id_consistent"] is True
    assert out["direction_consistent"] is True
    assert out["dd_vs_portfolio"] is False


def test_cross_check_catalyst_id_mismatch():
    # verdict has NO catalyst id to read — the threaded arg is authoritative. Trade + DD say
    # "cat-1" while the authoritative id is "cat-2": the §4.1 escalation-worthy factual conflict.
    out = cross_check(
        _verdict(), _dossier(), _dd(),
        catalyst_id="cat-2", min_tradeable_size=0.01,
    )
    assert out["catalyst_id_consistent"] is False
    assert out["clean"] is False
    assert out["catalyst_ids"]["threaded"] == "cat-2"
    assert out["catalyst_ids"]["trade"] == "cat-1"
    assert "cat-1" in out["catalyst_ids"]["diligence"]


def test_cross_check_dd_vs_portfolio():
    out = cross_check(
        _verdict(), _dossier(decision="promote"), _dd(verdict="no_go"),
        catalyst_id="cat-1", min_tradeable_size=0.01,
    )
    assert out["dd_vs_portfolio"] is True
    assert out["clean"] is False


def test_cross_check_direction_drift():
    out = cross_check(
        _verdict(direction="positive"),
        _dossier(trade=_trade(direction="negative")),
        _dd(),
        catalyst_id="cat-1", min_tradeable_size=0.01,
    )
    assert out["direction_consistent"] is False
    assert out["clean"] is False


# --- Task 2: uncovered red_flags / residual gaps / net-long-held-through ---


def test_cross_check_uncovered_red_flags():
    # one red_flag IS answered by a kill criterion (drops out); one is NOT covered anywhere.
    dd = _dd(red_flags=["primary endpoint is missed", "insider selling spike last quarter"])
    out = cross_check(
        _verdict(), _dossier(), dd,
        catalyst_id="cat-1", min_tradeable_size=0.01,
    )
    assert out["uncovered_red_flags"] == ["insider selling spike last quarter"]
    assert out["clean"] is False


def test_cross_check_dd_residual_gap():
    # one residual IS in the dossier's residual surface (dissent_log); one is absent -> the gap.
    dd = _dd(residual_risks=["FX exposure on EU sales", "second-source supply chain risk"])
    dossier = _dossier(dissent_log=["priced residual: FX exposure on EU sales carried in the memo"])
    out = cross_check(
        _verdict(), dossier, dd,
        catalyst_id="cat-1", min_tradeable_size=0.01,
    )
    assert out["dd_vs_risk_residuals"] == ["second-source supply chain risk"]
    assert out["clean"] is False


def test_cross_check_net_long_held_through():
    # net-long uncovered exposure held THROUGH the binary: which_risk_covered=="none"
    # AND size_pct > the threaded floor AND holds_through_catalyst.
    trade = _trade(hedge=None, holds_through_catalyst=True, size_pct=0.05)
    dossier = _dossier(trade=trade, which_risk_covered="none")
    out = cross_check(
        _verdict(), dossier, _dd(),
        catalyst_id="cat-1", min_tradeable_size=0.01,
    )
    assert out["sizing_vs_survival"] is True
    assert out["clean"] is False

    # below the floor -> not flagged (the floor is a real threshold, not a magic number).
    tiny = _dossier(trade=_trade(hedge=None, holds_through_catalyst=True, size_pct=0.005),
                    which_risk_covered="none")
    out2 = cross_check(
        _verdict(), tiny, _dd(),
        catalyst_id="cat-1", min_tradeable_size=0.01,
    )
    assert out2["sizing_vs_survival"] is False


def test_cross_check_all_clean_still_clean():
    out = cross_check(
        _verdict(), _dossier(), _dd(),
        catalyst_id="cat-1", min_tradeable_size=0.01,
    )
    assert out["catalyst_id_consistent"] is True
    assert out["direction_consistent"] is True
    assert out["dd_vs_portfolio"] is False
    assert out["uncovered_red_flags"] == []
    assert out["dd_vs_risk_residuals"] == []
    assert out["sizing_vs_survival"] is False
    assert out["clean"] is True
