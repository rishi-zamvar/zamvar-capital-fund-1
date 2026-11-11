"""paper_ledger.py (7.8-S4) — the forward PAPER trading ledger + the inviolable operator gate.

Three concerns, in order:
  1. STORE (this half): plain sqlite helpers mirroring store.py — open/mark/close a paper_position,
     upsert a paper_mark, and the pending gate (submit/approve/reject). The gate is STRUCTURAL: the
     ONLY code path that inserts a paper_position is ``approve_pending`` over a pending record, so no
     position can open without an explicit operator approval (the human gate, enforced by construction
     — there is no public ``open_*`` function).
  2. LIFECYCLE (Task 2): map an APPROVED MDDecision 'enter' -> position params; mark every open at the
     point-in-time quote and CLOSE any past exit_by at the SAME pessimistic fill the backtest uses
     (fill.fill_price + engine._net_return, half-spread both sides) — realized P&L is byte-identical to
     the backtest, no live-vs-backtest drift.
  3. FEEDBACK (Task 2): a closed position writes a CITED KB outcome referencing the decision's OWN
     evidence refs (cite-or-drop) — never a fabricated citation.

PAPER ONLY: no live-broker order path is ever imported or called here (Phase 11 is strictly last).
# ponytail: plain sqlite helpers mirroring store.py; no repository class, no ORM.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import sqlite3

from catalyst_trader.dates import now_iso

# --- store: paper_position (write path is PRIVATE — only approve_pending opens) ---------------

_POS_COLS = (
    "ticker", "side", "entry_price", "size_pct", "opened_at", "exit_by",
    "held_through", "direction", "decision_ref", "catalyst_id", "evidence_refs",
    "catalyst_type", "event_date", "hedge_ticker",
)


def _open_paper_position(conn: sqlite3.Connection, params: dict) -> int:
    """Insert one OPEN paper_position from an approved decision's params; return its id.

    PRIVATE by design — the SOLE caller is ``approve_pending`` (the structural human gate). Never
    call this directly; a position with no approved pending record is a gate violation.

    Trust-boundary guard (Phase 8 fill-gap): the backtest refuses an entry <= 0 (engine._fill_leg)
    and a non-finite entry/size would poison every later P&L number (0-entry -> ZeroDivisionError on
    close, sinking the whole mark pass). Refuse BEFORE the write; the pending record stays pending.
    """
    entry, size = float(params["entry"]), float(params["size_pct"])
    if not (math.isfinite(entry) and entry > 0):
        raise ValueError(f"refuse to open: entry must be finite and > 0, got {entry!r}")
    if not (math.isfinite(size) and 0 < size <= 1):
        raise ValueError(f"refuse to open: size_pct must be in (0, 1], got {size!r}")
    row = (
        params["ticker"], params.get("side", "long"), entry,
        size, params["opened_at"], params["exit_by"],
        1 if params.get("held_through", True) else 0, params.get("direction"),
        params.get("decision_ref"), params.get("catalyst_id"),
        json.dumps(params.get("evidence_refs", [])),
        params.get("catalyst_type"), params.get("event_date"), params.get("hedge_ticker"),
    )
    return conn.execute(
        f"INSERT INTO paper_position ({', '.join(_POS_COLS)}, status) "
        f"VALUES ({', '.join('?' * len(_POS_COLS))}, 'open')",
        row,
    ).lastrowid


def get_open_positions(conn: sqlite3.Connection) -> list[dict]:
    """Every position with status='open', as plain dicts (evidence_refs parsed back to a list)."""
    rows = conn.execute("SELECT * FROM paper_position WHERE status='open' ORDER BY id").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["held_through"] = bool(d["held_through"])
        d["evidence_refs"] = json.loads(d["evidence_refs"]) if d["evidence_refs"] else []
        out.append(d)
    return out


def mark_paper_position(
    conn: sqlite3.Connection, position_id: int, mark_date: str, mark_price: float,
    unrealized_ret: float | None, *, source: str = "bars",
) -> int:
    """UPSERT one weekly mark for an open position; idempotent on (position_id, mark_date) — a
    re-mark at the same date UPDATES in place (mirrors upsert_bars). Returns the row id."""
    try:
        existing = conn.execute(
            "SELECT id FROM paper_mark WHERE position_id=? AND mark_date=?",
            (position_id, mark_date),
        ).fetchone()
        if existing is not None:
            conn.execute(
                "UPDATE paper_mark SET mark_price=?, unrealized_ret=?, source=? WHERE id=?",
                (mark_price, unrealized_ret, source, existing["id"]),
            )
            row_id = existing["id"]
        else:
            row_id = conn.execute(
                "INSERT INTO paper_mark (position_id, mark_date, mark_price, unrealized_ret, source) "
                "VALUES (?,?,?,?,?)",
                (position_id, mark_date, mark_price, unrealized_ret, source),
            ).lastrowid
        conn.commit()
        return row_id
    except Exception:
        conn.rollback()
        raise


def close_paper_position(
    conn: sqlite3.Connection, position_id: int, *, close_price: float, realized_ret: float,
) -> None:
    """Book the realized close: status->'closed', close_price, realized_ret, closed_at. Guards a
    re-close (an already-closed position RAISES — realized P&L is never double-booked)."""
    row = conn.execute("SELECT status FROM paper_position WHERE id=?", (position_id,)).fetchone()
    if row is None:
        raise ValueError(f"no paper_position id={position_id}")
    if row["status"] != "open":
        raise ValueError(f"paper_position id={position_id} is already {row['status']} — refuse to re-close")
    try:
        conn.execute(
            "UPDATE paper_position SET status='closed', close_price=?, realized_ret=?, closed_at=? "
            "WHERE id=?",
            (close_price, realized_ret, now_iso(), position_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# --- the INVIOLABLE operator-approval gate ---------------------------------------------------
# submit -> a pending record only. approve -> the SOLE path that opens a position. reject -> nothing.


def submit_for_approval(conn: sqlite3.Connection, params: dict, *, review: dict | None = None) -> int:
    """Record a decision as PENDING operator approval; return the pending id. Opens NOTHING.

    `review` is the display-only snapshot (review_snapshot) the iOS dossier screen reads; the gate
    never reads it — approve_pending opens from `params` alone."""
    try:
        pid = conn.execute(
            "INSERT INTO paper_pending (status, params, submitted_at, review) VALUES ('pending', ?, ?, ?)",
            (json.dumps(params), now_iso(), None if review is None else json.dumps(review)),
        ).lastrowid
        conn.commit()
        return pid
    except Exception:
        conn.rollback()
        raise


def approve_pending(conn: sqlite3.Connection, pending_id: int) -> int | None:
    """The SOLE opener: over a still-'pending' record, open the position from its params and flip the
    record to 'approved' (returns the new position id). Idempotent — an already-approved record
    returns its existing position id (no duplicate); a rejected/absent record returns None.

    Race-free: BEGIN IMMEDIATE takes the write lock BEFORE the status read, so two concurrent
    approvers (CLI + dashboard, or a double-tap) serialize and the second sees 'approved' — never
    two positions from one pending record."""
    began = not conn.in_transaction
    if began:
        conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT status, params, position_id FROM paper_pending WHERE id=?",
                           (pending_id,)).fetchone()
        if row is None or row["status"] != "pending":
            if began:
                conn.rollback()  # release the lock; nothing was written
            if row is not None and row["status"] == "approved":
                return row["position_id"]  # idempotent: no second position
            return None  # absent / rejected -> never opens
        pos_id = _open_paper_position(conn, json.loads(row["params"]))
        conn.execute(
            "UPDATE paper_pending SET status='approved', resolved_at=?, position_id=? WHERE id=?",
            (now_iso(), pos_id, pending_id),
        )
        conn.commit()
        return pos_id
    except Exception:
        conn.rollback()
        raise


def reject_pending(conn: sqlite3.Connection, pending_id: int) -> None:
    """Flip a pending record to 'rejected'; opens NO position (the gate's negative path)."""
    try:
        conn.execute(
            "UPDATE paper_pending SET status='rejected', resolved_at=? WHERE id=? AND status='pending'",
            (now_iso(), pending_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# --- lifecycle: dossier->params, mark/close pass, cited outcome feedback (Task 2) ------------
# REUSES the backtest fill discipline verbatim (fill_price + _net_return + half_spread_pct via
# _net_return) so a paper fill is byte-identical to a backtest fill — NO live-vs-backtest drift.


def position_params_from_decision(result: dict, *, as_of: str) -> dict | None:
    """Map an APPROVED-shaped decision result to open-position params, or None for a non-'enter'.

    Only ``result['decision'].decision == 'enter'`` yields params; 'pass'/'escalate'/None -> None
    (nothing opens). Params carry the dossier's OWN trade fields + `opened_at=as_of` (the decision
    week — the C1 close-guard compares the exit-by action bar's week_end against it) + `direction`
    (provenance; side is always 'long', the desk is long-only) + the decision's evidence refs (cited
    on close). `decision_ref` back-references the authoring catalyst.
    """
    dec = result.get("decision")
    if dec is None or getattr(dec, "decision", None) != "enter":
        return None
    t = result["dossier"].trade
    cat = result.get("catalyst") or {}
    hedge = getattr(t, "hedge", None)
    return {
        "ticker": t.target_long,
        "entry": t.entry,
        "size_pct": t.size_pct,
        "side": "long",                       # desk is long-only; direction carried for provenance
        "opened_at": as_of,                   # the decision week — the C1 no-drift close guard
        "exit_by": t.exit_by_date,
        "held_through": t.holds_through_catalyst,
        "direction": t.direction,
        "catalyst_id": t.catalyst_id,
        "decision_ref": f"catalyst:{t.catalyst_id}",
        "evidence_refs": list(result["dossier"].all_evidence_refs),
        # Phase 8 post-mortem facts: the analog-prior key + the hedge peer (filled at post-mortem).
        "catalyst_type": cat.get("catalyst_type"),
        "event_date": cat.get("event_date"),
        "hedge_ticker": hedge.ticker if hedge is not None else None,
    }


def _plain(obj):
    """JSON-plain copy of a contract model / SimpleNamespace fake / container (None passes through)."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "__dict__"):
        return {k: _plain(v) for k, v in vars(obj).items()}
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    return obj


def review_snapshot(result: dict) -> dict:
    """The display-only WHY behind a submitted decision, for the operator's dossier review (Phase 9):
    the catalyst, the StrategyDossier (trade incl. SL/TP + thesis/kill criteria/pre-mortem), the sealed
    DiligenceDossier and the MDDecision. The MD round_log is collapsed to a count (it carries the full
    cross_check snapshots — audit material, not review material). Never read by the gate."""
    decision = _plain(result.get("decision"))
    if isinstance(decision, dict) and "round_log" in decision:
        decision["rounds"] = len(decision.pop("round_log"))
    return {
        "catalyst": _plain(result.get("catalyst")),
        "dossier": _plain(result.get("dossier")),
        "dd": _plain(result.get("dd")),
        "decision": decision,
    }


def _rh_quote(ticker: str, *, mcp_call=None) -> float | None:
    """Live mark fallback: robinhood.quotes_rt 'last' for one ticker, degrade-to-None. Only called
    when the point-in-time bars are empty (frugality: cache/bars first). Offline default is None."""
    from catalyst_trader.providers import robinhood

    quotes = robinhood.quotes_rt([ticker], mcp_call=mcp_call)
    return (quotes or {}).get(ticker, {}).get("last")


def mark_open_positions(conn: sqlite3.Connection, as_of: str, *, quotes_fn=None, embed=None) -> dict:
    """Mark every open position at the point-in-time quote and CLOSE any whose exit_by <= as_of.

    Returns {marked, closed, held}. No-look-ahead: marks read ONLY serving.asof(conn, as_of); a
    close reads the exit-by action bar at serving.asof(conn, exit_by).bars(ticker, exit_by) — so a
    LATE mark (run a week+ after exit_by) still fills at the exit-by action bar (C1, no drift). A
    missing mark quote / halted action bar / no-hold-week bar -> HOLD (never a fabricated price).
    quotes_fn(ticker)->last|None is the live fallback (default None = bars-only, offline).
    """
    from catalyst_trader import serving
    from catalyst_trader.backtest.engine import _net_return
    from catalyst_trader.backtest.fill import fill_price

    marked = closed = held = 0
    for pos in get_open_positions(conn):
        ticker, entry = pos["ticker"], pos["entry_price"]
        if pos["exit_by"] <= as_of:
            # --- CLOSE at the EXIT-BY action bar (mirror engine._fill_leg — byte-identical) ---
            exit_bars = serving.asof(conn, pos["exit_by"]).bars(ticker, pos["exit_by"])
            if not exit_bars or exit_bars[-1]["week_end"] <= pos["opened_at"]:
                held += 1                      # no hold-week bar yet -> unmeasurable, do not fabricate
                continue
            fill = fill_price(exit_bars, side=pos["side"], held_through=pos["held_through"],
                              slippage=0.0)    # C2: slippage=0.0, the backtest's effective value
            if fill is None:
                held += 1                      # halted / delisted / zero-vol action bar -> HOLD
                continue
            realized = _net_return(entry, fill, apply_costs=True)  # half-spread paid BOTH sides
            close_paper_position(conn, pos["id"], close_price=fill, realized_ret=realized)
            if pos["evidence_refs"]:           # C3: cite-or-drop — empty evidence closes but drops
                record_paper_outcome(conn, pos, realized, embed=embed)
            closed += 1
        else:
            # --- MARK at the point-in-time quote (cache-first bars, then live quote, else HOLD) ---
            bars = serving.asof(conn, as_of).bars(ticker, as_of)
            mark_price, source = (bars[-1]["close"], "bars") if bars else (None, None)
            if mark_price is None and quotes_fn is not None:
                q = quotes_fn(ticker)
                if q is not None:
                    mark_price, source = q, "quotes_rt"
            if mark_price is None:
                held += 1                      # no knowable mark -> HOLD, never fabricate
                continue
            unreal = _net_return(entry, mark_price, apply_costs=False)  # a mark is not a round-trip
            mark_paper_position(conn, pos["id"], as_of, mark_price, unreal, source=source)
            marked += 1
    return {"marked": marked, "closed": closed, "held": held}


def _evidence(ref: str, *, quote: str):
    """One decision ref -> EvidenceSource. Handles BOTH shapes (C4): ``tool:fn#hash`` (snippet_hash =
    the post-# hash) and ``kb:<id>`` (no '#' -> a stable sha256 of the whole ref)."""
    from catalyst_trader import kb

    snippet_hash = ref.split("#", 1)[1] if "#" in ref else hashlib.sha256(ref.encode()).hexdigest()
    return kb.EvidenceSource(url=ref, retrieved_at=now_iso(), snippet_hash=snippet_hash, quote=quote)


def record_paper_outcome(conn: sqlite3.Connection, position: dict, realized_ret: float, *,
                         embed=None) -> int:
    """Persist ONE cited KB 'outcome' claim for a closed paper leg, citing the decision's OWN FIRST
    evidence ref (cite-or-drop — the caller only calls this when evidence_refs is non-empty).

    Handles BOTH ref shapes (C4): ``tool:fn#hash`` (snippet_hash = the post-# hash) and ``kb:<id>``
    (no '#' -> snippet_hash = a stable hash of the whole ref). Does NOT reuse record_weekly_outcome
    (which forces a weekly_base_rate citation a catalyst leg does not have — that would fabricate a
    mismatched ref).
    """
    from catalyst_trader import kb

    ev = _evidence(position["evidence_refs"][0],
                   quote=f"paper leg {position['ticker']} realized_ret={realized_ret}")
    node = kb.KBNode(kind="outcome", attrs={
        "kind": "paper_leg",
        "ticker": position["ticker"],
        "direction": position.get("direction"),
        "size": position.get("size_pct"),
        "realized_ret": realized_ret,
        "win": realized_ret > 0,
    })
    return kb.insert_claim(conn, node, [ev], embed=embed,
                           embed_text=f"paper leg {position['ticker']}" if embed else None)


# --- Phase 8 (LEARN-03): per-resolved-trade attribution + good-decision/bad-luck post-mortem ----
# Deterministic, headless, no LLM. Runs over CLOSED positions whose attribution IS NULL, so it is
# idempotent and self-healing (a failure leaves the row pending -> retried on the next --mark pass).

logger = logging.getLogger(__name__)

VERDICTS = (
    "good_decision_good_outcome",   # the thesis-attributable (idiosyncratic) move paid, and we won
    "bad_decision_good_luck",       # we won, but only on beta/drift — the thesis piece lost
    "good_decision_bad_luck",       # the thesis piece paid, but beta/costs/sizing sank the trade
    "bad_decision_bad_outcome",     # the thesis piece lost, and so did we
)

# ponytail: the long/long hedge peer carries NO size this phase (PortfolioContext.portfolio_outcome
# is target-leg scope), so its book contribution is 0 and only its realized return is reported.
# Upgrade path: when hedge sizing lands, persist paper_position.hedge_size_pct and use it here.
_HEDGE_SIZE = 0.0


def _finite(name: str, v, *, allow_none: bool = False) -> None:
    if v is None and allow_none:
        return
    if v is None or not math.isfinite(v):
        raise ValueError(f"{name} must be finite, got {v!r}")


def attribute_trade(*, size: float, ref_size: float, entry: float, close: float,
                    realized_ret: float, beta: float | None, r_xbi: float | None,
                    hedge_ret: float | None) -> dict:
    """Decompose ONE resolved paper trade's book contribution (size * realized_ret, + hedge leg).

    PURE. In book-return units (fraction of the fund), with ``ref_size`` the neutral reference size:
      catalyst_effect = ref * (gross - beta * r_xbi)   the idiosyncratic, thesis-attributable move
      beta_drift      = ref * beta * r_xbi             the sector tape (XBI) over the same window
      costs           = ref * (realized_ret - gross)   the half-spread paid both sides
      sizing          = (size - ref) * realized_ret    what over/under-sizing vs reference added
      hedge_leg       = hedge_size * hedge_ret         0 this phase (peer carries no size)
    gross = close/entry - 1. The components reconcile EXACTLY to the total (quant.performance.
    attribution raises otherwise). beta or r_xbi unavailable -> beta_drift 0, the whole gross move is
    the catalyst effect and ``beta_available`` is False (flagged, never a silently invented beta).

    Verdict (Duke's 2x2): thesis_right = catalyst_effect > 0; win = total > 0 (flat is neither).
    """
    from catalyst_trader.quant.performance import attribution

    for name, v in (("size", size), ("ref_size", ref_size), ("entry", entry), ("close", close),
                    ("realized_ret", realized_ret)):
        _finite(name, v)
    for name, v in (("beta", beta), ("r_xbi", r_xbi), ("hedge_ret", hedge_ret)):
        _finite(name, v, allow_none=True)
    if entry <= 0:
        raise ValueError(f"entry must be > 0, got {entry!r}")

    gross = close / entry - 1.0
    beta_ok = beta is not None and r_xbi is not None
    beta_move = beta * r_xbi if beta_ok else 0.0
    hedge_leg = _HEDGE_SIZE * hedge_ret if hedge_ret is not None else 0.0
    components = {
        "catalyst_effect": ref_size * (gross - beta_move),
        "beta_drift": ref_size * beta_move,
        "costs": ref_size * (realized_ret - gross),
        "sizing": (size - ref_size) * realized_ret,
        "hedge_leg": hedge_leg,
    }
    total = size * realized_ret + hedge_leg
    attribution(components, total)  # reconciliation guard — a decomposition that doesn't add up raises

    win, thesis_right = total > 0, components["catalyst_effect"] > 0
    verdict = VERDICTS[(0 if win else 2) + (0 if thesis_right else 1)]
    return {
        "components": components, "total": total, "verdict": verdict,
        "r_gross": gross, "realized_ret": realized_ret, "beta": beta, "r_xbi": r_xbi,
        "beta_available": beta_ok, "hedge_ret": hedge_ret, "ref_size": ref_size, "size": size,
    }


def _beta_vs_xbi(conn: sqlite3.Connection, ticker: str, as_of: str) -> float | None:
    """Trailing weekly beta of `ticker` vs XBI at the DECISION date (point-in-time — no look-ahead),
    over the shipped beta window (params weekly.beta_window_weeks), via quant.pairs.correlation_beta.
    Weeks are aligned on week_end. Too little / degenerate history -> None (flagged downstream)."""
    from catalyst_trader import kb, serving
    from catalyst_trader.quant.pairs import correlation_beta

    window = kb.load_params(conn, "weekly")["weekly"]["beta_window_weeks"]
    book = serving.asof(conn, as_of)
    t = {b["week_end"]: b["close"] for b in book.bars(ticker, as_of, lookback_weeks=window + 1)}
    x = {b["week_end"]: b["close"] for b in book.bars("XBI", as_of, lookback_weeks=window + 1)}
    common = sorted(set(t) & set(x))
    try:
        a = [t[common[i]] / t[common[i - 1]] - 1.0 for i in range(1, len(common))]
        m = [x[common[i]] / x[common[i - 1]] - 1.0 for i in range(1, len(common))]
        return correlation_beta(a, m).detail["beta"]
    except (ValueError, ZeroDivisionError, TypeError):
        return None


def _attribute_position(conn: sqlite3.Connection, pos: dict) -> dict:
    """Gather the point-in-time facts for one closed position and run attribute_trade.

    The XBI window return and the hedge leg are filled with the BACKTEST's own engine._fill_leg over
    the SAME decision/exit-by bars (entry = decision-week close, exit = pessimistic fill_price at the
    exit-by action bar, slippage 0.0) — so paper attribution cannot drift from the Phase-7 backtest.
    ref_size = the mean size of every trade closed up to and including this one (an equal-weight
    reference, deterministic regardless of when the pass runs).
    """
    from catalyst_trader.backtest.engine import _fill_leg

    opened, exit_by, held = pos["opened_at"], pos["exit_by"], bool(pos["held_through"])
    ref_size = conn.execute(
        "SELECT AVG(size_pct) FROM paper_position WHERE status='closed' AND id<=?", (pos["id"],)
    ).fetchone()[0]
    xbi = _fill_leg(conn, "XBI", opened, exit_by, held_through=held, slippage=0.0, apply_costs=False)
    hedge = (_fill_leg(conn, pos["hedge_ticker"], opened, exit_by, held_through=held, slippage=0.0)
             if pos.get("hedge_ticker") else None)
    return attribute_trade(
        size=pos["size_pct"], ref_size=ref_size, entry=pos["entry_price"],
        close=pos["close_price"], realized_ret=pos["realized_ret"],
        beta=_beta_vs_xbi(conn, pos["ticker"], opened),
        r_xbi=xbi[2] if xbi else None, hedge_ret=hedge[2] if hedge else None,
    )


def _write_postmortem(conn: sqlite3.Connection, pos: dict, att: dict, embed) -> tuple[int, str]:
    """Write the post-mortem into the KB through kb.insert_claim (cite-or-drop), citing EVERY one of
    the decision's own evidence refs. Returns (outcome node id, prior-update status).

    Prior update: a catalyst node {type, ticker, knowable_asof=exit_by} + RESULTED_IN -> the outcome
    (SIGNED ``move`` = the realized gross move) + a kb_vec row, so the NEXT catalyst of this type's
    kb.analog_query sees it — the analog up/down move distribution that sizes the gap (the base-rate
    prior) updates. knowable_asof gates it out of any earlier as_of (no look-ahead). Skipped (and
    named) with no embedder, no catalyst_type, or an embedder that differs from the corpus's.
    """
    from catalyst_trader import kb
    from catalyst_trader.playbook.store import _embedder_name, assert_embedder_consistency

    ticker, ctype = pos["ticker"], pos.get("catalyst_type")
    quote = f"paper post-mortem {ticker} verdict={att['verdict']} realized_ret={att['realized_ret']}"
    evidence = [_evidence(ref, quote=quote) for ref in pos["evidence_refs"]]
    attrs = {
        "kind": "paper_postmortem", "ticker": ticker, "catalyst_id": pos.get("catalyst_id"),
        "catalyst_type": ctype, "direction": pos.get("direction"), "move": att["r_gross"],
        "realized_ret": att["realized_ret"], "size": att["size"], "win": att["total"] > 0,
        "verdict": att["verdict"], "components": att["components"], "beta": att["beta"],
        "r_xbi": att["r_xbi"], "hedge_ret": att["hedge_ret"],
    }
    if att.get("narrative") is not None:
        attrs["narrative"] = att["narrative"]
    out_id = kb.insert_claim(conn, kb.KBNode(kind="outcome", attrs=attrs), evidence)

    if embed is None:
        return out_id, "skipped: no embedder"
    if not ctype:
        return out_id, "skipped: no catalyst_type"
    try:
        assert_embedder_consistency(conn, embed)
    except ValueError as exc:
        return out_id, f"skipped: embedder mismatch ({exc})"
    cat = kb.KBNode(kind="catalyst", attrs={
        "type": ctype, "ticker": ticker, "event_date": pos.get("event_date"),
        "knowable_asof": pos["exit_by"], "source": "paper_postmortem",
        "embedder": _embedder_name(embed),
    })
    cat_id = kb.insert_claim(conn, cat, evidence, embed=embed, embed_text=f"{ticker} {ctype}")
    kb.add_edge(conn, cat_id, "RESULTED_IN", out_id)
    conn.commit()
    return out_id, "updated"


def postmortem_closed(conn: sqlite3.Connection, *, embed=None, narrate=None) -> dict:
    """Attribute + post-mortem every CLOSED position not yet attributed; return the pass counts
    {attributed, kb_written, prior_updated, failed}. Opens NOTHING.

    ``narrate(pos, attribution) -> str`` is the OPTIONAL LLM narrative seam (default None = fully
    deterministic headless pass); its text is attached to the KB outcome. Empty evidence -> the
    attribution is still booked on the ledger but nothing is written to the KB (cite-or-drop). One
    bad position is logged + counted and never sinks the pass; it stays pending for the next run.
    # ponytail: the KB write and the ledger UPDATE are separate commits (insert_claim commits); a
    #           crash between them re-writes the post-mortem once on the next pass (duplicate node,
    #           never a lost P&L). Upgrade: a savepoint-aware insert_claim if that ever matters.
    """
    rows = conn.execute(
        "SELECT * FROM paper_position WHERE status='closed' AND attribution IS NULL ORDER BY id"
    ).fetchall()
    out = {"attributed": 0, "kb_written": 0, "prior_updated": 0, "failed": 0}
    for r in rows:
        pos = dict(r)
        pos["evidence_refs"] = json.loads(pos["evidence_refs"]) if pos["evidence_refs"] else []
        try:
            att = _attribute_position(conn, pos)
            if narrate is not None:
                att["narrative"] = narrate(pos, att)
            node_id = None
            if pos["evidence_refs"]:
                node_id, att["prior_update"] = _write_postmortem(conn, pos, att, embed)
                out["kb_written"] += 1
                out["prior_updated"] += att["prior_update"] == "updated"
            else:
                att["prior_update"] = "skipped: no evidence to cite"
            conn.execute(
                "UPDATE paper_position SET hedge_ret=?, attribution=?, postmortem_node_id=? WHERE id=?",
                (att["hedge_ret"], json.dumps(att), node_id, pos["id"]),
            )
            conn.commit()
            out["attributed"] += 1
        except Exception as exc:  # one bad trade never sinks the weekly pass — it is retried
            conn.rollback()
            out["failed"] += 1
            logger.warning("post-mortem for paper_position %s failed (%s) — left pending",
                           pos["id"], exc)
    return out


# --- Phase 8 (EXEC-02): the SAMPLE-based go-live gate over the resolved paper book ------------------
# Reuses the Phase-7 backtest gate verbatim (baseline_distribution + sample_based_gate) on the paper
# closes, plus a significance floor: the probabilistic Sharpe of the per-trade returns
# (quant.performance.deflated_sharpe, n_trials=1 == PSR; raise n_trials to deflate for config search).

def _paper_thresholds() -> dict:
    from catalyst_trader.backtest.gate import THRESHOLDS

    # min_psr / n_trials are documented defaults the PM retunes (assumptions are the moat).
    return {**THRESHOLDS, "min_psr": 0.95, "n_trials": 1}


PAPER_GATE_THRESHOLDS = _paper_thresholds()


def go_live_gate(conn: sqlite3.Connection, thresholds: dict | None = None) -> dict:
    """Go/no-go for real capital from the RESOLVED paper book — sample-based, never calendar-based.

    N = DISTINCT catalysts among closed positions (many legs on one catalyst are one observation).
    Below thresholds['min_sample'] -> NO-GO whatever the metrics. Above it -> go iff every backtest
    floor clears (win_rate / sharpe / max_drawdown / hedge_effectiveness) AND the per-trade PSR clears
    min_psr; every miss is named. Thresholds read by direct subscript (a missing key raises).
    Returns {"verdict": GateVerdict, "psr": float|None, "distribution": BaselineDistribution|None}.
    Read-only: opens nothing, approves nothing.
    """
    from catalyst_trader.backtest.engine import BacktestResult, LegOutcome, baseline_distribution
    from catalyst_trader.backtest.gate import GateVerdict, _below_floor, sample_based_gate
    from catalyst_trader.quant.performance import deflated_sharpe

    th = thresholds if thresholds is not None else PAPER_GATE_THRESHOLDS
    min_sample, min_psr, n_trials = th["min_sample"], th["min_psr"], th["n_trials"]
    rows = conn.execute(
        "SELECT * FROM paper_position WHERE status='closed' AND realized_ret IS NOT NULL "
        "ORDER BY opened_at, id"
    ).fetchall()
    if not rows:
        return {"verdict": GateVerdict(go=False, reasons=["no resolved paper trades"],
                                       n_catalysts=0, min_sample=min_sample),
                "psr": None, "distribution": None}

    n = len({r["catalyst_id"] or f"position:{r['id']}" for r in rows})
    by_open: dict[str, list] = {}
    for r in rows:
        by_open.setdefault(r["opened_at"], []).append(LegOutcome(
            ticker=r["ticker"], side=r["side"], entry=r["entry_price"], fill=r["close_price"],
            exit=r["exit_by"], realized_ret=r["realized_ret"], held_through=bool(r["held_through"]),
            is_catalyst=True, hedge_ret=r["hedge_ret"], size_pct=r["size_pct"]))
    results = [BacktestResult(week=k, legs=v) for k, v in by_open.items()]
    dist = baseline_distribution(results, periods_per_year=52)
    base = sample_based_gate(dist, n_catalysts=n, thresholds=th)

    try:
        psr = deflated_sharpe([r["realized_ret"] for r in rows], n_trials=n_trials,
                              periods_per_year=52).value
    except ValueError:
        psr = None
    psr_miss = _below_floor("psr", psr, min_psr)
    reasons = base.reasons + ([psr_miss] if psr_miss else [])
    verdict = GateVerdict(go=base.go and not psr_miss, reasons=reasons, n_catalysts=n,
                          min_sample=min_sample)
    return {"verdict": verdict, "psr": psr, "distribution": dist}


def weekly_mark_pass(conn: sqlite3.Connection, as_of: str, *, quotes_fn=None, embed=None,
                     narrate=None) -> dict:
    """The headless weekly close path: mark/close (mark_open_positions) THEN attribute + post-mortem
    every newly (or previously failed) closed trade. Returns {"mark": ..., "postmortem": ...}.
    Deterministic and LLM-free unless a ``narrate`` seam is injected. Opens nothing."""
    mark = mark_open_positions(conn, as_of, quotes_fn=quotes_fn, embed=embed)
    return {"mark": mark, "postmortem": postmortem_closed(conn, embed=embed, narrate=narrate)}
