"""dashboard_api.py (Phase 9) — the FastAPI + SSE shim the iOS dashboard talks to over Tailscale.

READ-ONLY views of the paper book (this week, history, playbook, the diligence dossier) plus exactly
TWO write endpoints — approve / reject a PENDING decision — which call the existing gate verbatim
(paper_ledger.approve_pending / reject_pending). Nothing here can open a position any other way, and
no live-broker module is imported (Phase 11 is strictly last). The MD chat runs through the single
mocked LLM seam (desk.runtime.run_structured) with every built-in tool removed — the MD can explain,
never act.

Auth: one shared-secret bearer token (constant-time compare) on every /api/v1 route but /health.
Binding (loopback / Tailscale only) is enforced by the launcher, scripts/serve_dashboard.py.
# ponytail: one module, plain sqlite reads, a connection per request; no ORM, no service layer.
"""

from __future__ import annotations

import hmac
import json
from contextlib import closing
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from catalyst_trader import db as _db
from catalyst_trader import paper_ledger, serving
from catalyst_trader.backtest.engine import _net_return
from catalyst_trader.quant import performance

BENCHMARK_WEEKLY = 0.01      # the fund's ~1%/week objective (PROJECT.md core value)
UPCOMING_DAYS = 7            # the one-week hold horizon -> the catalyst countdown window
MIN_TOKEN_LEN = 16


class ChatRequest(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must be non-empty")
        return v


class MDChatReply(BaseModel):
    """The MD's structured chat answer (the run_structured contract for the chat role)."""
    answer: str


async def default_chat(prompt: str) -> str:
    """The real MD chat: one structured call through the mocked seam, NO tools (read-only)."""
    from catalyst_trader.desk import runtime

    reply = await runtime.run_structured(prompt, MDChatReply, allowed_tools=[], tools=[])
    return reply.answer


# --------------------------------------------------------------- pure read helpers


def _metric(fn, *args):
    """A quant.performance value, or None when the series is too short / degenerate (honest empty)."""
    try:
        return fn(*args).value
    except ValueError:
        return None


def _review_for_position(conn, position_id: int) -> dict | None:
    row = conn.execute("SELECT review FROM paper_pending WHERE position_id=?", (position_id,)).fetchone()
    return json.loads(row["review"]) if row and row["review"] else None


def _trade(review: dict | None) -> dict:
    return ((review or {}).get("dossier") or {}).get("trade") or {}


def _position_view(conn, pos: dict, quotes_fn) -> dict:
    review = _review_for_position(conn, pos["id"])
    dossier = (review or {}).get("dossier") or {}
    trade = _trade(review)
    live = quotes_fn(pos["ticker"]) if quotes_fn else None
    if live is not None:
        price, source, mark_date = live, "live", None
    else:
        m = conn.execute("SELECT mark_price, source, mark_date FROM paper_mark WHERE position_id=? "
                         "ORDER BY mark_date DESC LIMIT 1", (pos["id"],)).fetchone()
        price, source, mark_date = (m["mark_price"], m["source"], m["mark_date"]) if m else (None, None, None)
    sl, tp = trade.get("stop_loss"), trade.get("take_profit")
    return {
        "id": pos["id"], "ticker": pos["ticker"], "entry_price": pos["entry_price"],
        "size_pct": pos["size_pct"], "opened_at": pos["opened_at"], "exit_by": pos["exit_by"],
        "direction": pos["direction"],
        "mark_price": price, "mark_source": source, "mark_date": mark_date,
        # a mark is not a round-trip: no exit spread (mirrors paper_ledger.mark_open_positions)
        "unrealized_ret": _net_return(pos["entry_price"], price, apply_costs=False) if price else None,
        "stop_loss": sl, "take_profit": tp,
        "dist_to_sl": (price - sl) / price if price and sl is not None else None,
        "dist_to_tp": (tp - price) / price if price and tp is not None else None,
        "sl_advisory": trade.get("sl_advisory"),
        "hedge_ticker": (trade.get("hedge") or {}).get("ticker"),
        "thesis": dossier.get("verdict_summary"),
        "kill_criteria": dossier.get("kill_criteria") or [],
        "failure_factors": dossier.get("pre_mortem") or [],
        "mitigations": ((review or {}).get("decision") or {}).get("accepted_residuals") or [],
    }


def _decision_summary(row) -> dict:
    p = json.loads(row["params"])
    return {
        "id": row["id"], "status": row["status"], "submitted_at": row["submitted_at"],
        "resolved_at": row["resolved_at"], "position_id": row["position_id"],
        "ticker": p.get("ticker"), "entry": p.get("entry"), "size_pct": p.get("size_pct"),
        "exit_by": p.get("exit_by"), "direction": p.get("direction"),
    }


def _pending_rows(conn, status: str = "pending"):
    return conn.execute("SELECT * FROM paper_pending WHERE status=? ORDER BY id", (status,)).fetchall()


def _history(conn) -> dict:
    rows = conn.execute("SELECT * FROM paper_position WHERE status='closed' ORDER BY exit_by, id").fetchall()
    trades, weekly = [], {}
    for r in rows:
        predicted = _trade(_review_for_position(conn, r["id"])).get("expected_return_pct")
        book_ret = r["size_pct"] * r["realized_ret"]
        weekly[r["exit_by"]] = weekly.get(r["exit_by"], 0.0) + book_ret
        trades.append({
            "id": r["id"], "ticker": r["ticker"], "opened_at": r["opened_at"], "exit_by": r["exit_by"],
            "closed_at": r["closed_at"], "entry_price": r["entry_price"], "close_price": r["close_price"],
            "size_pct": r["size_pct"], "realized_ret": r["realized_ret"], "book_ret": book_ret,
            "predicted": predicted, "win": r["realized_ret"] > 0,
        })
    curve, equity = [], 1.0
    if trades:
        curve.append({"date": trades[0]["opened_at"], "equity": 1.0})
        for week_end, ret in weekly.items():  # dict keeps exit_by order
            equity *= 1 + ret
            curve.append({"date": week_end, "equity": equity})
    realized = [t["realized_ret"] for t in trades]
    return {
        "trades": trades,
        "equity_curve": curve,
        "win_rate": _metric(performance.win_rate, realized),
        "expectancy": sum(realized) / len(realized) if realized else None,  # mean per-trade return
        "sharpe": _metric(performance.sharpe, list(weekly.values()), 52),
        "calibration": [{"ticker": t["ticker"], "predicted": t["predicted"], "realized": t["realized_ret"]}
                        for t in trades if t["predicted"] is not None],
        # Phase 8 attribution (catalyst vs beta vs hedge vs sizing) is built in parallel — explicit
        # empty state until its contract lands; the app renders "pending Phase 8".
        "attribution": None,
        "attribution_status": "pending_phase_8",
    }


def _week(conn, today: str, quotes_fn) -> dict:
    positions = [_position_view(conn, p, quotes_fn) for p in paper_ledger.get_open_positions(conn)]
    pending = _pending_rows(conn)
    legs = [_trade(_review_for_position(conn, p["id"])) for p in positions]
    legs += [_trade(json.loads(r["review"]) if r["review"] else None) for r in pending]
    legs = [t for t in legs if t.get("expected_return_pct") is not None and t.get("size_pct") is not None]
    horizon = (date.fromisoformat(today) + timedelta(days=UPCOMING_DAYS)).isoformat()
    upcoming = sorted(
        ({"ticker": c.ticker, "catalyst_type": c.catalyst_type.value, "event_date": c.event_date,
          "days_until": (date.fromisoformat(c.event_date[:10]) - date.fromisoformat(today)).days}
         for c in serving.asof(conn).catalysts() if today <= c.event_date[:10] <= horizon),
        key=lambda c: c["event_date"])
    hist = _history(conn)
    return {
        "as_of": today,
        "benchmark_weekly": BENCHMARK_WEEKLY,
        "expected_return": sum(t["size_pct"] * t["expected_return_pct"] for t in legs) if legs else None,
        "sharpe": hist["sharpe"],
        "expectancy": hist["expectancy"],
        "pending_count": len(pending),
        "upcoming": upcoming,
        "positions": positions,
    }


def _playbook(conn) -> dict:
    out = []
    for n in serving.asof(conn).kb_nodes(kind="playbook"):
        a = json.loads(n["attrs_json"])
        if a["scenario_type"].startswith("fitted_params:"):
            continue  # parameter sets are config, not scenario playbooks
        s = a["strategy"]
        if isinstance(s, str):
            try:
                s = json.loads(s)
            except ValueError:
                pass
        struct = s if isinstance(s, dict) else {}
        out.append({
            "id": n["id"], "scenario_type": a["scenario_type"], "scenario": str(a["scenario"]),
            "confidence": n["confidence"],
            "strategy_text": s if isinstance(s, str) else None,
            "n": struct.get("n"), "median_move": struct.get("median_move"),
            "base_rate": struct.get("base_rate") or {}, "what_to_watch": struct.get("what_to_watch") or [],
        })
    out.sort(key=lambda p: -(p["confidence"] or 0))
    counts = {r["kind"]: r["c"] for r in conn.execute("SELECT kind, COUNT(*) c FROM kb_node GROUP BY kind")}
    return {"playbooks": out, "kb_counts": counts}


def _chat_prompt(conn, message: str, today: str, quotes_fn) -> str:
    context = {
        "open_positions": [_position_view(conn, p, quotes_fn) for p in paper_ledger.get_open_positions(conn)],
        "pending_decisions": [{**_decision_summary(r), "review": json.loads(r["review"]) if r["review"] else None}
                              for r in _pending_rows(conn)],
    }
    return (
        "You are the Managing Director (GP) of Zamvar Capital Fund 1, a paper-trading biotech catalyst "
        "desk. The LP is asking you about positioning, rationale and risk. Answer ONLY from the book "
        "context below; if it does not contain the answer, say so. You cannot approve, reject or place "
        "trades — the LP decides in the app.\n\n"
        f"as_of: {today}\nBOOK CONTEXT (JSON):\n{json.dumps(context, default=str)}\n\n"
        f"LP question: {message}"
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# --------------------------------------------------------------- the app


def create_app(db_path: str, token: str, *, chat_fn=None, quotes_fn=None, today_fn=None) -> FastAPI:
    """Build the dashboard app over `db_path`. `chat_fn(prompt)->str` (async) defaults to the MD seam;
    `quotes_fn(ticker)->last|None` is an optional read-only live quote; `today_fn()->'YYYY-MM-DD'`."""
    if not token or len(token) < MIN_TOKEN_LEN:
        raise ValueError(f"dashboard token must be at least {MIN_TOKEN_LEN} characters")
    chat_fn = chat_fn or default_chat
    today_fn = today_fn or (lambda: date.today().isoformat())
    expected = f"Bearer {token}".encode()

    def require_token(authorization: str = Header(default="")) -> None:
        if not hmac.compare_digest(authorization.encode(), expected):
            raise HTTPException(status_code=401, detail="unauthorized")

    def conn():
        return closing(_db.connect(db_path))

    app = FastAPI(title="Fund 1 Dashboard", docs_url=None, redoc_url=None, openapi_url=None)
    v1 = APIRouter(prefix="/api/v1", dependencies=[Depends(require_token)])

    @app.get("/api/v1/health")
    def health():
        return {"ok": True}

    @v1.get("/week")
    def week():
        with conn() as c:
            return _week(c, today_fn(), quotes_fn)

    @v1.get("/history")
    def history():
        with conn() as c:
            return _history(c)

    @v1.get("/playbook")
    def playbook():
        with conn() as c:
            return _playbook(c)

    @v1.get("/decisions")
    def decisions(status: Literal["pending", "approved", "rejected"] = "pending"):
        with conn() as c:
            return [_decision_summary(r) for r in _pending_rows(c, status)]

    def _row_or_404(c, pending_id: int):
        row = c.execute("SELECT * FROM paper_pending WHERE id=?", (pending_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"no pending decision {pending_id}")
        return row

    @v1.get("/decisions/{pending_id}")
    def dossier(pending_id: int):
        with conn() as c:
            row = _row_or_404(c, pending_id)
            return {**_decision_summary(row), "params": json.loads(row["params"]),
                    "review": json.loads(row["review"]) if row["review"] else None}

    # --- the ONLY two writes: both route to the existing gate, verbatim ---

    @v1.post("/decisions/{pending_id}/approve")
    def approve(pending_id: int):
        with conn() as c:
            _row_or_404(c, pending_id)
            position_id = paper_ledger.approve_pending(c, pending_id)  # the SOLE opener
            if position_id is None:
                raise HTTPException(status_code=409, detail=f"decision {pending_id} was rejected — not approvable")
            return {"id": pending_id, "status": "approved", "position_id": position_id}

    @v1.post("/decisions/{pending_id}/reject")
    def reject(pending_id: int):
        with conn() as c:
            row = _row_or_404(c, pending_id)
            if row["status"] == "approved":
                raise HTTPException(status_code=409, detail=f"decision {pending_id} is already approved")
            paper_ledger.reject_pending(c, pending_id)
            return {"id": pending_id, "status": "rejected", "position_id": None}

    @v1.post("/chat")
    async def chat(req: ChatRequest):
        with conn() as c:
            prompt = _chat_prompt(c, req.message, today_fn(), quotes_fn)

        async def stream():
            try:
                answer = await chat_fn(prompt)
            except Exception as exc:  # surface to the app as an SSE error, never a broken stream
                yield _sse("error", {"message": str(exc)})
                return
            yield _sse("delta", {"text": answer})
            yield _sse("done", {})

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    app.include_router(v1)
    return app
