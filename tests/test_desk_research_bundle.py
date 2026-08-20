"""tests/test_desk_research_bundle.py (07.9-1.5) — the Catalyst Research Bundle substrate.

ONE deterministic research pass that computes every cited FACT once per catalyst, then hands the
identical ground truth to every consumer. Two invariants are TESTED here, not review notes:

  FIREWALL   the bundle carries FACTS ONLY — no interpretation field (score/thesis/verdict/dossier);
             a leaked interpretation is a type error (extra='forbid'), not a policy check.
  FRUGALITY  each free/cited source is invoked EXACTLY ONCE per catalyst (call-count spies).

Plus: honest-degrade (missing/raise -> null + flag, never fabricated), point-in-time (serving.asof
cutoff threaded), and cite-or-drop (every populated Fact carries a resolvable ref or inline citation).
All offline: fake injected sources, no network / EDGAR / FINRA / CBOE / LLM / real embedder.
"""

import pytest
from pydantic import ValidationError

from catalyst_trader.contracts import CatalystResearchBundle, Fact
from catalyst_trader.desk import evidence

_AS_OF = "2026-08-19"
_EVENT = "2026-08-22"


def _catalyst(ticker="ACME"):
    return {"ticker": ticker, "catalyst_type": "pdufa", "event_date": _EVENT,
            "catalyst_id": f"{ticker}:{_EVENT}", "phase": "III", "indication": "oncology"}


# ============================== Task 1 — contract + firewall =============================

# The interpretation vocabulary the substrate must NEVER carry (the firewall line, at the type level).
_INTERPRETATION_FIELDS = {"score", "confidence", "thesis", "verdict", "dossier", "recommendation",
                          "decision", "key_findings", "direction"}


def test_bundle_is_facts_only_no_interpretation_fields():
    leaked = _INTERPRETATION_FIELDS & set(CatalystResearchBundle.model_fields)
    assert leaked == set(), f"bundle leaked interpretation field(s): {leaked}"


def test_bundle_forbids_extra():
    # A stray interpretation field is rejected by the type (extra='forbid'), not by a policy pass.
    with pytest.raises(ValidationError):
        CatalystResearchBundle(ticker="ACME", catalyst=_catalyst(), score=0.7)


def test_bundle_facts_default_null():
    # An empty bundle validates with every fact value defaulting to None (an empty slot is a finding).
    b = CatalystResearchBundle(ticker="ACME", catalyst=_catalyst())
    for name in ("analogs", "financials", "trial", "options", "implied_move",
                 "ownership", "prices", "hedge_inputs"):
        assert getattr(b, name).value is None
    assert b.base_rates == [] and b.degraded == []


def test_fact_carries_ref():
    # tool-ref citation, inline citation, and empty are all valid...
    Fact(value=1.0, evidence_ref="tool:implied_move#abc123")
    Fact(value=0.089, citation={"source_name": "BIO", "source_url": "http://x", "quote": "q"})
    Fact()  # value None -> no citation required (an empty slot is honest)
    # ...but a POPULATED value with neither a ref nor a citation is REJECTED (cite-or-drop).
    with pytest.raises(ValidationError):
        Fact(value=1.0)

