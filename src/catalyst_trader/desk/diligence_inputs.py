"""desk/diligence_inputs.py (7.8-S2) — the (DiligenceInput, market_data) live binding.

The second missing wire onto the Slice-1 dossier: an injectable-provider factory (mirrors
`catalyst_context.make_catalyst_context`) that turns free/cached point-in-time data into EXACTLY the
`run_diligence(market_data=...)` contract, so one promoted trade can be diligence-checked. Every money
dim is honestly SOURCED or honestly DEGRADED — never fabricated.

What Slice 2 SOURCES honestly (plan-checker–corrected contracts, verified against code):
  - options  (CBOE): `options_cboe.fetch(ticker)` -> {"options_quote": {...}|None, "underlying_quote":
      {...}, "underlying_price": ...}. The quote is NESTED under "options_quote" and is None when no
      live ATM pair qualifies (B2). We inject catalyst_date=event_date + wrap it as
      market_data["options"]={"quote", "underlying_price"=entry, "days_to_event"}. None -> a HONEST
      sentinel (call_bid=0 -> options_liquid False -> run_diligence's grounded historical-gap fallback,
      never a fabricated IV). Every options structure (liquid OR sentinel) carries days_to_event
      (diligence.py subscripts it unconditionally).
  - liquidity (CBOE underlying): {"bid","volume","oi"} from cboe["underlying_quote"]; bid can be None,
      so coerce None->0 (C1 — zero_liquidity's `.get(default)` only fires on a MISSING key, so a present
      None would raise `None <= 0`). cboe None -> all-zero (conservative -> honest NO-GO).
  - hedge     (Slice-1 catalyst_context): market_data["hedge"] REUSES {entry, exit_by_date,
      analog_gaps, prices} straight from the caller's risk_inputs (no recompute). Exactly those four
      keys — hedge_context(**md["hedge"]) TypeErrors on any extra.

What Slice 2 DEGRADES (omit + flag -> ungrounded money dim -> forced NO-GO in synthesize_verdict):
  - financials: edgar.fundamentals exposes {shares_outstanding, cash_runway_months} — NOT the
      {cash_usd, monthly_burn_usd, months_to_catalyst} keys financials_context direct-subscripts (B1).
      OMIT the key (financials_context(None) -> None -> ungrounded). Sourcing it is Slice 2.5.
  - ownership: no free insider_net source (EDGAR Form-4 deferred). OMIT the WHOLE key (a partial dict
      KeyErrors at diligence.py:269), append a degrade flag (C4). Sourcing it is Slice 2.5.

# ponytail: one factory + one closure + honest field builders. No per-provider class, no registry —
#           reuse the existing free provider; financials/ownership stay omitted-and-flagged this slice.
"""

from __future__ import annotations

from datetime import date

from ..contracts import DiligenceInput
from ..providers import options_cboe

# The two honest data-gaps this slice carries forward to Slice 2.5 (extend edgar.fundamentals +
# Form-4 net-insider). Each is an ungrounded money dim -> synthesize_verdict forces NO-GO.
_FINANCIALS_DEGRADE = (
    "financials: cash_usd/monthly_burn_usd/months_to_catalyst not exposed by edgar.fundamentals "
    "(only shares_outstanding + cash_runway_months) — dim ungrounded, forces NO-GO (Slice 2.5)"
)
_OWNERSHIP_DEGRADE = (
    "ownership: insider_net unavailable (EDGAR Form-4 deferred) — dim ungrounded, forces NO-GO (Slice 2.5)"
)

# The honest illiquid sentinel: a call_bid=0 quote trips options_liquid=False, so run_diligence uses
# the in-house historical-gap fallback (options_move stays GROUNDED) — never a fabricated implied vol.
_SENTINEL = {"call_bid": 0, "call_ask": 0, "put_bid": 0, "put_ask": 0, "call_oi": 0, "put_oi": 0}


def _num(x) -> float:
    """Coerce a nullable numeric to float (None -> 0.0). C1: keeps a present-but-None bid from
    reaching zero_liquidity's `None <= 0` (its `.get(default)` only fires on a MISSING key)."""
    return float(x) if x is not None else 0.0


def make_diligence_inputs(*, options_source=None, trial_source=None):
    """Build the (DiligenceInput, market_data, degraded) binding closure.

    Injectable providers (production defaults are the free, cache-first snapshots; tests inject fakes):
      options_source(ticker) -> the CBOE seam dict (nested options_quote|None) | None  [now-snapshot]
      trial_source(ticker)   -> a ClinicalTrials.gov record | None (non-money; None is fine, no NO-GO)

    The closure:
      diligence_inputs(conn, ticker, catalyst, *, entry, risk_inputs, exit_by_date, pair=None, as_of)
        -> (DiligenceInput, market_data, degraded: list[str])
    """
    options_source = options_source or options_cboe.fetch
    trial_source = trial_source or (lambda ticker: None)

    def diligence_inputs(conn, ticker, catalyst, *, entry, risk_inputs, exit_by_date, pair=None, as_of):
        event_date = catalyst["event_date"]
        days_to_event = (date.fromisoformat(event_date) - date.fromisoformat(as_of)).days

        # --- options (CBOE, nested + nullable) + the honest illiquid sentinel (B2) ---
        cboe = options_source(ticker)
        oq = cboe.get("options_quote") if cboe else None
        if oq is not None:
            quote = {**oq, "catalyst_date": event_date}   # inject the event date the provider can't know
        else:
            quote = {**_SENTINEL, "expiry": event_date, "catalyst_date": event_date}
        options = {"quote": quote, "underlying_price": entry, "days_to_event": days_to_event}

        # --- liquidity (CBOE underlying); None-bid coerced to 0 (C1); cboe None -> all-zero ---
        uq = (cboe or {}).get("underlying_quote") or {}
        liquidity_quote = {"bid": _num(uq.get("bid")), "volume": _num(uq.get("volume")),
                           "oi": _num(uq.get("oi"))}

        # --- hedge: REUSE the Slice-1 catalyst_context risk_inputs verbatim (no recompute) ---
        hedge = {"entry": entry, "exit_by_date": exit_by_date,
                 "analog_gaps": risk_inputs["analog_gaps"], "prices": risk_inputs["prices"]}

        market_data = {
            "options": options,
            "liquidity_quote": liquidity_quote,
            "hedge": hedge,
            "trial": trial_source(ticker),
            # financials + ownership OMITTED this slice (B1/C4) -> ungrounded money dims -> forced NO-GO.
        }
        degraded = [_FINANCIALS_DEGRADE, _OWNERSHIP_DEGRADE]

        dd_input = DiligenceInput(ticker=ticker, catalyst=catalyst, pair=pair)
        return dd_input, market_data, degraded

    return diligence_inputs
