"""Trade builder (PORT-02 + HEDGE-01/04): DebateVerdict -> TradeProposal, the single-leg
estimated-move construction engine.

Money-critical invariants under test:
  - a candidate inverse peer is only ever a -1 peer (a +1 co-move peer is a conviction long,
    never an idiosyncratic hedge candidate, HEDGE-01); the builder NEVER fabricates a validated
    hedge (validation is Risk's job) — TradeProposal.hedge is None out of the builder.
  - the estimated down-move (not a blanket 0.70) sizes the leg: size_for_survival receives
    est.detail["down_move"] as gap.
  - the hold-through-vs-exit decision is made by the quant hold_vs_exit tool (expected-LOG-growth
    at the survival-constrained size f), NEVER raw EV (BLOCKER-2); the builder FOLLOWS its verdict.
  - SL is advisory whenever the leg holds through the catalyst (a stop can't fill in a gap).
  - the estimate is vetted via enforce_estimate BEFORE finalize; a reject blocks the proposal.
  - every builder threshold (min_tradeable_size, log_growth_margin, runup_capture_frac) is a loaded
    param — a missing builder param RAISES; no literal in the builder body.

Quant + KB run FOR REAL (deterministic); run_structured is monkeypatched -> fully offline.
"""

from catalyst_trader.contracts import DebateVerdict, TradeProposal
from catalyst_trader.desk import builder, risk, verifier
from catalyst_trader.desk.verifier import EstimateRejectedError
from catalyst_trader.kb import EvidenceSource, KBNode, add_edge, insert_claim, insert_hedge_peer
from catalyst_trader import kb

_EV = [EvidenceSource(url="https://sec.gov/10k", retrieved_at="2026-08-14", snippet_hash="h")]

CAT = {
    "ticker": "ACME", "company_name": "Acme Bio", "catalyst_type": "pdufa",
    "event_date": "2026-11-15", "event_date_end": "2026-11-22", "catalyst_id": "cat-1",
}


def _verdict(direction="positive", confidence=0.62):
    return DebateVerdict(
        thesis="ACME PDUFA likely approves on a met pivotal endpoint",
        direction=direction, confidence=confidence,
        bull_strongest_point="pivotal endpoint met", bear_strongest_point="cash runway is tight",
        kill_criteria=["a Complete Response Letter is issued", "label carve-out on the lead indication"],
        evidence_refs=["tool:base_rate#abc123"],
    )


# --- offline seams ---------------------------------------------------------

def _narrative_seam(calls, rationale="Long ACME; RIVAL candidate inverse hedge pending Risk."):
    async def _fake(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        calls.append({"prompt": prompt, "schema": schema, "model": model})
        return builder.BuilderNarrative(pair_rationale=rationale)
    return _fake


def _comparability_seam(comparable=True):
    async def _fake(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        return verifier.AnalogComparability(comparable=comparable, reasons=["same-type analogs"])
    return _fake


def _seed_analog(db, *, ctype, move, text):
    """Insert a cited catalyst node (+vector) with a realized outcome move, filterable by type."""
    ev = EvidenceSource(url="https://ct.gov/x", retrieved_at="2026-08-14", snippet_hash=text)
    cid = insert_claim(db, KBNode(kind="catalyst", attrs={"type": ctype}), [ev],
                       embed=kb.hash_embed, embed_text=text)
    oid = insert_claim(db, KBNode(kind="outcome", attrs={"move": move}), [ev])
    add_edge(db, cid, "RESULTED_IN", oid)
    db.commit()


def _seed_analogs(db, ups=(0.20, 0.30), downs=(0.50, 0.60)):
    """A comparable analog set with both branches populated, in the default down-move band."""
    for i, m in enumerate(ups):
        _seed_analog(db, ctype="pdufa", move=+m, text=f"pdufa approval analog up {i}")
    for i, m in enumerate(downs):
        _seed_analog(db, ctype="pdufa", move=-m, text=f"pdufa crl analog down {i}")


def _patch_seams(monkeypatch, calls=None, comparable=True):
    """Patch BOTH the builder narrative seam and the verifier comparability seam (offline)."""
    monkeypatch.setattr(builder, "run_structured", _narrative_seam(calls if calls is not None else []))
    monkeypatch.setattr(verifier, "run_structured", _comparability_seam(comparable))


# ---------------------------------------------------------------------------
# Task 1 — skeleton: candidate peer, direction/catalyst_id/exit carried, no fabricated hedge
# ---------------------------------------------------------------------------

def test_candidate_peer_is_inverse_minus1_only(db):
    insert_hedge_peer(db, "ACME", "RIVAL", "same-indication competitor", -1, 0.82, _EV)
    insert_hedge_peer(db, "ACME", "COMOV", "correlated long", +1, 0.80, _EV)
    assert builder._candidate_peer(db, "ACME") == "RIVAL"  # the -1 peer, never the +1


def test_candidate_peer_plus_one_never_surfaced(db):
    insert_hedge_peer(db, "ACME", "COMOV", "correlated long", +1, 0.80, _EV)
    assert builder._candidate_peer(db, "ACME") is None  # a +1 co-move is a long, not a hedge (HEDGE-01)


def test_candidate_peer_none_when_no_peer(db):
    assert builder._candidate_peer(db, "ACME") is None


async def test_direction_and_catalyst_id_carried(db, monkeypatch):
    _seed_analogs(db)
    _patch_seams(monkeypatch)
    out = await builder.build(db, kb.hash_embed, _verdict("positive"), CAT, entry=100.0)
    assert isinstance(out, TradeProposal)
    assert out.direction == "positive"
    assert out.catalyst_id == "cat-1"
    assert out.target_long == "ACME"


async def test_exit_by_date_is_the_catalyst_window(db, monkeypatch):
    _seed_analogs(db)
    _patch_seams(monkeypatch)
    out = await builder.build(db, kb.hash_embed, _verdict(), CAT, entry=100.0)
    assert out.exit_by_date == "2026-11-22"  # event_date_end (the window), not the point date


async def test_builder_never_fabricates_a_validated_hedge(db, monkeypatch):
    # even with a valid -1 peer in the KB, the builder does NOT validate — hedge is None out of
    # the builder; validation is risk.validate_hedge (05-07 reconciles the object on).
    insert_hedge_peer(db, "ACME", "RIVAL", "same-indication competitor", -1, 0.82, _EV)
    _seed_analogs(db)
    _patch_seams(monkeypatch)
    out = await builder.build(db, kb.hash_embed, _verdict(), CAT, entry=100.0)
    assert out.hedge is None


async def test_kill_criteria_carried_into_the_narrative(db, monkeypatch):
    # the DebateVerdict's kill criteria feed the memo (OPS-01) — threaded into the builder narrative.
    _seed_analogs(db)
    calls = []
    _patch_seams(monkeypatch, calls=calls)
    v = _verdict()
    await builder.build(db, kb.hash_embed, v, CAT, entry=100.0)
    prompt = " ".join(c["prompt"] for c in calls)
    assert all(k in prompt for k in v.kill_criteria)


async def test_kb_analogs_carried(db, monkeypatch):
    _seed_analogs(db)
    _patch_seams(monkeypatch)
    out = await builder.build(db, kb.hash_embed, _verdict(), CAT, entry=100.0)
    assert out.kb_analogs  # the queried analogs are carried for the memo


# ---------------------------------------------------------------------------
# Task 2 — estimated-move construction: estimate -> vet -> hold-vs-exit -> advisory SL/TP
# ---------------------------------------------------------------------------

import pytest

from catalyst_trader.contracts import EstimateVetting
from catalyst_trader.quant.events import catalyst_move_estimate
from catalyst_trader.quant.result import ToolResult


def _est(db, p_positive=0.62, ups=(0.20, 0.30), downs=(0.50, 0.60)):
    """The estimate the builder should compute from the seeded analogs + default params."""
    params = kb.load_params(db, "pdufa")
    return catalyst_move_estimate(p_positive, list(ups), list(downs), params)


def _canned_size(value):
    return ToolResult(tool="size_for_survival", tool_version="1.0.0", inputs={},
                      value=value, detail={"ruin_at_size": 0.01, "risk_of_ruin": {}})


async def test_size_for_survival_receives_estimated_down_move_as_gap(db, monkeypatch):
    _seed_analogs(db)
    _patch_seams(monkeypatch)
    captured = {}
    real = risk.size_for_survival

    def _spy(p_loss, gap=0.70, **kw):
        captured["p_loss"], captured["gap"] = p_loss, gap
        return real(p_loss, gap, **kw)

    monkeypatch.setattr(builder.risk, "size_for_survival", _spy)
    await builder.build(db, kb.hash_embed, _verdict(confidence=0.62), CAT, entry=100.0)

    assert captured["gap"] == pytest.approx(0.55)   # est down_move (median of 0.5,0.6), NOT 0.70
    assert captured["gap"] != 0.70
    assert captured["p_loss"] == pytest.approx(0.38)  # 1 - p_positive


async def test_hold_decision_calls_hold_vs_exit_at_survival_size(db, monkeypatch):
    _seed_analogs(db)
    _patch_seams(monkeypatch)
    captured = {}
    real = builder.hold_vs_exit

    def _spy(f, hold_outcomes, exit_outcomes, margin=0.0):
        captured.update(f=f, hold=hold_outcomes, exit=exit_outcomes, margin=margin)
        return real(f, hold_outcomes, exit_outcomes, margin)

    monkeypatch.setattr(builder, "hold_vs_exit", _spy)
    await builder.build(db, kb.hash_embed, _verdict(confidence=0.62), CAT, entry=100.0)

    size = risk.size_for_survival(0.38, 0.55).value
    assert captured["f"] == size                               # decided AT the survival-constrained size
    assert captured["hold"][0][1] == pytest.approx(0.25)       # up branch = est up_move
    assert captured["hold"][1][1] == pytest.approx(-0.55)      # down branch = -est down_move (the fat tail)
    assert captured["exit"][0][1] == pytest.approx(0.3 * 0.25)  # runup_capture_frac * up_move
    assert captured["margin"] == 0.0                           # params["builder"]["log_growth_margin"]


async def test_hold_through_follows_hold_vs_exit_and_sl_is_advisory(db, monkeypatch):
    _seed_analogs(db)
    _patch_seams(monkeypatch)
    monkeypatch.setattr(builder, "hold_vs_exit",
                        lambda *a, **k: ToolResult(tool="hold_vs_exit", tool_version="1.0.0",
                                                   inputs={}, value=1.0, detail={"decision": "hold"}))
    out = await builder.build(db, kb.hash_embed, _verdict(), CAT, entry=100.0)
    assert out.holds_through_catalyst is True
    assert out.sl_advisory is True   # a held-through stop is gap-exposed — advisory only


async def test_exit_before_when_hold_vs_exit_says_exit(db, monkeypatch):
    _seed_analogs(db)
    _patch_seams(monkeypatch)
    monkeypatch.setattr(builder, "hold_vs_exit",
                        lambda *a, **k: ToolResult(tool="hold_vs_exit", tool_version="1.0.0",
                                                   inputs={}, value=0.0, detail={"decision": "exit"}))
    out = await builder.build(db, kb.hash_embed, _verdict(), CAT, entry=100.0)
    assert out.holds_through_catalyst is False
    assert out.sl_advisory is False  # exit-before-event: a real (non-advisory) stop can fill


async def test_positive_ev_hold_but_log_growth_favors_exit(db, monkeypatch):
    # BLOCKER-2 crux (reuse the 05-02 tail shape): raw EV would HOLD, but the fat -70% tail makes
    # expected-LOG-growth favor EXIT. size is fixed to f=1.0 so the tail penalty bites end-to-end;
    # the REAL hold_vs_exit runs and the builder must FOLLOW it (never raw EV).
    _seed_analogs(db, ups=(1.0, 1.0), downs=(0.7, 0.7))
    _patch_seams(monkeypatch)
    monkeypatch.setattr(builder.risk, "size_for_survival", lambda *a, **k: _canned_size(1.0))
    out = await builder.build(db, kb.hash_embed, _verdict(confidence=0.6), CAT, entry=100.0)
    assert out.holds_through_catalyst is False   # log-growth said EXIT despite +EV


async def test_estimate_reject_blocks_finalize(db, monkeypatch):
    _seed_analogs(db)
    _patch_seams(monkeypatch)

    async def _reject(*a, **k):
        raise EstimateRejectedError(EstimateVetting(
            verdict="reject", input_refs=[], reasons=["off-type analogs"]))

    monkeypatch.setattr(builder, "enforce_estimate", _reject)
    out = await builder.build(db, kb.hash_embed, _verdict(), CAT, entry=100.0)
    assert out is None  # a rejected estimate never finalizes a trade (pass / no proposal)


async def test_endorsed_estimate_is_attached_and_return_is_display_only(db, monkeypatch):
    _seed_analogs(db)
    _patch_seams(monkeypatch)
    out = await builder.build(db, kb.hash_embed, _verdict(confidence=0.62), CAT, entry=100.0)

    est = _est(db)
    size = risk.size_for_survival(0.38, est.detail["down_move"]).value
    assert out.estimate_vetting.verdict == "endorse"
    assert out.expected_return_pct == pytest.approx(est.value)  # display only
    assert out.size_pct == pytest.approx(size)                  # the quant survival size
    # adaptive SL/TP delegated to the quant tool (entry 100, up 0.25, vol 0.55, default params)
    assert out.stop_loss == pytest.approx(45.0)
    assert out.take_profit == pytest.approx(120.0)


async def test_one_pct_is_never_a_sizing_input(db, monkeypatch):
    # expected_return_pct (display) must not equal size_pct — the return target never sizes the leg
    _seed_analogs(db)
    _patch_seams(monkeypatch)
    out = await builder.build(db, kb.hash_embed, _verdict(confidence=0.62), CAT, entry=100.0)
    assert out.size_pct != out.expected_return_pct


async def test_below_min_tradeable_size_passes(db, monkeypatch):
    _seed_analogs(db)
    _patch_seams(monkeypatch)
    monkeypatch.setattr(builder.risk, "size_for_survival", lambda *a, **k: _canned_size(0.001))
    out = await builder.build(db, kb.hash_embed, _verdict(), CAT, entry=100.0)
    assert out is None  # below params["builder"]["min_tradeable_size"] (0.002) -> zero-trade


async def test_missing_builder_param_raises_no_magic_number(db, monkeypatch):
    _seed_analogs(db)
    _patch_seams(monkeypatch)
    # params with estimator + sl_tp but NO builder group -> a threshold access must RAISE
    monkeypatch.setattr(builder.kb, "load_params", lambda conn, ct: {
        "estimator": {"method": "median", "min_analogs": 5, "implied_blend": 0.5, "default_down_move": 0.70},
        "sl_tp": {"sl_vol_mult": 1.0, "tp_frac": 0.8, "drift_coef": 0.0},
    })
    with pytest.raises(KeyError):
        await builder.build(db, kb.hash_embed, _verdict(), CAT, entry=100.0)


# ---------------------------------------------------------------------------
# 06.7-02 Task 2 — extra_context re-trigger (RECON-03): default None is byte-for-byte;
# a non-None gap reaches the narrative prompt's extra= slot (the ONLY LLM surface).
# ---------------------------------------------------------------------------

async def test_build_extra_context_none_unchanged(db, monkeypatch):
    """Default path byte-for-byte: build(..., entry=E) and build(..., entry=E, extra_context=None)
    produce the IDENTICAL narrative prompt (no MD RE-TRIGGER line) AND an identical TradeProposal."""
    _seed_analogs(db)
    calls_default, calls_explicit = [], []

    _patch_seams(monkeypatch, calls=calls_default)
    out_default = await builder.build(db, kb.hash_embed, _verdict(confidence=0.62), CAT, entry=100.0)

    _patch_seams(monkeypatch, calls=calls_explicit)
    out_explicit = await builder.build(db, kb.hash_embed, _verdict(confidence=0.62), CAT,
                                       entry=100.0, extra_context=None)

    assert [c["prompt"] for c in calls_default] == [c["prompt"] for c in calls_explicit]
    assert all("MD RE-TRIGGER" not in c["prompt"] for c in calls_default)
    assert out_default == out_explicit   # byte-for-byte TradeProposal


async def test_build_extra_context_injects_gap(db, monkeypatch):
    """A non-None extra_context appears in the narrative prompt's extra= slot (the LLM re-reasons)."""
    _seed_analogs(db)
    calls = []
    _patch_seams(monkeypatch, calls=calls)
    fact = "DD found insider selling the prior round did not weigh"

    await builder.build(db, kb.hash_embed, _verdict(), CAT, entry=100.0, extra_context=fact)

    narrative_prompt = next(c["prompt"] for c in calls if c["schema"] is builder.BuilderNarrative)
    assert fact in narrative_prompt
    assert "MD RE-TRIGGER" in narrative_prompt


def test_no_raw_ev_hold_branch_in_source():
    # structural BLOCKER-2 guard: the builder must never branch on the raw estimate value
    src = (builder.__file__)
    with open(src) as f:
        body = f.read()
    import re
    assert not re.search(r"est\.value\s*>", body)  # hold-vs-exit is log-growth, never raw EV
