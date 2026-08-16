"""Plan 06.10-06 Task 3 — the monitor data-health tab + alerts. Offline: write a sample
.monitor/data_health.json to a temp dir, then assert the stdlib monitor reads it into the dashboard
payload and raises the alert flag on a degraded source / coverage drop (the ZeeChat ping is
best-effort and mocked — it must never block or fail the monitor)."""

import importlib.util
import json
import os
import sys

import pytest

_SERVER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "monitor", "server.py")


@pytest.fixture
def server(monkeypatch, tmp_path):
    """Import monitor/server.py safely (it reads sys.argv at import) with MONDIR pointed at tmp."""
    monkeypatch.setattr(sys, "argv", ["server.py"])
    spec = importlib.util.spec_from_file_location("fund1_monitor_server", _SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "MONDIR", str(tmp_path))
    return mod


def _write(server, payload):
    with open(os.path.join(server.MONDIR, "data_health.json"), "w") as f:
        json.dump(payload, f)


_HEALTHY = {"updated": "2026-02-06T00:00:00Z",
            "sources": {"alpha_vantage": {"last_success": "2026-02-06T00:00:00Z",
                                          "consec_fail": 0, "degraded": False}},
            "coverage_pct": 100.0, "stale_sources": [], "gaps": {"price_weeks_missing": 0},
            "divergences_this_cycle": 2, "degraded": False}


def test_sample_includes_data_health(server, monkeypatch):
    _write(server, _HEALTHY)
    # neutralise the heavy git/node/file collaborators so sample() is fast + deterministic
    for name, val in {"git_state": {"count": 0, "recent": [], "last_epoch": 0},
                      "roadmap_phases": [], "current_phase": None, "session_jsonl": None,
                      "active_agent": {}, "tokens_total": 0, "graphify_savings": {},
                      "decisions": [], "research_docs": [], "deliverables": [],
                      "blocker": None, "review_items": [], "roadmap_scope": []}.items():
        monkeypatch.setattr(server, name, lambda *a, _v=val: _v)
    payload = server.sample()
    assert "data_health" in payload
    assert payload["data_health"]["divergences_this_cycle"] == 2
    assert payload["data_health"]["coverage_pct"] == 100.0
    assert payload["data_health"]["alerts"] == []  # healthy -> no alert


def test_alert_fires_on_degraded_source(server, monkeypatch):
    pings = []
    monkeypatch.setattr(server, "_ping_alerts", lambda alerts: pings.append(alerts))
    bad = {**_HEALTHY, "sources": {"finra": {"last_success": None, "consec_fail": 4,
                                             "degraded": True}}, "degraded": True}
    _write(server, bad)
    dh = server.data_health()
    assert dh["alerts"], "no alert raised for a degraded source"
    assert any("finra" in a for a in dh["alerts"])
    assert pings, "ping was not fired (best-effort) for a degraded source"


def test_alert_on_coverage_drop(server, monkeypatch):
    monkeypatch.setattr(server, "_ping_alerts", lambda alerts: None)
    low = {**_HEALTHY, "coverage_pct": 40.0}
    _write(server, low)
    dh = server.data_health()
    assert dh["alerts"], "no alert raised on a coverage drop"
    assert any("coverage" in a.lower() for a in dh["alerts"])


def test_missing_data_health_is_empty(server):
    assert server.data_health() == {}  # no file -> empty, never a crash
