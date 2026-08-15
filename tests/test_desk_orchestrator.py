"""Workflow-1a end-to-end (CALL-01..04 together): run_desk wires the whole desk —
four concurrent analysts -> bounded bull/bear/moderator debate -> verifier-gated
verdict — with every role call routed through the one desk.runtime.run_structured
seam. Patching that seam per module (analysts / debate / verifier) with a
role-routing fake drives the entire pipeline off the recorded fixtures, so the desk
runs offline with zero live API.

These tests prove the three load-bearing properties:
  (a) end-to-end: run_desk returns a finalized, verifier-survived DebateVerdict —
      binary direction, non-empty kill_criteria, both strongest points, surviving refs;
  (b) fan-out: the four dimension analysts run concurrently via a single asyncio.gather;
  (c) gate: losing all support raises VerdictUnsupportedError — an unsupported verdict
      never finalizes (and the structural drop spends no opus semantic call).
"""

import asyncio

import pytest

from catalyst_trader.contracts import AnalystSignal, DebateVerdict
from catalyst_trader.desk import analysts, debate, orchestrator, verifier
from catalyst_trader.desk.debate import Argument

DIMENSIONS = ["clinical", "regulatory", "financial", "market_sentiment"]

CATALYST = {
    "ticker": "ACME",
    "company_name": "Acme Therapeutics",
    "catalyst_type": "pdufa",
    "event_date": "2026-11-28",
    "catalyst_id": "cat-001",
}


def _router(load_fixture, verdict, calls):
    """Fake run_structured that dispatches by role: the four analyst dimensions (matched
    on the dimension token the prompt mandates), bull vs bear, the moderator verdict, and
    the verifier's SupportCheck — each returning its recorded fixture."""
    signals = {
        d: AnalystSignal.model_validate(load_fixture(f"agent_responses/{d}_signal"))
        for d in DIMENSIONS
    }
    bull = Argument.model_validate(load_fixture("agent_responses/bull_argument"))
    bear = Argument.model_validate(load_fixture("agent_responses/bear_argument"))
    support = verifier.SupportCheck.model_validate(load_fixture("agent_responses/verifier_support"))

    async def _fake(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        calls.append({"prompt": prompt, "schema": schema, "model": model})
        if schema is AnalystSignal:
            for d in DIMENSIONS:
                if f'"{d}"' in prompt:   # build_prompt: Emit `dimension` EXACTLY as "<d>"
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
    for mod in (analysts, debate, verifier):
        monkeypatch.setattr(mod, "run_structured", fake)


async def test_run_desk_end_to_end(db, monkeypatch, load_fixture):
    """catalyst -> 4 cited signals -> debate -> verifier-gated verdict, fully offline.
    The moderator's evidence_refs are all tool: refs (resolved-by-construction), so they
    survive the verifier and the verdict finalizes."""
    verdict = DebateVerdict.model_validate(load_fixture("agent_responses/moderator_verdict"))
    calls = []
    _patch_seam(monkeypatch, _router(load_fixture, verdict, calls))

    out = await orchestrator.run_desk(db, CATALYST)

    assert isinstance(out, DebateVerdict)
    assert out.direction in ("positive", "negative")       # binary (CALL-03)
    assert out.kill_criteria                               # required falsification criteria
    assert out.bull_strongest_point.strip()               # both sides' strongest point survives
    assert out.bear_strongest_point.strip()
    assert out.evidence_refs                               # support survived the verifier (CALL-04)

    # all four analysts ran, then the moderator, then the verifier semantic gate.
    assert len([c for c in calls if c["schema"] is AnalystSignal]) == 4
    assert any(c["schema"] is DebateVerdict for c in calls)
    assert any(c["schema"] is verifier.SupportCheck for c in calls)


async def test_analysts_run_concurrently(db, monkeypatch, load_fixture):
    """The four analysts fan out through a single asyncio.gather of exactly four awaitables,
    issuing four distinct dimension prompts (concurrent, isolated sessions — CALL-01)."""
    verdict = DebateVerdict.model_validate(load_fixture("agent_responses/moderator_verdict"))
    calls = []
    _patch_seam(monkeypatch, _router(load_fixture, verdict, calls))

    gathered = []
    real_gather = asyncio.gather

    async def _spy_gather(*aws, **kw):
        gathered.append(len(aws))
        return await real_gather(*aws, **kw)

    monkeypatch.setattr(orchestrator.asyncio, "gather", _spy_gather)

    await orchestrator.run_desk(db, CATALYST)

    assert gathered == [4]   # one fan-out of exactly the four analysts, not sequential awaits
    analyst_prompts = [c["prompt"] for c in calls if c["schema"] is AnalystSignal]
    dims = {d for d in DIMENSIONS for p in analyst_prompts if f'"{d}"' in p}
    assert dims == set(DIMENSIONS)   # four distinct dimension prompts issued


async def test_verifier_gates_run_desk(db, monkeypatch, load_fixture):
    """If the moderator's every ref fails structural resolution, run_desk surfaces the
    finalize-blocked error — it never returns an unsupported verdict. The structural drop
    spends no opus semantic call."""
    base = load_fixture("agent_responses/moderator_verdict")
    base["evidence_refs"] = ["garbage", "kb:999999"]   # unresolvable + absent node -> all dropped
    verdict = DebateVerdict.model_validate(base)
    calls = []
    _patch_seam(monkeypatch, _router(load_fixture, verdict, calls))

    with pytest.raises(verifier.VerdictUnsupportedError):
        await orchestrator.run_desk(db, CATALYST)

    assert not any(c["schema"] is verifier.SupportCheck for c in calls)  # blocked structurally


async def test_run_desk_passes_extra_context(db, monkeypatch, load_fixture):
    """06.7-02 (RECON-02): run_desk threads extra_context THROUGH to debate.run so a GP re-trigger
    re-reasons the debate. Default None keeps the Phase-4 path byte-for-byte."""
    captured = {}

    async def _fake_run(signals, catalyst, rounds=orchestrator.MAX_ROUNDS, *, extra_context=None):
        captured["extra_context"] = extra_context
        return DebateVerdict.model_validate(load_fixture("agent_responses/moderator_verdict"))

    async def _fake_analyst(dim, catalyst, **kw):
        return AnalystSignal.model_validate(load_fixture(f"agent_responses/{dim}_signal"))

    async def _fake_enforce(conn, verdict, **kw):
        return verdict

    monkeypatch.setattr(orchestrator.debate, "run", _fake_run)
    monkeypatch.setattr(orchestrator.verifier, "enforce", _fake_enforce)
    monkeypatch.setattr(orchestrator.analysts, "run_analyst", _fake_analyst)

    await orchestrator.run_desk(db, CATALYST, extra_context="GP: reconsider the AdCom gap")
    assert captured["extra_context"] == "GP: reconsider the AdCom gap"

    await orchestrator.run_desk(db, CATALYST)  # default omitted -> None (Phase-4 byte-for-byte)
    assert captured["extra_context"] is None
