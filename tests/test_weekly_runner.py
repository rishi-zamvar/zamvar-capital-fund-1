"""Weekly runner (WEEK-01, WEEK-05) — the thin cadence composition + the LEARN record seam.

Fully offline: run_structured is monkeypatched, run_desk is monkeypatched, and the price bars are
synthetic (no live FMP). The money-critical invariants under test:
  - run_portfolio threads the ~1% target into risk.assess (Plan-02 kwargs) WITHOUT touching the
    catalyst-only default path (byte-for-byte — the test_desk_portfolio run_portfolio suite stays green);
  - the statistical sleeve is capped at statistical_sleeve_cap * weekly_budget in a catalyst week (the
    moat is never crowded out) but NOT starved in a pure-statistical week;
  - the defensive book deploys instead of an empty week (no zero-trade weeks);
  - run_weekly composes scan -> shortlist -> desk -> book with ONE anchor for measurement + execution;
  - per-leg weekly outcomes persist as CITED KB outcome claims (cite-or-drop) for the Phase-10 LEARN loop.
"""

from datetime import date, timedelta

import pytest

from catalyst_trader import kb, store
from catalyst_trader.contracts import (
    DebateVerdict,
    EstimateVetting,
    Hedge,
    PortfolioContext,
    RiskAssessment,
    StrategyDossier,
    TradeProposal,
)
from catalyst_trader.desk import builder, orchestrator, portfolio, risk
from catalyst_trader.desk.portfolio import Candidate, PMDecision, PositionMemo, PreMortem

_KILL = ["a Complete Response Letter is issued", "label carve-out on the lead indication"]


# --- shared builders (mirror test_desk_portfolio) --------------------------------------------


def _hedge():
    return Hedge(instrument="equity_peer", ticker="RIVAL", payoff_direction=-1,
                 validated=True, covers="idiosyncratic", mechanism="same-indication competitor",
                 conditional_worst=-0.35)


def _proposal(hedge=None, size_pct=0.02):
    return TradeProposal(
        target_long="ACME", hedge=hedge, pair_rationale="long ACME, RIVAL inverse hedge",
        entry=100.0, exit_by_date="2026-11-22", stop_loss=45.0, take_profit=120.0,
        size_pct=size_pct, expected_return_pct=0.25, kb_analogs=["n1"],
        holds_through_catalyst=True, catalyst_id="cat-1", direction="positive",
        estimate_vetting=EstimateVetting(verdict="endorse", input_refs=["tool:x#1"], reasons=["ok"]),
        sl_advisory=True,
    )


def _risk(load_fixture, hedge=None):
    base = RiskAssessment.model_validate(load_fixture("agent_responses/risk_synthesis"))
    return base.model_copy(update={"recommended_size_pct": 0.02, "hedge": hedge,
                                   "hedge_valid": hedge is not None and hedge.validated})


def _verdict():
    return DebateVerdict(thesis="ACME PDUFA likely approves", direction="positive", confidence=0.6,
                         bull_strongest_point="endpoint met", bear_strongest_point="cash tight",
                         kill_criteria=_KILL)


def _item(entry=100.0):
    return {
        "verdict": _verdict(),
        "catalyst": {"ticker": "ACME", "event_date": "2026-11-15", "catalyst_id": "cat-1",
                     "event_date_end": "2026-11-22", "catalyst_type": "pdufa"},
        "entry": entry,
        "risk_inputs": {"p_loss": 0.4, "gap": 0.55, "analog_gaps": {}, "prices": {}},
    }


def _pm_seam(calls):
    memo = PositionMemo(memo="LLM memo body")
    pre = PreMortem(scenarios=["it lost because the CRL hit"])
    decision = PMDecision(verdict_summary="promote it", dissent_log=[], all_evidence_refs=[])

    async def _fake(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        calls.append({"prompt": prompt, "schema": schema, "model": model})
        if schema is PositionMemo:
            return memo
        if schema is PreMortem:
            return pre
        if schema is PMDecision:
            return decision
        raise AssertionError(f"unexpected schema {schema!r}")

    return _fake


def _stat_cand(ticker, size=0.02, move=0.03):
    return Candidate(
        size_pct=size, expected_move=move, weight=size,
        payload={"weekly": True, "ticker": ticker, "thesis_type": "mean_reversion",
                 "trigger": "drop_le_-0.05", "p": 0.6, "mean_next": move,
                 "entry": 10.0, "exit_by_date": "2026-11-22"},
    )


def _defensive_cand(ticker, size=0.02):
    return Candidate(
        size_pct=size, expected_move=0.0001, weight=size,
        payload={"defensive": True, "ticker": ticker, "entry": 1.0, "exit_by_date": "2026-11-22"},
    )


def _is_weekly_leg(dossier):
    """A single-leg STATISTICAL weekly leg (not a defensive cash anchor)."""
    cid = dossier.trade.catalyst_id
    return cid.startswith("weekly:") and not cid.startswith("weekly:defensive:")


def _is_defensive(dossier):
    return dossier.trade.catalyst_id.startswith("weekly:defensive:")


# --- Task 1: run_portfolio threading -----------------------------------------------------------


async def test_target_return_threads_expected_move_into_assess(monkeypatch, load_fixture):
    """target_return set -> risk.assess gets target_return AND expected_move=proposal.expected_return_pct."""
    seen = {}
    risk_obj = _risk(load_fixture, _hedge())

    async def _b(conn, embed, verdict, catalyst, *, entry):
        return _proposal(hedge=None, size_pct=0.02)

    async def _a(conn, embed, proposal, catalyst, *, p_loss, gap, analog_gaps, prices,
                 target_return=None, expected_move=None):
        seen["target_return"] = target_return
        seen["expected_move"] = expected_move
        return risk_obj

    monkeypatch.setattr(builder, "build", _b)
    monkeypatch.setattr(risk, "assess", _a)
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))

    await orchestrator.run_portfolio(None, None, [_item()], open_book=[], target_return=0.01)
    assert seen["target_return"] == 0.01
    assert seen["expected_move"] == 0.25   # proposal.expected_return_pct (net EV — DELIBERATE, not up_move)


async def test_defensive_book_deploys_when_nothing_promotes(monkeypatch):
    """No catalyst + defensive_book supplied -> the defensive legs come back as a book, never empty."""
    dossiers = await orchestrator.run_portfolio(
        None, None, [], open_book=[],
        defensive_book=[_defensive_cand("SGOV"), _defensive_cand("BIL")],
    )
    assert dossiers, "a no-signal week must never be empty"
    tickers = {d.trade.target_long for d in dossiers}
    assert tickers == {"SGOV", "BIL"}
    assert all(d.trade.hedge is None and d.which_risk_covered == "none" for d in dossiers)
    assert all(not d.trade.holds_through_catalyst for d in dossiers)  # one-week exit


async def test_extra_statistical_candidates_merged_into_book(monkeypatch, load_fixture):
    risk_obj = _risk(load_fixture, _hedge())

    async def _b(conn, embed, verdict, catalyst, *, entry):
        return _proposal(hedge=None, size_pct=0.02)

    async def _a(conn, embed, proposal, catalyst, *, p_loss, gap, analog_gaps, prices):
        return risk_obj

    monkeypatch.setattr(builder, "build", _b)
    monkeypatch.setattr(risk, "assess", _a)
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))

    dossiers = await orchestrator.run_portfolio(
        None, None, [_item()], open_book=[],
        weekly_budget=0.10, target_weekly=10.0,
        extra_candidates=[_stat_cand("BOUNCE")],
    )
    weekly = [d for d in dossiers if _is_weekly_leg(d)]
    assert weekly and weekly[0].trade.target_long == "BOUNCE"
    assert weekly[0].trade.hedge is None            # single-leg statistical (no hedge)


async def test_statistical_sleeve_capped_in_catalyst_week_but_catalyst_promotes(monkeypatch, load_fixture):
    risk_obj = _risk(load_fixture, _hedge())

    async def _b(conn, embed, verdict, catalyst, *, entry):
        return _proposal(hedge=None, size_pct=0.02)

    async def _a(conn, embed, proposal, catalyst, *, p_loss, gap, analog_gaps, prices):
        return risk_obj

    monkeypatch.setattr(builder, "build", _b)
    monkeypatch.setattr(risk, "assess", _a)
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))

    stat = [_stat_cand(f"S{i}", size=0.02) for i in range(4)]  # 0.08 combined, pre-cap
    dossiers = await orchestrator.run_portfolio(
        None, None, [_item()], open_book=[],
        weekly_budget=0.10, target_weekly=10.0, heat_cap=1e9,
        extra_candidates=stat, statistical_sleeve_cap=0.5,   # cap = 0.05
    )
    weekly = [d for d in dossiers if _is_weekly_leg(d)]
    catalyst = [d for d in dossiers if not _is_weekly_leg(d)]
    assert sum(d.trade.size_pct for d in weekly) <= 0.05 + 1e-9   # sleeve cap holds
    assert any(d.decision == "promote" for d in catalyst)          # catalyst engine not crowded out


async def test_pure_statistical_week_not_starved_by_cap(monkeypatch, load_fixture):
    stat = [_stat_cand(f"S{i}", size=0.02) for i in range(4)]  # 0.08 combined
    dossiers = await orchestrator.run_portfolio(
        None, None, [], open_book=[],   # NO catalyst candidates
        weekly_budget=0.10, target_weekly=10.0, heat_cap=1e9,
        extra_candidates=stat, statistical_sleeve_cap=0.5,   # cap must NOT apply (pure-statistical)
    )
    weekly = [d for d in dossiers if _is_weekly_leg(d)]
    assert sum(d.trade.size_pct for d in weekly) > 0.05   # cap NOT applied -> the book fills past 0.05


# --- Task 2: run_weekly composition + build_defensive_book -------------------------------------

from types import SimpleNamespace

from catalyst_trader.desk import weekly
from catalyst_trader.desk.weekly import build_defensive_book, run_weekly


def _syn_bars(returns, *, start=1000.0, vol=2_000_000.0, first="2020-01-06"):
    d = date.fromisoformat(first)
    out = [{"week_end": d.isoformat(), "close": start, "volume": vol}]
    close = start
    for r in returns:
        close *= 1.0 + r
        d += timedelta(days=7)
        out.append({"week_end": d.isoformat(), "close": close, "volume": vol})
    return out


def _osc(n, amp=0.02):
    return [amp if i % 2 == 0 else -amp for i in range(n)]


def _rep(seq, times):
    return seq * times


def _seed_universe(db, tickers, as_of):
    for tk in tickers:
        db.execute(
            "INSERT INTO universe_snapshot "
            "(as_of_date,ticker,included,delisted,criteria_json,reason,recorded_at) "
            "VALUES (?,?,?,?,?,?,?)",
            # recorded_at = as_of (contemporaneous cohort) so the serving gateway (07.6) serves it;
            # a raw INSERT that omits the transaction stamp is denied deny-by-default.
            (as_of, tk, 1, 0, "{}", None, as_of),
        )
    db.commit()


def _params(db, **overrides):
    p = kb.load_params(db, "weekly")
    for k, v in overrides.items():
        p["weekly"][k] = v
    return p


async def test_run_weekly_end_to_end_offline_produces_book(db):
    """scan -> shortlist -> (statistical) book, fully offline on synthetic bars. No catalyst, no LLM."""
    elig = _rep([0.03, -0.06], 60)
    store.upsert_bars(db, "XBI", _syn_bars(_osc(120)))
    store.upsert_bars(db, "ELIG", _syn_bars(elig))
    as_of = _syn_bars(elig)[-1]["week_end"]
    _seed_universe(db, ["ELIG"], as_of)

    dossiers = await run_weekly(db, None, as_of, open_book=[], params=_params(db))
    assert dossiers, "every week produces a book"
    weekly_legs = [d for d in dossiers if _is_weekly_leg(d)]
    assert any(d.trade.target_long == "ELIG" for d in weekly_legs)
    assert all(d.trade.hedge is None for d in weekly_legs)             # single-leg statistical


async def test_run_weekly_defensive_week_never_empty(db):
    """No eligible statistical row + no catalyst -> the DEFENSIVE book (SGOV/BIL/XBI), never empty."""
    store.upsert_bars(db, "XBI", _syn_bars(_osc(120)))
    store.upsert_bars(db, "FLAT", _syn_bars(_osc(120, amp=0.01)))   # never triggers a cell
    as_of = _syn_bars(_osc(120, amp=0.01))[-1]["week_end"]
    _seed_universe(db, ["FLAT"], as_of)

    dossiers = await run_weekly(db, None, as_of, open_book=[], params=_params(db))
    assert dossiers, "a no-signal week must never be empty"
    tickers = {d.trade.target_long for d in dossiers}
    assert tickers == {"SGOV", "BIL", "XBI"}                          # the defensive book deployed
    assert all(not d.trade.holds_through_catalyst for d in dossiers)  # one-week exit


async def test_run_weekly_shortlist_capped_at_k(db, monkeypatch):
    """The shortlist keeps only the top `shortlist_k` eligible rows (a stubbed scan isolates the cap
    from the base-rate cohort math). 3 eligible rows, k=2 -> at most 2 statistical legs."""
    names = ["E1", "E2", "E3"]
    store.upsert_bars(db, "XBI", _syn_bars(_osc(160)))
    for tk in names:
        store.upsert_bars(db, tk, _syn_bars(_osc(160)))
    as_of = _syn_bars(_osc(160))[-1]["week_end"]
    _seed_universe(db, names, as_of)

    from types import SimpleNamespace

    def _stub_scan(universe, week_end, store_, kb_conn, *, params):
        rows = [{"ticker": tk, "thesis_type": "mean_reversion", "trigger": "drop_le_-0.05",
                 "p": 0.6 + i * 0.1, "mean_next": 0.03, "n_effective": 40, "eligible": True,
                 "veto_reasons": []} for i, tk in enumerate(names)]
        return SimpleNamespace(detail={"rows": rows})

    monkeypatch.setattr(weekly, "thesis_scan", _stub_scan)
    dossiers = await run_weekly(db, None, as_of, open_book=[], params=_params(db, shortlist_k=2))
    weekly_legs = {d.trade.target_long for d in dossiers if _is_weekly_leg(d)}
    assert len(weekly_legs) <= 2                                      # shortlist_k caps the sleeve
    assert weekly_legs <= {"E1", "E2", "E3"}


async def test_run_weekly_statistical_legs_single_leg_and_one_week_exit(db):
    elig = _rep([0.03, -0.06], 60)
    store.upsert_bars(db, "XBI", _syn_bars(_osc(120)))
    store.upsert_bars(db, "ELIG", _syn_bars(elig))
    as_of = _syn_bars(elig)[-1]["week_end"]
    _seed_universe(db, ["ELIG"], as_of)

    dossiers = await run_weekly(db, None, as_of, open_book=[], params=_params(db))
    leg = [d for d in dossiers if d.trade.target_long == "ELIG"][0]
    assert leg.trade.hedge is None and leg.which_risk_covered == "none"   # single-leg fallback
    assert leg.trade.holds_through_catalyst is False                      # ALWAYS exits at horizon
    expected_exit = (date.fromisoformat(as_of) + timedelta(days=7)).isoformat()
    assert leg.trade.exit_by_date == expected_exit                        # one-week horizon


async def test_run_weekly_one_anchor_for_measurement_and_execution(db, monkeypatch):
    """The MEASUREMENT anchor (thesis_scan) equals the EXECUTION anchor (enter/exit) — one param, no trap."""
    seen = {}

    def _spy_scan(universe, week_end, store_, kb_conn, *, params):
        seen["scan_anchor"] = params["weekly"]["anchor"]
        return SimpleNamespace(detail={"rows": []})

    def _spy_exit(as_of, anchor):
        seen["exit_anchor"] = anchor
        return (date.fromisoformat(as_of) + timedelta(days=7)).isoformat()

    monkeypatch.setattr(weekly, "thesis_scan", _spy_scan)
    monkeypatch.setattr(weekly, "_weekly_exit", _spy_exit)

    _seed_universe(db, ["ANY"], "2020-01-06")
    await run_weekly(db, None, "2020-01-06", open_book=[], params=_params(db, anchor="FRI_CLOSE"))
    assert seen["scan_anchor"] == "FRI_CLOSE"
    assert seen["exit_anchor"] == "FRI_CLOSE"                          # the SAME single anchor drives both


def test_build_defensive_book_from_params(db):
    book = build_defensive_book(_params(db))
    assert [c.payload["ticker"] for c in book] == ["SGOV", "BIL", "XBI"]
    assert all(c.payload.get("defensive") for c in book)
    assert all(c.size_pct > 0 for c in book)


# --- Task 3: WEEK-05 per-leg outcome record seam ----------------------------------------------

import json

from catalyst_trader.desk import evidence
from catalyst_trader.desk.evidence import tool_ref_for
from catalyst_trader.desk.weekly import record_weekly_outcome


def _leg(realized_ret=0.04):
    return {
        "ticker": "ELIG", "thesis_type": "mean_reversion", "trigger": "drop_le_-0.05",
        "p_quoted": 0.62, "size": 0.03, "realized_ret": realized_ret,
        "base_rate_inputs": {"ticker": "ELIG", "trigger": "drop_le_-0.05",
                             "drop_class": "idio_no_news", "turnover": "low",
                             "as_of": "2099-01-01", "params": {"weekly": {}}, "window_years": None},
    }


def _outcome_node(db):
    row = db.execute(
        "SELECT id, attrs_json FROM kb_node WHERE kind='outcome' "
        "AND json_extract(attrs_json,'$.kind')='weekly_leg' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def test_records_leg_outcomes(db):
    """WEEK-05: one KB outcome claim per leg carrying {thesis_type, trigger, p_quoted, size, realized_ret, win}."""
    nid = record_weekly_outcome(db, _leg(realized_ret=0.04))
    attrs = json.loads(db.execute("SELECT attrs_json FROM kb_node WHERE id=?", (nid,)).fetchone()[0])
    assert attrs["thesis_type"] == "mean_reversion"
    assert attrs["trigger"] == "drop_le_-0.05"
    assert attrs["p_quoted"] == 0.62
    assert attrs["size"] == 0.03
    assert attrs["realized_ret"] == 0.04
    assert attrs["win"] is True                                    # realized_ret > 0
    loss = json.loads(db.execute(
        "SELECT attrs_json FROM kb_node WHERE id=?",
        (record_weekly_outcome(db, _leg(realized_ret=-0.02)),)).fetchone()[0])
    assert loss["win"] is False


def test_weekly_outcome_is_cited_by_construction(db):
    """cite-or-drop: the claim CITES the weekly_base_rate ToolResult via a resolvable tool: ref."""
    leg = _leg()
    nid = record_weekly_outcome(db, leg)
    ev_id = db.execute(
        "SELECT dst_id FROM kb_edge WHERE src_id=? AND rel='CITES'", (nid,)
    ).fetchone()[0]
    ev_attrs = json.loads(db.execute("SELECT attrs_json FROM kb_node WHERE id=?", (ev_id,)).fetchone()[0])
    expected_ref = tool_ref_for("weekly_base_rate", leg["base_rate_inputs"])
    assert ev_attrs["url"] == expected_ref
    assert expected_ref.startswith("tool:weekly_base_rate#")
    resolved = evidence.resolve(db, ev_attrs["url"])               # resolved-by-construction
    assert resolved == {"kind": "tool", "tool": "weekly_base_rate",
                        "inputs_hash": expected_ref.split("#", 1)[1]}


def test_recording_is_uncited_safe_and_idempotent(db):
    """An uncited weekly outcome can never persist; recording never corrupts other outcome rows."""
    # a pre-existing (catalyst) outcome row must be untouched by weekly recording.
    catalyst_ev = kb.EvidenceSource(url="https://x", retrieved_at="t", snippet_hash="h")
    cat_id = kb.insert_claim(db, kb.KBNode(kind="outcome", attrs={"kind": "catalyst", "r": "win"}),
                             [catalyst_ev])
    before = db.execute("SELECT attrs_json FROM kb_node WHERE id=?", (cat_id,)).fetchone()[0]

    record_weekly_outcome(db, _leg())
    record_weekly_outcome(db, _leg())                              # twice — no raise, no corruption

    after = db.execute("SELECT attrs_json FROM kb_node WHERE id=?", (cat_id,)).fetchone()[0]
    assert after == before                                         # catalyst outcome row untouched
    n_weekly = db.execute(
        "SELECT count(*) FROM kb_node WHERE kind='outcome' AND json_extract(attrs_json,'$.kind')='weekly_leg'"
    ).fetchone()[0]
    assert n_weekly == 2
