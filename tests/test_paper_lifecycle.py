"""7.8-S4 Task 2: the paper lifecycle — dossier->params, mark/close, cited outcome feedback.

Money-critical, all offline (:memory: + injected bars/quotes; NO network/LLM):
  - position_params_from_decision maps an 'enter' dossier -> params; pass/escalate/None -> None.
  - a CLOSE (exit_by <= as_of) fills at the EXIT-BY action bar (C1) via the SAME fill discipline the
    backtest uses (fill.fill_price + engine._net_return, half-spread both sides, slippage=0.0) so the
    realized P&L is byte-identical to the backtest — proven by asserting == the reused primitives.
  - a late --mark (run a week+ after exit_by) STILL fills at the exit-by action bar, not the mark date.
  - a halted action bar / no-hold-week bar / missing mark quote -> HOLD (never a fabricated price).
  - empty evidence (C3) -> the position STILL closes + books realized_ret, but NO outcome node.
  - record_paper_outcome handles BOTH tool:fn#hash and kb:<id> refs (C4) without crashing.
"""

from types import SimpleNamespace

import pytest

from catalyst_trader import db as _db
from catalyst_trader import paper_ledger as pl
from catalyst_trader.backtest.engine import _net_return
from catalyst_trader.backtest.fill import fill_price
from catalyst_trader.store import upsert_bars


def _conn():
    conn = _db.connect(":memory:")
    _db.migrate(conn)
    return conn


def _result(decision="enter", *, entry=10.0, exit_by="2026-08-21", refs=None, held_through=True):
    trade = SimpleNamespace(
        target_long="ABCD", entry=entry, size_pct=0.02, exit_by_date=exit_by,
        holds_through_catalyst=held_through, catalyst_id="cat-1", direction="positive",
    )
    dossier = SimpleNamespace(trade=trade, all_evidence_refs=(refs if refs is not None else ["kb:42"]))
    dec = None if decision is None else SimpleNamespace(decision=decision)
    return {"decision": dec, "dossier": dossier}


def _open(conn, *, as_of="2026-08-14", **over):
    params = pl.position_params_from_decision(_result(**over), as_of=as_of)
    return pl.approve_pending(conn, pl.submit_for_approval(conn, params))


# --------------------------------------------------------------- position_params_from_decision


def test_given_enter_when_mapped_then_carries_dossier_params():
    p = pl.position_params_from_decision(_result("enter", entry=42.5), as_of="2026-08-14")
    assert p["ticker"] == "ABCD" and p["entry"] == 42.5 and p["size_pct"] == 0.02
    assert p["side"] == "long" and p["direction"] == "positive"
    assert p["opened_at"] == "2026-08-14" and p["exit_by"] == "2026-08-21"
    assert p["held_through"] is True and p["catalyst_id"] == "cat-1"
    assert p["evidence_refs"] == ["kb:42"] and p["decision_ref"]


@pytest.mark.parametrize("decision", ["pass", "escalate", None])
def test_given_non_enter_when_mapped_then_none(decision):
    assert pl.position_params_from_decision(_result(decision), as_of="2026-08-14") is None


# --------------------------------------------------------------- mark (future exit_by)


def test_given_future_exit_when_marked_then_unrealized_no_close():
    conn = _conn()
    upsert_bars(conn, "ABCD", [{"week_end": "2026-08-14", "close": 11.0, "open": 10.0,
                                "high": 11.5, "low": 9.5, "volume": 1000}])
    pos_id = _open(conn, as_of="2026-08-14", exit_by="2026-08-28")
    summary = pl.mark_open_positions(conn, "2026-08-14")
    assert summary == {"marked": 1, "closed": 0, "held": 0}
    m = conn.execute("SELECT mark_price, unrealized_ret, source FROM paper_mark WHERE position_id=?",
                     (pos_id,)).fetchone()
    assert m["mark_price"] == 11.0 and m["source"] == "bars"
    assert m["unrealized_ret"] == _net_return(10.0, 11.0, apply_costs=False)
    assert pl.get_open_positions(conn)  # still open


def test_given_no_bars_when_quotes_fn_supplies_last_then_marks_from_quote():
    conn = _conn()
    _open(conn, as_of="2026-08-14", exit_by="2026-08-28")  # no bars seeded
    summary = pl.mark_open_positions(conn, "2026-08-14", quotes_fn=lambda t: 12.0)
    assert summary["marked"] == 1
    m = conn.execute("SELECT mark_price, source FROM paper_mark").fetchone()
    assert m["mark_price"] == 12.0 and m["source"] == "quotes_rt"


def test_given_no_bars_and_no_quote_when_marked_then_holds_never_fabricates():
    conn = _conn()
    _open(conn, as_of="2026-08-14", exit_by="2026-08-28")  # no bars, quotes_fn None
    summary = pl.mark_open_positions(conn, "2026-08-14")
    assert summary == {"marked": 0, "closed": 0, "held": 1}
    assert conn.execute("SELECT COUNT(*) c FROM paper_mark").fetchone()["c"] == 0
    assert pl.get_open_positions(conn)  # held open, not closed


# --------------------------------------------------------------- close (exit_by <= as_of) — C1


def test_given_past_exit_when_closed_then_fills_at_exit_by_action_bar_byte_identical():
    conn = _conn()
    # the exit-by (hold) week action bar — held-through fills at the GAP OPEN.
    exit_bar = {"week_end": "2026-08-21", "open": 12.0, "high": 13.0, "low": 11.0,
                "close": 12.5, "volume": 5000}
    upsert_bars(conn, "ABCD", [exit_bar])
    pos_id = _open(conn, as_of="2026-08-14", exit_by="2026-08-21")
    # a LATE mark: run a full week AFTER exit_by. C1 -> must still fill at the exit-by action bar.
    summary = pl.mark_open_positions(conn, "2026-08-28")
    assert summary == {"marked": 0, "closed": 1, "held": 0}
    pos = conn.execute("SELECT close_price, realized_ret FROM paper_position WHERE id=?",
                       (pos_id,)).fetchone()
    # byte-identical to the backtest: the SAME fill_price + _net_return over the SAME action bar.
    expect_fill = fill_price([exit_bar], side="long", held_through=True, slippage=0.0)
    expect_ret = _net_return(10.0, expect_fill, apply_costs=True)
    assert pos["close_price"] == expect_fill
    assert pos["realized_ret"] == expect_ret
    assert expect_fill == 12.0  # gap open, slippage 0.0 (sanity)


def test_given_halted_action_bar_when_closing_then_holds_never_fabricates():
    conn = _conn()
    # zero volume == halted -> fill_price None -> HOLD (unmeasurable, never a fabricated close).
    upsert_bars(conn, "ABCD", [{"week_end": "2026-08-21", "open": 12.0, "high": 13.0,
                                "low": 11.0, "close": 12.5, "volume": 0}])
    _open(conn, as_of="2026-08-14", exit_by="2026-08-21")
    summary = pl.mark_open_positions(conn, "2026-08-28")
    assert summary == {"marked": 0, "closed": 0, "held": 1}
    assert pl.get_open_positions(conn)  # still open, unmeasurable


def test_given_no_hold_week_bar_yet_when_closing_then_holds():
    conn = _conn()
    # the only bar is AT/BEFORE opened_at -> no hold-week action bar yet (mirrors engine.py:233).
    upsert_bars(conn, "ABCD", [{"week_end": "2026-08-14", "open": 10.0, "high": 10.5,
                                "low": 9.5, "close": 10.0, "volume": 1000}])
    _open(conn, as_of="2026-08-14", exit_by="2026-08-21")
    summary = pl.mark_open_positions(conn, "2026-08-21")
    assert summary["closed"] == 0 and summary["held"] == 1


def test_given_short_direction_sign_when_closing_then_uses_stored_side():
    # provenance direction is carried; side stays long (desk long-only) so the fill side is honest.
    conn = _conn()
    exit_bar = {"week_end": "2026-08-21", "open": 8.0, "high": 9.0, "low": 7.0,
                "close": 7.5, "volume": 5000}
    upsert_bars(conn, "ABCD", [exit_bar])
    _open(conn, as_of="2026-08-14", exit_by="2026-08-21")  # a losing long
    pl.mark_open_positions(conn, "2026-08-28")
    pos = conn.execute("SELECT realized_ret FROM paper_position WHERE status='closed'").fetchone()
    assert pos["realized_ret"] < 0  # long into a gap-down loses


# --------------------------------------------------------------- cited outcome feedback (C3/C4)


def test_given_close_with_evidence_when_closed_then_writes_cited_outcome():
    conn = _conn()
    upsert_bars(conn, "ABCD", [{"week_end": "2026-08-21", "open": 12.0, "high": 13.0,
                                "low": 11.0, "close": 12.5, "volume": 5000}])
    _open(conn, as_of="2026-08-14", exit_by="2026-08-21", refs=["tool:weekly_base_rate#abc123"])
    pl.mark_open_positions(conn, "2026-08-28")
    node = conn.execute("SELECT attrs_json FROM kb_node WHERE kind='outcome'").fetchone()
    assert node is not None
    import json
    attrs = json.loads(node["attrs_json"])
    assert attrs["kind"] == "paper_leg" and attrs["ticker"] == "ABCD" and attrs["win"] is True


def test_given_close_with_empty_evidence_when_closed_then_books_ret_but_no_outcome():
    # C3: empty all_evidence_refs -> the position STILL closes + books realized_ret, outcome DROPPED,
    # NO fabricated citation, no crash.
    conn = _conn()
    upsert_bars(conn, "ABCD", [{"week_end": "2026-08-21", "open": 12.0, "high": 13.0,
                                "low": 11.0, "close": 12.5, "volume": 5000}])
    pos_id = _open(conn, as_of="2026-08-14", exit_by="2026-08-21", refs=[])
    summary = pl.mark_open_positions(conn, "2026-08-28")
    assert summary["closed"] == 1
    pos = conn.execute("SELECT status, realized_ret FROM paper_position WHERE id=?",
                       (pos_id,)).fetchone()
    assert pos["status"] == "closed" and pos["realized_ret"] is not None
    assert conn.execute("SELECT COUNT(*) c FROM kb_node WHERE kind='outcome'").fetchone()["c"] == 0


def test_given_kb_ref_without_hash_when_recording_outcome_then_no_indexerror():
    # C4: a kb:<id> ref has no '#'; snippet_hash must hash the whole ref, never blindly split.
    conn = _conn()
    pos = {"ticker": "ABCD", "direction": "positive", "size_pct": 0.02,
           "evidence_refs": ["kb:42"]}
    nid = pl.record_paper_outcome(conn, pos, realized_ret=0.05)
    assert nid > 0
    # and a tool:fn#hash ref also works
    pos2 = dict(pos, evidence_refs=["tool:weekly_base_rate#deadbeef"])
    assert pl.record_paper_outcome(conn, pos2, realized_ret=-0.03) > 0


def test_no_live_broker_order_symbol_imported():
    import catalyst_trader.paper_ledger as mod
    assert not hasattr(mod, "place_equity_order")
