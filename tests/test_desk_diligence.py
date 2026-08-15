"""Shared OFFLINE test harness for the independent diligence desk (Workflow-3).

Offline recipe (mirrors tests/test_desk_orchestrator.py): the diligence desk makes every
LLM call through the ONE `desk.diligence.run_structured` seam. `_patch_dd_seam` monkeypatches
that single seam with a role-routing fake (`_dd_router`) so the whole desk runs off recorded
fixtures with zero live API. Downstream plans (Waves 2-4: dimensions, synthesizer, orchestrator)
ADD their tests to this file and reuse these constants + helpers.

The 8 dimension keys are LOCKED for the whole phase — fixtures, prompts and the Wave-3
MONEY_TOUCHING set all use them verbatim.

`desk/diligence.py` does not exist until Wave 2, so this module NEVER imports it at top level:
`AnalystSignal` comes from contracts (available now), and the ONLY reference to
`catalyst_trader.desk.diligence` is the lazy import on the first line of `_patch_dd_seam`.
The smoke test below (`test_dd_fixtures_are_valid_signals`) runs now with no dependence on the
Wave-2 module; only tests that CALL `_patch_dd_seam` depend on it.
"""

import asyncio

import pytest

from catalyst_trader.contracts import (
    AnalystSignal,
    DiligenceDossier,
    DiligenceInput,
    KeyFinding,
)
from catalyst_trader.desk import evidence

# LOCKED dimension keys (verbatim across the whole phase).
DD_DIMENSIONS = [
    "trial_stats",
    "regulatory",
    "financials",
    "ownership_flow",
    "options_move",
    "hedge_revalidation",
    "liquidity",
    "historical_analog",
]

# The money-touching subset the Wave-3 synthesizer gates on (asserted against the module's
# frozenset in Wave 3).
MONEY_DIMS = {
    "financials",
    "ownership_flow",
    "options_move",
    "hedge_revalidation",
    "liquidity",
}

# The firewall-clean input the diligence desk receives (bare facts only — no Workflow-1/2
# reasoning; `pair` is a bare peer ticker).
DD_INPUT = {
    "ticker": "ACME",
    "catalyst": {
        "catalyst_id": "cat-001",
        "catalyst_type": "pdufa",
        "event_date": "2026-11-28",
        "company_name": "Acme Therapeutics",
    },
    "pair": "PEER",
}


def _dd_router(load_fixture, calls, *, narrative=None, verdict_signals=None):
    """Fake run_structured dispatching by role: the 8 dimension analysts (matched on the
    dimension token the prompt mandates) return their recorded AnalystSignal fixture; any
    other schema (the Wave-3 narrative model) is validated from the recorded dd_narrative
    fixture against whatever schema the caller passes — so this stays decoupled from the
    not-yet-existent narrative model's name. Every call is recorded in `calls`."""
    signals = {
        d: AnalystSignal.model_validate(load_fixture(f"agent_responses/dd_{d}_signal"))
        for d in DD_DIMENSIONS
    }
    if verdict_signals:
        signals.update(verdict_signals)

    async def _fake(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        calls.append({"prompt": prompt, "schema": schema, "model": model})
        if schema is AnalystSignal:
            for d in DD_DIMENSIONS:
                if f'"{d}"' in prompt:  # build_dimension_prompt mandates the token, like analysts
                    return signals[d]
            raise AssertionError("diligence analyst prompt matched no known dimension")
        if schema.__name__ == "SupportCheck":  # the Wave-4 enforce_dossier cite-or-drop gate
            return schema(supported=True, reason="ok")
        # Wave-3 narrative model: validate the recorded narrative against the passed schema
        # (no import of / name-coupling to desk.diligence, which may not exist yet).
        return schema.model_validate(narrative or load_fixture("agent_responses/dd_narrative"))

    return _fake


def _patch_dd_seam(monkeypatch, fake):
    from catalyst_trader.desk import diligence  # LAZY: Wave 2 creates this module

    monkeypatch.setattr(diligence, "run_structured", fake)


def test_dd_fixtures_are_valid_signals(load_fixture):
    """Every locked-dimension fixture is a valid AnalystSignal whose `.dimension` matches its
    key and carries >=1 sourced key_finding. Runs now, independent of desk.diligence."""
    for d in DD_DIMENSIONS:
        sig = AnalystSignal.model_validate(load_fixture(f"agent_responses/dd_{d}_signal"))
        assert sig.dimension == d
        assert len(sig.key_findings) >= 1


# ---------------------------------------------------------------------------
# Wave 2 — Task 1: 8 adversarial dimensions (prompts + runner + fan-out)
# ---------------------------------------------------------------------------


async def test_eight_dimensions_run_concurrently(db, monkeypatch, load_fixture):
    """gather_dimensions fans the 8 locked dimensions out through a SINGLE asyncio.gather of
    exactly 8 awaitables (spy the same way test_desk_orchestrator does) and returns 8 cited
    AnalystSignals, one per locked key."""
    from catalyst_trader.desk import diligence

    calls = []
    _patch_dd_seam(monkeypatch, _dd_router(load_fixture, calls))

    gathered = []
    real_gather = asyncio.gather

    async def _spy_gather(*aws, **kw):
        gathered.append(len(aws))
        return await real_gather(*aws, **kw)

    monkeypatch.setattr(diligence.asyncio, "gather", _spy_gather)

    signals = await diligence.gather_dimensions(db, DiligenceInput(**DD_INPUT))

    assert gathered == [8]  # one fan-out of exactly the 8 dimensions, not sequential awaits
    assert len(signals) == 8
    assert {s.dimension for s in signals} == set(DD_DIMENSIONS)
    for s in signals:
        assert len(s.key_findings) >= 1  # each dimension is source-cited


def test_dimension_prompt_reads_only_firewall_fields():
    """build_dimension_prompt interpolates ONLY DiligenceInput fields — the firewall cannot
    leak Workflow-1/2 reasoning into a prompt (there is no such data in scope)."""
    from catalyst_trader.desk import diligence

    prompt = diligence.build_dimension_prompt("financials", DiligenceInput(**DD_INPUT))
    assert "ACME" in prompt  # ticker
    assert "pdufa" in prompt  # catalyst fact
    assert '"financials"' in prompt  # the mandated dimension token (router matches on this)
    for leaked in ("thesis", "bull_strongest_point", "direction", "kill_criteria"):
        assert leaked not in prompt


def test_build_dimension_prompt_rejects_unknown_dimension():
    from catalyst_trader.desk import diligence

    import pytest

    with pytest.raises(ValueError):
        diligence.build_dimension_prompt("not_a_dimension", DiligenceInput(**DD_INPUT))


# ---------------------------------------------------------------------------
# Wave 2 — Task 2: money-dim prep seams + candidate-peer hedge + DILIGENCE_PARAMS
# ---------------------------------------------------------------------------

_LIQUID_OPTS = {
    "call_bid": 2.0, "call_ask": 2.2, "put_bid": 2.0, "put_ask": 2.2,
    "call_oi": 300, "put_oi": 300, "expiry": "2026-12-05", "catalyst_date": "2026-11-28",
}
_ILLIQUID_OPTS = {
    "call_bid": 0.0, "call_ask": 2.0, "put_bid": 2.0, "put_ask": 2.2,
    "call_oi": 10, "put_oi": 10, "expiry": "2026-12-05", "catalyst_date": "2026-11-28",
}


def test_options_dimension_degrades_on_illiquid():
    from catalyst_trader.desk import diligence

    P = diligence.DILIGENCE_PARAMS
    illiquid = diligence.options_context(_ILLIQUID_OPTS, underlying_price=100.0, days_to_event=14, params=P)
    assert "none/illiquid" in illiquid
    assert "LOW" in illiquid  # emit low confidence, do not fabricate IV
    assert "IV" in illiquid  # explicit "do NOT trust IV" instruction

    liquid = diligence.options_context(_LIQUID_OPTS, underlying_price=100.0, days_to_event=14, params=P)
    assert "options_data: ok" in liquid
    assert "%" in liquid  # carries the straddle-preferred implied move


def test_financials_context_carries_raw_figures():
    from catalyst_trader.desk import diligence

    ctx = diligence.financials_context(
        {"cash_usd": 500000000, "monthly_burn_usd": 20000000, "months_to_catalyst": 6}
    )
    assert ctx is not None
    assert "500000000" in ctx and "20000000" in ctx
    assert "mcp__quant__cash_runway" in ctx  # agent calls the tool; no arithmetic here
    assert diligence.financials_context(None) is None
    assert diligence.financials_context({}) is None


def test_ownership_context_carries_raw_figures():
    from catalyst_trader.desk import diligence

    ctx = diligence.ownership_context(
        {"short_interest_pct": 18.5, "days_to_cover": 4.2, "insider_net": -1200000}
    )
    assert ctx is not None
    assert "18.5" in ctx and "4.2" in ctx and "-1200000" in ctx
    assert diligence.ownership_context(None) is None
    assert diligence.ownership_context({}) is None


def test_trial_stats_context_from_provider():
    from catalyst_trader.desk import diligence

    study = {"phase": "Phase 3", "status": "Completed", "primary_endpoint": "OS", "enrollment": 450}
    ctx = diligence.trial_stats_context(study)
    assert ctx is not None
    assert "Phase 3" in ctx and "OS" in ctx
    assert diligence.trial_stats_context(None) is None
    assert diligence.trial_stats_context({}) is None


def test_liquidity_zero_flag():
    from catalyst_trader.desk import diligence

    assert diligence.zero_liquidity({"bid": 0.0, "volume": 100, "oi": 50}) is True
    assert diligence.zero_liquidity({"bid": 1.0, "volume": 0, "oi": 50}) is True
    assert diligence.zero_liquidity({"bid": 1.0, "volume": 100, "oi": 0}) is True
    assert diligence.zero_liquidity({"bid": 1.0, "volume": 100, "oi": 50}) is False


def test_hedge_dimension_revalidates_independently(db, embed, monkeypatch):
    """hedge_context re-runs validate_hedge INDEPENDENTLY, scoped to input.pair (candidate_peer)
    with input.ticker as target — never a Workflow-2 Hedge artifact."""
    from catalyst_trader.desk import diligence
    from catalyst_trader.contracts import Hedge

    captured = {}

    def _spy(conn, embed_, target, catalyst, entry, exit_by_date, analog_gaps, prices, *, candidate_peer=None):
        captured["candidate_peer"] = candidate_peer
        captured["target"] = target
        return Hedge(instrument="equity_peer", ticker=candidate_peer, payoff_direction=-1,
                     validated=True, covers="idiosyncratic", mechanism="same-indication rival",
                     conditional_worst=-0.4)

    monkeypatch.setattr(diligence.risk, "validate_hedge", _spy)
    inp = DiligenceInput(**DD_INPUT)
    ctx = diligence.hedge_context(db, embed, inp, entry="2026-11-27", exit_by_date="2026-12-05",
                                  analog_gaps={}, prices={})

    assert captured["candidate_peer"] == inp.pair == "PEER"
    assert captured["target"] == inp.ticker == "ACME"
    assert "PEER" in ctx  # the independently-produced Hedge is reflected in the context


def test_hedge_dimension_none_falls_back(db, embed, monkeypatch):
    from catalyst_trader.desk import diligence

    monkeypatch.setattr(diligence.risk, "validate_hedge", lambda *a, **k: None)
    inp = DiligenceInput(**DD_INPUT)
    ctx = diligence.hedge_context(db, embed, inp, entry="2026-11-27", exit_by_date="2026-12-05",
                                  analog_gaps={}, prices={})
    assert "no valid inverse hedge" in ctx.lower()  # HEDGE-04 fallback


def test_diligence_params_survive_seeded_path(db):
    """After the STEADY-state seeded path, diligence thresholds still resolve from the
    module-level DILIGENCE_PARAMS — kb.load_params (a seeded strategy dict) has NO diligence key."""
    from catalyst_trader import kb
    from catalyst_trader.desk import diligence

    kb.seed_fitted_params(db)

    assert diligence.options_liquid(_LIQUID_OPTS, params=diligence.DILIGENCE_PARAMS) is True
    assert diligence.DILIGENCE_PARAMS["diligence"]["dimension_min_conf"] == 0.5
    assert "diligence" not in kb.load_params(db, "pdufa")


# ---------------------------------------------------------------------------
# Wave 3 — Task 1: deterministic synthesize_verdict + dimension_passed + MONEY_TOUCHING
# ---------------------------------------------------------------------------

# Test-local thresholds (mirrors DILIGENCE_PARAMS shape; money code reads from params,
# never a literal). Kept independent so a threshold drift in the module can't silently
# pass these edge tests.
PARAMS = {"diligence": {"dimension_score_floor": -0.2, "dimension_min_conf": 0.5}}


def _sig(dimension, *, score=0.3, confidence=0.7):
    """A data-backed AnalystSignal for `dimension` (one cited finding, score above floor,
    confidence above min_conf) — i.e. `dimension_passed` True under PARAMS by default."""
    return AnalystSignal(
        dimension=dimension, ticker="ACME", catalyst_id="cat-001",
        score=score, confidence=confidence,
        key_findings=[KeyFinding(claim="cited fact", evidence_ref="tool:x#abc123")],
    )


def _all_pass():
    return [_sig(d) for d in DD_DIMENSIONS]


def test_money_touching_matches_harness():
    """The synthesizer's money set is EXACTLY the harness MONEY_DIMS (the locked money keys)."""
    from catalyst_trader.desk import diligence

    assert diligence.MONEY_TOUCHING == frozenset(MONEY_DIMS)


@pytest.mark.parametrize("failing", sorted(MONEY_DIMS))
def test_one_money_dimension_failure_forces_no_go(failing):
    """Every other dimension passes but ONE money dim fails dimension_passed -> NO-GO.
    Parametrized over each of the 5 money dims failing individually."""
    from catalyst_trader.desk import diligence

    findings = [
        _sig(d, confidence=0.1) if d == failing else _sig(d)
        for d in DD_DIMENSIONS
    ]
    assert diligence.synthesize_verdict(findings, liquidity_zero=False, params=PARAMS) == "no_go"


def test_go_requires_all_money_dimensions_backed():
    """All 5 money dims present + data-backed -> GO. Removing ANY single money dim
    (a 'tie'/missing) -> NO-GO (GO needs the full money set present AND all backed)."""
    from catalyst_trader.desk import diligence

    findings = _all_pass()
    assert diligence.synthesize_verdict(findings, liquidity_zero=False, params=PARAMS) == "go"

    for money in MONEY_DIMS:
        subset = [f for f in findings if f.dimension != money]
        assert diligence.synthesize_verdict(subset, liquidity_zero=False, params=PARAMS) == "no_go"


def test_non_money_dimension_failure_does_not_block():
    """A non-money dim failing while all money dims pass -> still GO (asymmetry is money-scoped)."""
    from catalyst_trader.desk import diligence

    for nonmoney in ("trial_stats", "regulatory", "historical_analog"):
        findings = [
            _sig(d, confidence=0.05, score=-0.9) if d == nonmoney else _sig(d)
            for d in DD_DIMENSIONS
        ]
        assert diligence.synthesize_verdict(findings, liquidity_zero=False, params=PARAMS) == "go"


def test_zero_liquidity_hard_fails():
    """Zero-liquidity is a hard NO-GO even when every dimension passes."""
    from catalyst_trader.desk import diligence

    assert diligence.synthesize_verdict(_all_pass(), liquidity_zero=True, params=PARAMS) == "no_go"


def test_ties_default_no_go():
    """An empty money set (no money dims present) -> NO-GO (never a silent GO)."""
    from catalyst_trader.desk import diligence

    findings = [_sig(d) for d in DD_DIMENSIONS if d not in MONEY_DIMS]
    assert diligence.synthesize_verdict(findings, liquidity_zero=False, params=PARAMS) == "no_go"


def test_dimension_passed_reads_params():
    """Thresholds come from params (missing-key-raises, NO hardcoded literals). A cited signal
    below min_conf / below score floor / with zero cited findings -> False; otherwise True."""
    from catalyst_trader.desk import diligence

    sig = _sig("financials")
    with pytest.raises(KeyError):
        diligence.dimension_passed(sig, params={})
    with pytest.raises(KeyError):  # missing dimension_min_conf
        diligence.dimension_passed(sig, params={"diligence": {"dimension_score_floor": -0.2}})

    assert diligence.dimension_passed(_sig("financials", confidence=0.4), params=PARAMS) is False
    assert diligence.dimension_passed(_sig("financials", score=-0.5), params=PARAMS) is False
    assert diligence.dimension_passed(_sig("financials"), params=PARAMS) is True

    # zero cited findings (constructed to bypass the AnalystSignal validator) -> False (defense).
    empty = _sig("financials").model_copy(update={"key_findings": []})
    assert diligence.dimension_passed(empty, params=PARAMS) is False


# ---------------------------------------------------------------------------
# Wave 3 — Task 2: verdict-immutable LLM narrative + enforce_dossier cite-or-drop
# ---------------------------------------------------------------------------


def _seed_evidence(db, *, snippet, quote):
    """Insert one resolvable EvidenceSource node; return its node id (a kb: ref target)."""
    from catalyst_trader.kb import EvidenceSource, KBNode, insert_claim

    insert_claim(
        db, KBNode(kind="playbook", attrs={"x": 1}),
        [EvidenceSource(url="https://ct.gov/NCT", retrieved_at="2026-08-14",
                        snippet_hash=snippet, quote=quote)],
    )
    row = db.execute(
        "SELECT id FROM kb_node WHERE kind='evidence_source' "
        "AND json_extract(attrs_json,'$.snippet_hash')=?",
        (snippet,),
    ).fetchone()
    return row["id"]


def test_narrative_schema_is_narrative_only():
    """The narrative model structurally CANNOT carry a verdict — the go/no-go is not
    representable in the LLM's output schema."""
    from catalyst_trader.desk import diligence

    assert "verdict" not in diligence.DiligenceNarrative.model_fields


async def test_llm_narrative_cannot_override_verdict(monkeypatch, load_fixture):
    """A findings set that deterministically yields no_go, plus a narrative fixture that
    argues (in prose) for going ahead: the assembled dossier's verdict is the DETERMINISTIC
    no_go (overwritten via model_copy), and the narrative TEXT is carried through."""
    from catalyst_trader.desk import diligence

    calls = []
    _patch_dd_seam(monkeypatch, _dd_router(load_fixture, calls))

    findings = [
        _sig(d, confidence=0.1) if d == "financials" else _sig(d)
        for d in DD_DIMENSIONS
    ]
    verdict = diligence.synthesize_verdict(findings, liquidity_zero=False, params=PARAMS)
    assert verdict == "no_go"

    narrative = await diligence._narrative(findings, verdict)
    dossier = diligence.assemble_dossier(findings, verdict, narrative, liquidity_zero=False, params=PARAMS)

    assert dossier.verdict == "no_go"  # deterministic verdict wins
    assert dossier.red_flags == narrative.red_flags  # narrative text carried through
    assert dossier.strongest_disconfirming_evidence == narrative.strongest_disconfirming_evidence
    assert dossier.residual_risks == narrative.residual_risks
    # the narrative call ran against the verdict-free schema
    assert any(c["schema"] is diligence.DiligenceNarrative for c in calls)


async def test_dossier_cite_or_drop(db, monkeypatch):
    """enforce_dossier drops unresolvable refs (garbage, kb:999999); a tool: ref survives
    by construction; a kb: ref survives only if its cited claim is quote_supported. Mirrors
    the verifier two-stage shape, reuses evidence primitives, NEVER calls verifier.enforce."""
    from catalyst_trader.desk import diligence

    nid = _seed_evidence(db, snippet="h1", quote="Short interest spiked to 18% before the event.")
    tool_ref = evidence.tool_ref_for("cash_runway", {"cash_usd": 1})
    signals = [
        _sig("ownership_flow").model_copy(update={
            "key_findings": [KeyFinding(claim="short interest spiked to 18%", evidence_ref=f"kb:{nid}")],
        }),
    ]
    dossier = DiligenceDossier(
        verdict="no_go", per_dimension=[], strongest_disconfirming_evidence="x",
        all_evidence_refs=[f"kb:{nid}", tool_ref, "garbage", "kb:999999"],
    )

    async def _fake(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        return schema(supported=True, reason="ok")

    monkeypatch.setattr(diligence, "run_structured", _fake)

    out = await diligence.enforce_dossier(db, dossier, signals=signals)

    assert f"kb:{nid}" in out.all_evidence_refs   # supported quote survives
    assert tool_ref in out.all_evidence_refs       # resolved-by-construction survives
    assert "garbage" not in out.all_evidence_refs  # unresolvable dropped
    assert "kb:999999" not in out.all_evidence_refs  # missing node dropped


async def test_dossier_no_go_all_unsupported_flags_audit(db):
    """A NO-GO whose disconfirming evidence loses ALL support is surfaced as an audit flag,
    not silently passed."""
    from catalyst_trader.desk import diligence

    dossier = DiligenceDossier(
        verdict="no_go", per_dimension=[], strongest_disconfirming_evidence="x",
        all_evidence_refs=["garbage", "kb:999999"],
    )
    out = await diligence.enforce_dossier(db, dossier, signals=[])

    assert out.all_evidence_refs == []
    assert any("AUDIT" in f for f in out.red_flags)


# ---------------------------------------------------------------------------
# Wave 4 — Task 1: run_diligence — firewalled entry point, end-to-end (offline)
# ---------------------------------------------------------------------------

_DD_OPTS = {
    "call_bid": 2.0, "call_ask": 2.2, "put_bid": 2.0, "put_ask": 2.2,
    "call_oi": 300, "put_oi": 300, "expiry": "2026-12-05", "catalyst_date": "2026-11-28",
}


def _full_market_data():
    """A fully-grounded market_data — EVERY money-touching dim has its raw-data seam value
    (options / financials / ownership / hedge / liquidity) plus the non-money trial record.
    Deleting any money key models the ungrounded-money case."""
    return {
        "options": {"quote": dict(_DD_OPTS), "underlying_price": 100.0, "days_to_event": 14},
        "financials": {"cash_usd": 500000000, "monthly_burn_usd": 20000000, "months_to_catalyst": 6},
        "ownership": {"short_interest_pct": 18.5, "days_to_cover": 4.2, "insider_net": -1200000},
        "trial": {"phase": "Phase 3", "status": "Completed", "primary_endpoint": "OS", "enrollment": 450},
        "hedge": {"entry": "2026-11-27", "exit_by_date": "2026-12-05", "analog_gaps": {}, "prices": {}},
        "liquidity_quote": {"bid": 1.0, "volume": 100, "oi": 50},
    }


def _mock_valid_hedge(monkeypatch):
    """Stub the INDEPENDENT hedge re-validation with a validated inverse Hedge so the hedge dim
    is grounded offline (the real validate_hedge is exercised in test_hedge_dimension_*)."""
    from catalyst_trader.contracts import Hedge
    from catalyst_trader.desk import diligence

    monkeypatch.setattr(diligence.risk, "validate_hedge", lambda *a, **k: Hedge(
        instrument="equity_peer", ticker="PEER", payoff_direction=-1, validated=True,
        covers="idiosyncratic", mechanism="same-indication rival", conditional_worst=-0.4,
    ))


def test_run_diligence_signature_is_firewalled():
    """The firewall at the type level: run_diligence's trade-facts parameter is annotated EXACTLY
    DiligenceInput, and NO parameter is annotated with a Workflow-1/2 artifact — there is provably
    no code path through which a DebateVerdict/TradeProposal/StrategyDossier/RiskAssessment enters."""
    import typing

    from catalyst_trader.contracts import (
        DebateVerdict,
        DiligenceInput,
        RiskAssessment,
        StrategyDossier,
        TradeProposal,
    )
    from catalyst_trader.desk import diligence

    hints = typing.get_type_hints(diligence.run_diligence)
    assert DiligenceInput in hints.values()
    forbidden = {DebateVerdict, TradeProposal, StrategyDossier, RiskAssessment}
    assert not (forbidden & set(hints.values()))

    # 06.7-02 (RECON-06): the re-trigger plumbing added to debate.run/builder.build/orchestrators
    # must NOT leak into the DD firewall — run_diligence gains NO extra_context (and no WF-1/2 param).
    import inspect
    params = inspect.signature(diligence.run_diligence).parameters
    assert "extra_context" not in params  # DD only ever re-runs on a sealed DiligenceInput


async def test_run_diligence_end_to_end(db, monkeypatch, load_fixture):
    """Fully-grounded market_data + all-passing dimension fixtures -> a GO DiligenceDossier with
    8 per-dimension entries, evidence surviving the gate, and residual_risks from the narrative.
    All 8 dimensions ran (one fan-out) and the narrative ran once. Fully offline."""
    from catalyst_trader.desk import diligence

    _mock_valid_hedge(monkeypatch)
    calls = []
    _patch_dd_seam(monkeypatch, _dd_router(load_fixture, calls))

    dossier = await diligence.run_diligence(
        db, DiligenceInput(**DD_INPUT), market_data=_full_market_data()
    )

    assert isinstance(dossier, DiligenceDossier)
    assert dossier.verdict == "go"  # fully grounded + all fixtures pass -> GO
    assert len(dossier.per_dimension) == 8
    assert dossier.all_evidence_refs  # tool: refs survived cite-or-drop
    assert dossier.residual_risks  # populated from the narrative fixture
    assert len([c for c in calls if c["schema"] is AnalystSignal]) == 8
    assert len([c for c in calls if c["schema"] is diligence.DiligenceNarrative]) == 1


async def test_run_diligence_verdict_is_deterministic(db, monkeypatch, load_fixture):
    """Swap the (grounded) financials dim to a failing signal: the returned verdict is no_go
    regardless of the narrative's tone — the Wave-3 model_copy overwrite through the real pipeline."""
    from catalyst_trader.desk import diligence

    _mock_valid_hedge(monkeypatch)
    failing = _sig("financials", confidence=0.1)  # below min_conf -> dimension_passed False
    calls = []
    _patch_dd_seam(monkeypatch, _dd_router(load_fixture, calls, verdict_signals={"financials": failing}))

    dossier = await diligence.run_diligence(
        db, DiligenceInput(**DD_INPUT), market_data=_full_market_data()
    )
    assert dossier.verdict == "no_go"


async def test_run_diligence_zero_liquidity_no_go(db, monkeypatch, load_fixture):
    """A zero-liquidity leg is a hard NO-GO end-to-end even with all dimensions passing."""
    from catalyst_trader.desk import diligence

    _mock_valid_hedge(monkeypatch)
    calls = []
    _patch_dd_seam(monkeypatch, _dd_router(load_fixture, calls))
    md = _full_market_data()
    md["liquidity_quote"] = {"bid": 0.0, "volume": 0, "oi": 0}

    dossier = await diligence.run_diligence(db, DiligenceInput(**DD_INPUT), market_data=md)
    assert dossier.verdict == "no_go"


@pytest.mark.parametrize("missing", ["financials", "ownership"])
async def test_run_diligence_money_dim_without_raw_data_is_no_go(db, monkeypatch, load_fixture, missing):
    """A money-touching dim with NO raw-data seam value cannot be grounded, so it CANNOT yield a
    GO — even though its dimension fixture is a PASSING GO signal. The ungrounded money dim forces
    NO-GO (no false GO from a hallucinated finding). Parametrized over financials + ownership_flow."""
    from catalyst_trader.desk import diligence

    _mock_valid_hedge(monkeypatch)
    calls = []
    _patch_dd_seam(monkeypatch, _dd_router(load_fixture, calls))
    md = _full_market_data()
    del md[missing]  # no raw data for this money dim -> ungrounded -> forced NO-GO

    dossier = await diligence.run_diligence(db, DiligenceInput(**DD_INPUT), market_data=md)
    assert dossier.verdict == "no_go"
