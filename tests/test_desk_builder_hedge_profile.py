"""Out-of-band hedge_profile retrieval wiring (HEDGE-CORR-1c).

The hedge_profile is ALWAYS pulled alongside retrieval for a ticker and attached to the TradeProposal
as CONTEXT — but it is NEVER a ranking signal. Invariants under test (offline):
  - present: a target with a stamped hedge_profile -> TradeProposal.hedge_profile == the stored dict.
  - backward-compat: no stamped profile -> TradeProposal.hedge_profile is None.
  - OUT-OF-BAND PROOF (byte-for-byte): size_pct, expected_return_pct, expected_move_field, kb_analogs,
    and retrieval_confidence are IDENTICAL with vs without a stamped profile — proving the profile
    never entered _split_moves / methods / the football field / size_for_survival / score.
"""

from catalyst_trader import kb
from catalyst_trader.contracts import DebateVerdict, TradeProposal
from catalyst_trader.desk import builder, verifier

CAT = {
    "ticker": "ACME", "company_name": "Acme Bio", "catalyst_type": "pdufa",
    "event_date": "2026-11-15", "event_date_end": "2026-11-22", "catalyst_id": "cat-1",
}

_HP = {"as_of": "2026-08-19", "xbi": {"full": {"corr": 0.31, "beta": 0.4, "r2": 0.0961,
        "verdict": "weak", "direction": "co-move", "window": "full"}},
       "peers": [], "systematic_frac": 0.0961, "idiosyncratic_frac": 0.9039,
       "suggested_hedge": "sizing_only", "note": "n"}


def _verdict(direction="positive", confidence=0.62):
    return DebateVerdict(
        thesis="ACME PDUFA likely approves on a met pivotal endpoint",
        direction=direction, confidence=confidence,
        bull_strongest_point="pivotal endpoint met", bear_strongest_point="cash runway is tight",
        kill_criteria=["a Complete Response Letter is issued"],
        evidence_refs=["tool:base_rate#abc123"],
    )


def _patch_seams(monkeypatch):
    async def _narr(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        return builder.BuilderNarrative(pair_rationale="Long ACME; candidate hedge pending Risk.")

    async def _cmp(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        return verifier.AnalogComparability(comparable=True, reasons=["same-type analogs"])

    monkeypatch.setattr(builder, "run_structured", _narr)
    monkeypatch.setattr(verifier, "run_structured", _cmp)


def _seed_analogs(db):
    from catalyst_trader.kb import EvidenceSource, KBNode, add_edge, insert_claim

    def _one(ctype, move, text):
        ev = EvidenceSource(url="https://ct.gov/x", retrieved_at="2026-08-14", snippet_hash=text)
        cid = insert_claim(db, KBNode(kind="catalyst", attrs={"type": ctype}), [ev],
                           embed=kb.hash_embed, embed_text=text)
        oid = insert_claim(db, KBNode(kind="outcome", attrs={"move": move}), [ev])
        add_edge(db, cid, "RESULTED_IN", oid)
        db.commit()

    for i, m in enumerate((0.20, 0.30)):
        _one("pdufa", +m, f"pdufa approval analog up {i}")
    for i, m in enumerate((0.50, 0.60)):
        _one("pdufa", -m, f"pdufa crl analog down {i}")


async def test_givenStampedProfile_whenBuild_thenProposalCarriesIt(db, monkeypatch):
    _seed_analogs(db)
    _patch_seams(monkeypatch)
    kb.stamp_hedge_profile(db, "ACME", _HP)
    out = await builder.build(db, kb.hash_embed, _verdict(), CAT, entry=100.0)
    assert isinstance(out, TradeProposal)
    assert out.hedge_profile == _HP


async def test_givenNoProfile_whenBuild_thenHedgeProfileIsNone(db, monkeypatch):
    _seed_analogs(db)
    _patch_seams(monkeypatch)
    out = await builder.build(db, kb.hash_embed, _verdict(), CAT, entry=100.0)
    assert out.hedge_profile is None


async def test_givenProfileVsNoProfile_whenBuild_thenScoringFieldsByteForByteIdentical(db, monkeypatch):
    _seed_analogs(db)
    _patch_seams(monkeypatch)

    out_default = await builder.build(db, kb.hash_embed, _verdict(), CAT, entry=100.0)
    kb.stamp_hedge_profile(db, "ACME", _HP)
    out_explicit = await builder.build(db, kb.hash_embed, _verdict(), CAT, entry=100.0)

    assert out_default.hedge_profile is None
    assert out_explicit.hedge_profile == _HP
    # the profile NEVER entered any scoring/sizing/field path -> these are byte-for-byte identical
    assert out_explicit.size_pct == out_default.size_pct
    assert out_explicit.expected_return_pct == out_default.expected_return_pct
    assert out_explicit.expected_move_field == out_default.expected_move_field
    assert out_explicit.kb_analogs == out_default.kb_analogs
    assert out_explicit.retrieval_confidence == out_default.retrieval_confidence
