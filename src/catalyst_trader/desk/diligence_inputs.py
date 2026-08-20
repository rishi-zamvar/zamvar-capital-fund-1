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

What Slice 2.5 now SOURCES honestly (source-or-omit, never fabricated):
  - financials: edgar.fundamentals (Slice 2.5) exposes {cash_usd, monthly_burn_usd}; we add
      months_to_catalyst from (event_date - as_of). Grounded only when BOTH cash_usd + monthly_burn_usd
      exist (financials_context direct-subscripts all three); else OMIT the key + flag (honest NO-GO).
  - ownership: FINRA short_interest + fundamentals shares_outstanding + free EDGAR Form-4 insider_net.
      Assembled as the WHOLE {short_interest_pct, days_to_cover, insider_net} dict ONLY when all three
      ground (a partial dict KeyErrors at diligence.py:269); a single miss OMITS the key + flags.
      insider_net == 0.0 (a quiet tape) is a REAL datum and STILL grounds ownership.

# ponytail: one factory + one closure + honest field builders. No per-provider class, no registry —
#           a single fundamentals fetch is reused for BOTH financials cash/burn AND ownership shares.
"""

from __future__ import annotations

from datetime import date

from ..contracts import DiligenceInput
from .research_bundle import build_research_bundle

# The days->months conversion for months_to_catalyst (missing-key-raises — no magic literal in-line).
# months_to_catalyst is a function of as_of/event, not a sourced fact, so it stays in the DD mapping.
_INPUTS_PARAMS = {"days_per_month": 30.4375}

# The honest illiquid sentinel: a call_bid=0 quote trips options_liquid=False, so run_diligence uses
# the in-house historical-gap fallback (options_move stays GROUNDED) — never a fabricated implied vol.
_SENTINEL = {"call_bid": 0, "call_ask": 0, "put_bid": 0, "put_ask": 0, "call_oi": 0, "put_oi": 0}


def _num(x) -> float:
    """Coerce a nullable numeric to float (None -> 0.0). C1: keeps a present-but-None bid from
    reaching zero_liquidity's `None <= 0` (its `.get(default)` only fires on a MISSING key)."""
    return float(x) if x is not None else 0.0


def make_diligence_inputs(*, options_source=None, trial_source=None, financials_source=None,
                          finra_source=None, insider_source=None, bundle_fn=None):
    """Build the (DiligenceInput, market_data, degraded) binding closure.

    DD no longer re-sources anything: it DELEGATES to the Catalyst Research Bundle (built ONCE per
    catalyst — the single ground-truth pass) and MAPS the bundle's already-sourced FACTS into the
    existing market_data shape. The firewall is unchanged: DD reads the same FACTS the desk does and
    forms its verdict independently. The per-source kwargs are threaded INTO the bundle builder
    (backward-compatible with the old injection points); tests may instead inject `bundle_fn`.

    Injectable providers (production defaults are the free, cache-first snapshots; tests inject fakes):
      options_source(ticker)     -> the CBOE seam dict (nested options_quote|None) | None  [now-snapshot]
      trial_source(ticker)       -> a ClinicalTrials.gov record | None (non-money; None is fine, no NO-GO)
      financials_source(ticker)  -> edgar.fundamentals dict | None (reused for financials AND ownership shares)
      finra_source(ticker)       -> finra.fetch dict | None (defaulted INSIDE the bundle — needs as_of)
      insider_source(tk, since, until) -> edgar.insider_net float | None (0.0 = quiet tape, grounds)
      bundle_fn                  -> the bundle builder (default build_research_bundle)

    The closure:
      diligence_inputs(conn, ticker, catalyst, *, entry, risk_inputs, exit_by_date, pair=None, as_of)
        -> (DiligenceInput, market_data, degraded: list[str])
    """
    bundle_fn = bundle_fn or build_research_bundle

    def diligence_inputs(conn, ticker, catalyst, *, entry, risk_inputs, exit_by_date, pair=None, as_of):
        event_date = catalyst["event_date"]
        days_to_event = (date.fromisoformat(event_date) - date.fromisoformat(as_of)).days

        # ONE research pass. Request ONLY the DD-consumed facts, so the conn-touching sources
        # (analog/base_rate/price) never fire — conn=None safe (B1). cutoff=as_of = point-in-time.
        bundle = bundle_fn(conn, ticker, catalyst, as_of, cutoff=as_of,
                           facts={"options", "financials", "ownership", "trial"},
                           options_source=options_source, trial_source=trial_source,
                           financials_source=financials_source, finra_source=finra_source,
                           insider_source=insider_source)

        # --- options (CBOE, nested + nullable) + the honest illiquid sentinel (B2), mapped from the bundle ---
        cboe = bundle.options.value
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
            "trial": bundle.trial.value,
        }

        # --- financials: map the bundle fact + months_to_catalyst (a function of as_of, not sourced) ---
        fund = bundle.financials.value  # whole edgar.fundamentals dict (cash+burn present) | None
        if fund is not None:
            months_to_catalyst = round(days_to_event / _INPUTS_PARAMS["days_per_month"], 2)
            market_data["financials"] = {"cash_usd": fund["cash_usd"],
                                         "monthly_burn_usd": fund["monthly_burn_usd"],
                                         "months_to_catalyst": months_to_catalyst}

        # --- ownership: map the bundle fact verbatim (whole-dict-or-absent) ---
        if bundle.ownership.value is not None:
            market_data["ownership"] = bundle.ownership.value

        # B1: scope the DD degrade list to the DD money-dim flags (financials/ownership) only — the
        # bundle only computes those dims in this seam, so this is a no-op safety net.
        degraded = [f for f in bundle.degraded if f.startswith(("financials:", "ownership:"))]

        dd_input = DiligenceInput(ticker=ticker, catalyst=catalyst, pair=pair)
        return dd_input, market_data, degraded

    return diligence_inputs
