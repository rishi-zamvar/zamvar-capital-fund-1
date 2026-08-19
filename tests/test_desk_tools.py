"""build_quant_server (CALL-01): the analyst tool surface — quant/ + kb.py wrapped as ONE
in-process SDK MCP server ("quant"). Analysts CALL these, they never compute the numbers.

Every tool result carries a resolvable citation:
  * quant ToolResult tools + analog_query + query_playbooks -> a ``tool:<name>#<hash>`` ref
    that round-trips through ``desk.evidence.resolve`` (resolved-by-construction).
  * base_rate -> an INLINE source citation dict (the citation is embedded, not a ref pointer).

The CALL-04 regression guard: analog_query/query_playbooks are cited as ``tool:`` refs, NEVER
``kb:`` — a kb: ref would fail resolve() (they return catalyst/playbook NODE ids, not
evidence_source ids) and get silently dropped by the Plan-06 verifier. All offline (no live API).
"""

import json

from catalyst_trader import kb
from catalyst_trader.desk import evidence, tools
from catalyst_trader.kb import (
    EvidenceSource,
    KBNode,
    add_edge,
    insert_claim,
    insert_playbook,
)


def _handlers(conn):
    return {t.name: t for t in tools.build_quant_tools(conn)}


def _payload(result: dict) -> dict:
    return json.loads(result["content"][0]["text"])


def _seed_analog(conn, embed_text="pdufa decision imminent"):
    ev = EvidenceSource(url="https://ct.gov/x", retrieved_at="2026-08-14", snippet_hash="h")
    cid = insert_claim(
        conn, KBNode(kind="catalyst", attrs={"type": "pdufa"}), [ev],
        embed=kb.hash_embed, embed_text=embed_text,
    )
    oid = insert_claim(conn, KBNode(kind="outcome", attrs={"move": -0.3, "label": "crl"}), [ev])
    add_edge(conn, cid, "RESULTED_IN", oid)
    conn.commit()


def test_server_builds_with_name_quant(db):
    server = tools.build_quant_server(db)
    assert server["name"] == "quant"


async def test_rnpv_returns_resolvable_tool_ref(db):
    out = await _handlers(db)["rnpv"].handler(
        {"cashflows": [[1.0, 100.0, 0.5]], "discount_rate": 0.1}
    )
    payload = _payload(out)
    assert payload["value"] is not None
    ref = payload["evidence_ref"]
    assert ref.startswith("tool:rnpv#")
    assert evidence.resolve(db, ref) is not None  # resolves, not merely non-empty


async def test_financial_and_market_tools_resolve(db):
    h = _handlers(db)
    cases = [
        ("cash_runway", {"cash_usd": 100.0, "monthly_burn_usd": 10.0}),
        ("implied_move", {"underlying_price": 50.0, "call_mid": 2.0, "put_mid": 2.0, "days_to_event": 5}),
        ("correlation_beta", {"asset_returns": [0.1, -0.2, 0.3, 0.0], "market_returns": [0.05, -0.1, 0.2, 0.01]}),
    ]
    for name, args in cases:
        payload = _payload(await h[name].handler(args))
        ref = payload["evidence_ref"]
        assert ref.startswith(f"tool:{name}#"), name
        assert evidence.resolve(db, ref) is not None, name


async def test_base_rate_returns_inline_citation(db):
    out = await _handlers(db)["base_rate"].handler(
        {"metric": "transition", "phase": "II", "indication": "all"}
    )
    payload = _payload(out)
    assert payload["value"] == 0.289
    cit = payload["citation"]  # inline citation, NOT a ref pointer
    assert cit["source_url"]
    assert cit["quote"]


async def test_base_rate_miss_is_error_payload_not_crash(db):
    out = await _handlers(db)["base_rate"].handler({"metric": "does_not_exist"})
    payload = _payload(out)
    assert "error" in payload  # the analyst sees "no base rate", never a hallucinated number
    assert "no base rate" in payload["error"]


async def test_analog_query_cited_as_resolvable_tool_ref(db, monkeypatch):
    monkeypatch.setenv("CT_EMBEDDER", "hash")  # keep default_embedder offline
    _seed_analog(db)
    out = await _handlers(db)["analog_query"].handler(
        {"context": "pdufa decision imminent", "filters": {"type": "pdufa"}}
    )
    payload = _payload(out)
    assert len(payload["results"]) == 1
    ref = payload["evidence_ref"]
    # CALL-04 regression guard: tool: ref (NOT kb:) that the Plan-06 verifier will accept.
    assert ref.startswith("tool:analog_query#")
    assert not ref.startswith("kb:")
    assert evidence.resolve(db, ref) is not None


async def test_analog_query_refuses_embedder_mismatch(db, monkeypatch):
    """Plan-05 warm-retrieval guard: the query path asserts embedder consistency BEFORE the KNN, so
    a corpus populated with a different embedder fails loud instead of returning garbage neighbours."""
    import pytest

    monkeypatch.setenv("CT_EMBEDDER", "hash")  # default_embedder -> hash_embed
    ev = EvidenceSource(url="https://ct.gov/x", retrieved_at="2026-08-14", snippet_hash="h")
    # a catalyst STAMPED with a foreign embedder name (as Plan 04's writer does)
    insert_claim(
        db, KBNode(kind="catalyst", attrs={"type": "pdufa", "embedder": "some_other_embedder"}), [ev],
        embed=kb.hash_embed, embed_text="x",
    )
    db.commit()
    with pytest.raises(ValueError, match="embedder"):
        await _handlers(db)["analog_query"].handler(
            {"context": "c", "filters": {"type": "pdufa"}, "k": 5})


async def test_query_playbooks_cited_as_resolvable_tool_ref(db):
    ev = EvidenceSource(url="https://x/y", retrieved_at="2026-08-14", snippet_hash="p")
    insert_playbook(db, "pdufa", "prior-cycle CRL", "size tiny / exit pre-event", 0.8, [ev])
    out = await _handlers(db)["query_playbooks"].handler({"scenario_type": "pdufa"})
    payload = _payload(out)
    assert len(payload["results"]) == 1
    ref = payload["evidence_ref"]
    assert ref.startswith("tool:query_playbooks#")
    assert not ref.startswith("kb:")
    assert evidence.resolve(db, ref) is not None


async def test_build_portfolio_is_in_the_analyst_tool_surface(db):
    assert "build_portfolio" in _handlers(db)   # backward-compat: purely additive


async def test_build_portfolio_handler_returns_structured_outcome(db):
    out = await _handlers(db)["build_portfolio"].handler({
        "positions": [{"ticker": "AAA", "side": "long", "size_pct": 0.5},
                      {"ticker": "BBB", "side": "short", "size_pct": 0.4}],
        "assumptions": {"AAA": {"expected_move": 0.2, "p_positive": 0.6},
                        "BBB": {"expected_move": 0.1, "p_positive": 0.55}},
    })
    p = _payload(out)
    assert p["gross_exposure"] == 0.9          # |0.5| + |-0.4|
    assert p["portfolio_vol"] is not None
    assert "worst_case" in p["scenarios"]
    assert "risk_of_ruin" in p["risk"]


async def test_build_portfolio_defaults_to_stored_hedge_profiles_offline(db):
    # No corr_source supplied -> the closure binds kb.hedge_profile(conn, .). An unstamped ticker
    # degrades to idiosyncratic (profile None) with NO crash, proving the offline default binding.
    out = await _handlers(db)["build_portfolio"].handler({
        "positions": [{"ticker": "NOSUCH", "side": "long", "size_pct": 0.5}],
        "assumptions": {"NOSUCH": {"expected_move": 0.2}},
    })
    p = _payload(out)
    assert p["portfolio_variance"] == 0.5**2 * 0.2**2   # own sigma, zero off-diagonal


async def test_analog_ref_is_stable_for_same_inputs(db, monkeypatch):
    monkeypatch.setenv("CT_EMBEDDER", "hash")
    _seed_analog(db)
    h = _handlers(db)
    args = {"context": "pdufa decision imminent", "filters": {"type": "pdufa"}}
    r1 = _payload(await h["analog_query"].handler(dict(args)))["evidence_ref"]
    r2 = _payload(await h["analog_query"].handler(dict(args)))["evidence_ref"]
    assert r1 == r2  # inputs-hash is reproducible
