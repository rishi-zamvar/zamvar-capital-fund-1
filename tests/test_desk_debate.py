"""The research layer (CALL-02 + CALL-03): a bounded bull<->bear debate in REAL
context isolation, then a moderator that synthesizes a binary DebateVerdict.

Bull and Bear are DISTINCT run_structured invocations = fresh isolated sessions.
Each side sees only the shared AnalystSignals + the prior opposing FINAL argument
text, never the opponent's private scratchpad/transcript. These tests fake the
run_structured seam (dispatching on schema) so the whole suite runs offline.
"""

from catalyst_trader.contracts import AnalystSignal, DebateVerdict, KeyFinding
from catalyst_trader.desk import MAX_ROUNDS
from catalyst_trader.desk import debate
from catalyst_trader.desk.debate import Argument

CATALYST = {
    "ticker": "ACME",
    "company_name": "Acme Therapeutics",
    "catalyst_type": "pdufa",
    "event_date": "2026-11-28",
    "catalyst_id": "cat-001",
}

SIGNALS = [
    AnalystSignal(
        dimension="clinical", ticker="ACME", catalyst_id="cat-001", score=0.5, confidence=0.6,
        thesis="The science supports a positive readout: the pivotal endpoint was met with strong significance.",
        key_findings=[KeyFinding(claim="Phase 3 endpoint met p<0.001", evidence_ref="tool:base_rate#a1b2c3")],
        unknowns=["secondary endpoint durability not reported"],
    ),
    AnalystSignal(
        dimension="financial", ticker="ACME", catalyst_id="cat-001", score=-0.3, confidence=0.5,
        thesis="Financially fragile into the event: cash runway lapses just after the PDUFA, raising dilution risk.",
        key_findings=[KeyFinding(claim="cash runway ends one quarter post-PDUFA", evidence_ref="tool:cash_runway#99aa88")],
        unknowns=["dilution timing unknown"],
    ),
]


def _seam(bull: Argument, bear: Argument, verdict: DebateVerdict, calls: list):
    """Fake run_structured: records every call and dispatches on schema/role."""

    async def _fake(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        calls.append({"prompt": prompt, "schema": schema, "model": model})
        if schema is DebateVerdict:
            return verdict
        return bull if "You are the BULL" in prompt else bear

    return _fake


def _fixtures(load_fixture):
    return (
        Argument.model_validate(load_fixture("agent_responses/bull_argument")),
        Argument.model_validate(load_fixture("agent_responses/bear_argument")),
        DebateVerdict.model_validate(load_fixture("agent_responses/moderator_verdict")),
    )


async def test_bull_bear_context_isolation(monkeypatch, load_fixture):
    bull, bear, verdict = _fixtures(load_fixture)
    calls = []
    monkeypatch.setattr(debate, "run_structured", _seam(bull, bear, verdict, calls))

    await debate.run(SIGNALS, CATALYST, rounds=2)

    bull_prompts = [c["prompt"] for c in calls if c["schema"] is Argument and "You are the BULL" in c["prompt"]]
    bear_prompts = [c["prompt"] for c in calls if c["schema"] is Argument and "You are the BEAR" in c["prompt"]]

    # Neither side ever sees the opponent's private scratchpad (real isolation, not a shared board).
    assert all(bear.scratchpad not in p for p in bull_prompts)
    assert all(bull.scratchpad not in p for p in bear_prompts)
    # But each side IS threaded the opponent's shareable FINAL argument text.
    assert any(bear.argument in p for p in bull_prompts)   # bull round 2 replies to bear round 1
    assert all(bull.argument in p for p in bear_prompts)   # bear replies to the bull case


async def test_debate_is_bounded(monkeypatch, load_fixture):
    bull, bear, verdict = _fixtures(load_fixture)
    calls = []
    monkeypatch.setattr(debate, "run_structured", _seam(bull, bear, verdict, calls))

    await debate.run(SIGNALS, CATALYST)  # default rounds == MAX_ROUNDS
    side_calls = [c for c in calls if c["schema"] is Argument]
    assert len(side_calls) == 2 * MAX_ROUNDS  # bull + bear per round, no unbounded loop

    calls.clear()
    await debate.run(SIGNALS, CATALYST, rounds=1)
    assert len([c for c in calls if c["schema"] is Argument]) == 2  # halving rounds halves the calls


async def test_verdict_names_losing_side(monkeypatch, load_fixture):
    bull, bear, verdict = _fixtures(load_fixture)
    monkeypatch.setattr(debate, "run_structured", _seam(bull, bear, verdict, []))

    out = await debate.run(SIGNALS, CATALYST)

    assert isinstance(out, DebateVerdict)
    assert out.bull_strongest_point.strip()   # both sides' strongest point survives
    assert out.bear_strongest_point.strip()   # the moderator names the LOSING side too


async def test_confidence_is_grounded(monkeypatch, load_fixture):
    bull, bear, verdict = _fixtures(load_fixture)
    calls = []
    monkeypatch.setattr(debate, "run_structured", _seam(bull, bear, verdict, calls))

    out = await debate.run(SIGNALS, CATALYST)

    mod_prompt = next(c["prompt"] for c in calls if c["schema"] is DebateVerdict)
    low = mod_prompt.lower()
    assert "base_rate" in low or "base rate" in low  # anchor confidence to a cited base rate
    assert "analog" in low
    assert "unknown" in low                            # ...and lower it when unknowns remain
    assert out.evidence_refs                           # grounded in cited refs, not vibes


# ---------------------------------------------------------------------------
# 06.7-02 Task 1 — extra_context re-trigger (RECON-02): default None is byte-for-byte;
# a non-None gap reaches BOTH sides AND the moderator (one shared-evidence injection).
# ---------------------------------------------------------------------------

async def test_run_extra_context_none_unchanged(monkeypatch, load_fixture):
    """Default path is byte-for-byte: run(...) and run(..., extra_context=None) produce the
    IDENTICAL prompt strings, and neither carries the MD RE-TRIGGER marker (no-regression)."""
    bull, bear, verdict = _fixtures(load_fixture)

    calls_default = []
    monkeypatch.setattr(debate, "run_structured", _seam(bull, bear, verdict, calls_default))
    await debate.run(SIGNALS, CATALYST, rounds=2)

    calls_explicit = []
    monkeypatch.setattr(debate, "run_structured", _seam(bull, bear, verdict, calls_explicit))
    await debate.run(SIGNALS, CATALYST, rounds=2, extra_context=None)

    prompts_default = [c["prompt"] for c in calls_default]
    prompts_explicit = [c["prompt"] for c in calls_explicit]
    assert prompts_default == prompts_explicit           # byte-for-byte identical
    assert all("MD RE-TRIGGER" not in p for p in prompts_default)  # no marker on the default path


async def test_run_extra_context_injects_gap(monkeypatch, load_fixture):
    """A non-None extra_context reaches the BULL prompt AND the BEAR prompt AND the MODERATOR
    prompt — one injection on the shared evidence string re-reasons the WHOLE debate."""
    bull, bear, verdict = _fixtures(load_fixture)
    fact = "DD surfaced an FDA AdCom scheduled 3 days pre-PDUFA the prior round ignored"
    calls = []
    monkeypatch.setattr(debate, "run_structured", _seam(bull, bear, verdict, calls))

    await debate.run(SIGNALS, CATALYST, rounds=2, extra_context=fact)

    bull_prompts = [c["prompt"] for c in calls if c["schema"] is Argument and "You are the BULL" in c["prompt"]]
    bear_prompts = [c["prompt"] for c in calls if c["schema"] is Argument and "You are the BEAR" in c["prompt"]]
    mod_prompt = next(c["prompt"] for c in calls if c["schema"] is DebateVerdict)

    assert all(fact in p for p in bull_prompts)   # the gap reaches every bull round
    assert all(fact in p for p in bear_prompts)   # ...and every bear round
    assert fact in mod_prompt                      # ...and the moderator synthesis
    assert all("MD RE-TRIGGER" in p for p in bull_prompts)  # the re-reason instruction, not the answer


async def test_no_positioning_in_verdict():
    positioning = {
        "size", "size_pct", "entry", "stop_loss", "take_profit",
        "position", "exit_by_date", "quantity", "shares", "allocation",
    }
    assert positioning.isdisjoint(set(DebateVerdict.model_fields))  # prediction only; sizing is Phase 5
