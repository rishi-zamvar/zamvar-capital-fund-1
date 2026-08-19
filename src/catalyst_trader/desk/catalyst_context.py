"""desk/catalyst_context.py (7.8-S1) — the live catalyst_context hook.

The one missing wire desk/weekly.py:115 skips on: a per-catalyst ``{entry, risk_inputs}`` feed that
satisfies the run_portfolio work-item contract (orchestrator.py:96-98). ``make_catalyst_context`` is
an INJECTABLE-PROVIDER factory (mirrors builder's options_adapter / verify_moves' bars_provider): it
returns the async closure ``catalyst_context(conn, ticker, catalyst, as_of) -> {"entry", "risk_inputs"}``
matching weekly.py:84 EXACTLY.

Every number is an existing point-in-time tool output or the shipped honest degrade — NEVER fabricated:
  - entry:   the cache-first last close (serving.asof bars, == weekly._last_close), optional live RH
             quote override; None/<=0 -> entry=None (the caller skips the leg, no exception).
  - p_loss:  1 - P(positive) from the base-rate direction proxy (the INDEPENDENT risk prior, NOT the
             analyst's verdict). No measured cell (None / ValueError / KeyError) -> entry=None honest
             skip — never a coin-flip p_loss = 1 - None.
  - gap:     BINARY catalysts (pdufa/adcom/trial_readout) size against the TAIL down-move via
             quant.sizing.binary_survival_gap (max(high-pctile analog down-move, binary_gap_default))
             — a CRL/trial miss is a tail event, so the ~8.5% median would drastically under-size
             (BGAP-01). NON-binary (earnings/conference) keep the SAME stat_gap the statistical
             sleeve + backtest use: median of the analogs' DOWN moves, else abs(hard_veto_drop).
             All knobs are params (missing key RAISES — no new magic number).
  - analog_gaps: a COPY of engine._NO_ANALOG_GAPS with target_up/target_down overwritten from the
             analogs (split like builder._split_moves). peer_up/peer_down/w_peer stay the 0.0 honest
             default: the KB stores no peer conditional co-moves (hedge_peers carries only
             peer/direction/weight), so an honest paired-comove source is out of scope for the
             skeleton -> single-leg by honest degrade (mirrors backtest.engine._honest_hedge; the
             resulting dict makes risk.validate_hedge return None — never a fabricated hedge).
  - prices:  {"target": [close series], "peer": []}. peer is only read by validate_hedge WHEN an
             inverse peer exists, so [] is sound under the single-leg degrade.

# ponytail: no new money math — the hook only ROUTES point-in-time reads into the work-item shape.
"""

from __future__ import annotations

from statistics import median

from .. import kb, serving
from ..backtest.engine import _NO_ANALOG_GAPS, resolve_direction_proxy
from ..quant.sizing import binary_survival_gap
from ..quant.weekly import as_of_view
from .builder import _split_moves


def _default_price_source(lookback_weeks, cutoff):
    """Cache-first close series through the serving gateway (the SAME read weekly._last_close uses).
    lookback_weeks None -> params['weekly']['beta_window_weeks'] (the existing pair/beta horizon —
    the window cointegration would consume; reused, not a new constant)."""
    def _src(conn, ticker, as_of):
        lb = lookback_weeks
        if lb is None:
            lb = kb.load_params(conn, "weekly")["weekly"]["beta_window_weeks"]
        bars = serving.asof(conn, cutoff).bars(ticker, as_of, lookback_weeks=lb)
        return [float(b["close"]) for b in bars] if bars else []
    return _src


def _default_proxy(cutoff):
    """The base-rate P(positive) moat over the point-in-time sleeve view (engine.py:303 proxy)."""
    base = resolve_direction_proxy("base_rate")

    def _pf(ticker, as_of, conn, params):
        view = as_of_view(conn, cutoff)
        return base(ticker, as_of, view, conn, params=params)
    return _pf


def _default_analog_source(embed):
    """Nearest past catalysts of the same type with their realized moves (kb.analog_query). C3: embed
    is captured at factory construction time (the call-site signature carries no embed)."""
    def _src(conn, ticker, catalyst, as_of):
        ctype = catalyst["catalyst_type"]
        context = f"{ticker} {ctype}"
        return kb.analog_query(conn, embed, context, {"type": ctype}, as_of=as_of)
    return _src


def make_catalyst_context(*, price_source=None, analog_source=None, proxy_fn=None,
                          embed=None, params=None, lookback_weeks=None, quote_override=None,
                          cutoff=None):
    """Build the live ``catalyst_context`` hook (weekly.py:84 contract).

    Injectable providers (production defaults bind lazily on the passed ``conn``):
      price_source(conn, ticker, as_of) -> list[float] close series (cache-first).
      analog_source(conn, ticker, catalyst, as_of) -> list of analog dicts ({"outcome": {"move": ..}}).
      proxy_fn(ticker, as_of, conn, params) -> (side, p_positive, ev) — the base-rate direction proxy.
      quote_override(ticker) -> float|None — the --live RH real-time entry override (degrades to None).
      cutoff: transaction-time gate for the serving reads — as_of (backtest/knowable) or None=now (live).
    """
    price_source = price_source or _default_price_source(lookback_weeks, cutoff)
    proxy_fn = proxy_fn or _default_proxy(cutoff)
    analog_source = analog_source or _default_analog_source(embed)

    async def catalyst_context(conn, ticker, catalyst, as_of):
        p = params or kb.load_params(conn, "weekly")

        # --- entry: optional live quote override, else the cache-first last close (frugal) ---
        closes = price_source(conn, ticker, as_of)
        entry = None
        if quote_override is not None:
            q = quote_override(ticker)
            if q is not None and float(q) > 0:
                entry = float(q)
        if entry is None and closes:
            last = float(closes[-1])
            entry = last if last > 0 else None
        if entry is None:
            return {"entry": None, "risk_inputs": {}}   # degraded price -> caller skips the leg

        # --- p_loss: the INDEPENDENT base-rate prior (not the verdict). Honest skip on no cell. ---
        try:
            side, p_positive, _ev = proxy_fn(ticker, as_of, conn, p)
        except (ValueError, KeyError):
            side, p_positive = None, None
        if side is None or p_positive is None:
            return {"entry": None, "risk_inputs": {}}   # no measured cell -> skip, never 1 - None
        p_loss = 1.0 - p_positive

        # --- analogs -> gap + target up/down branch magnitudes (split like builder._split_moves) ---
        analogs = analog_source(conn, ticker, catalyst, as_of)
        up_moves, down_moves = _split_moves(analogs)
        w = p["weekly"]
        if catalyst["catalyst_type"] in w["binary_catalyst_types"]:
            # BINARY (BGAP-01): a CRL/trial miss is a TAIL event -> size against the tail/prior, not median.
            gap = binary_survival_gap(down_moves, percentile=w["binary_gap_percentile"],
                                      default=w["binary_gap_default"])
        else:
            gap = median(down_moves) if down_moves else abs(w["hard_veto_drop"])
        analog_gaps = dict(_NO_ANALOG_GAPS)             # honest single-leg default (peer branches 0.0)
        analog_gaps["target_up"] = median(up_moves) if up_moves else 0.0
        analog_gaps["target_down"] = -median(down_moves) if down_moves else 0.0

        return {
            "entry": entry,
            "risk_inputs": {
                "p_loss": p_loss,
                "gap": gap,
                "analog_gaps": analog_gaps,
                "prices": {"target": [float(c) for c in closes], "peer": []},
            },
        }

    return catalyst_context
