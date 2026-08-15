"""OPS-03 pre-trade guardrails: one FAIL-CLOSED runtime gate over the shipped invariants.

This module does NOT re-implement any invariant — it AGGREGATES the already-shipped
pre-trade invariants into a single gate the pipeline (and later paper/live execution)
calls before acting. A False on ANY check makes the whole gate fail (AND-over-checks);
a missing/None input for any invariant is a violation, never a skipped check.

The five aggregated invariants (all reuse):
  1. catalyst_fresh          — calendar.verify.is_tradeable (the single tradeable gate)
  2. cite_or_drop_present    — verifier.enforce / enforce_estimate / diligence.enforce_dossier
  3. dd_firewall_sealed      — contracts.DiligenceInput (extra="forbid", field-disjoint)
  4. concentration_within_cap — quant.portfolio.concentration vs the heat_cap
  5. no_scrape_to_order      — desk ALLOWED_TOOLS is web-free (mcp__quant__* only)

SCOPE SPLIT (research open-Q3, LOCKED): Phase 7 delivers the PRE-TRADE / pipeline
guardrails ONLY. The live-position monitors also listed under OPS-03 — stop-loss /
take-profit tracking, catalyst countdown, paper P&L — need a ledger and ride with
Phase 8 (paper ledger) / Phase 8.5 (intra-week monitor). This gate is pre-trade/pipeline.

# ponytail: live-position monitors are intentionally out of scope until a ledger exists
#           (Phase 8/8.5). Do not bolt SL/TP polling onto this pre-trade gate — it has
#           no positions to watch; it decides whether a book may be placed at all.
"""

from pydantic import BaseModel, ConfigDict

from ..calendar.verify import is_tradeable
from ..contracts import DebateVerdict, DiligenceInput, TradeProposal
from ..quant.portfolio import concentration
from . import diligence as _diligence
from . import orchestrator as _orchestrator

# Patterns that betray a path from scraped/raw web content to an order. The desk's
# ALLOWED_TOOLS must be DISJOINT from these — asserted, not assumed.
_WEB_TOOL_DENYLIST = ("web", "fetch", "http", "browser", "scrape")


class GuardrailReport(BaseModel):
    """The frozen verdict of the pre-trade gate. `passed` is the AND over `checks`; it
    cannot be mutated after the fact (frozen), so a caller can't flip a block to a pass."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    passed: bool
    checks: dict[str, bool]
    violations: list[str] = []


class GuardrailViolation(Exception):
    """Raised by assert_guardrails when the pre-trade gate does not pass — the hard-stop
    for call sites that must never proceed on a blocked book."""


def _catalyst_fresh(candidates) -> bool:
    """Every candidate's catalyst is is_tradeable (verified/fresh) — reuses the SINGLE
    tradeable gate, never a scattered re-check. None candidates => fail-closed."""
    if candidates is None:
        return False
    try:
        for c in candidates:
            catalyst = getattr(c, "catalyst", c)
            if catalyst is None or not is_tradeable(catalyst):
                return False
    except Exception:
        return False
    return True


def _cite_or_drop_present() -> bool:
    """The fact-check / provenance cite-or-drop enforcers are wired and reachable — the
    gate references them (does not run the LLM). Import failure => fail-closed."""
    try:
        from .diligence import enforce_dossier
        from .verifier import enforce, enforce_estimate
    except Exception:
        return False
    return callable(enforce) and callable(enforce_estimate) and callable(enforce_dossier)


def _dd_firewall_sealed() -> bool:
    """The Workflow-3 firewall is sealed at the TOP LEVEL: DiligenceInput has
    extra="forbid" AND its top-level field set is disjoint from the Workflow-1/2 artifact
    fields (DebateVerdict / TradeProposal) — no top-level reasoning can be passed in.

    SCOPE (checker Warning 3): DiligenceInput.catalyst is a raw `dict`
    (contracts/__init__.py L195), so extra="forbid" seals the TOP LEVEL only — it does
    NOT deep-seal keys smuggled INSIDE that nested catalyst dict. This check proves the
    top-level firewall only. The Layer-B outcome-blind catalyst projection (07-05 Task 1)
    is the safeguard that whitelists the nested catalyst keys handed to the desk; that is
    where nested-key sealing lives, cross-referenced here (do not imply full sealing).
    """
    if DiligenceInput.model_config.get("extra") != "forbid":
        return False
    top_level = set(DiligenceInput.model_fields)
    wf12 = set(DebateVerdict.model_fields) | set(TradeProposal.model_fields)
    return top_level.isdisjoint(wf12)


def _concentration_within_cap(weights, heat_cap) -> bool:
    """Herfindahl concentration AND the aggregate net-long book weight are <= heat_cap —
    reuses quant.concentration + the select_book heat_cap semantics. Any error
    (None weights, None cap, empty book) => fail-closed."""
    try:
        net_long = sum(w for w in weights if w > 0)
        return concentration(weights).value <= heat_cap and net_long <= heat_cap
    except Exception:
        return False


def _no_scrape_to_order() -> bool:
    """No path from scraped/raw content to an order: the desk's ALLOWED_TOOLS (both the
    orchestrator's and diligence's) are DISJOINT from the web-tool denylist — asserted at
    call time so a smuggled web/fetch tool is caught. Read live so tests can monkeypatch."""
    all_tools = list(_orchestrator.ALLOWED_TOOLS) + list(_diligence.ALLOWED_TOOLS)
    return not any(
        pat in tool.lower() for tool in all_tools for pat in _WEB_TOOL_DENYLIST
    )


def check_guardrails(*, candidates, weights, heat_cap) -> GuardrailReport:
    """Run the five OPS-03 pre-trade invariants and return a frozen GuardrailReport.
    FAIL-CLOSED: a False on ANY check makes passed=False; missing/None inputs are
    violations, never skipped checks."""
    checks = {
        "catalyst_fresh": _catalyst_fresh(candidates),
        "cite_or_drop_present": _cite_or_drop_present(),
        "dd_firewall_sealed": _dd_firewall_sealed(),
        "concentration_within_cap": _concentration_within_cap(weights, heat_cap),
        "no_scrape_to_order": _no_scrape_to_order(),
    }
    violations = [name for name, ok in checks.items() if not ok]
    return GuardrailReport(passed=not violations, checks=checks, violations=violations)


def assert_guardrails(*, candidates, weights, heat_cap) -> GuardrailReport:
    """check_guardrails, but RAISE GuardrailViolation when the gate does not pass — the
    hard-stop for call sites that must never proceed on a blocked book. Returns the report
    on pass so the caller can inspect the per-check detail."""
    report = check_guardrails(candidates=candidates, weights=weights, heat_cap=heat_cap)
    if not report.passed:
        raise GuardrailViolation(
            "pre-trade guardrails blocked the book: " + ", ".join(report.violations)
        )
    return report
