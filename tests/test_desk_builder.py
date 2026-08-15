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
from catalyst_trader.desk import builder, verifier
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
