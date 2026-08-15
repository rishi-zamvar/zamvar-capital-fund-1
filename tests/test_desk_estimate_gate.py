"""§7 estimate VETTING gate: enforce_estimate — the estimate-layer mirror of
verifier.enforce. It audits the ASSUMPTIONS/INPUTS behind catalyst_move_estimate +
adaptive_sl_tp_levels (never the arithmetic — agents never do math) before the builder
consumes them: cite-or-drop on every input (reusing evidence.resolve/quote_supported),
deterministic consistency checks, cold-start widening, and a semantic analog-comparability
judgment. A reject raises EstimateRejectedError (blocks finalize), mirroring
VerdictUnsupportedError. Whole suite offline: run_structured is monkeypatched.
"""

import pytest

from catalyst_trader.contracts import DebateVerdict
from catalyst_trader.desk import evidence, verifier
from catalyst_trader.kb import EvidenceSource, KBNode, insert_claim


# --- helpers ---------------------------------------------------------------

def _seed(db, *, snippet="e1", quote):
    """Insert one resolvable EvidenceSource node; return its id (a kb: ref target)."""
    ev = EvidenceSource(url="https://ct.gov/NCT1", retrieved_at="2026-08-14", snippet_hash=snippet, quote=quote)
    insert_claim(db, KBNode(kind="playbook", attrs={"x": 1}), [ev])
    row = db.execute(
        "SELECT id FROM kb_node WHERE kind='evidence_source' "
        "AND json_extract(attrs_json,'$.snippet_hash')=?",
        (snippet,),
    ).fetchone()
    return row["id"]


def _params(min_analogs=5, default_down_move=0.45):
    return {"estimator": {"min_analogs": min_analogs, "default_down_move": default_down_move}}


def _verdict(direction="positive", confidence=0.6):
    return DebateVerdict(
        thesis="ACME PDUFA likely approves", direction=direction, confidence=confidence,
        bull_strongest_point="pivotal endpoint met", bear_strongest_point="cash runway is tight",
        kill_criteria=["a Complete Response Letter is issued"], evidence_refs=["tool:x#1"],
    )


def _inputs(p_positive=0.6, with_analog=True, extra=None):
    """Fully-cited estimator inputs (tool: refs resolve-by-construction)."""
    items = [
        {"input": "p_positive", "ref": evidence.tool_ref_for("base_rate", {"metric": "pos"}), "value": p_positive},
        {"input": "implied_move", "ref": evidence.tool_ref_for("implied_move", {"t": "ACME"}), "value": 0.4},
    ]
    if with_analog:
        items.append({"input": "analogs", "ref": evidence.tool_ref_for("analog_query", {"k": 5}), "value": ["a1", "a2"]})
    if extra:
        items.extend(extra)
    return items


def _seam(calls, response):
    async def _fake(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        calls.append({"prompt": prompt, "schema": schema, "model": model})
        return verifier.AnalogComparability.model_validate(response)

    return _fake


def _call(db, **over):
    """enforce_estimate with sane defaults; override any kwarg."""
    kw = dict(
        estimate_inputs=_inputs(),
        verdict=_verdict(),
        params=_params(),
        holds_through_catalyst=False,
        sl_advisory=False,
        down_move=0.45,
        catalyst_type="pdufa",
        n_analogs=8,
    )
    kw.update(over)
    return verifier.enforce_estimate(db, kw.pop("estimate_inputs"), **kw)


# --- structural stage (Task 1) --------------------------------------------

async def test_uncited_input_dropped_blocks(db, monkeypatch, load_fixture):
    """An estimator input with an absent/unresolvable ref is DROPPED (cite-or-drop) and
    does NOT survive to input_refs — a dropped load-bearing input blocks finalize."""
    monkeypatch.setattr(verifier, "run_structured", _seam([], load_fixture("agent_responses/estimate_comparability")))
    bad = {"input": "vol_proxy", "ref": "garbage", "value": 0.3}
    with pytest.raises(verifier.EstimateRejectedError) as ei:
        await _call(db, estimate_inputs=_inputs(extra=[bad]))
    vetting = ei.value.vetting
    assert vetting.verdict == "reject"
    assert "garbage" in vetting.dropped_inputs
    assert "garbage" not in vetting.input_refs


async def test_kb_quote_unsupported_dropped(db, monkeypatch, load_fixture):
    """A kb: input whose claim is NOT a substring of its source quote fails the quote gate
    (quote_supported) → dropped, same as an uncited claim in verifier.enforce."""
    monkeypatch.setattr(verifier, "run_structured", _seam([], load_fixture("agent_responses/estimate_comparability")))
    nid = _seed(db, quote="The primary endpoint met.")
    bad = {"input": "vol_proxy", "ref": f"kb:{nid}", "claim": "endpoint MISSED", "value": 0.3}
    with pytest.raises(verifier.EstimateRejectedError) as ei:
        await _call(db, estimate_inputs=_inputs(extra=[bad]))
    assert f"kb:{nid}" in ei.value.vetting.dropped_inputs


async def test_p_positive_consistency_reject(db, monkeypatch, load_fixture):
    """P(positive) contradicting the Phase-4 verdict direction → deterministic reject."""
    monkeypatch.setattr(verifier, "run_structured", _seam([], load_fixture("agent_responses/estimate_comparability")))
    with pytest.raises(verifier.EstimateRejectedError) as ei:
        await _call(db, estimate_inputs=_inputs(p_positive=0.2), verdict=_verdict("positive", 0.6))
    assert any("P(positive)" in r for r in ei.value.vetting.reasons)


async def test_base_rate_band_reject(db, monkeypatch, load_fixture):
    """Estimated down-move outside the type's sanity band (relative to the cited
    default_down_move) → deterministic reject."""
    monkeypatch.setattr(verifier, "run_structured", _seam([], load_fixture("agent_responses/estimate_comparability")))
    with pytest.raises(verifier.EstimateRejectedError) as ei:
        await _call(db, down_move=0.95)  # band for default 0.45 is [0.225, 0.90]
    assert any("down-move" in r for r in ei.value.vetting.reasons)


async def test_advisory_inconsistency_reject(db, monkeypatch, load_fixture):
    """hold-through leg with a NON-advisory SL is the gap-exposed invariant violation
    (pure boolean) → reject."""
    monkeypatch.setattr(verifier, "run_structured", _seam([], load_fixture("agent_responses/estimate_comparability")))
    with pytest.raises(verifier.EstimateRejectedError) as ei:
        await _call(db, holds_through_catalyst=True, sl_advisory=False)
    assert any("advisory" in r.lower() for r in ei.value.vetting.reasons)


async def test_cold_start_widens(db, monkeypatch, load_fixture):
    """Thin analog set (< min_analogs) sets uncertainty_widened=True — a flag, not an
    auto-reject; a structurally-clean estimate still endorses."""
    calls = []
    monkeypatch.setattr(verifier, "run_structured", _seam(calls, load_fixture("agent_responses/estimate_comparability")))
    out = await _call(db, n_analogs=2)  # < min_analogs (5)
    assert out.verdict == "endorse"
    assert out.uncertainty_widened is True


async def test_reject_raises_and_blocks_finalize(db, monkeypatch, load_fixture):
    """A reject raises EstimateRejectedError (blocks finalize) with the EstimateVetting
    attached for the audit trail — mirrors verifier.enforce raising VerdictUnsupportedError."""
    monkeypatch.setattr(verifier, "run_structured", _seam([], load_fixture("agent_responses/estimate_comparability")))
    with pytest.raises(verifier.EstimateRejectedError) as ei:
        await _call(db, holds_through_catalyst=True, sl_advisory=False)
    assert ei.value.vetting.verdict == "reject"
    assert ei.value.vetting.reasons  # audit trail populated


# --- semantic stage + endorse path (Task 2) --------------------------------

async def test_endorse_path(db, monkeypatch, load_fixture):
    """A fully-cited, consistent estimate whose analogs the LLM judges comparable →
    verdict='endorse'; all surviving input_refs retained; the judgment uses opus."""
    calls = []
    monkeypatch.setattr(verifier, "run_structured", _seam(calls, load_fixture("agent_responses/estimate_comparability")))
    out = await _call(db)
    assert out.verdict == "endorse"
    assert not out.dropped_inputs
    assert len(out.input_refs) == 3           # p_positive + implied_move + analogs
    assert len(calls) == 1                     # one semantic call, on the analog survivors
    assert calls[0]["model"] == "opus"


async def test_off_type_comparability_reject(db, monkeypatch):
    """Off-type / cherry-picked analogs (LLM judges comparable=false) → reject + raise,
    even when the structural stage passed cleanly."""
    calls = []
    monkeypatch.setattr(
        verifier, "run_structured",
        _seam(calls, {"comparable": False, "reasons": ["Analogs are earnings moves, not PDUFA decisions — off-type."]}),
    )
    with pytest.raises(verifier.EstimateRejectedError) as ei:
        await _call(db)
    assert ei.value.vetting.verdict == "reject"
    assert any("off-type" in r.lower() for r in ei.value.vetting.reasons)


async def test_semantic_skipped_without_analogs(db, monkeypatch, load_fixture):
    """No surviving analog input → no LLM spent; a structurally-clean estimate still
    endorses (comparability only judges analog survivors)."""
    calls = []
    monkeypatch.setattr(verifier, "run_structured", _seam(calls, load_fixture("agent_responses/estimate_comparability")))
    out = await _call(db, estimate_inputs=_inputs(with_analog=False))
    assert out.verdict == "endorse"
    assert calls == []                         # no analogs → no semantic call


async def test_cold_start_carried_onto_endorse(db, monkeypatch, load_fixture):
    """Cold-start widening from the structural stage is carried through onto the endorsed
    EstimateVetting (not lost when the semantic stage passes)."""
    monkeypatch.setattr(verifier, "run_structured", _seam([], load_fixture("agent_responses/estimate_comparability")))
    out = await _call(db, n_analogs=1)
    assert out.verdict == "endorse"
    assert out.uncertainty_widened is True
