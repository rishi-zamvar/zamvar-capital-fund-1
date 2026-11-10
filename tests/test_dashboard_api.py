"""Phase 9 (09-01): the iOS dashboard serving shim — reads, the gate, auth, chat SSE, bind guard.

Offline: a migrated tmp-file db, FastAPI TestClient, and the LLM seam (run_structured) monkeypatched.
The gate assertions are the point: approve is the ONLY path that opens a paper_position and it goes
through paper_ledger.approve_pending; reject/chat/reads never open anything.
"""

import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from catalyst_trader import dashboard_api as api
from catalyst_trader import db as _db
from catalyst_trader import kb
from catalyst_trader import paper_ledger as pl
from catalyst_trader.store import upsert_bars

import scripts.serve_dashboard as serve

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}
TODAY = "2026-08-17"

REVIEW = {
    "catalyst": {"ticker": "ABCD", "catalyst_type": "pdufa", "event_date": "2026-08-20"},
    "dossier": {
        "verdict_summary": "approval likely; run-up modest",
        "kill_criteria": ["CRL on CMC"],
        "pre_mortem": ["label narrower than modeled"],
        "position_memo": "memo",
        "all_evidence_refs": ["kb:1", "https://www.fda.gov/x"],
        "trade": {"target_long": "ABCD", "entry": 10.0, "size_pct": 0.02, "stop_loss": 8.0,
                  "take_profit": 12.0, "expected_return_pct": 0.05, "sl_advisory": True,
                  "exit_by_date": "2026-08-21", "hedge": {"ticker": "PEER"}},
    },
    "dd": {"verdict": "go", "red_flags": ["thin float"], "strongest_disconfirming_evidence": "AdCom split"},
    "decision": {"decision": "enter", "rationale": "edge priced", "accepted_residuals": ["gap -> size"],
                 "dissent_preserved": ["bear: CMC"], "rounds": 2},
}


def _params(ticker="ABCD", **kw):
    p = {"ticker": ticker, "entry": 10.0, "size_pct": 0.02, "opened_at": "2026-08-14",
         "exit_by": "2026-08-21", "direction": "positive", "evidence_refs": ["kb:1"]}
    p.update(kw)
    return p


@pytest.fixture
def dbpath(tmp_path):
    path = str(tmp_path / "dash.db")
    conn = _db.connect(path)
    _db.migrate(conn)
    conn.close()
    return path


def _conn(path):
    return _db.connect(path)


def _client(path, **kw):
    kw.setdefault("today_fn", lambda: TODAY)
    return TestClient(api.create_app(path, TOKEN, **kw))


def _n_positions(path):
    return _conn(path).execute("SELECT COUNT(*) c FROM paper_position").fetchone()["c"]


# --------------------------------------------------------------- auth


def test_health_needs_no_token(dbpath):
    assert _client(dbpath).get("/api/v1/health").json() == {"ok": True}


@pytest.mark.parametrize("method,path", [
    ("get", "/api/v1/week"), ("get", "/api/v1/history"), ("get", "/api/v1/playbook"),
    ("get", "/api/v1/decisions"), ("get", "/api/v1/decisions/1"),
    ("post", "/api/v1/decisions/1/approve"), ("post", "/api/v1/decisions/1/reject"),
    ("post", "/api/v1/chat"),
])
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": TOKEN}])
def test_every_route_rejects_missing_or_wrong_token(dbpath, method, path, headers):
    r = getattr(_client(dbpath), method)(path, headers=headers)
    assert r.status_code == 401


def test_create_app_refuses_weak_token(dbpath):
    with pytest.raises(ValueError):
        api.create_app(dbpath, "short")


# --------------------------------------------------------------- the gate


def test_approve_opens_exactly_one_position_via_the_gate(dbpath):
    pid = pl.submit_for_approval(_conn(dbpath), _params(), review=REVIEW)
    c = _client(dbpath)
    r = c.post(f"/api/v1/decisions/{pid}/approve", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved" and body["position_id"] is not None
    again = c.post(f"/api/v1/decisions/{pid}/approve", headers=AUTH).json()
    assert again["position_id"] == body["position_id"]  # idempotent
    assert _n_positions(dbpath) == 1


def test_approve_absent_is_404(dbpath):
    assert _client(dbpath).post("/api/v1/decisions/999/approve", headers=AUTH).status_code == 404


def test_approve_rejected_is_409_and_opens_nothing(dbpath):
    conn = _conn(dbpath)
    pid = pl.submit_for_approval(conn, _params())
    pl.reject_pending(conn, pid)
    assert _client(dbpath).post(f"/api/v1/decisions/{pid}/approve", headers=AUTH).status_code == 409
    assert _n_positions(dbpath) == 0


def test_reject_opens_nothing_and_is_idempotent(dbpath):
    pid = pl.submit_for_approval(_conn(dbpath), _params())
    c = _client(dbpath)
    assert c.post(f"/api/v1/decisions/{pid}/reject", headers=AUTH).json()["status"] == "rejected"
    assert c.post(f"/api/v1/decisions/{pid}/reject", headers=AUTH).status_code == 200
    assert _n_positions(dbpath) == 0


def test_reject_approved_is_409_and_keeps_position(dbpath):
    conn = _conn(dbpath)
    pid = pl.submit_for_approval(conn, _params())
    pl.approve_pending(conn, pid)
    assert _client(dbpath).post(f"/api/v1/decisions/{pid}/reject", headers=AUTH).status_code == 409
    row = _conn(dbpath).execute("SELECT status FROM paper_pending WHERE id=?", (pid,)).fetchone()
    assert row["status"] == "approved"


def test_reject_absent_is_404(dbpath):
    assert _client(dbpath).post("/api/v1/decisions/5/reject", headers=AUTH).status_code == 404


def test_reads_never_open_positions(dbpath):
    pl.submit_for_approval(_conn(dbpath), _params(), review=REVIEW)
    c = _client(dbpath)
    for path in ("/api/v1/week", "/api/v1/history", "/api/v1/playbook", "/api/v1/decisions",
                 "/api/v1/decisions/1"):
        assert c.get(path, headers=AUTH).status_code == 200
    assert _n_positions(dbpath) == 0


def test_module_imports_no_live_broker_or_order_path():
    src = pathlib.Path(api.__file__).read_text() + pathlib.Path(serve.__file__).read_text()
    for banned in ("place_equity_order", "robinhood", "_open_paper_position", "INSERT INTO paper_position"):
        assert banned not in src


# --------------------------------------------------------------- decisions / dossier


def test_decisions_list_and_dossier(dbpath):
    conn = _conn(dbpath)
    pid = pl.submit_for_approval(conn, _params(), review=REVIEW)
    other = pl.submit_for_approval(conn, _params("ZZZZ"))
    pl.reject_pending(conn, other)
    c = _client(dbpath)
    pending = c.get("/api/v1/decisions", headers=AUTH).json()
    assert [d["id"] for d in pending] == [pid]
    assert pending[0]["ticker"] == "ABCD" and pending[0]["size_pct"] == 0.02
    rejected = c.get("/api/v1/decisions?status=rejected", headers=AUTH).json()
    assert [d["id"] for d in rejected] == [other]
    d = c.get(f"/api/v1/decisions/{pid}", headers=AUTH).json()
    assert d["status"] == "pending"
    assert d["params"]["exit_by"] == "2026-08-21"
    assert d["review"]["dossier"]["kill_criteria"] == ["CRL on CMC"]
    assert c.get(f"/api/v1/decisions/{other}", headers=AUTH).json()["review"] is None


def test_decisions_bad_status_is_422(dbpath):
    assert _client(dbpath).get("/api/v1/decisions?status=bogus", headers=AUTH).status_code == 422


def test_dossier_absent_is_404(dbpath):
    assert _client(dbpath).get("/api/v1/decisions/42", headers=AUTH).status_code == 404


# --------------------------------------------------------------- week


def test_week_empty_db_is_honest_empty_state(dbpath):
    w = _client(dbpath).get("/api/v1/week", headers=AUTH).json()
    assert w["as_of"] == TODAY
    assert w["benchmark_weekly"] == 0.01
    assert w["expected_return"] is None
    assert w["positions"] == [] and w["upcoming"] == [] and w["pending_count"] == 0
    assert w["sharpe"] is None and w["expectancy"] is None


def test_week_position_marks_sl_tp_and_review(dbpath):
    conn = _conn(dbpath)
    pid = pl.submit_for_approval(conn, _params(), review=REVIEW)
    pos = pl.approve_pending(conn, pid)
    pl.mark_paper_position(conn, pos, "2026-08-15", 11.0, 0.1)
    pl.submit_for_approval(conn, _params("PEND"), review=REVIEW)  # a pending one counts toward expected
    w = _client(dbpath).get("/api/v1/week", headers=AUTH).json()
    assert w["pending_count"] == 1
    assert w["expected_return"] == pytest.approx(2 * 0.02 * 0.05)
    p = w["positions"][0]
    assert p["ticker"] == "ABCD" and p["mark_price"] == 11.0
    assert p["mark_source"] == "bars" and p["mark_date"] == "2026-08-15"
    assert p["unrealized_ret"] == pytest.approx(0.1)
    assert p["dist_to_sl"] == pytest.approx((11.0 - 8.0) / 11.0)
    assert p["dist_to_tp"] == pytest.approx((12.0 - 11.0) / 11.0)
    assert p["sl_advisory"] is True
    assert p["thesis"] == "approval likely; run-up modest"
    assert p["kill_criteria"] == ["CRL on CMC"]
    assert p["failure_factors"] == ["label narrower than modeled"]
    assert p["mitigations"] == ["gap -> size"]
    assert p["hedge_ticker"] == "PEER"


def test_week_live_quote_overrides_stale_mark(dbpath):
    conn = _conn(dbpath)
    pos = pl.approve_pending(conn, pl.submit_for_approval(conn, _params(), review=REVIEW))
    pl.mark_paper_position(conn, pos, "2026-08-15", 11.0, 0.1)
    w = _client(dbpath, quotes_fn=lambda t: 9.0).get("/api/v1/week", headers=AUTH).json()
    p = w["positions"][0]
    assert p["mark_price"] == 9.0 and p["mark_source"] == "live"
    assert p["unrealized_ret"] == pytest.approx(-0.1)


def test_week_position_without_mark_or_review_is_null_not_zero(dbpath):
    conn = _conn(dbpath)
    pl.approve_pending(conn, pl.submit_for_approval(conn, _params()))
    p = _client(dbpath, quotes_fn=lambda t: None).get("/api/v1/week", headers=AUTH).json()["positions"][0]
    assert p["mark_price"] is None and p["unrealized_ret"] is None
    assert p["dist_to_sl"] is None and p["thesis"] is None and p["kill_criteria"] == []


def test_week_upcoming_catalyst_countdown(dbpath):
    from catalyst_trader import store
    from catalyst_trader.models import (Catalyst, CatalystSource, CatalystType, DatePrecision,
                                        SourceOrigin, SourceType, Status, Uncertainty)
    conn = _conn(dbpath)
    for t, d in (("ABCD", "2026-08-20"), ("FARX", "2026-10-01")):
        c = Catalyst(ticker=t, catalyst_type=CatalystType.pdufa, event_date=d,
                     date_precision=DatePrecision.day, uncertainty_type=Uncertainty.firm,
                     source_origin=SourceOrigin.curated_pdufa,
                     sources=[CatalystSource(source_name="FDA", source_url="https://www.fda.gov/x",
                                             source_type=SourceType.primary, reported_date=d,
                                             retrieved_at="2026-08-01T00:00:00Z")])
        cid = store.insert_catalyst(conn, c)
        conn.execute("UPDATE catalyst SET status=? WHERE id=?", (Status.verified.value, cid))
    conn.commit()
    up = _client(dbpath).get("/api/v1/week", headers=AUTH).json()["upcoming"]
    assert up == [{"ticker": "ABCD", "catalyst_type": "pdufa", "event_date": "2026-08-20", "days_until": 3}]


# --------------------------------------------------------------- history


def _closed(conn, ticker, realized, exit_by, review=REVIEW):
    pos = pl.approve_pending(conn, pl.submit_for_approval(conn, _params(ticker, exit_by=exit_by),
                                                          review=review))
    pl.close_paper_position(conn, pos, close_price=10.0 * (1 + realized), realized_ret=realized)
    return pos


def test_history_empty(dbpath):
    h = _client(dbpath).get("/api/v1/history", headers=AUTH).json()
    assert h["trades"] == [] and h["equity_curve"] == [] and h["calibration"] == []
    assert h["win_rate"] is None and h["sharpe"] is None and h["expectancy"] is None
    assert h["attribution"] is None and h["attribution_status"] == "pending_phase_8"


def test_history_metrics_curve_and_calibration(dbpath):
    conn = _conn(dbpath)
    _closed(conn, "AAAA", 0.10, "2026-08-21")
    _closed(conn, "BBBB", -0.05, "2026-08-28", review=None)
    _closed(conn, "CCCC", 0.02, "2026-09-04")
    h = _client(dbpath).get("/api/v1/history", headers=AUTH).json()
    assert [t["ticker"] for t in h["trades"]] == ["AAAA", "BBBB", "CCCC"]
    assert h["trades"][0]["book_ret"] == pytest.approx(0.02 * 0.10)
    assert h["trades"][1]["predicted"] is None
    assert h["win_rate"] == pytest.approx(2 / 3)
    assert h["expectancy"] == pytest.approx((0.10 - 0.05 + 0.02) / 3)
    assert h["sharpe"] is not None
    eq = [p["equity"] for p in h["equity_curve"]]
    assert eq[0] == 1.0
    assert eq[-1] == pytest.approx((1 + 0.002) * (1 - 0.001) * (1 + 0.0004))
    assert h["calibration"] == [
        {"ticker": "AAAA", "predicted": 0.05, "realized": 0.10},
        {"ticker": "CCCC", "predicted": 0.05, "realized": 0.02},
    ]
    assert h["attribution"] is None


def test_history_single_trade_sharpe_is_null_not_fabricated(dbpath):
    _closed(_conn(dbpath), "AAAA", 0.10, "2026-08-21")
    h = _client(dbpath).get("/api/v1/history", headers=AUTH).json()
    assert h["sharpe"] is None and h["win_rate"] == 1.0


# --------------------------------------------------------------- playbook


def test_playbook_lists_scenarios_confidence_desc_excludes_fitted_params(dbpath):
    conn = _conn(dbpath)
    ev = [kb.EvidenceSource(url="kb:1", retrieved_at="2026-08-01T00:00:00Z", snippet_hash="h")]
    kb.insert_playbook(conn, "pdufa", "clean approvals drift up", {
        "n": 12, "median_move": 0.08, "base_rate": {"approve": 0.8}, "what_to_watch": ["AdCom"]}, 0.6, ev)
    kb.insert_playbook(conn, "trial_readout", "free text strategy", "buy the dip", 0.9, ev)
    kb.insert_playbook(conn, "fitted_params:pdufa", "bootstrap", "{}", 0.3, ev)
    pb = _client(dbpath).get("/api/v1/playbook", headers=AUTH).json()
    assert [p["scenario_type"] for p in pb["playbooks"]] == ["trial_readout", "pdufa"]
    first, second = pb["playbooks"]
    assert first["confidence"] == 0.9 and first["strategy_text"] == "buy the dip"
    assert first["what_to_watch"] == [] and first["n"] is None
    assert second["n"] == 12 and second["median_move"] == 0.08
    assert second["base_rate"] == {"approve": 0.8} and second["what_to_watch"] == ["AdCom"]
    assert pb["kb_counts"]["playbook"] == 3


# --------------------------------------------------------------- chat (SSE)


def _events(text):
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_chat_streams_answer_with_context_in_prompt(dbpath):
    conn = _conn(dbpath)
    pl.approve_pending(conn, pl.submit_for_approval(conn, _params(), review=REVIEW))
    pl.submit_for_approval(conn, _params("PEND"), review=REVIEW)
    seen = {}

    async def fake_chat(prompt):
        seen["prompt"] = prompt
        return "We hold ABCD because the edge is priced."

    r = _client(dbpath, chat_fn=fake_chat).post("/api/v1/chat", headers=AUTH,
                                                 json={"message": "Why ABCD?"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    evs = _events(r.text)
    assert evs[0] == ("delta", {"text": "We hold ABCD because the edge is priced."})
    assert evs[-1][0] == "done"
    assert "Why ABCD?" in seen["prompt"]
    assert "ABCD" in seen["prompt"] and "PEND" in seen["prompt"]
    assert "edge priced" in seen["prompt"]  # the MD's own rationale is in context
    assert _n_positions(dbpath) == 1  # chat never opens anything


def test_chat_failure_streams_error_event(dbpath):
    async def boom(prompt):
        raise RuntimeError("model down")

    r = _client(dbpath, chat_fn=boom).post("/api/v1/chat", headers=AUTH, json={"message": "hi"})
    assert r.status_code == 200
    assert _events(r.text) == [("error", {"message": "model down"})]


def test_chat_empty_message_is_422(dbpath):
    r = _client(dbpath).post("/api/v1/chat", headers=AUTH, json={"message": "  "})
    assert r.status_code == 422


async def test_default_chat_goes_through_the_seam_with_no_tools(monkeypatch):
    from catalyst_trader.desk import runtime

    captured = {}

    async def fake_query(prompt, options):
        captured["opts"] = options

        class Msg:
            result = json.dumps({"answer": "seam answer"})
        yield Msg()

    monkeypatch.setattr(runtime, "query", fake_query)
    assert await api.default_chat("question") == "seam answer"
    opts = captured["opts"]
    assert opts.tools == [] and opts.allowed_tools == []


# --------------------------------------------------------------- launcher bind guard


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "100.64.0.1", "100.91.236.115", "100.127.255.254"])
def test_bind_guard_allows_loopback_and_tailscale(host):
    assert serve.check_bind_host(host) == host


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.5", "10.0.0.2", "8.8.8.8",
                                  "100.128.0.1", "100.63.255.255", "localhost", "my-mac", ""])
def test_bind_guard_refuses_everything_else(host):
    with pytest.raises(ValueError):
        serve.check_bind_host(host)


def test_load_token_requires_strong_secret(monkeypatch):
    monkeypatch.delenv("DASHBOARD_TOKEN", raising=False)
    with pytest.raises(ValueError):
        serve.load_token()
    monkeypatch.setenv("DASHBOARD_TOKEN", "short")
    with pytest.raises(ValueError):
        serve.load_token()
    monkeypatch.setenv("DASHBOARD_TOKEN", TOKEN)
    assert serve.load_token() == TOKEN
