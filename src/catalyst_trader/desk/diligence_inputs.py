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

from datetime import date, timedelta

from ..contracts import DiligenceInput
from ..providers import edgar, finra, options_cboe, registry

# Money-dim sourcing params (missing-key-raises — no magic literals): the Form-4 trailing window and
# the days->months conversion for months_to_catalyst.
_INPUTS_PARAMS = {"form4_lookback_days": 90, "days_per_month": 30.4375}

# The honest illiquid sentinel: a call_bid=0 quote trips options_liquid=False, so run_diligence uses
# the in-house historical-gap fallback (options_move stays GROUNDED) — never a fabricated implied vol.
_SENTINEL = {"call_bid": 0, "call_ask": 0, "put_bid": 0, "put_ask": 0, "call_oi": 0, "put_oi": 0}


def _num(x) -> float:
    """Coerce a nullable numeric to float (None -> 0.0). C1: keeps a present-but-None bid from
    reaching zero_liquidity's `None <= 0` (its `.get(default)` only fires on a MISSING key)."""
    return float(x) if x is not None else 0.0


def make_diligence_inputs(*, options_source=None, trial_source=None, financials_source=None,
                          finra_source=None, insider_source=None):
    """Build the (DiligenceInput, market_data, degraded) binding closure.

    Injectable providers (production defaults are the free, cache-first snapshots; tests inject fakes):
      options_source(ticker)     -> the CBOE seam dict (nested options_quote|None) | None  [now-snapshot]
      trial_source(ticker)       -> a ClinicalTrials.gov record | None (non-money; None is fine, no NO-GO)
      financials_source(ticker)  -> edgar.fundamentals dict | None (reused for financials AND ownership shares)
      finra_source(ticker)       -> finra.fetch dict | None (defaulted INSIDE the closure — needs as_of)
      insider_source(tk, since, until) -> edgar.insider_net float | None (0.0 = quiet tape, grounds)

    The closure:
      diligence_inputs(conn, ticker, catalyst, *, entry, risk_inputs, exit_by_date, pair=None, as_of)
        -> (DiligenceInput, market_data, degraded: list[str])
    """
    options_source = options_source or options_cboe.fetch
    trial_source = trial_source or (lambda ticker: None)
    financials_source = financials_source or edgar.fundamentals
    insider_source = insider_source or (
        lambda tk, since, until: edgar.insider_net(tk, since=since, until=until))
    # finra_source is NOT defaulted here: its production default binds as_of (recent_si_settlement),
    # which is only in scope inside the closure (C1 — defaulting it here NameErrors on as_of).

    def diligence_inputs(conn, ticker, catalyst, *, entry, risk_inputs, exit_by_date, pair=None, as_of):
        event_date = catalyst["event_date"]
        days_to_event = (date.fromisoformat(event_date) - date.fromisoformat(as_of)).days
        # C1: resolve the FINRA default HERE, where as_of is bound (recent_si_settlement(as_of)).
        finra_fetch = finra_source or (lambda tk: finra.fetch(tk, registry.recent_si_settlement(as_of)))

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
        }
        degraded: list[str] = []  # built up ONLY from genuine misses (empty when every dim grounds)

        # --- ONE fundamentals fetch, reused for BOTH financials (cash/burn) AND ownership (shares) ---
        fund = financials_source(ticker)  # {shares_outstanding, cash_usd, monthly_burn_usd, ...} | None

        # --- financials (SEC XBRL): grounded only when BOTH cash_usd + monthly_burn_usd exist ---
        if fund and fund.get("cash_usd") is not None and fund.get("monthly_burn_usd") is not None:
            months_to_catalyst = round(days_to_event / _INPUTS_PARAMS["days_per_month"], 2)
            market_data["financials"] = {"cash_usd": fund["cash_usd"],
                                         "monthly_burn_usd": fund["monthly_burn_usd"],
                                         "months_to_catalyst": months_to_catalyst}
        else:
            degraded.append("financials: cash_usd/monthly_burn_usd absent from SEC XBRL — "
                            "dim ungrounded, forces NO-GO")

        # --- ownership (FINRA + shares + Form-4): whole-dict-or-omit (NEVER a partial dict) ---
        shares = fund.get("shares_outstanding") if fund else None
        si = finra_fetch(ticker)
        since = (date.fromisoformat(as_of) - timedelta(days=_INPUTS_PARAMS["form4_lookback_days"])).isoformat()
        net = insider_source(ticker, since, as_of)  # 0.0 quiet-tape | float | None
        if si and shares and net is not None:  # net==0.0 GROUNDS (0 is a real datum -> `is not None`)
            # ponytail: short_interest_pct is short_interest / shares_outstanding — a shares-out ratio,
            #           which slightly UNDERSTATES true short-%-of-float (free float isn't free).
            #           Upgrade to a float denominator if a free float source ever lands.
            market_data["ownership"] = {"short_interest_pct": si["short_interest"] / shares,
                                        "days_to_cover": si["days_to_cover"], "insider_net": net}
        else:
            degraded.append("ownership: short_interest/shares/insider_net incomplete — "
                            "dim ungrounded, forces NO-GO")

        dd_input = DiligenceInput(ticker=ticker, catalyst=catalyst, pair=pair)
        return dd_input, market_data, degraded

    return diligence_inputs
