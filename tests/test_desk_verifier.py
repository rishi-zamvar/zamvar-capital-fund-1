"""CALL-04 fact-check verifier: source-quote-or-drop before a DebateVerdict
finalizes. The structural half (resolve + quote-substring) is deterministic Python
(desk.evidence); the semantic half (does the quote actually support the claim?) is a
gated LLM call, spent only on the load-bearing structural survivors. Dropping all
support blocks finalize. Whole suite offline: run_structured is monkeypatched.

The CALL-04 regression guard lives here: a KB-analog claim cited as
`tool:analog_query#<hash>` (the exact ref shape 04-03 mints) survives structural
resolution and reaches the semantic gate — it is NOT dropped as unresolvable. The
same analog cited as `kb:<node_id>` (a catalyst node, not an evidence_source) IS
dropped — which is exactly why 04-03 mints tool: refs.
"""

import pytest

from catalyst_trader.contracts import ClinicalReport, DebateVerdict, KeyFinding
from catalyst_trader.desk import evidence, verifier
from catalyst_trader.kb import EvidenceSource, KBNode, insert_claim


# --- helpers ---------------------------------------------------------------

def _seed(db, *, url="https://ct.gov/NCT1", snippet="h1", quote):
    """Insert one resolvable EvidenceSource node; return its node id (a kb: ref target)."""
    ev = EvidenceSource(url=url, retrieved_at="2026-08-14", snippet_hash=snippet, quote=quote)
    insert_claim(db, KBNode(kind="playbook", attrs={"x": 1}), [ev])
    row = db.execute(
        "SELECT id FROM kb_node WHERE kind='evidence_source' "
        "AND json_extract(attrs_json,'$.snippet_hash')=?",
        (snippet,),
    ).fetchone()
    return row["id"]


def _signal(pairs):
    """One AnalystSignal whose key_findings map each (ref, claim) — the ref->claim table
    the verifier uses to run quote_supported."""
    return ClinicalReport(
        dimension="clinical", ticker="ACME", catalyst_id="cat-001",
        score=0.4, confidence=0.6,
        thesis="The cited clinical findings point to a positive readout.",
        key_findings=[KeyFinding(claim=c, evidence_ref=r) for r, c in pairs],
    )


def _verdict(refs):
    return DebateVerdict(
        thesis="ACME PDUFA likely approves", direction="positive", confidence=0.6,
        bull_strongest_point="pivotal endpoint met", bear_strongest_point="cash runway is tight",
        kill_criteria=["a Complete Response Letter is issued"], evidence_refs=refs,
    )


def _seam(calls, support):
    """Fake run_structured: records each call, returns the patched SupportCheck response."""

    async def _fake(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        calls.append({"prompt": prompt, "schema": schema, "model": model})
        return verifier.SupportCheck.model_validate(support)

    return _fake


# --- tests -----------------------------------------------------------------

async def test_source_quote_or_drop(db, monkeypatch, load_fixture):
    """(a) resolvable kb: ref, quote supported -> survives; (b) kb: ref, quote NOT
    supported -> dropped; (c) garbage ref -> dropped; (d) tool:analog_query ref ->
    survives (resolved-by-construction, no quote gate). Structural drops need no LLM."""
    calls = []
    monkeypatch.setattr(verifier, "run_structured", _seam(calls, load_fixture("agent_responses/verifier_support")))

    nid_a = _seed(db, url="https://ct.gov/NCT1", snippet="h1", quote="The primary endpoint met at p<0.001.")
    nid_b = _seed(db, url="https://ct.gov/NCT2", snippet="h2", quote="Primary endpoint met.")
    tool_ref = evidence.tool_ref_for("analog_query", {"context": "ACME PDUFA", "filters": {"type": "pdufa"}, "k": 5})

    signals = [_signal([
        (f"kb:{nid_a}", "primary endpoint met"),      # substring of source quote -> supported
        (f"kb:{nid_b}", "primary endpoint missed"),   # NOT in source quote -> unsupported
        (tool_ref, "nearest analog resolved positive"),
    ])]
    verdict = _verdict([f"kb:{nid_a}", f"kb:{nid_b}", "garbage", tool_ref])

    out = await verifier.enforce(db, verdict, signals=signals)

    assert set(out.evidence_refs) == {f"kb:{nid_a}", tool_ref}   # (a)+(d) survive
    assert f"kb:{nid_b}" not in out.evidence_refs                # (b) unsupported -> dropped
    assert "garbage" not in out.evidence_refs                    # (c) unresolvable -> dropped


async def test_kb_analog_tool_ref_survives(db, monkeypatch, load_fixture):
    """CALL-04 regression guard: a verdict whose ONLY support is a KB-analog claim cited
    as tool:analog_query#<hash> passes structural resolution and reaches the semantic
    gate — NOT dropped as unresolvable. A kb: ref here would have been dropped."""
    calls = []
    monkeypatch.setattr(verifier, "run_structured", _seam(calls, load_fixture("agent_responses/verifier_support")))

    tool_ref = evidence.tool_ref_for("analog_query", {"context": "ACME PDUFA", "filters": {"type": "pdufa"}, "k": 5})
    assert tool_ref.startswith("tool:analog_query#")

    signals = [_signal([(tool_ref, "nearest analog to an ACME-like PDUFA resolved positive")])]
    verdict = _verdict([tool_ref])

    out = await verifier.enforce(db, verdict, signals=signals)

    assert out.evidence_refs == [tool_ref]   # survived structural resolution
    assert len(calls) == 1                    # AND reached the semantic gate (not silently dropped)


async def test_kb_analog_cited_as_kb_ref_would_be_dropped(db, monkeypatch, load_fixture):
    """The contrast that justifies 04-03's tool:-ref minting: analog_query returns a
    catalyst NODE id, not an evidence_source id — citing it as kb:<id> is unresolvable
    and gets dropped, taking the verdict's only support with it -> finalize blocked."""
    calls = []
    monkeypatch.setattr(verifier, "run_structured", _seam(calls, load_fixture("agent_responses/verifier_support")))

    cat_id = insert_claim(
        db, KBNode(kind="catalyst", attrs={"type": "pdufa"}),
        [EvidenceSource(url="u", retrieved_at="t", snippet_hash="hc")],
    )
    signals = [_signal([(f"kb:{cat_id}", "nearest analog resolved positive")])]
    verdict = _verdict([f"kb:{cat_id}"])

    with pytest.raises(verifier.VerdictUnsupportedError):
        await verifier.enforce(db, verdict, signals=signals)
    assert calls == []   # dropped structurally, no LLM spent


async def test_verifier_gates_finalize(db, monkeypatch, load_fixture):
    """If dropping claims removes ALL support, enforce raises — the verdict cannot
    finalize on unsupported evidence."""
    calls = []
    monkeypatch.setattr(verifier, "run_structured", _seam(calls, load_fixture("agent_responses/verifier_support")))

    nid = _seed(db, quote="Primary endpoint met.")
    signals = [_signal([(f"kb:{nid}", "primary endpoint MISSED")])]  # claim absent from source -> dropped
    verdict = _verdict([f"kb:{nid}", "garbage"])

    with pytest.raises(verifier.VerdictUnsupportedError):
        await verifier.enforce(db, verdict, signals=signals)
    assert calls == []   # every ref dropped structurally, no LLM spent


async def test_semantic_check_only_for_load_bearing(db, monkeypatch, load_fixture):
    """run_structured is invoked only for the structural survivors — never for dropped
    refs (assert call count + dropped refs absent from the prompts)."""
    calls = []
    monkeypatch.setattr(verifier, "run_structured", _seam(calls, load_fixture("agent_responses/verifier_support")))

    nid_a = _seed(db, url="https://ct.gov/NCT1", snippet="h1", quote="The primary endpoint met.")
    nid_b = _seed(db, url="https://ct.gov/NCT2", snippet="h2", quote="Primary endpoint met.")
    tool_ref = evidence.tool_ref_for("analog_query", {"k": 5})

    signals = [_signal([
        (f"kb:{nid_a}", "primary endpoint met"),
        (f"kb:{nid_b}", "endpoint missed"),
        (tool_ref, "analog positive"),
    ])]
    verdict = _verdict([f"kb:{nid_a}", f"kb:{nid_b}", "garbage", tool_ref])

    await verifier.enforce(db, verdict, signals=signals)

    assert len(calls) == 2                              # only the two structural survivors
    prompts = " ".join(c["prompt"] for c in calls)
    assert "garbage" not in prompts                     # unresolvable ref never reaches the LLM
    assert f"kb:{nid_b}" not in prompts                 # unsupported kb ref never reaches the LLM
    assert all(c["model"] == "opus" for c in calls)     # load-bearing judgment uses the strongest tier


def test_claim_for_maps_headline_source_to_field_value():
    """07.9-03: a cited headline *_source ref yields a precise '<field>=<value>' claim
    (not the verdict-thesis fallback); key_findings still win when they cite the ref."""
    sig = _signal([("tool:x#1", "finding claim")]).model_copy(
        update={"pos_estimate": 0.62, "pos_estimate_source": "tool:base_rate#h1"})
    assert verifier._claim_for("tool:base_rate#h1", [sig]) == "pos_estimate=0.62"
    assert verifier._claim_for("tool:x#1", [sig]) == "finding claim"
    assert verifier._claim_for("tool:nope#0", [sig]) is None


async def test_enforce_semantic_prompt_uses_headline_claim(db, monkeypatch):
    calls = []
    monkeypatch.setattr(verifier, "run_structured", _seam(calls, {"supported": True, "reason": "ok"}))
    sig = _signal([("tool:x#1", "other claim")]).model_copy(update={"pos_estimate": 0.62, "pos_estimate_source": "tool:base_rate#h1"})
    await verifier.enforce(db, _verdict(["tool:base_rate#h1"]), signals=[sig])
    assert "Claim: pos_estimate=0.62" in calls[0]["prompt"]
