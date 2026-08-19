"""Portfolio what-if ENGINE (Wave 2) — a STATELESS pure function over agent assumptions.

`build_portfolio(positions, assumptions) -> PortfolioOutcome` computes everything a desk needs
for the week from EXPLICIT, agent-supplied assumptions: gross/net exposure, Herfindahl
concentration, aggregate expected return, a correlation-adjusted portfolio vol/variance, per-name
+ book scenario P&L, an XBI sector-shock P&L, Sharpe/Sortino/maxDD over the scenario cross-section,
and a portfolio-level risk-of-ruin. No DB, no network, no hidden state — the agent iterates by
re-calling with adjusted assumptions.

Reuse discipline: every money number comes from an already-shipped quant primitive
(quant.exposure/concentration/conditional_payoff/sharpe/sortino/max_drawdown/risk_of_ruin). This
module is GLUE — a covariance builder + a scenario roll-up + honest labels — never a re-implement.

Two honest PROXIES, both overridable and both LABELLED in the outcome:
  * vol proxy: per-name sigma defaults to |expected_move| (a point-estimate catalyst move, NOT a
    measured symmetric weekly vol — the agent can override via assumptions[ticker]['sigma']).
  * single-factor implied corr: rho_ij = rho_i,xbi · rho_j,xbi assumes XBI is the only common
    factor and residuals are uncorrelated (used only when no mutual peer corr is available).
"""

import math

from pydantic import BaseModel, ConfigDict

from catalyst_trader import quant

# No magic literals: every default/threshold lives here, read by DIRECT SUBSCRIPT so a missing
# key RAISES (mirrors quant/correlations.py::PARAMS).
PARAMS = {
    "default_p_positive": 0.5,        # branch prob when the agent omits p_positive
    "default_periods_per_year": 52,   # weekly book annualization for Sharpe/Sortino
    "default_n_trades": 52,           # ruin horizon (one year of weekly books)
    "max_scenario_names": 8,          # O(2^n) joint enumeration cap; beyond -> marginal roll-up
    "rho_clamp": (-1.0, 1.0),         # correlations are clamped into [-1, 1]
    "reserved_keys": ("corr_source", "sector_shock", "periods_per_year"),
}


class PortfolioOutcome(BaseModel):
    """Frozen, extra-forbidden what-if result — echoes its assumptions for reproducibility.

    Metrics that can be undefined are `| None` (never a fabricated number), mirroring
    backtest.engine.BaselineDistribution: a scenario Sharpe/Sortino/maxDD is None when the
    underlying primitive would RAISE (e.g. <2 branches, zero vol).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # static book metrics
    gross_exposure: float
    net_exposure: float
    concentration: float
    max_weight: float
    expected_return: float
    portfolio_variance: float
    portfolio_vol: float
    covariance_detail: dict   # {"sigma_by_name", "vol_proxy_names", "rho_source": {"AAA-BBB": ...}}
    # scenario / stress P&L + portfolio risk (populated from the scenario cross-section)
    scenarios: dict
    risk: dict
    # verbatim assumptions snapshot (like ToolResult.inputs)
    assumptions_echo: dict


# ── assumption plumbing ────────────────────────────────────────────────────────────────────────
def _resolve_corr_source(assumptions: dict):
    """Return a callable ticker -> profile|None from the corr_source assumption (dict OR callable).

    Absent -> everything idiosyncratic (no off-diagonal correlation). The correlation source is an
    ASSUMPTION; the tool layer binds the stored hedge_profiles as the default.
    """
    src = assumptions.get("corr_source")
    if src is None:
        return lambda _t: None
    if callable(src):
        return src
    if isinstance(src, dict):
        return lambda t: src.get(t)
    raise ValueError(f"corr_source must be a dict, callable, or None (got {type(src).__name__})")


def _side_sign(pos: dict) -> float:
    side = pos["side"]
    if side == "long":
        return 1.0
    if side == "short":
        return -1.0
    raise ValueError(f"side must be 'long' or 'short' (got {side!r})")


def _signed_weights(positions: list[dict]) -> list[float]:
    """Book weight per position in order: side sign × size_pct (long +, short -)."""
    return [_side_sign(p) * float(p["size_pct"]) for p in positions]


def _move(assumptions: dict, ticker: str) -> dict:
    """The per-name assumption sub-dict; RAISES if the name has no supplied moves."""
    if ticker not in assumptions:
        raise ValueError(f"assumptions missing per-name moves for {ticker!r}")
    return assumptions[ticker]


def _sigma(mv: dict) -> tuple[float, bool]:
    """(sigma, used_proxy). Supplied sigma wins; else the vol proxy |expected_move|."""
    if "sigma" in mv:
        return float(mv["sigma"]), False
    return abs(float(mv["expected_move"])), True


def _down_move(mv: dict) -> float:
    """Down-branch magnitude: supplied down_move, else symmetric |expected_move|."""
    return abs(float(mv["down_move"])) if "down_move" in mv else abs(float(mv["expected_move"]))


def _p_positive(mv: dict) -> float:
    return float(mv.get("p_positive", PARAMS["default_p_positive"]))


# ── covariance (genuinely new glue over the assumption corrs/betas) ──────────────────────────────
def _peer_corr(profile, other: str):
    """corr_full for `other` in profile['peers'], or None if absent."""
    if not profile:
        return None
    for p in profile.get("peers", []):
        if p.get("peer") == other and p.get("corr_full") is not None:
            return float(p["corr_full"])
    return None


def _xbi_corr(profile):
    if not profile:
        return None
    c = profile.get("xbi", {}).get("full", {}).get("corr")
    return None if c is None else float(c)


def _pair_rho(ti, tj, pi, pj) -> tuple[float, str]:
    """Off-diagonal precedence: mutual peer corr -> single-factor XBI-implied -> 0. Clamped."""
    lo, hi = PARAMS["rho_clamp"]
    r = _peer_corr(pi, tj)
    if r is None:
        r = _peer_corr(pj, ti)
    if r is not None:
        return max(lo, min(hi, r)), "peer"
    ci, cj = _xbi_corr(pi), _xbi_corr(pj)
    if ci is not None and cj is not None:
        return max(lo, min(hi, ci * cj)), "xbi_implied"
    return 0.0, "zero"


def _covariance(tickers, weights, sigmas, corr_fn):
    """(variance, vol, rho_source_map). sigma_p^2 = ΣΣ wᵢwⱼσᵢσⱼρᵢⱼ; diagonal ρ=1."""
    n = len(tickers)
    profiles = [corr_fn(t) for t in tickers]
    rho_source: dict = {}
    variance = 0.0
    for i in range(n):
        for j in range(n):
            if i == j:
                rho = 1.0
            else:
                rho, src = _pair_rho(tickers[i], tickers[j], profiles[i], profiles[j])
                if i < j:
                    rho_source[f"{tickers[i]}-{tickers[j]}"] = src
            variance += weights[i] * weights[j] * sigmas[i] * sigmas[j] * rho
    return variance, math.sqrt(max(variance, 0.0)), rho_source


# ── the engine ───────────────────────────────────────────────────────────────────────────────
def _validate(positions, assumptions):
    if not positions:
        raise ValueError("positions must be non-empty")
    reserved = PARAMS["reserved_keys"]
    for p in positions:
        if p["ticker"] in reserved:
            raise ValueError(f"ticker {p['ticker']!r} collides with a reserved assumption key")
    for t, mv in assumptions.items():
        if t in reserved:
            continue
        for k, v in mv.items():
            if isinstance(v, (int, float)) and not math.isfinite(v):
                raise ValueError(f"assumption {t}.{k} must be finite (got {v!r})")


def build_portfolio(positions: list[dict], assumptions: dict) -> PortfolioOutcome:
    """Pure what-if: literal positions + literal assumptions -> a frozen PortfolioOutcome."""
    _validate(positions, assumptions)
    tickers = [p["ticker"] for p in positions]
    weights = _signed_weights(positions)
    weights_by_ticker = dict(zip(tickers, weights))
    corr_fn = _resolve_corr_source(assumptions)

    # static exposure/concentration — REUSE the quant primitives on signed weights.
    exp = quant.exposure(weights)
    conc = quant.concentration(weights)

    # aggregate expected return = Σ signed_weight · expected_move (side sign applied).
    expected_return = sum(w * float(_move(assumptions, t)["expected_move"])
                          for t, w in weights_by_ticker.items())

    # per-name sigma (proxy vs supplied) + correlation-adjusted covariance.
    sigmas, proxy_names, sigma_by_name = [], [], {}
    for t in tickers:
        s, is_proxy = _sigma(_move(assumptions, t))
        sigmas.append(s)
        sigma_by_name[t] = s
        if is_proxy:
            proxy_names.append(t)
    variance, vol, rho_source = _covariance(tickers, weights, sigmas, corr_fn)

    # scenario / stress P&L + portfolio risk are populated in Task 2 (contract fields already exist).
    scen: dict = {}
    risk: dict = {}

    return PortfolioOutcome(
        gross_exposure=exp.value,
        net_exposure=exp.detail["net"],
        concentration=conc.value,
        max_weight=conc.detail["max_weight"],
        expected_return=expected_return,
        portfolio_variance=variance,
        portfolio_vol=vol,
        covariance_detail={
            "sigma_by_name": sigma_by_name,
            "vol_proxy_names": proxy_names,
            "rho_source": rho_source,
        },
        scenarios=scen,
        risk=risk,
        assumptions_echo=dict(assumptions),
    )
