"""Phase 8 (EXEC-01/EXEC-02/LEARN-03): fill-gap closure, per-trade attribution + post-mortem, and
the sample-based go-live gate. Money-critical, all offline (:memory: + seeded bars, hash embedder).

  - attribute_trade (PURE): catalyst + beta + costs + sizing + hedge reconcile EXACTLY to the book
    contribution (quant.performance.attribution guards it); good-decision/bad-luck quadrant.
  - _open_paper_position rejects a non-positive / non-finite entry and an out-of-range size (the
    backtest refuses entry<=0 too) — the gate can never open an unpriceable position.
  - postmortem_closed: idempotent, self-healing, hedge leg filled byte-identically to the backtest
    (engine._fill_leg), beta vs XBI over the same window, cited KB write + analog prior update that
    analog_query actually returns (gated by knowable_asof), empty evidence never fabricates a cite.
  - go_live_gate: SAMPLE-based (catalyst N + PSR significance), no calendar term, never opens.
"""

import json
import math
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from catalyst_trader import db as _db
from catalyst_trader import kb
from catalyst_trader import paper_ledger as pl
from catalyst_trader.backtest.engine import _fill_leg, _net_return
from catalyst_trader.store import upsert_bars


def _conn():
    conn = _db.connect(":memory:")
    _db.migrate(conn)
    return conn


def _bar(week_end, o, c, *, vol=5000):
    return {"week_end": week_end, "open": o, "high": max(o, c) * 1.02, "low": min(o, c) * 0.98,
            "close": c, "volume": vol}


def _result(*, ticker="ABCD", entry=10.0, size=0.02, exit_by="2026-08-21", refs=("kb:42",),
            hedge=None, ctype="pdufa", cid="7"):
    trade = SimpleNamespace(
        target_long=ticker, entry=entry, size_pct=size, exit_by_date=exit_by,
        holds_through_catalyst=True, catalyst_id=cid, direction="positive",
        hedge=(SimpleNamespace(ticker=hedge) if hedge else None),
    )
    dossier = SimpleNamespace(trade=trade, all_evidence_refs=list(refs))
    return {"decision": SimpleNamespace(decision="enter"), "dossier": dossier,
            "catalyst": {"catalyst_type": ctype, "event_date": "2026-08-17"}}


def _open(conn, as_of="2026-08-14", **kw):
    params = pl.position_params_from_decision(_result(**kw), as_of=as_of)
    return pl.approve_pending(conn, pl.submit_for_approval(conn, params))


def _seed_history(conn, ticker, *, start="2025-08-15", weeks=52, drift=0.0, beta=1.0, seed=1):
    """Deterministic weekly closes for `ticker` and XBI up to the decision week 2026-08-14."""
    import random
    rnd = random.Random(seed)
    d0 = date.fromisoformat(start)
    px_t, px_x = 10.0, 100.0
    tb, xb = [], []
    for i in range(weeks + 1):
        we = (d0 + timedelta(weeks=i)).isoformat()
        rx = rnd.gauss(0, 0.03)
        rt = beta * rx + rnd.gauss(0, 0.01) + drift
        px_x *= 1 + rx
        px_t *= 1 + rt
        xb.append(_bar(we, px_x, px_x))
        tb.append(_bar(we, px_t, px_t))
    upsert_bars(conn, "XBI", xb)
    upsert_bars(conn, ticker, tb)
    return tb[-1]["close"], xb[-1]["close"]


# =============================================================== attribute_trade (pure)

_BASE = dict(size=0.02, ref_size=0.02, entry=10.0, close=12.0, beta=1.0, r_xbi=0.05,
             hedge_ret=None)


def _rr(entry, close):
    return _net_return(entry, close, apply_costs=True)


def test_components_reconcile_to_book_contribution():
    a = pl.attribute_trade(**_BASE, realized_ret=_rr(10.0, 12.0))
    c = a["components"]
    assert set(c) == {"catalyst_effect", "beta_drift", "hedge_leg", "sizing", "costs"}
    assert math.isclose(sum(c.values()), 0.02 * _rr(10.0, 12.0), rel_tol=1e-12)
    assert math.isclose(a["total"], 0.02 * _rr(10.0, 12.0), rel_tol=1e-12)
    # gross 20%, beta 1 * xbi 5% -> idio 15% of a 2% book slice
    assert math.isclose(c["beta_drift"], 0.02 * 0.05)
    assert math.isclose(c["catalyst_effect"], 0.02 * 0.15)
    assert c["costs"] < 0 and c["sizing"] == 0.0 and c["hedge_leg"] == 0.0


def test_sizing_component_is_oversize_times_net_return():
    r = _rr(10.0, 8.0)
    a = pl.attribute_trade(**{**_BASE, "close": 8.0, "size": 0.04}, realized_ret=r)
    assert math.isclose(a["components"]["sizing"], (0.04 - 0.02) * r)
    assert math.isclose(a["total"], 0.04 * r)


def test_beta_unavailable_puts_whole_gross_move_in_catalyst_and_flags_it():
    r = _rr(10.0, 12.0)
    a = pl.attribute_trade(**{**_BASE, "beta": None}, realized_ret=r)
    assert a["components"]["beta_drift"] == 0.0
    assert math.isclose(a["components"]["catalyst_effect"], 0.02 * 0.2)
    assert a["beta_available"] is False
    a2 = pl.attribute_trade(**{**_BASE, "r_xbi": None}, realized_ret=r)
    assert a2["beta_available"] is False and a2["components"]["beta_drift"] == 0.0


def test_hedge_leg_carries_no_size_this_phase_but_reports_its_return():
    a = pl.attribute_trade(**{**_BASE, "hedge_ret": -0.07}, realized_ret=_rr(10.0, 12.0))
    assert a["components"]["hedge_leg"] == 0.0   # peer carries no size (PortfolioContext)
    assert a["hedge_ret"] == -0.07


@pytest.mark.parametrize("close,beta,r_xbi,verdict", [
    (12.0, 0.0, 0.0, "good_decision_good_outcome"),   # idio up, won
    (10.5, 1.0, 0.20, "bad_decision_good_luck"),      # won only on sector beta, idio negative
    (9.0, 1.0, -0.25, "good_decision_bad_luck"),      # idio positive, lost to the sector tape
    (7.0, 0.0, 0.0, "bad_decision_bad_outcome"),      # thesis wrong, lost
])
def test_post_mortem_quadrant(close, beta, r_xbi, verdict):
    a = pl.attribute_trade(**{**_BASE, "close": close, "beta": beta, "r_xbi": r_xbi},
                           realized_ret=_rr(10.0, close))
    assert a["verdict"] == verdict


def test_flat_trade_is_neither_win_nor_thesis_right():
    a = pl.attribute_trade(**{**_BASE, "close": 10.0, "beta": 0.0, "r_xbi": 0.0},
                           realized_ret=0.0)
    assert a["verdict"] == "bad_decision_bad_outcome"


@pytest.mark.parametrize("bad", [
    {"entry": 0.0}, {"entry": -1.0}, {"entry": float("nan")}, {"close": float("inf")},
    {"size": float("nan")}, {"beta": float("nan")}, {"r_xbi": float("inf")},
])
def test_non_finite_or_unpriceable_inputs_raise(bad):
    with pytest.raises(ValueError):
        pl.attribute_trade(**{**_BASE, **bad}, realized_ret=0.01)


def test_realized_ret_nan_raises():
    with pytest.raises(ValueError):
        pl.attribute_trade(**_BASE, realized_ret=float("nan"))


# =============================================================== open-time guard (fill gap)


@pytest.mark.parametrize("entry,size", [(0.0, 0.02), (-5.0, 0.02), (float("nan"), 0.02),
                                        (10.0, 0.0), (10.0, -0.01), (10.0, 1.5),
                                        (10.0, float("nan"))])
def test_gate_refuses_to_open_unpriceable_or_oversized_position(entry, size):
    conn = _conn()
    params = pl.position_params_from_decision(_result(entry=entry, size=size), as_of="2026-08-14")
    pid = pl.submit_for_approval(conn, params)
    with pytest.raises(ValueError):
        pl.approve_pending(conn, pid)
    assert conn.execute("SELECT COUNT(*) c FROM paper_position").fetchone()["c"] == 0
    assert conn.execute("SELECT status FROM paper_pending WHERE id=?", (pid,)).fetchone()[0] == "pending"


def test_params_carry_catalyst_type_event_date_and_hedge_ticker():
    p = pl.position_params_from_decision(_result(hedge="PEER"), as_of="2026-08-14")
    assert p["catalyst_type"] == "pdufa" and p["event_date"] == "2026-08-17"
    assert p["hedge_ticker"] == "PEER"
    p2 = pl.position_params_from_decision(_result(), as_of="2026-08-14")
    assert p2["hedge_ticker"] is None


def test_params_tolerate_result_without_catalyst_dict():
    r = _result()
    del r["catalyst"]
    p = pl.position_params_from_decision(r, as_of="2026-08-14")
    assert p["catalyst_type"] is None and p["event_date"] is None


# =============================================================== postmortem_closed (close path)


def _close_one(conn, *, exit_open=12.0, hedge=None, refs=("kb:42",), size=0.02, ticker="ABCD",
               seed=1):
    entry_t, _ = _seed_history(conn, ticker, seed=seed)
    upsert_bars(conn, ticker, [_bar("2026-08-21", exit_open, exit_open)])
    upsert_bars(conn, "XBI", [_bar("2026-08-21", 103.0, 103.0)])
    if hedge:
        upsert_bars(conn, hedge, [_bar("2026-08-14", 20.0, 20.0), _bar("2026-08-21", 19.0, 19.0)])
    pos_id = _open(conn, ticker=ticker, entry=entry_t, hedge=hedge, refs=refs, size=size)
    assert pl.mark_open_positions(conn, "2026-08-28")["closed"] == 1
    return pos_id, entry_t


def test_postmortem_attributes_closed_trade_and_reconciles():
    conn = _conn()
    pos_id, entry = _close_one(conn)
    out = pl.postmortem_closed(conn, embed=kb.hash_embed)
    assert out["attributed"] == 1
    row = conn.execute("SELECT * FROM paper_position WHERE id=?", (pos_id,)).fetchone()
    att = json.loads(row["attribution"])
    assert math.isclose(sum(att["components"].values()), row["size_pct"] * row["realized_ret"],
                        rel_tol=1e-9, abs_tol=1e-12)
    assert att["beta_available"] is True
    # XBI window return is the backtest-identical gross fill over the SAME entry/exit bars
    xbi = _fill_leg(conn, "XBI", "2026-08-14", "2026-08-21", held_through=True, slippage=0.0,
                    apply_costs=False)
    assert att["r_xbi"] == xbi[2]


def test_postmortem_is_idempotent():
    conn = _conn()
    _close_one(conn)
    assert pl.postmortem_closed(conn, embed=kb.hash_embed)["attributed"] == 1
    n_nodes = conn.execute("SELECT COUNT(*) c FROM kb_node").fetchone()["c"]
    assert pl.postmortem_closed(conn, embed=kb.hash_embed)["attributed"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM kb_node").fetchone()["c"] == n_nodes


def test_postmortem_ignores_open_positions():
    conn = _conn()
    _seed_history(conn, "ABCD")
    _open(conn, exit_by="2026-09-04")
    assert pl.postmortem_closed(conn, embed=kb.hash_embed)["attributed"] == 0


def test_hedge_leg_filled_byte_identical_to_backtest():
    conn = _conn()
    pos_id, _ = _close_one(conn, hedge="PEER")
    pl.postmortem_closed(conn, embed=kb.hash_embed)
    row = conn.execute("SELECT hedge_ret FROM paper_position WHERE id=?", (pos_id,)).fetchone()
    expect = _fill_leg(conn, "PEER", "2026-08-14", "2026-08-21", held_through=True, slippage=0.0)
    assert row["hedge_ret"] == expect[2] < 0


def test_hedge_without_bars_is_none_not_fabricated():
    conn = _conn()
    entry_t, _ = _seed_history(conn, "ABCD")
    upsert_bars(conn, "ABCD", [_bar("2026-08-21", 12.0, 12.0)])
    pos_id = _open(conn, entry=entry_t, hedge="GHOST")
    pl.mark_open_positions(conn, "2026-08-28")
    pl.postmortem_closed(conn, embed=kb.hash_embed)
    row = conn.execute("SELECT hedge_ret, attribution FROM paper_position WHERE id=?",
                       (pos_id,)).fetchone()
    assert row["hedge_ret"] is None and json.loads(row["attribution"])["hedge_ret"] is None


def test_no_xbi_history_degrades_beta_but_still_attributes():
    conn = _conn()
    upsert_bars(conn, "ABCD", [_bar("2026-08-14", 10.0, 10.0), _bar("2026-08-21", 12.0, 12.0)])
    pos_id = _open(conn, entry=10.0)
    pl.mark_open_positions(conn, "2026-08-28")
    assert pl.postmortem_closed(conn, embed=kb.hash_embed)["attributed"] == 1
    att = json.loads(conn.execute("SELECT attribution FROM paper_position WHERE id=?",
                                  (pos_id,)).fetchone()[0])
    assert att["beta_available"] is False and att["components"]["beta_drift"] == 0.0


def test_sizing_reference_is_mean_size_of_trades_closed_so_far():
    conn = _conn()
    _close_one(conn, size=0.02, ticker="AAA", seed=1)
    _close_one(conn, size=0.04, ticker="BBB", seed=2)
    pl.postmortem_closed(conn, embed=kb.hash_embed)
    rows = conn.execute("SELECT size_pct, realized_ret, attribution FROM paper_position "
                        "ORDER BY id").fetchall()
    first, second = (json.loads(r["attribution"]) for r in rows)
    assert first["ref_size"] == 0.02 and first["components"]["sizing"] == 0.0
    assert math.isclose(second["ref_size"], 0.03)
    assert math.isclose(second["components"]["sizing"], 0.01 * rows[1]["realized_ret"])


def test_postmortem_writes_cited_outcome_and_analog_prior_visible_to_analog_query():
    conn = _conn()
    _close_one(conn, refs=("tool:weekly_base_rate#abc", "kb:9"))
    out = pl.postmortem_closed(conn, embed=kb.hash_embed)
    assert out["kb_written"] == 1 and out["prior_updated"] == 1
    node_id = conn.execute("SELECT postmortem_node_id FROM paper_position").fetchone()[0]
    node = kb.get_node(conn, node_id)
    assert node["kind"] == "outcome" and node["attrs"]["kind"] == "paper_postmortem"
    assert node["attrs"]["verdict"] in pl.VERDICTS
    # cited — every decision ref, never a fabricated one
    cites = conn.execute("SELECT COUNT(*) c FROM kb_edge WHERE src_id=? AND rel='CITES'",
                         (node_id,)).fetchone()["c"]
    assert cites == 2
    # the analog prior: the next catalyst of the same type sees the realized SIGNED move...
    hits = kb.analog_query(conn, kb.hash_embed, "ABCD pdufa", {"type": "pdufa"}, as_of="2026-09-01")
    assert len(hits) == 1 and hits[0]["outcome"]["move"] == node["attrs"]["move"]
    # ...but never before it was knowable (no look-ahead)
    assert kb.analog_query(conn, kb.hash_embed, "ABCD pdufa", {"type": "pdufa"},
                           as_of="2026-08-20") == []


def test_postmortem_empty_evidence_attributes_but_never_writes_kb():
    conn = _conn()
    _close_one(conn, refs=())
    n_before = conn.execute("SELECT COUNT(*) c FROM kb_node").fetchone()["c"]
    out = pl.postmortem_closed(conn, embed=kb.hash_embed)
    assert out == {"attributed": 1, "kb_written": 0, "prior_updated": 0, "failed": 0}
    assert conn.execute("SELECT COUNT(*) c FROM kb_node").fetchone()["c"] == n_before
    row = conn.execute("SELECT attribution, postmortem_node_id FROM paper_position").fetchone()
    assert row["attribution"] is not None and row["postmortem_node_id"] is None


def test_postmortem_without_embed_writes_outcome_but_skips_prior():
    conn = _conn()
    _close_one(conn)
    out = pl.postmortem_closed(conn, embed=None)
    assert out["kb_written"] == 1 and out["prior_updated"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM kb_node WHERE kind='catalyst'").fetchone()["c"] == 0


def test_postmortem_skips_prior_on_embedder_mismatch():
    conn = _conn()
    # a corpus populated with a DIFFERENT embedder: never grow it with mismatched vectors
    kb.insert_claim(conn, kb.KBNode(kind="catalyst", attrs={"type": "pdufa", "embedder": "local_embed"}),
                    [kb.EvidenceSource(url="u", retrieved_at="t", snippet_hash="h")])
    _close_one(conn)
    out = pl.postmortem_closed(conn, embed=kb.hash_embed)
    assert out["kb_written"] == 1 and out["prior_updated"] == 0
    att = json.loads(conn.execute("SELECT attribution FROM paper_position").fetchone()[0])
    assert "embedder" in att["prior_update"]


def test_postmortem_without_catalyst_type_skips_prior():
    conn = _conn()
    entry_t, _ = _seed_history(conn, "ABCD")
    upsert_bars(conn, "ABCD", [_bar("2026-08-21", 12.0, 12.0)])
    _open(conn, entry=entry_t, ctype=None)
    pl.mark_open_positions(conn, "2026-08-28")
    out = pl.postmortem_closed(conn, embed=kb.hash_embed)
    assert out["kb_written"] == 1 and out["prior_updated"] == 0


def test_one_bad_position_never_sinks_the_pass(monkeypatch):
    conn = _conn()
    _close_one(conn, ticker="AAA", seed=1)
    _close_one(conn, ticker="BBB", seed=2)
    real = pl.attribute_trade

    def boom(**kw):
        if kw["entry"] == conn.execute("SELECT entry_price FROM paper_position WHERE ticker='AAA'"
                                       ).fetchone()[0]:
            raise ValueError("boom")
        return real(**kw)
    monkeypatch.setattr(pl, "attribute_trade", boom)
    out = pl.postmortem_closed(conn, embed=kb.hash_embed)
    assert out["attributed"] == 1 and out["failed"] == 1
    # the failed one stays pending -> retried next pass (self-healing)
    monkeypatch.setattr(pl, "attribute_trade", real)
    assert pl.postmortem_closed(conn, embed=kb.hash_embed)["attributed"] == 1


def test_narrate_seam_is_optional_and_attached():
    conn = _conn()
    _close_one(conn)
    seen = {}

    def narrate(pos, att):
        seen["v"] = att["verdict"]
        return "thesis played out"
    pl.postmortem_closed(conn, embed=kb.hash_embed, narrate=narrate)
    node_id = conn.execute("SELECT postmortem_node_id FROM paper_position").fetchone()[0]
    assert kb.get_node(conn, node_id)["attrs"]["narrative"] == "thesis played out"
    assert seen["v"] in pl.VERDICTS


def test_postmortem_never_opens_anything():
    conn = _conn()
    _close_one(conn)
    n = conn.execute("SELECT COUNT(*) c FROM paper_position").fetchone()["c"]
    pl.postmortem_closed(conn, embed=kb.hash_embed)
    pl.go_live_gate(conn)
    assert conn.execute("SELECT COUNT(*) c FROM paper_position").fetchone()["c"] == n
    assert pl.get_open_positions(conn) == []


# =============================================================== go_live_gate (EXEC-02)


def _book_closed(conn, rets, *, hedge_rets=None, cids=None):
    """Insert closed positions directly (gate tests only read closed rows)."""
    for i, r in enumerate(rets):
        conn.execute(
            "INSERT INTO paper_position (ticker, side, entry_price, size_pct, opened_at, exit_by, "
            "held_through, status, close_price, realized_ret, catalyst_id, hedge_ret) "
            "VALUES (?,?,?,?,?,?,1,'closed',?,?,?,?)",
            (f"T{i}", "long", 10.0, 0.02, f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}",
             "2027-01-01", 10.0 * (1 + r), r, (cids[i] if cids else str(i)),
             (hedge_rets[i] if hedge_rets else None)),
        )
    conn.commit()


def test_gate_no_trades_is_no_go():
    v = pl.go_live_gate(_conn())
    assert v["verdict"].go is False and v["verdict"].n_catalysts == 0
    assert v["distribution"] is None and v["psr"] is None


def test_gate_below_sample_floor_is_no_go_even_with_perfect_record():
    conn = _conn()
    _book_closed(conn, [0.05 + 0.001 * i for i in range(10)], hedge_rets=[0.01] * 10)
    v = pl.go_live_gate(conn)
    assert v["verdict"].go is False
    assert any("insufficient sample" in r for r in v["verdict"].reasons)


def test_gate_counts_distinct_catalysts_not_legs():
    conn = _conn()
    _book_closed(conn, [0.03] * 40, cids=["same"] * 40)
    v = pl.go_live_gate(conn)
    assert v["verdict"].n_catalysts == 1 and v["verdict"].go is False


def _strong(n=40):
    rets = [0.04 if i % 4 else -0.02 for i in range(n)]
    hedges = [0.01 if r < 0 else -0.005 for r in rets]
    return rets, hedges


def test_gate_go_with_sufficient_significant_sample():
    conn = _conn()
    rets, hedges = _strong()
    _book_closed(conn, rets, hedge_rets=hedges)
    v = pl.go_live_gate(conn)
    assert v["verdict"].go is True, v["verdict"].reasons
    assert v["psr"] >= pl.PAPER_GATE_THRESHOLDS["min_psr"]


def test_gate_names_insignificant_edge():
    conn = _conn()
    rets = [0.031 if i % 2 else -0.03 for i in range(40)]   # a coin flip with a sliver of mean
    hedges = [0.01 if r < 0 else 0.0 for r in rets]
    _book_closed(conn, rets, hedge_rets=hedges)
    v = pl.go_live_gate(conn, thresholds={**pl.PAPER_GATE_THRESHOLDS, "win_rate": 0.0,
                                          "sharpe": -99, "max_drawdown": -1.0})
    assert v["verdict"].go is False
    assert any("psr" in r for r in v["verdict"].reasons)


def test_gate_without_any_hedged_trade_names_hedge_failure():
    conn = _conn()
    rets, _ = _strong()
    _book_closed(conn, rets)
    v = pl.go_live_gate(conn)
    assert v["verdict"].go is False
    assert any("hedge_effectiveness" in r for r in v["verdict"].reasons)


def test_gate_constant_returns_psr_undefined_is_named_failure():
    conn = _conn()
    _book_closed(conn, [0.02] * 40, hedge_rets=[0.0] * 40)
    v = pl.go_live_gate(conn, thresholds={**pl.PAPER_GATE_THRESHOLDS, "sharpe": -99,
                                          "hedge_effectiveness": -1})
    assert v["psr"] is None and v["verdict"].go is False
    assert any("psr" in r and "undefined" in r for r in v["verdict"].reasons)


def test_gate_missing_threshold_raises_no_magic_default():
    conn = _conn()
    rets, hedges = _strong()
    _book_closed(conn, rets, hedge_rets=hedges)
    th = dict(pl.PAPER_GATE_THRESHOLDS)
    del th["min_psr"]
    with pytest.raises(KeyError):
        pl.go_live_gate(conn, thresholds=th)


def test_gate_has_no_calendar_term():
    import inspect
    src = inspect.getsource(pl.go_live_gate)
    for word in ("weeks", "days", "month", "date.today", "now_iso", "timedelta"):
        assert word not in src


# =============================================================== headless close-path hook


def test_weekly_mark_pass_closes_then_postmortems_in_one_headless_pass():
    conn = _conn()
    entry_t, _ = _seed_history(conn, "ABCD")
    upsert_bars(conn, "ABCD", [_bar("2026-08-21", 12.0, 12.0)])
    upsert_bars(conn, "XBI", [_bar("2026-08-21", 103.0, 103.0)])
    _open(conn, entry=entry_t)
    out = pl.weekly_mark_pass(conn, "2026-08-28", embed=kb.hash_embed)
    assert out["mark"]["closed"] == 1
    assert out["postmortem"] == {"attributed": 1, "kb_written": 1, "prior_updated": 1, "failed": 0}
    assert pl.weekly_mark_pass(conn, "2026-09-04", embed=kb.hash_embed)["postmortem"]["attributed"] == 0


def test_weekly_cycle_gate_prints_verdict_and_opens_nothing(capsys):
    import scripts.weekly_cycle as wc
    conn = _conn()
    out = wc.gate(conn)
    assert out["verdict"].go is False
    assert "NO-GO" in capsys.readouterr().out
    assert conn.execute("SELECT COUNT(*) c FROM paper_position").fetchone()["c"] == 0
