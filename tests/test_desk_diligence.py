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

from catalyst_trader.contracts import AnalystSignal

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
