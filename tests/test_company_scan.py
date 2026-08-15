"""Phase 6.8 Plan 01 — company-card store (migration 006 + store fns) + scan contracts.

Mirrors the price-bar store discipline (tests/test_price_store.py): write-once per
(ticker, week_end), point-in-time reads with the week_end <= as_of no-look-ahead guard.
"""

import copy
import inspect

import pytest
from pydantic import ValidationError

from catalyst_trader import store
from catalyst_trader.contracts import KeyFinding, OpportunityFlag, ScanInput, WeeklyFlag
from catalyst_trader.desk import company_scan


# --- Task 1: company_card + scan_flag store ------------------------------------------------


def test_card_written_once_per_ticker_week(db):
    """A second write for the same (ticker, week_end) UPDATES in place — one row, latest wins."""
    store.write_card(db, "ABCD", "2026-01-02", {"price": 10.0, "note": "v1"})
    store.write_card(db, "ABCD", "2026-01-02", {"price": 11.0, "note": "v2"})

    rows = db.execute(
        "SELECT COUNT(*) AS n FROM company_card WHERE ticker=? AND week_end=?",
        ("ABCD", "2026-01-02"),
    ).fetchone()
    assert rows["n"] == 1  # UNIQUE(ticker, week_end) — no duplicate row

    card = store.card_asof(db, "ABCD", "2026-01-02")
    assert card == {"price": 11.0, "note": "v2"}  # second content is what we read back


def test_card_asof_never_returns_future(db):
    """card_asof returns the latest card with week_end <= as_of, NEVER a future card."""
    store.write_card(db, "ABCD", "2026-01-02", {"wk": "W1"})
    store.write_card(db, "ABCD", "2026-01-16", {"wk": "W3"})

    # as_of between W1 and W3 -> W1, never the future W3 (no look-ahead, the money invariant)
    assert store.card_asof(db, "ABCD", "2026-01-09") == {"wk": "W1"}
    # as_of before the earliest card -> None
    assert store.card_asof(db, "ABCD", "2025-12-01") is None
    # as_of at/after W3 -> W3
    assert store.card_asof(db, "ABCD", "2026-01-16") == {"wk": "W3"}


def test_scan_flag_round_trips_and_is_pointintime(db):
    """write_scan_flag persists a JSON payload once per (ticker, week_end); scan_flags_asof
    reads payloads with week_end <= as_of (audit ledger), never a future one."""
    store.write_scan_flag(db, "ABCD", "2026-01-02", {"opportunity_type": "no_opportunity"})
    store.write_scan_flag(db, "ABCD", "2026-01-02", {"opportunity_type": "squeeze_setup"}, routed=True)
    store.write_scan_flag(db, "ABCD", "2026-01-16", {"opportunity_type": "dilution_risk"})

    n = db.execute(
        "SELECT COUNT(*) AS n FROM scan_flag WHERE ticker=? AND week_end=?",
        ("ABCD", "2026-01-02"),
    ).fetchone()["n"]
    assert n == 1  # idempotent per (ticker, week_end)

    asof = store.scan_flags_asof(db, "ABCD", "2026-01-09")
    assert asof == [{"opportunity_type": "squeeze_setup"}]  # future W3 flag excluded


# --- Task 2: ScanInput firewall + OpportunityFlag contract ---------------------------------


def test_scan_input_firewall_forbids_desk_artifacts():
    """ScanInput carries ONLY {ticker, week_end, card_prev, card_cur, tripped} — any desk
    artifact (verdict/thesis/position/direction) is a ValidationError, not a policy check."""
    # clean construction succeeds
    ok = ScanInput(ticker="ABCD", week_end="2026-01-02", card_cur={"price": 10.0})
    assert ok.card_prev is None and ok.tripped == []

    for leak in ("verdict", "thesis", "position", "direction"):
        with pytest.raises(ValidationError):
            ScanInput(ticker="ABCD", week_end="2026-01-02", card_cur={}, **{leak: "x"})


def _flag(**over):
    base = dict(
        ticker="ABCD",
        week_end="2026-01-02",
        opportunity_type="catalyst_vol",
        thesis_to_verify="PDUFA within 2 weeks could drive a >20% move",
        verification_needed="catalyst_call",
        key_findings=[KeyFinding(claim="PDUFA 2026-01-20", evidence_ref="kb:1")],
        confidence=0.4,
    )
    base.update(over)
    return OpportunityFlag(**base)


def test_flag_vocabulary_fixed():
    """opportunity_type + verification_needed accept ONLY their fixed vocabularies."""
    for ot in ("catalyst_vol", "squeeze_setup", "dilution_risk", "technical_reversal",
               "continuation", "competitor_event", "unknown_vol", "no_opportunity"):
        _flag(opportunity_type=ot)
    for vn in ("catalyst_call", "measured_edge", "mini_backtest", "diligence"):
        _flag(verification_needed=vn)
    with pytest.raises(ValidationError):
        _flag(opportunity_type="buy")
    with pytest.raises(ValidationError):
        _flag(verification_needed="yolo")


def test_flag_carries_gap_not_answer():
    """OpportunityFlag exposes the gap-not-answer payload and NO answer-shaped field."""
    fields = set(OpportunityFlag.model_fields.keys())
    assert {"thesis_to_verify", "verification_needed"} <= fields
    assert fields.isdisjoint({"direction", "size", "size_pct", "target", "route"})
    # no_opportunity is a first-class outcome; confidence bounded [0,1]
    _flag(opportunity_type="no_opportunity")
    with pytest.raises(ValidationError):
        _flag(confidence=1.5)


# --- Plan 02 Task 1: SCAN_PARAMS + build_card (deterministic, point-in-time, no recompute) ---

_ROW = {  # a verbatim quant.weekly.thesis_scan detail row (build_card embeds it, never recomputes)
    "ticker": "ABCD", "thesis_type": "mean_reversion", "trigger": "drop_5_10",
    "drop_class": "idio_no_news", "p": 0.58, "mean_next": 0.012, "n_effective": 9,
    "eligible": True, "veto_reasons": [], "ret_1w": -0.08, "tool_ref": "tool:thesis_scan#abc123",
}


def test_card_point_in_time(db):
    """build_card at week T derives price/vol ONLY from bars_asof (week_end <= T) — no look-ahead:
    ret_1w at W2 is close_W2/close_W1-1, computed off the W1..W2 window, never the W3/W4 bars."""
    store.upsert_bars(db, "ABCD", [
        {"week_end": "2026-01-02", "close": 100.0, "volume": 1_000},
        {"week_end": "2026-01-09", "close": 110.0, "volume": 1_100},
        {"week_end": "2026-01-16", "close": 200.0, "volume": 9_000},  # future spike, must be unseen
        {"week_end": "2026-01-23", "close": 50.0, "volume": 20_000},
    ])
    card = company_scan.build_card(db, "ABCD", "2026-01-09", raw={}, thesis_row=_ROW)
    assert card["price_vol"]["ret_1w"] == pytest.approx(0.10)   # 110/100-1, NOT the W3/W4 bars
    assert card["week_end"] == "2026-01-09"
    assert card["card_version"] == "1"
    assert card["fired"] == {}                                   # no prior card -> empty latch state


def test_card_embeds_thesis_row_no_recompute(db, monkeypatch):
    """build_card EMBEDS the thesis row verbatim and recomputes NO quant number: monkeypatch the
    weekly quant fns to RAISE — build_card still completes and returns the row untouched."""
    import catalyst_trader.quant.weekly as wk

    def _boom(*a, **k):
        raise AssertionError("build_card must not recompute a quant number")

    monkeypatch.setattr(wk, "weekly_base_rate", _boom)
    monkeypatch.setattr(wk, "classify_drop", _boom)
    monkeypatch.setattr(wk, "thesis_scan", _boom)

    store.upsert_bars(db, "ABCD", [
        {"week_end": "2026-01-02", "close": 100.0, "volume": 1_000},
        {"week_end": "2026-01-09", "close": 92.0, "volume": 1_100},
    ])
    card = company_scan.build_card(db, "ABCD", "2026-01-09", raw={}, thesis_row=_ROW)
    assert card["thesis_row"] == _ROW                            # verbatim, byte-for-byte
    assert card["thesis_ref"] == "tool:thesis_scan#abc123"


# --- Plan 02 Task 2: delta_card (F1-F13 transitions, latching, hysteresis, cadence, tier gate) ---


def _mk(week_end, *, fired=None, **groups):
    """Minimal card factory for delta_card tests — empty groups; only the flag's fields set."""
    base = {
        "ticker": "ABCD", "week_end": week_end,
        "catalyst": {}, "options": {}, "positioning": {}, "price_vol": {},
        "balance_sheet": {}, "thesis_row": {}, "thesis_ref": None,
        "fired": dict(fired or {}), "card_version": "1",
    }
    for k, v in groups.items():
        base[k] = {**base[k], **v} if isinstance(base.get(k), dict) else v
    return base


def _tripped_flags(tripped):
    return {t["flag"] for t in tripped}


def test_delta_pure_and_reproducible():
    """delta_card(prev, cur, *, params) is pure — signature has NO conn/network arg, and identical
    input state yields identical tripped lists (built on fresh copies each call)."""
    import copy
    import inspect

    sig = inspect.signature(company_scan.delta_card)
    assert list(sig.parameters) == ["prev", "cur", "params"]
    assert "conn" not in sig.parameters

    def fresh():
        prev = _mk("2026-01-02", positioning={"short_interest": 0.10, "days_to_cover": 1.0,
                                               "si_settlement_date": "2025-12-31"})
        cur = _mk("2026-01-09", positioning={"short_interest": 0.14, "days_to_cover": 1.2,
                                             "si_settlement_date": "2026-01-15"})
        return prev, cur

    p1, c1 = fresh()
    t1 = company_scan.delta_card(p1, c1)
    p2, c2 = fresh()
    t2 = company_scan.delta_card(p2, c2)
    assert t1 == t2                                  # reproducible: same state -> same fires
    assert _tripped_flags(t1) == {"F6"}             # only the SI shift on a new settlement date
    assert copy.deepcopy(t1) == t2                  # values, not identities


def test_band_transition_fires_level_does_not():
    """A band/sign TRANSITION fires once; a standing (latched, same-settlement) level does not
    re-fire (latching + cadence honesty on F6)."""
    prev = _mk("2026-01-02", positioning={"short_interest": 0.10, "si_settlement_date": "2025-12-31"})
    week_a = _mk("2026-01-09", positioning={"short_interest": 0.13, "si_settlement_date": "2026-01-15"})
    trip_a = company_scan.delta_card(prev, week_a)
    assert "F6" in _tripped_flags(trip_a)           # rel step 0.30 >= 0.20 on a NEW settlement

    # week B: SI held, SAME settlement date -> no new datum -> F6 does not re-fire (cadence)
    week_b = _mk("2026-01-16", fired=week_a["fired"],
                 positioning={"short_interest": 0.13, "si_settlement_date": "2026-01-15"})
    trip_b = company_scan.delta_card(week_a, week_b)
    assert "F6" not in _tripped_flags(trip_b)


def test_hysteresis_rearm_at_half_threshold():
    """A latched flag (F7 vol_regime) re-arms ONLY after the metric retreats past
    hysteresis_rearm_frac (0.5) of the threshold distance; a partial retreat does not re-arm."""
    T = company_scan.SCAN_PARAMS["scan"]["vol_regime_ratio"]   # 2.0 -> re-arm line 1.0

    # week A: ratio 1.5 -> 2.5 crosses up -> F7 fires + latches
    prev = _mk("2026-01-02", price_vol={"sigma5": 1.5, "sigma20": 1.0})
    wk_a = _mk("2026-01-09", price_vol={"sigma5": 2.5, "sigma20": 1.0})
    trip_a = company_scan.delta_card(prev, wk_a)
    assert "F7" in _tripped_flags(trip_a) and "F7" in wk_a["fired"]

    # week B: partial retreat to ratio 1.5 (> re-arm line 1.0) -> stays latched, no fire, no re-arm
    wk_b = _mk("2026-01-16", fired=wk_a["fired"], price_vol={"sigma5": 1.5, "sigma20": 1.0})
    trip_b = company_scan.delta_card(wk_a, wk_b)
    assert "F7" not in _tripped_flags(trip_b) and "F7" in wk_b["fired"]

    # week C: full retreat to ratio 0.8 (< re-arm line 1.0) -> re-arms (drops the latch), no fire
    wk_c = _mk("2026-01-23", fired=wk_b["fired"], price_vol={"sigma5": 0.8, "sigma20": 1.0})
    trip_c = company_scan.delta_card(wk_b, wk_c)
    assert "F7" not in _tripped_flags(trip_c) and "F7" not in wk_c["fired"]

    # week D: re-armed -> a fresh cross-up fires again
    wk_d = _mk("2026-01-30", fired=wk_c["fired"], price_vol={"sigma5": 2.5, "sigma20": 1.0})
    trip_d = company_scan.delta_card(wk_c, wk_d)
    assert "F7" in _tripped_flags(trip_d)
    assert T == 2.0


def test_si_delta_only_on_new_settlement_date():
    """F6 fires ONLY on a NEW si_settlement_date — an identical SI jump with the SAME settlement
    date does not fire (bi-monthly FINRA cadence honesty)."""
    prev = _mk("2026-01-02", positioning={"short_interest": 0.10, "si_settlement_date": "2025-12-31"})

    # same settlement date -> no fire even though SI jumped 40%
    same = _mk("2026-01-09", positioning={"short_interest": 0.14, "si_settlement_date": "2025-12-31"})
    assert "F6" not in _tripped_flags(company_scan.delta_card(prev, same))

    # new settlement date -> the same jump fires
    fresh = _mk("2026-01-09", positioning={"short_interest": 0.14, "si_settlement_date": "2026-01-15"})
    assert "F6" in _tripped_flags(company_scan.delta_card(prev, fresh))


def test_wakes_tier_gate():
    """The wake gate wakes on ANY PRINCIPAL or >=2 CORROBORATORs; a lone CORROBORATOR never wakes."""
    principal = [{"flag": "F1", "tier": "PRINCIPAL"}]
    one_corr = [{"flag": "F11", "tier": "CORROBORATOR"}]
    two_corr = [{"flag": "F7", "tier": "CORROBORATOR"}, {"flag": "F11", "tier": "CORROBORATOR"}]
    assert company_scan._wakes(principal, company_scan.SCAN_PARAMS) is True
    assert company_scan._wakes(one_corr, company_scan.SCAN_PARAMS) is False
    assert company_scan._wakes(two_corr, company_scan.SCAN_PARAMS) is True
    assert company_scan._wakes([], company_scan.SCAN_PARAMS) is False


# ============================================================================
# Plan 03 Task 1 — SCAN_PROMPT + run_scan (ONE Haiku pass per woken name, cite-or-drop)
#
# Fully offline: every test monkeypatches company_scan.run_structured. Cards are built
# from raw + (optional) bars; F1 (days_to_catalyst crossing a band) is the cheapest
# PRINCIPAL wake trigger — no bars needed.
# ============================================================================


def _canned(**over):
    """A canned Haiku OpportunityFlag (confidence 0.7 -> no escalation) — the fake LLM return."""
    base = dict(
        ticker="ABCD",
        week_end="2026-01-09",
        opportunity_type="catalyst_vol",
        thesis_to_verify="a PDUFA inside 2 weeks could drive a >20% move",
        verification_needed="catalyst_call",
        key_findings=[KeyFinding(claim="PDUFA 2026-01-19", evidence_ref="tool:analog_query#abc123abc123")],
        kb_analogs=["tool:query_playbooks#cafe12345678"],
        tripped_flags=["F1"],
        confidence=0.7,
    )
    base.update(over)
    return OpportunityFlag(**base)


def _fake_llm(op, calls=None):
    """A fake run_structured that returns `op` (recording the model tier if `calls` given)."""
    async def _f(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        if calls is not None:
            calls.append(model)
        return op
    return _f


def _seed_baseline(db, ticker, *, days, thesis_row=None, week="2026-01-02"):
    """Write a prior-week card so the trip week has a `prev` to delta against."""
    card = company_scan.build_card(db, ticker, week, raw={"days_to_catalyst": days},
                                   thesis_row=thesis_row or {})
    store.write_card(db, ticker, week, card)


def test_scan_prompt_carries_hard_rules_and_three_questions():
    """SCAN_PROMPT carries the DD HARD RULES (call-the-tool / cite-or-drop / fill-unknowns) + the
    three scanner questions (interest / explorable / build-or-verify) + the adversarial framing."""
    low = company_scan.SCAN_PROMPT.lower()
    assert "cite" in low                       # cite-or-drop
    assert "call" in low and "mcp__quant__" in low   # call the tool, never compute
    assert "unknown" in low                    # fill unknowns
    assert "interest" in low                   # Q1
    assert "explor" in low or "real opportunity" in low   # Q2
    assert "verify" in low or "build" in low   # Q3
    assert "noise" in low or "priced in" in low or "untradeable" in low  # adversarial framing


async def test_no_llm_when_no_material_delta(db, monkeypatch):
    """20 unchanged names (no tripped flag) never reach Stage-2; each gets a stored no-op row."""
    async def _boom(*a, **k):
        raise AssertionError("Stage-2 must not run on a no-delta name")
    monkeypatch.setattr(company_scan, "run_structured", _boom)

    raw_by, rows = {}, {}
    for i in range(20):
        t = f"T{i:02d}"
        _seed_baseline(db, t, days=20)
        raw_by[t] = {"days_to_catalyst": 20}     # unchanged -> F1 does not cross
        rows[t] = {}

    out = await company_scan.run_scan(db, None, "2026-01-09", raw_by, rows)
    assert out == []
    for t in raw_by:
        stored = store.scan_flags_asof(db, t, "2026-01-09")
        assert stored and stored[-1]["opportunity_type"] == "no_opportunity"


async def test_corroborator_never_wakes_alone(db, monkeypatch):
    """A name tripping only F11 (a lone CORROBORATOR) is stored, never woken."""
    async def _boom(*a, **k):
        raise AssertionError("a lone corroborator must not wake Stage-2")
    monkeypatch.setattr(company_scan, "run_structured", _boom)

    store.upsert_bars(db, "ABCD", [
        {"week_end": "2025-12-26", "close": 100.0, "volume": 100},
        {"week_end": "2026-01-02", "close": 100.0, "volume": 90},    # prev turnover False
        {"week_end": "2026-01-09", "close": 100.0, "volume": 500},   # cur turnover True, 5x median
    ])
    _seed_baseline(db, "ABCD", days=None)   # baseline card at 2026-01-02 (no catalyst)

    out = await company_scan.run_scan(db, None, "2026-01-09", {"ABCD": {}}, {"ABCD": {}})
    assert out == []
    stored = store.scan_flags_asof(db, "ABCD", "2026-01-09")[-1]
    assert stored["opportunity_type"] == "no_opportunity"
    assert "F11" in stored.get("tripped_flags", [])   # the corroborator DID trip — it just didn't wake


async def test_wake_count_le_flagged_and_cap_batches(db, monkeypatch):
    """N woken names -> N Haiku passes (no escalation); lowering the cap stores the overflow."""
    calls = []
    monkeypatch.setattr(company_scan, "run_structured", _fake_llm(_canned(), calls))

    N = 5
    raw_by, rows = {}, {}
    for i in range(N):
        t = f"W{i}"
        _seed_baseline(db, t, days=20)
        raw_by[t] = {"days_to_catalyst": 10}   # crosses the 14-day band -> F1 (PRINCIPAL) wakes
        rows[t] = {}
    await company_scan.run_scan(db, None, "2026-01-09", raw_by, rows)
    assert len(calls) == N and all(m == "haiku" for m in calls)

    calls.clear()
    capped = copy.deepcopy(company_scan.SCAN_PARAMS)
    capped["scan"]["max_stage2_wakes"] = 2
    raw2, rows2 = {}, {}
    for i in range(N):
        t = f"X{i}"
        _seed_baseline(db, t, days=20)
        raw2[t] = {"days_to_catalyst": 10}
        rows2[t] = {}
    await company_scan.run_scan(db, None, "2026-01-09", raw2, rows2, params=capped)
    assert len(calls) == 2   # cap enforced; overflow names stored, not woken


async def test_stage2_allowed_tools_include_analog_and_playbooks(db, monkeypatch):
    """The Stage-2 call reuses diligence.ALLOWED_TOOLS (analog_query + query_playbooks), model=haiku."""
    captured = {}
    async def _f(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        captured.update(allowed_tools=allowed_tools, mcp_servers=mcp_servers, model=model)
        return _canned()
    monkeypatch.setattr(company_scan, "run_structured", _f)

    _seed_baseline(db, "ABCD", days=20)
    await company_scan.run_scan(db, None, "2026-01-09", {"ABCD": {"days_to_catalyst": 10}}, {"ABCD": {}})
    assert "mcp__quant__analog_query" in captured["allowed_tools"]
    assert "mcp__quant__query_playbooks" in captured["allowed_tools"]
    assert captured["model"] == "haiku"
    assert "quant" in captured["mcp_servers"]


async def test_analog_context_built_by_python(db, monkeypatch):
    """The analog_context handed to build_scan_prompt is the deterministic _analog_context(...) —
    Python authors it, never the model."""
    seen = {}
    orig = company_scan.build_scan_prompt
    def _spy(scan_input, analog_context):
        seen.update(si=scan_input, ctx=analog_context)
        return orig(scan_input, analog_context)
    monkeypatch.setattr(company_scan, "build_scan_prompt", _spy)
    monkeypatch.setattr(company_scan, "run_structured", _fake_llm(_canned()))

    _seed_baseline(db, "ABCD", days=20)
    await company_scan.run_scan(db, None, "2026-01-09", {"ABCD": {"days_to_catalyst": 10}}, {"ABCD": {}})
    si = seen["si"]
    assert seen["ctx"] == company_scan._analog_context(si.tripped, si.card_cur)
    assert "F1" in seen["ctx"]


async def test_uncited_finding_dropped(db, monkeypatch):
    """A key_finding whose evidence_ref fails evidence.resolve is dropped before persist/route."""
    op = _canned(key_findings=[
        KeyFinding(claim="resolvable", evidence_ref="tool:analog_query#abc123abc123"),
        KeyFinding(claim="dangling", evidence_ref="kb:999999"),   # no such node -> unresolvable
    ])
    monkeypatch.setattr(company_scan, "run_structured", _fake_llm(op))

    _seed_baseline(db, "ABCD", days=20)
    out = await company_scan.run_scan(db, None, "2026-01-09", {"ABCD": {"days_to_catalyst": 10}}, {"ABCD": {}})
    survivors = [kf.evidence_ref for kf in out[0].key_findings]
    assert "tool:analog_query#abc123abc123" in survivors
    assert "kb:999999" not in survivors
    stored = store.scan_flags_asof(db, "ABCD", "2026-01-09")[-1]
    assert "kb:999999" not in [kf["evidence_ref"] for kf in stored["key_findings"]]


async def test_no_opportunity_is_valid_and_stored_not_routed(db, monkeypatch):
    """no_opportunity is written to scan_flag with routed=False and NOT returned in the routed list."""
    monkeypatch.setattr(company_scan, "run_structured", _fake_llm(_canned(opportunity_type="no_opportunity")))

    _seed_baseline(db, "ABCD", days=20)
    out = await company_scan.run_scan(db, None, "2026-01-09", {"ABCD": {"days_to_catalyst": 10}}, {"ABCD": {}})
    assert out == []
    stored = store.scan_flags_asof(db, "ABCD", "2026-01-09")[-1]
    assert stored["opportunity_type"] == "no_opportunity"
    row = db.execute("SELECT routed FROM scan_flag WHERE ticker='ABCD' AND week_end='2026-01-09'").fetchone()
    assert row["routed"] == 0


async def test_latch_persists_across_weeks(db, monkeypatch):
    """SCAN-02 replayability money-gate: a flag latched at week T (F1 band-14) is persisted (card
    written AFTER delta_card mutates fired) and does NOT re-fire at T+1 while the band still stands."""
    monkeypatch.setattr(company_scan, "run_structured", _fake_llm(_canned()))
    tr = {"thesis_type": "mean_reversion"}   # NOT catalyst -> no precedence suppression
    _seed_baseline(db, "ABCD", days=20, thesis_row=tr)   # week T-1 baseline (outside both bands)

    # week T: days 10 crosses the 14-day band -> F1 latches; persisted AFTER delta_card
    await company_scan.run_scan(db, None, "2026-01-09", {"ABCD": {"days_to_catalyst": 10}}, {"ABCD": tr})
    card_T = store.card_asof(db, "ABCD", "2026-01-09")
    assert card_T["fired"]["F1:14"] == "2026-01-09"   # FAILS if write_card ran before delta_card

    # week T+1: days 9 still inside band 14 -> latch stands, F1 must NOT re-fire
    await company_scan.run_scan(db, None, "2026-01-16", {"ABCD": {"days_to_catalyst": 9}}, {"ABCD": tr})
    card_T1 = store.card_asof(db, "ABCD", "2026-01-16")
    assert card_T1["fired"]["F1:14"] == "2026-01-09"   # latch memory preserved, not restamped
    stored_T1 = store.scan_flags_asof(db, "ABCD", "2026-01-16")[-1]
    assert stored_T1["opportunity_type"] == "no_opportunity"
    assert "F1" not in stored_T1.get("tripped_flags", [])   # no spurious re-fire


async def test_low_confidence_escalates_to_sonnet(db, monkeypatch):
    """confidence < escalate_conf_floor triggers ONE re-run on model='sonnet'."""
    models = []
    low = _canned(confidence=0.2)     # below the 0.4 floor
    async def _f(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        models.append(model)
        return low
    monkeypatch.setattr(company_scan, "run_structured", _f)

    _seed_baseline(db, "ABCD", days=20)
    await company_scan.run_scan(db, None, "2026-01-09", {"ABCD": {"days_to_catalyst": 10}}, {"ABCD": {}})
    assert models == ["haiku", "sonnet"]   # cheap-first, then ONE escalation


async def test_catalyst_precedence_suppresses_bare_f1(db, monkeypatch):
    """A bare-F1 fire on a name whose thesis is already a catalyst is logged, not woken (no double-flag)."""
    async def _boom(*a, **k):
        raise AssertionError("a bare-F1 catalyst name is already routed to WF-1 — do not wake")
    monkeypatch.setattr(company_scan, "run_structured", _boom)
    tr = {"thesis_type": "catalyst"}
    _seed_baseline(db, "ABCD", days=20, thesis_row=tr)
    out = await company_scan.run_scan(db, None, "2026-01-09", {"ABCD": {"days_to_catalyst": 10}}, {"ABCD": tr})
    assert out == []
    stored = store.scan_flags_asof(db, "ABCD", "2026-01-09")[-1]
    assert stored["opportunity_type"] == "no_opportunity"


# ============================================================================
# Plan 03 Task 2 — to_weekly_flag projection + MD routing (zero md.py change)
# ============================================================================


def test_flag_carries_gap_not_answer():
    """to_weekly_flag yields a qual WeeklyFlag carrying the gap (thesis_to_verify), no answer field,
    and verification_needed does NOT leak onto the wire."""
    op = _canned(opportunity_type="squeeze_setup",
                 thesis_to_verify="a borrow-rate spike could force a squeeze unwind",
                 tripped_flags=["F6", "F7"])
    wf = company_scan.to_weekly_flag(op)
    assert isinstance(wf, WeeklyFlag)
    assert wf.flag_type == "qual"
    assert wf.finding == op.thesis_to_verify
    assert wf.evidence_ref == "tool:analog_query#abc123abc123"   # promoted from the cited finding
    wire_fields = set(type(wf).model_fields)
    assert wire_fields.isdisjoint({"direction", "size", "size_pct", "target", "verification_needed"})


def test_no_opportunity_not_projected():
    """to_weekly_flag on a no_opportunity flag returns None (stored-not-routed)."""
    assert company_scan.to_weekly_flag(_canned(opportunity_type="no_opportunity")) is None


def test_no_code_path_flag_to_candidate():
    """No code path from an OpportunityFlag to a Candidate / run_portfolio (type-pinned)."""
    src = inspect.getsource(company_scan)
    assert "run_portfolio" not in src
    assert "Candidate" not in src
    # run_portfolio does not accept an OpportunityFlag anywhere in its signature
    from catalyst_trader.desk.orchestrator import run_portfolio
    for p in inspect.signature(run_portfolio).parameters.values():
        assert p.annotation is inspect.Parameter.empty or "OpportunityFlag" not in str(p.annotation)


async def test_routed_flag_lands_in_md_queue(db, monkeypatch):
    """A projected WeeklyFlag(flag_type='qual') passed in item['incoming_flags'] reaches reconcile's
    round-1 logged_flags with md.py UNCHANGED (the 6.7 seam is live)."""
    from catalyst_trader.contracts import (
        DebateVerdict, DiligenceDossier, DiligenceInput, EstimateVetting, Hedge,
        MDDecision, PortfolioContext, StrategyDossier, TradeProposal,
    )
    from catalyst_trader.desk import md as md_mod
    from catalyst_trader.desk.md import MDReview, reconcile

    verdict = DebateVerdict(thesis="endpoint likely met", direction="positive", confidence=0.6,
                            bull_strongest_point="strong phase-2", bear_strongest_point="thin precedent",
                            kill_criteria=["fails if the primary endpoint is missed"])
    hedge = Hedge(instrument="equity_peer", ticker="PEER", payoff_direction=-1, validated=True,
                  covers="idiosyncratic", mechanism="peer rises when target's drug fails",
                  conditional_worst=-0.02)
    trade = TradeProposal(target_long="ACME", hedge=hedge, pair_rationale="inverse peer", entry=10.0,
                          exit_by_date="2026-12-05", stop_loss=9.0, take_profit=12.0, size_pct=0.05,
                          expected_return_pct=0.01, holds_through_catalyst=True, catalyst_id="cat-1",
                          direction="positive",
                          estimate_vetting=EstimateVetting(verdict="endorse", input_refs=["tool:x#1"], reasons=["ok"]),
                          sl_advisory=True)
    dossier = StrategyDossier(decision="promote", trade=trade,
                              portfolio_context=PortfolioContext(concentration=0.2, corr_to_open_positions=[0.1],
                                                                 weekly_budget_remaining=0.5),
                              verdict_summary="promote", dissent_log=[], all_evidence_refs=[],
                              residual_net_long=0.0, which_risk_covered="idiosyncratic",
                              position_memo="memo", pre_mortem=["assume it lost"],
                              kill_criteria=["fails if the primary endpoint is missed"])
    dd = DiligenceDossier(verdict="go", per_dimension=[{"dimension": "clinical", "catalyst_id": "cat-1"}],
                          strongest_disconfirming_evidence="thin precedent", all_evidence_refs=[])
    wf = company_scan.to_weekly_flag(_canned(opportunity_type="squeeze_setup"))

    async def _rs(prompt, schema, *, model="opus"):
        if schema is MDReview:
            return MDReview(satisfied=True, response_delta="clean", flags=[])
        return MDDecision(decision="enter", rationale="ok", round_log=[])
    async def _noop(*a, **k):
        raise AssertionError("no cascade expected")
    monkeypatch.setattr(md_mod, "run_structured", _rs)
    monkeypatch.setattr(md_mod, "run_desk", _noop)
    monkeypatch.setattr(md_mod, "run_portfolio", _noop)
    monkeypatch.setattr(md_mod, "run_diligence", _noop)

    item = {
        "verdict": verdict, "dossier": dossier, "dd": dd,
        "catalyst": {"catalyst_id": "cat-1", "catalyst_type": "pdufa"},
        "entry": 10.0, "risk_inputs": {"p_loss": 0.4, "gap": 0.1},
        "dd_input": DiligenceInput(ticker="ACME", catalyst={"catalyst_id": "cat-1"}, pair="PEER"),
        "market_data": {}, "open_book": [], "incoming_flags": [wf],
    }
    out = await reconcile(db, None, item)
    assert any(w.evidence_ref == wf.evidence_ref for r in out.round_log for w in r.logged_flags)
