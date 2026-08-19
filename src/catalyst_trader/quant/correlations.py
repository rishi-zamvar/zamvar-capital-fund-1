"""DB-aware correlation engine (HEDGE-CORR-1a) — explicit per-name hedge facts.

The strategy's names are ~90% idiosyncratic (peer pairs corr ~0.11 median; XBI explains ~10% of
the median name's weekly variance). This engine gives the desk an EXPLICIT, always-available
correlation/hedge profile per name — corr/beta/R2 to XBI + same-group peer pairwise corr, computed
BOTH full-window and ex-event-week, each with a plain verdict AND an explicit co-move/inverse
direction — so an agent SEES whether a hedge is real rather than assuming 0.7-corr = hedged.

This is a NEW module (not an extension of quant/pairs.py): pairs.py is pure numpy with zero DB
coupling and must stay that way. This engine is DB-aware orchestration (reads price_bar + catalyst
nodes, groups by disease_area/mechanism_class, aligns weeks, bands verdicts) — it REUSES the numpy
math (pairs.correlation_beta, R2 == corr**2) and the weekly-return helper (weekly._weekly_returns),
never re-implementing either.

Two money-safety guarantees:
  - WEEK ALIGNMENT (the XBI trap): XBI in price_bar is Monday-anchored while the universe is
    Friday-anchored; pairing them raw mis-correlates. Every pair is intersected STRICTLY on common
    week_end BEFORE returns; too few common weeks RAISES (insufficient obs) — never a length-padded,
    silently-wrong number.
  - SIGNED verdict (C3): the SIGNED corr/beta is always stored; the strength verdict is on |corr|
    and the direction ("co-move"/"inverse") is explicit — a strong negative is a real INVERSE
    relationship, not "none".

No magic literals: verdict bands, ex-event window, min-obs, and the hedge-verdict set live in the
module-level PARAMS dict, read by DIRECT SUBSCRIPT so a missing key RAISES.
"""

from datetime import date, timedelta

from .pairs import correlation_beta
from .weekly import _weekly_returns

_XBI = "XBI"

# The one place any threshold lives. Direct-subscript reads => a missing key raises (no fallback).
PARAMS = {
    # strength bands on |corr|; a corr >= band is that verdict, most-severe first.
    "verdict_bands": {"strong": 0.6, "moderate": 0.4, "weak": 0.2},
    # ex-event-week strip: a return whose destination week_end is within +/- this many weeks of any
    # of the ticker's OWN catalyst event_dates is dropped (isolates systematic co-movement from alpha).
    "ex_event_window_weeks": 2,
    # minimum aligned RETURN observations before we trust a corr/beta (else abstain/raise).
    "min_obs": 8,
    # xbi verdicts that justify an overlay hedge (else sizing_only).
    "hedge_verdicts": ["strong", "moderate"],
}


# --- verdict + direction ---------------------------------------------------

def _verdict(corr: float, bands: dict) -> str:
    """Strength band on |corr|. Direct subscripts => a missing band key RAISES (no magic literal)."""
    a = abs(corr)
    if a >= bands["strong"]:
        return "strong"
    if a >= bands["moderate"]:
        return "moderate"
    if a >= bands["weak"]:
        return "weak"
    return "none"


def _direction(corr: float) -> str:
    """Explicit co-move vs inverse (C3) — a strong negative is an inverse relationship, not 'none'."""
    return "co-move" if corr >= 0 else "inverse"


# --- series + alignment (the XBI-trap fix) ---------------------------------

def _series(conn, ticker) -> dict:
    """{week_end: close} for a ticker from price_bar (whole history, order-independent)."""
    rows = conn.execute(
        "SELECT week_end, close FROM price_bar WHERE ticker=?", (ticker,)
    ).fetchall()
    return {r["week_end"]: r["close"] for r in rows}


def _aligned_bars(conn, a, b):
    """Two bar lists intersected STRICTLY on common week_end (chronological). This is the week-
    alignment guarantee — a Monday-anchored XBI vs a Friday name shares few/zero week_ends here,
    so the pair is short (and downstream raises) rather than length-padded and mis-correlated."""
    sa, sb = _series(conn, a), _series(conn, b)
    common = sorted(set(sa) & set(sb))
    bars_a = [{"week_end": w, "close": sa[w]} for w in common]
    bars_b = [{"week_end": w, "close": sb[w]} for w in common]
    return bars_a, bars_b


def _aligned_returns(conn, a, b, *, ex_event_ends=frozenset()):
    """Aligned close-to-close weekly returns for the pair, REUSING weekly._weekly_returns.

    ex_event_ends (C1): drop the RETURN-observation whose DESTINATION week_end is in the set,
    POST-computation — not the raw bar. Dropping the bar would fuse two weeks into one multi-week
    return; dropping the observation keeps every remaining return a true single-week move and keeps
    both legs aligned (same destination week_ends)."""
    bars_a, bars_b = _aligned_bars(conn, a, b)
    ra, rb = _weekly_returns(bars_a), _weekly_returns(bars_b)
    # returns[i] is the return of the week ending at bars[i+1] -> its destination week_end.
    dest = [bars_a[i + 1]["week_end"] for i in range(len(bars_a) - 1)]
    out_a, out_b = [], []
    for i, d in enumerate(dest):
        if d in ex_event_ends:
            continue
        out_a.append(ra[i])
        out_b.append(rb[i])
    return out_a, out_b


def _ex_event_week_ends(conn, ticker, window) -> frozenset:
    """The set of `ticker`'s OWN price_bar week_ends within +/- `window` weeks of any of its catalyst
    event_dates. Keys on the ticker's own events only (no cross-name leakage) — the peer-pair caller
    unions BOTH names' sets itself (C2)."""
    events = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT json_extract(attrs_json,'$.event_date') FROM kb_node "
            "WHERE kind='catalyst' AND json_extract(attrs_json,'$.ticker')=? "
            "AND json_extract(attrs_json,'$.event_date') IS NOT NULL",
            (ticker,),
        ).fetchall()
    ]
    if not events:
        return frozenset()
    span_days = timedelta(weeks=window).days
    ev_dates = [date.fromisoformat(e) for e in events]
    out = set()
    for w in _series(conn, ticker):
        wd = date.fromisoformat(w)
        if any(abs((wd - ev).days) <= span_days for ev in ev_dates):
            out.add(w)
    return frozenset(out)


# --- pairwise + XBI stats --------------------------------------------------

def compute_pair_corr(conn, a, b, *, ex_event=False) -> float:
    """Signed Pearson corr of two names' aligned weekly returns (REUSE correlation_beta). ex_event
    strips the UNION of BOTH names' event weeks (C2 — symmetric, so the number is well-defined).
    RAISES on < PARAMS['min_obs'] aligned observations (abstain rather than emit a padded number)."""
    ex_ends = frozenset()
    if ex_event:
        w = PARAMS["ex_event_window_weeks"]
        ex_ends = _ex_event_week_ends(conn, a, w) | _ex_event_week_ends(conn, b, w)
    ra, rb = _aligned_returns(conn, a, b, ex_event_ends=ex_ends)
    if len(ra) < PARAMS["min_obs"]:
        raise ValueError(f"insufficient common obs for {a} vs {b} (got {len(ra)})")
    return correlation_beta(ra, rb).value


def compute_xbi_stats(conn, ticker, *, ex_event=False) -> dict:
    """corr / beta / R2 of `ticker` vs XBI on aligned weekly returns (REUSE correlation_beta;
    R2 == corr**2 for simple regression). ex_event strips the ticker's OWN event weeks only (XBI has
    no catalysts of its own). RAISES on insufficient aligned obs — this is the XBI-trap regression:
    a Monday XBI vs a Friday name shares ~zero week_ends and RAISES instead of mis-correlating."""
    ex_ends = _ex_event_week_ends(conn, ticker, PARAMS["ex_event_window_weeks"]) if ex_event else frozenset()
    ra, rb = _aligned_returns(conn, ticker, _XBI, ex_event_ends=ex_ends)
    if len(ra) < PARAMS["min_obs"]:
        raise ValueError(f"insufficient common obs for {ticker} vs XBI (got {len(ra)})")
    res = correlation_beta(ra, rb)  # asset=ticker, market=XBI
    c = res.value
    return {"corr": c, "beta": res.detail["beta"], "r2": c ** 2}


# --- same-group peers ------------------------------------------------------

def _company_axes(conn, ticker):
    """The (disease_areas, mechanism_classes) `ticker` belongs to, from its catalyst nodes."""
    rows = conn.execute(
        "SELECT DISTINCT json_extract(attrs_json,'$.disease_area'), "
        "json_extract(attrs_json,'$.mechanism_class') FROM kb_node "
        "WHERE kind='catalyst' AND json_extract(attrs_json,'$.ticker')=?",
        (ticker,),
    ).fetchall()
    diseases = {r[0] for r in rows if r[0]}
    mechs = {r[1] for r in rows if r[1]}
    return diseases, mechs


def _same_group_peers(conn, ticker):
    """Other tickers sharing `ticker`'s disease_area OR mechanism_class, as [(peer, label)] sorted
    by ticker (deterministic). Disease match takes label precedence over mechanism match."""
    diseases, mechs = _company_axes(conn, ticker)
    if not diseases and not mechs:
        return []
    rows = conn.execute(
        "SELECT DISTINCT json_extract(attrs_json,'$.ticker'), "
        "json_extract(attrs_json,'$.disease_area'), json_extract(attrs_json,'$.mechanism_class') "
        "FROM kb_node WHERE kind='catalyst' AND json_extract(attrs_json,'$.ticker') IS NOT NULL",
    ).fetchall()
    peers: dict[str, str] = {}
    for tk, dis, mech in rows:
        if tk == ticker or tk in peers:
            continue
        if dis and dis in diseases:
            peers[tk] = f"disease:{dis}"
        elif mech and mech in mechs:
            peers[tk] = f"mechanism:{mech}"
    return sorted(peers.items())


# --- the profile blob ------------------------------------------------------

def _xbi_block(conn, ticker, *, ex_event):
    stats = compute_xbi_stats(conn, ticker, ex_event=ex_event)
    stats["verdict"] = _verdict(stats["corr"], PARAMS["verdict_bands"])
    stats["direction"] = _direction(stats["corr"])
    stats["window"] = "ex_event" if ex_event else "full"
    return stats


def compute_hedge_profile(conn, ticker, *, as_of=None) -> dict:
    """The explicit hedge-profile blob for one name (the spec shape). Every relationship (XBI +
    each peer) carries a strength verdict AND a co-move/inverse direction. Peers with too few aligned
    obs are OMITTED (abstain — never a misleading number). systematic_frac == R2, idiosyncratic ==
    1-R2; suggested_hedge is an XBI overlay only when the XBI verdict justifies it, else sizing_only."""
    bands = PARAMS["verdict_bands"]
    xbi_full = _xbi_block(conn, ticker, ex_event=False)  # raises on the XBI trap / insufficient obs
    xbi_ex = _xbi_block(conn, ticker, ex_event=True)

    r2 = xbi_full["r2"]
    suggested = (
        f"xbi_overlay@beta {xbi_full['beta']:.2f}"
        if xbi_full["verdict"] in PARAMS["hedge_verdicts"]
        else "sizing_only"
    )

    peers = []
    for peer, label in _same_group_peers(conn, ticker):
        try:
            corr_full = compute_pair_corr(conn, ticker, peer, ex_event=False)
            corr_ex = compute_pair_corr(conn, ticker, peer, ex_event=True)
        except ValueError:
            continue  # abstain — omit the pair rather than emit a padded/misleading number
        peers.append({
            "peer": peer, "disease_or_mech": label,
            "corr_full": corr_full, "corr_ex_event": corr_ex,
            "verdict": _verdict(corr_full, bands), "direction": _direction(corr_full),
        })

    note = (
        "Verdict is |corr| strength; direction is explicit co-move/inverse. XBI R2 is the systematic "
        "share of weekly variance; the rest is idiosyncratic. Peers with insufficient aligned weeks "
        "are omitted (abstained), not zeroed."
    )
    return {
        "as_of": as_of,
        "ticker": ticker,
        "xbi": {"full": xbi_full, "ex_event": xbi_ex},
        "peers": peers,
        "systematic_frac": r2,
        "idiosyncratic_frac": 1.0 - r2,
        "suggested_hedge": suggested,
        "note": note,
    }
