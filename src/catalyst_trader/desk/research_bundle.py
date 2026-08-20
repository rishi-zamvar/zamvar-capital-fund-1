"""desk/research_bundle.py (07.9-1.5) — the Catalyst Research Bundle builder.

ONE deterministic research pass that computes every free/cited FACT once per catalyst, then hands the
identical ground truth to every consumer (DD via make_diligence_inputs here; the 4 analysts via
tool-backing in Plan 2). It ORCHESTRATES the shipped free/cached readers — it re-implements NONE of
them:

  analogs / hedge_inputs  kb.analog_query (ONE call feeds both; hedge_inputs = analog_gaps split via
                          builder._split_moves over engine._NO_ANALOG_GAPS — C4, no re-derived math)
  base_rates              quant.base_rate per distinct metric (RAISES on miss -> try/except -> degrade)
  financials / ownership  edgar.fundamentals (ONE fetch reused for cash/burn AND ownership shares) +
                          finra.fetch + edgar.insider_net (0.0 = quiet tape, GROUNDS)
  trial                   the CT.gov reader (non-money; None is fine — no NO-GO). C3: the honest
                          per-catalyst default is `lambda t: None` — clinicaltrials.fetch_trial_readouts
                          is a PLURAL-ticker date-range DISCOVERY fn, NOT a per-catalyst reader.
  options / implied_move  options_cboe.fetch (nested quote) + quant.implied_move (C2: wrapped in
                          try/except — it RAISES on underlying_price<=0 / incomplete legs -> degrade)
  prices                  serving.asof(conn, cutoff).bars — point-in-time close series (cache-first).
                          C1: point-in-time is strictly true for PRICES; options_cboe/edgar/finra are
                          now-snapshots (same as today's DD), not asof reads.

Every populated Fact is cite-or-drop: provider/quant facts carry an evidence.tool_ref_for ref
(resolvable-by-construction); base_rate facts carry the inline citation dict. A missing / raising /
None source -> value=None + a `degraded` flag — NEVER a fabricated figure.

`facts` scopes WHICH facts to compute (default = all). A consumer that needs only a subset (the DD
seam: {options, financials, ownership, trial}) passes that set, so the sources for the un-requested
facts (analog/base_rate/price — the conn-touching ones) NEVER fire. This is what keeps
make_diligence_inputs conn=None-safe and byte-compatible (B1).

# ponytail: one function + injected sources + honest field builders. No provider class, no registry,
#           no cache class — serving.asof IS the cache; the ONE fundamentals fetch is reused.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from .. import kb, serving  # noqa: F401  (serving used by the default price source, via catalyst_context)
from ..backtest.engine import _NO_ANALOG_GAPS
from ..contracts import CatalystResearchBundle, Fact
from ..providers import edgar, finra, options_cboe, registry
from ..quant import base_rate as _base_rate_lookup, implied_move as _implied_move
from . import evidence
from .builder import _split_moves
from .catalyst_context import _default_analog_source, _default_price_source

# The Form-4 trailing window for insider_net (missing-key-raises — no magic literal in-line).
_BUNDLE_PARAMS = {"form4_lookback_days": 90}

# The cited clinical priors to pull for any biotech catalyst (metric NAMES, not magic numbers). Each
# resolves against data/base_rates.csv or honestly degrades; pos is narrowed by the catalyst's phase.
_BASE_RATE_METRICS = ("pos", "crl_penalty", "adcom_followthrough")


def _base_rate_requests(catalyst: dict) -> list[dict]:
    """The per-catalyst base-rate call specs (distinct metrics; pos narrowed by phase/indication)."""
    reqs = []
    for metric in _BASE_RATE_METRICS:
        if metric == "pos":
            reqs.append({"metric": "pos", "phase": catalyst.get("phase"),
                         "indication": catalyst.get("indication")})
        else:
            reqs.append({"metric": metric})
    return reqs


def build_research_bundle(conn, ticker, catalyst, as_of, *, cutoff=None, embed=None,
                          analog_source=None, base_rate_source=None, financials_source=None,
                          trial_source=None, options_source=None, finra_source=None,
                          insider_source=None, price_source=None, facts=None,
                          params=None) -> CatalystResearchBundle:
    """Compute the cited-fact substrate for one catalyst.

    Injectable sources (production defaults = the free, cache-first readers; each called ONCE):
      analog_source(conn, ticker, catalyst, as_of) -> list of analog dicts (kb.analog_query)
      base_rate_source(metric, phase, indication)  -> {value, source_name, source_url, quote} | RAISES
      financials_source(ticker)                    -> edgar.fundamentals dict | None (reused for shares)
      trial_source(ticker)                         -> a CT.gov record | None (non-money)
      options_source(ticker)                       -> the CBOE seam dict | None (now-snapshot)
      finra_source(ticker)                         -> finra.fetch dict | None (defaulted with as_of)
      insider_source(ticker, since, until)         -> edgar.insider_net float | None (0.0 grounds)
      price_source(conn, ticker, as_of)            -> list[float] close series (point-in-time)

    `facts`: a set naming which facts to compute (None = all). `cutoff`: the transaction-time gate for
    the point-in-time price read (as_of for backtest/knowable, None = now/live).
    """
    want = (lambda n: True) if facts is None else (lambda n: n in facts)
    ctype = catalyst.get("catalyst_type")
    degraded: list[str] = []
    fields: dict = {}

    # --- analogs + hedge_inputs: ONE analog_query feeds both (frugality) ---
    if want("analogs") or want("hedge_inputs"):
        src = analog_source or _default_analog_source(embed or kb.default_embedder())
        analogs = src(conn, ticker, catalyst, as_of)
        ref = evidence.tool_ref_for(
            "analog_query", {"context": f"{ticker} {ctype}", "filters": {"type": ctype}, "k": 5,
                             "as_of": as_of})
        if want("analogs"):
            fields["analogs"] = Fact(value=analogs, evidence_ref=ref, context=f"{ticker} {ctype}")
        if want("hedge_inputs"):
            up_moves, down_moves = _split_moves(analogs)   # C4: reuse, do not re-derive gap math
            gaps = dict(_NO_ANALOG_GAPS)                    # honest single-leg default (peer 0.0)
            gaps["target_up"] = median(up_moves) if up_moves else 0.0
            gaps["target_down"] = -median(down_moves) if down_moves else 0.0
            fields["hedge_inputs"] = Fact(value=gaps, evidence_ref=ref)

    # --- base_rates: one cited Fact per distinct metric (RAISES on miss -> degrade, never a guess) ---
    if want("base_rates"):
        brl = base_rate_source or _base_rate_lookup
        brs: list[Fact] = []
        for spec in _base_rate_requests(catalyst):
            try:
                r = brl(spec["metric"], spec.get("phase"), spec.get("indication"))
            except ValueError as e:
                degraded.append(f"base_rate:{spec['metric']}: {e}")
                continue
            brs.append(Fact(value=r["value"], context=spec["metric"],
                            citation={k: r[k] for k in ("source_name", "source_url", "quote")}))
        fields["base_rates"] = brs

    # --- financials + ownership: ONE fundamentals fetch reused for cash/burn AND ownership shares ---
    fund = None
    if want("financials") or want("ownership"):
        fund = (financials_source or edgar.fundamentals)(ticker)

    if want("financials"):
        if fund and fund.get("cash_usd") is not None and fund.get("monthly_burn_usd") is not None:
            fields["financials"] = Fact(
                value=fund, evidence_ref=evidence.tool_ref_for("fundamentals", {"ticker": ticker}))
        else:
            degraded.append("financials: cash_usd/monthly_burn_usd absent from SEC XBRL — "
                            "dim ungrounded, forces NO-GO")

    if want("ownership"):
        shares = fund.get("shares_outstanding") if fund else None
        si = (finra_source or (lambda t: finra.fetch(t, registry.recent_si_settlement(as_of))))(ticker)
        since = (date.fromisoformat(as_of)
                 - timedelta(days=_BUNDLE_PARAMS["form4_lookback_days"])).isoformat()
        get_net = insider_source or (
            lambda t, s, u: edgar.insider_net(t, since=s, until=u))
        net = get_net(ticker, since, as_of)  # 0.0 quiet-tape | float | None
        if si and shares and net is not None:  # net==0.0 GROUNDS (0 is a real datum -> `is not None`)
            fields["ownership"] = Fact(
                value={"short_interest_pct": si["short_interest"] / shares,
                       "days_to_cover": si["days_to_cover"], "insider_net": net},
                evidence_ref=evidence.tool_ref_for("short_interest", {"ticker": ticker, "as_of": as_of}))
        else:
            degraded.append("ownership: short_interest/shares/insider_net incomplete — "
                            "dim ungrounded, forces NO-GO")

    # --- trial (non-money; None is fine, no NO-GO) ---
    if want("trial"):
        rec = (trial_source or (lambda t: None))(ticker)
        if rec is not None:
            fields["trial"] = Fact(value=rec,
                                   evidence_ref=evidence.tool_ref_for("trial_readouts", {"ticker": ticker}))

    # --- options (CBOE now-snapshot) + implied_move (a deterministic quant DERIVATION over the quote) ---
    cboe = None
    if want("options") or want("implied_move"):
        cboe = (options_source or options_cboe.fetch)(ticker)

    if want("options") and cboe is not None:
        fields["options"] = Fact(
            value=cboe, evidence_ref=evidence.tool_ref_for("options_cboe", {"ticker": ticker}))

    if want("implied_move"):
        oq = cboe.get("options_quote") if cboe else None
        up = cboe.get("underlying_price") if cboe else None
        if oq is not None and up is not None:
            try:
                res = _implied_move(float(up),
                                    call_mid=(oq["call_bid"] + oq["call_ask"]) / 2,
                                    put_mid=(oq["put_bid"] + oq["put_ask"]) / 2)
                fields["implied_move"] = Fact(value=res.value, evidence_ref=evidence.tool_ref(res))
            except (ValueError, KeyError) as e:  # C2: implied_move RAISES on bad input -> degrade
                degraded.append(f"implied_move: {e}")

    # --- prices: point-in-time close series (serving.asof cutoff) ---
    if want("prices"):
        psrc = price_source or _default_price_source(None, cutoff)
        closes = psrc(conn, ticker, as_of)
        if closes:
            fields["prices"] = Fact(
                value={"target": [float(c) for c in closes], "peer": []},
                evidence_ref=evidence.tool_ref_for(
                    "price_bars", {"ticker": ticker, "as_of": as_of, "cutoff": cutoff}))
        else:
            degraded.append("prices: no point-in-time close series — dim ungrounded")

    return CatalystResearchBundle(ticker=ticker, catalyst=catalyst, as_of=as_of,
                                  degraded=degraded, **fields)
