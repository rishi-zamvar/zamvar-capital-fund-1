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

import pytest

from catalyst_trader.contracts import (
    DebateVerdict,
    DiligenceDossier,
    DiligenceInput,
    EstimateVetting,
    Hedge,
    MDDecision,
    PortfolioContext,
    ReconciliationRound,
    RetriggerFlag,
    StrategyDossier,
    TradeProposal,
    WeeklyFlag,
)
from catalyst_trader.desk import md as md_mod
from catalyst_trader.desk.md import (
    MDReview,
    _gap_only,
    _md_decide_prompt,
    _md_review_prompt,
    cross_check,
    reconcile,
)

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


# ============================================================================
# Plan 04 — reconcile loop + general flag router + escalation (RECON-01..08)
# ============================================================================


def _rf(target="catalyst_call", finding="endpoint powered at 80% not the assumed 90%",
        evidence_ref="kb:ev-1", why_material="lowers P(positive) into a smaller sizing bucket"):
    return RetriggerFlag(target=target, finding=finding, evidence_ref=evidence_ref,
                         why_material=why_material)


def _wf(ticker="ACME", flag_type="quant", finding="short interest doubled week-over-week",
        evidence_ref="tool:si#1", why_material="a crowded exit raises gap risk into the binary"):
    return WeeklyFlag(ticker=ticker, flag_type=flag_type, finding=finding,
                      evidence_ref=evidence_ref, why_material=why_material)


# --- Task 1: gap-not-answer plumbing + MD prompt surfaces + MDReview ---


def test_gap_only_carries_no_answer():
    # The string is a PURE function of RetriggerFlag fields (no answer field exists on the
    # contract) — so a verdict/direction/size cannot leak (RECON-06 firewall in code).
    f = _rf()
    s = _gap_only([f])
    assert s == (
        f"DD/flag surfaced: {f.finding} (evidence_ref {f.evidence_ref}). "
        f"Material because: {f.why_material}"
    )
    assert f.finding in s and f.why_material in s and f.evidence_ref in s


def test_gap_only_filters_by_target():
    flags = [_rf(target="catalyst_call", finding="AAA endpoint"),
             _rf(target="portfolio_build", finding="BBB sizing", evidence_ref="kb:ev-2")]
    s = _gap_only(flags, "catalyst_call")
    assert "AAA endpoint" in s and "BBB sizing" not in s
    s2 = _gap_only(flags, "portfolio_build")
    assert "BBB sizing" in s2 and "AAA endpoint" not in s2


def test_md_review_prompt_includes_packet_sheet_and_incoming_flags():
    verdict, dossier, dd = _verdict(), _dossier(), _dd()
    packet = {"verdict": verdict, "dossier": dossier, "dd": dd}
    sheet = cross_check(verdict, dossier, dd, catalyst_id="cat-1", min_tradeable_size=0.01)
    p = _md_review_prompt(packet, sheet, [_wf()])
    assert verdict.thesis in p                       # packet artifacts referenced
    assert dd.strongest_disconfirming_evidence in p
    assert "short interest doubled" in p             # incoming WeeklyFlag surfaced (RECON-08)
    assert "clean" in p.lower()                      # the cross_check sheet is embedded


def test_md_decide_prompt_includes_rounds():
    packet = {"verdict": _verdict(), "dossier": _dossier(), "dd": _dd()}
    rnd = ReconciliationRound(round=1, response_delta="unmoved + rebuttal",
                              convergence={"cross_check_clean": True}, cross_check={"clean": True},
                              disposition="converged")
    p = _md_decide_prompt(packet, [rnd])
    assert "unmoved + rebuttal" in p


def test_mdreview_model():
    r = MDReview(satisfied=True, response_delta="no material change")
    assert r.flags == [] and r.rerun_diligence is False
    with pytest.raises(Exception):
        MDReview(satisfied=True, response_delta="x", bogus=1)


# --- Task 2: reconcile loop + general flag router + cascade + sizing-gap ---


def _item(incoming_flags=None, p_loss=0.4):
    return {
        "verdict": _verdict(),
        "dossier": _dossier(),
        "dd": _dd(),
        "catalyst": {"catalyst_id": "cat-1", "catalyst_type": "pdufa"},
        "entry": 10.0,
        "risk_inputs": {"p_loss": p_loss, "gap": 0.1, "analog_gaps": [0.1], "prices": [10.0, 9.0]},
        "dd_input": DiligenceInput(ticker="ACME", catalyst={"catalyst_id": "cat-1"}, pair="PEER"),
        "market_data": {"options": {}, "financials": {}},
        "open_book": [],
        "incoming_flags": incoming_flags or [],
    }


def _install(monkeypatch, reviews, decision, calls):
    """Offline seam: route run_structured by schema to the fixtured MDReview sequence / MDDecision,
    and stub run_desk/run_portfolio/run_diligence on desk.md — isolates the loop control."""
    review_iter = iter(reviews)

    async def _rs(prompt, schema, *, model="opus"):
        calls.append(("run_structured", schema))
        if schema is MDReview:
            return next(review_iter)
        if schema is MDDecision:
            return decision
        raise AssertionError(f"unexpected schema {schema!r}")

    async def _rdesk(conn, catalyst, *, extra_context=None):
        calls.append(("run_desk", extra_context))
        return _verdict()

    async def _rport(conn, embed, verdicts, open_book, *, extra_context=None, **kw):
        calls.append(("run_portfolio", extra_context, verdicts))
        return [_dossier()]

    async def _rdil(conn, dd_input, *, market_data, embed=None):
        calls.append(("run_diligence", dd_input, market_data))
        return _dd()

    monkeypatch.setattr(md_mod, "run_structured", _rs)
    monkeypatch.setattr(md_mod, "run_desk", _rdesk)
    monkeypatch.setattr(md_mod, "run_portfolio", _rport)
    monkeypatch.setattr(md_mod, "run_diligence", _rdil)


async def test_reconcile_is_sole_decision_point(db, monkeypatch):
    calls = []
    _install(monkeypatch,
             [MDReview(satisfied=True, response_delta="clean", flags=[])],
             MDDecision(decision="enter", rationale="clean", round_log=[]), calls)
    out = await reconcile(db, None, _item())
    assert isinstance(out, MDDecision)
    assert out.decision == "enter"
    assert len(out.round_log) == 1
    assert out.round_log[0].disposition == "converged"
    assert not any(c[0] in ("run_desk", "run_portfolio", "run_diligence") for c in calls)


async def test_catalyst_flag_retriggers_debate_gap_only(db, monkeypatch):
    calls = []
    _install(monkeypatch, [
        MDReview(satisfied=False, response_delta="gap", flags=[_rf(target="catalyst_call")]),
        MDReview(satisfied=True, response_delta="resolved", flags=[]),
    ], MDDecision(decision="enter", rationale="ok", round_log=[]), calls)
    await reconcile(db, None, _item())
    rd = [c for c in calls if c[0] == "run_desk"]
    assert len(rd) == 1
    # extra_context is EXACTLY the pure gap string — no verdict/direction/size can be in it (RECON-06)
    assert rd[0][1] == _gap_only([_rf(target="catalyst_call")], "catalyst_call")
    assert "endpoint powered at 80%" in rd[0][1]
    # cascade 1 -> 2 -> 3
    assert any(c[0] == "run_portfolio" for c in calls)
    assert any(c[0] == "run_diligence" for c in calls)


async def test_portfolio_flag_retriggers_builder_then_dd(db, monkeypatch):
    calls = []
    _install(monkeypatch, [
        MDReview(satisfied=False, response_delta="gap",
                 flags=[_rf(target="portfolio_build", evidence_ref="kb:ev-p")]),
        MDReview(satisfied=True, response_delta="ok", flags=[]),
    ], MDDecision(decision="enter", rationale="ok", round_log=[]), calls)
    await reconcile(db, None, _item())
    assert not any(c[0] == "run_desk" for c in calls)     # debate NOT re-run
    rp = [c for c in calls if c[0] == "run_portfolio"]
    assert len(rp) == 1 and rp[0][1] is not None          # builder re-run WITH a gap
    assert any(c[0] == "run_diligence" for c in calls)     # then a fresh DD (2 -> 3)


async def test_dd_reruns_firewalled(db, monkeypatch):
    calls = []
    item = _item()
    _install(monkeypatch, [
        MDReview(satisfied=False, response_delta="dd", flags=[], rerun_diligence=True),
        MDReview(satisfied=True, response_delta="ok", flags=[]),
    ], MDDecision(decision="enter", rationale="ok", round_log=[]), calls)
    await reconcile(db, None, item)
    rdd = [c for c in calls if c[0] == "run_diligence"]
    assert len(rdd) == 1
    _, dd_input, market_data = rdd[0]
    assert isinstance(dd_input, DiligenceInput)            # sealed input only — never a verdict/gap
    assert market_data == item["market_data"]
    assert not any(c[0] == "run_desk" for c in calls)


def test_sizing_gap_refreshes_risk_inputs():
    # a sizing-related portfolio flag refreshes risk_inputs (the deterministic size path changes),
    # not just the narrative extra_context.
    flag = RetriggerFlag(
        target="portfolio_build",
        finding="true p_loss is 0.6 given the endpoint miss risk",
        evidence_ref="kb:ev-size",
        why_material="raises risk-of-ruin; the position must be resized smaller",
    )
    wi = md_mod._workitem(_verdict(), _item(p_loss=0.4), [flag])
    assert wi["risk_inputs"]["p_loss"] == 0.6
    # a NON-sizing catalyst flag leaves risk_inputs untouched
    wi2 = md_mod._workitem(_verdict(), _item(p_loss=0.4), [_rf(target="catalyst_call")])
    assert wi2["risk_inputs"]["p_loss"] == 0.4


async def test_loop_caps_at_three(db, monkeypatch):
    calls = []
    reviews = [
        MDReview(satisfied=False, response_delta=f"r{i}", flags=[_rf(evidence_ref=f"kb:ev-{i}")])
        for i in range(3)
    ]
    _install(monkeypatch, reviews,
             MDDecision(decision="pass", rationale="cap", round_log=[]), calls)
    out = await reconcile(db, None, _item(), max_rounds=3)
    assert len(out.round_log) == 3
    assert out.round_log[-1].disposition == "cap_hit"
    assert len([c for c in calls if c[0] == "run_structured" and c[1] is MDReview]) == 3


async def test_oscillation_forces_pass(db, monkeypatch):
    calls = []
    _install(monkeypatch, [
        MDReview(satisfied=False, response_delta="r1", flags=[_rf(evidence_ref="kb:same")]),
        MDReview(satisfied=False, response_delta="r2", flags=[_rf(evidence_ref="kb:same")]),
    ], MDDecision(decision="enter", rationale="model wanted enter", round_log=[]), calls)
    out = await reconcile(db, None, _item())
    assert out.round_log[-1].disposition == "diverged_pass"
    assert out.decision == "pass"                          # forced, overrides the model's "enter"


async def test_every_round_logged(db, monkeypatch):
    calls = []
    _install(monkeypatch, [
        MDReview(satisfied=False, response_delta="gap", flags=[_rf(evidence_ref="kb:ev-a")]),
        MDReview(satisfied=True, response_delta="ok", flags=[]),
    ], MDDecision(decision="enter", rationale="ok", round_log=[]), calls)
    out = await reconcile(db, None, _item())
    assert len(out.round_log) == 2
    for r in out.round_log:
        assert isinstance(r, ReconciliationRound)
        assert r.response_delta
        assert "clean" in r.cross_check
        assert r.convergence
        assert r.disposition in ("continue", "converged", "cap_hit", "diverged_pass")


async def test_general_flag_router_act(db, monkeypatch):
    calls = []
    wf = _wf(evidence_ref="tool:si#1")
    _install(monkeypatch, [
        # the MD ACTS on the incoming weekly flag -> raises a RetriggerFlag sharing its evidence_ref
        MDReview(satisfied=False, response_delta="act",
                 flags=[_rf(target="catalyst_call", evidence_ref="tool:si#1")]),
        MDReview(satisfied=True, response_delta="ok", flags=[]),
    ], MDDecision(decision="enter", rationale="ok", round_log=[]), calls)
    out = await reconcile(db, None, _item(incoming_flags=[wf]))
    assert any(c[0] == "run_desk" for c in calls)          # routed to WF1 via the re-trigger machinery
    assert out.round_log[0].logged_flags == []             # actioned -> NOT logged


async def test_general_flag_router_log_not_forced(db, monkeypatch):
    calls = []
    wf = _wf(evidence_ref="tool:x#9")
    _install(monkeypatch,
             [MDReview(satisfied=True, response_delta="log it", flags=[])],
             MDDecision(decision="enter", rationale="ok", round_log=[]), calls)
    out = await reconcile(db, None, _item(incoming_flags=[wf]))
    assert wf in out.round_log[0].logged_flags             # unactioned -> logged
    assert not any(c[0] in ("run_desk", "run_portfolio", "run_diligence") for c in calls)  # never forced
