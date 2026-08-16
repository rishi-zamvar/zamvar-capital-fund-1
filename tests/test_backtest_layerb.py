"""Layer B (BACK-03) — the guarded AGENTIC replay, labeled biased_optimistic.

These tests drive the REAL desk pipeline (run_desk) over the 07-02 point-in-time event set
with the single SDK seam (desk.runtime.run_structured) monkeypatched per module, so the whole
replay runs offline with ZERO live API. They prove the money-honesty invariants:

  (Task 1) replay runs the real desk behind the mocked seam; every result is a STRUCTURAL
           biased_optimistic=True; the catalyst handed to the desk is outcome-blind
           (extra="forbid" firewall); the run refuses if the desk ALLOWED_TOOLS is not web-free.
  (Task 2) sampling logs every dropped catalyst (no silent [:N] cap).
"""

import pytest
from pydantic import ValidationError

from catalyst_trader.backtest.layerb import (
    LayerBResult,
    OutcomeBlindCatalyst,
    run_layer_b,
    sample_catalysts,
)
from catalyst_trader.contracts import AnalystSignal, DebateVerdict
from catalyst_trader.desk import analysts, debate, diligence, md, orchestrator, verifier
from catalyst_trader.desk.debate import Argument
from catalyst_trader.desk.guardrails import GuardrailViolation
from tests.synth_history import seed_history, week_ends

DIMENSIONS = ["clinical", "regulatory", "financial", "market_sentiment"]


def _seam(load_fixture):
    """A role-routing fake run_structured returning the recorded fixtures — the offline desk seam."""
    signals = {
        d: AnalystSignal.model_validate(load_fixture(f"agent_responses/{d}_signal"))
        for d in DIMENSIONS
    }
    bull = Argument.model_validate(load_fixture("agent_responses/bull_argument"))
    bear = Argument.model_validate(load_fixture("agent_responses/bear_argument"))
    verdict = DebateVerdict.model_validate(load_fixture("agent_responses/moderator_verdict"))
    support = verifier.SupportCheck.model_validate(load_fixture("agent_responses/verifier_support"))

    async def _fake(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        if schema is AnalystSignal:
            for d in DIMENSIONS:
                if f'"{d}"' in prompt:
                    return signals[d]
            raise AssertionError("analyst prompt matched no known dimension")
        if schema is Argument:
            return bull if "You are the BULL" in prompt else bear
        if schema is DebateVerdict:
            return verdict
        if schema is verifier.SupportCheck:
            return support
        raise AssertionError(f"unexpected schema {schema!r}")

    return _fake


def _patch_seam(monkeypatch, fake):
    """Patch the single SDK seam across every desk module the pipeline routes through."""
    for mod in (analysts, debate, verifier, diligence, md):
        monkeypatch.setattr(mod, "run_structured", fake, raising=False)


def _seed_one_catalyst(db):
    """Seed a deterministic history with ONE point-in-time-visible catalyst; return (start, end)."""
    weeks = week_ends(6)
    seed_history(
        db,
        tickers=["ACME", "PEER"],
        weeks=6,
        catalysts=[{"ticker": "ACME", "event_date": weeks[3], "last_verified_at": weeks[0]}],
    )
    return weeks[0], weeks[-1]


# ============================== Task 1: replay + label + firewalls =====================


async def test_layer_b_runs_real_desk_with_mocked_seam(db, embed, monkeypatch, load_fixture):
    """run_layer_b drives run_desk over the point-in-time event set, fully offline; results non-empty."""
    _patch_seam(monkeypatch, _seam(load_fixture))
    start, end = _seed_one_catalyst(db)

    batch = await run_layer_b(db, embed, start=start, end=end)

    assert batch.results, "the seeded catalyst must be replayed"
    r = batch.results[0]
    assert isinstance(r, LayerBResult)
    assert r.ticker == "ACME"
    assert r.direction in ("positive", "negative")


async def test_layer_b_result_labeled_biased_optimistic(db, embed, monkeypatch, load_fixture):
    """Every LayerBResult carries biased_optimistic=True as a STRUCTURAL contract field."""
    _patch_seam(monkeypatch, _seam(load_fixture))
    start, end = _seed_one_catalyst(db)

    batch = await run_layer_b(db, embed, start=start, end=end)

    assert batch.results
    assert all(r.biased_optimistic is True for r in batch.results)
    # it is a real field with a True default, not a comment
    assert LayerBResult.model_fields["biased_optimistic"].default is True


def test_layer_b_catalyst_is_outcome_blind():
    """Projecting a catalyst that smuggles a realized-outcome field is a ValidationError (firewall)."""
    OutcomeBlindCatalyst(ticker="ACME", catalyst_type="pdufa", event_date="2024-01-22")  # clean OK
    with pytest.raises(ValidationError):
        OutcomeBlindCatalyst(
            ticker="ACME", catalyst_type="pdufa", event_date="2024-01-22",
            realized_direction="positive",  # leaked outcome -> extra="forbid" rejects it
        )


async def test_layer_b_asserts_web_free(db, embed, monkeypatch, load_fixture):
    """A monkeypatched desk ALLOWED_TOOLS containing a web tool makes run_layer_b refuse."""
    _patch_seam(monkeypatch, _seam(load_fixture))
    start, end = _seed_one_catalyst(db)
    monkeypatch.setattr(
        orchestrator, "ALLOWED_TOOLS", [*orchestrator.ALLOWED_TOOLS, "mcp__web__fetch"]
    )

    with pytest.raises(GuardrailViolation):
        await run_layer_b(db, embed, start=start, end=end)


# ============================== Task 2: sampling + logged drop-list ====================


def _seed_four_catalysts(db):
    """Seed four point-in-time-visible catalysts across distinct weeks; return (start, end)."""
    weeks = week_ends(10)
    cats = [
        {"ticker": t, "event_date": weeks[i], "last_verified_at": weeks[0]}
        for t, i in (("ACME", 3), ("BETA", 4), ("GAMM", 5), ("DELT", 6))
    ]
    seed_history(db, tickers=["ACME", "BETA", "GAMM", "DELT"], weeks=10, catalysts=cats)
    return weeks[0], weeks[-1]


async def test_layer_b_sample_logs_dropped(db, embed, monkeypatch, load_fixture):
    """n < available -> the dropped list is populated, sampled+dropped == all, reason set."""
    _patch_seam(monkeypatch, _seam(load_fixture))
    start, end = _seed_four_catalysts(db)

    batch = await run_layer_b(db, embed, start=start, end=end, n=2)

    log = batch.sample_log
    assert len(log.sampled) == 2
    assert len(log.dropped) >= 1, "n < available must log the dropped catalysts, never silently cap"
    assert len(log.sampled) + len(log.dropped) == 4
    assert log.reason
    assert len(batch.results) == len(log.sampled)


async def test_layer_b_sample_all_when_n_ge_len(db, embed, monkeypatch, load_fixture):
    """n >= available -> everything sampled, nothing dropped (the SampleLog is a full replay)."""
    _patch_seam(monkeypatch, _seam(load_fixture))
    start, end = _seed_one_catalyst(db)

    batch = await run_layer_b(db, embed, start=start, end=end, n=99)

    assert batch.sample_log.dropped == []
    assert len(batch.sample_log.sampled) == len(batch.results) == 1


def test_layer_b_sample_catalysts_no_silent_cap():
    """sample_catalysts records EVERY dropped item with a reason — never a truncated list."""
    items = [{"catalyst": {"catalyst_type": "pdufa"}} for _ in range(5)]
    out = sample_catalysts(items, n=2, seed=0)
    assert len(out["sampled"]) == 2
    assert len(out["dropped"]) == 3
    assert len(out["sampled"]) + len(out["dropped"]) == len(items)
    assert out["reason"]


def test_layer_b_sample_catalysts_deterministic():
    """Same (items, n, seed) -> identical sample (deterministic, reproducible)."""
    items = [{"catalyst": {"catalyst_type": t}} for t in ("a", "b", "a", "b", "c", "c")]
    a = sample_catalysts(items, n=3, seed=7)
    b = sample_catalysts(items, n=3, seed=7)
    assert a["sampled"] == b["sampled"]
