"""desk/weekly.py — the weekly cadence runner (WEEK-01) + the LEARN record seam (WEEK-05).

`run_weekly` is a THIN composition of the shipped desk — it adds NO new money logic:

    thesis_scan (every name, deterministic)          -- Plan 03
      -> shortlist = catalyst names + top-k eligible statistical rows
      -> run_desk per catalyst name -> verdict work items   -- Workflow-1 (Phase 4/5)
      -> single-leg statistical Candidates (no hedge, size_for_survival target-within-cap)  -- Plan 02
      -> run_portfolio(target_return, extra_candidates, defensive_book, statistical_sleeve_cap)  -- Task 1
      -> a StrategyDossier book, never empty (defensive book on a no-signal week)

The measurement trap is closed by using the ONE ``params["weekly"]["anchor"]`` in BOTH the base-rate
measurement (inside thesis_scan) and the runner's enter/exit horizon — there is a single anchor source.
Statistical (non-catalyst) legs are ALWAYS single-leg (the Phase-5 size-tiny / no-hedge fallback) and
ALWAYS exit at the one-week horizon; the catalyst path keeps Workflow-1's hold-vs-exit decision.

The per-catalyst market context (entry + risk_inputs) is a caller-injected ``catalyst_context`` hook:
the desk has no live price/analog feed this phase (a documented carry-forward), so the caller supplies
it exactly as ``run_portfolio``'s contract states. With no hook wired, catalyst names are still
shortlisted but produce no leg this phase — the statistical + defensive sleeves carry the book.

# ponytail: no new sizing/selection math here — every money number comes from the shipped tools
#           (size_for_survival, select_book). This file only WIRES them into the weekly cadence.
"""

from datetime import date, timedelta

from catalyst_trader.dates import now_iso

from .. import kb, store
from ..quant.weekly import classify_drop, thesis_scan
from ..universe.build import universe_as_of
from .evidence import tool_ref_for
from .orchestrator import run_desk, run_portfolio
from .portfolio import Candidate
from .risk import size_for_survival


def _weekly_exit(as_of, anchor):
    """The one-week hard-exit horizon for a weekly leg.

    ``anchor`` is the SAME single ``params["weekly"]["anchor"]`` that thesis_scan measures the base rate
    on (measurement window == execution window — the trap that silently evaporates the edge). The hold
    is one week; the anchor pins the reference day (MON_OPEN / FRI_CLOSE).
    """
    return (date.fromisoformat(as_of) + timedelta(days=7)).isoformat()


def _last_close(conn, ticker, as_of):
    bars = store.bars_asof(conn, ticker, as_of, lookback_weeks=1)
    return float(bars[-1]["close"]) if bars else 0.0


def build_defensive_book(params) -> list[Candidate]:
    """The cash-like DEFENSIVE book (SGOV/BIL + a tiny XBI) deployed when no cell clears the bar
    (WEEK-03 — no zero-trade weeks). Instruments + max fraction come from ``params["weekly"]``; the
    fraction is split evenly and every leg is marked ``defensive`` so the dossier language is honest."""
    w = params["weekly"]
    instruments = w["defensive_instruments"]
    max_frac = w["defensive_max_frac"]
    per = max_frac / len(instruments) if instruments else 0.0
    return [
        Candidate(size_pct=per, expected_move=0.0001, weight=per,
                  payload={"defensive": True, "ticker": tk, "entry": 1.0})
        for tk in instruments
    ]


def _catalyst_dict(conn, ticker, as_of):
    """The verified catalyst for `ticker` inside the upcoming hold week (as_of, as_of + 7d], or None."""
    end = (date.fromisoformat(as_of) + timedelta(days=7)).isoformat()
    for c in store.tradeable_catalysts(conn):
        if c.ticker == ticker and as_of < c.event_date <= end:
            return {"ticker": c.ticker, "catalyst_type": c.catalyst_type.value,
                    "event_date": c.event_date, "catalyst_id": f"{ticker}:{c.event_date}"}
    return None


async def run_weekly(conn, embed, as_of, open_book, *, params=None, target_weekly=0.01,
                     catalyst_context=None, closing_legs=None):
    """Run one weekly cadence and return the week's StrategyDossier book (WEEK-01) — never empty.

    `target_weekly` is the ~1% objective sizing serves within the survival cap (a caller value, not a
    literal in a tool body). `catalyst_context(conn, ticker, catalyst, as_of) -> {"entry", "risk_inputs"}`
    supplies the per-catalyst market context (the caller owns the price/analog feed); None skips the
    catalyst legs this phase (statistical + defensive carry the book).
    """
    params = params or kb.load_params(conn, "weekly")
    w = params["weekly"]
    anchor = w["anchor"]                      # the ONE anchor — measurement == execution
    shortlist_k = w["shortlist_k"]
    sleeve_cap = w["statistical_sleeve_cap"]
    stat_gap = abs(w["hard_veto_drop"])       # worst tolerated weekly move = the survival down-gap
    exit_by = _weekly_exit(as_of, anchor)

    universe = [u.ticker for u in universe_as_of(conn, as_of)]
    scan = thesis_scan(universe, as_of, store, conn, params=params)
    rows = scan.detail["rows"]

    # shortlist: catalyst names (Workflow-1 owns them) + top-k eligible statistical rows (edge x mean).
    catalyst_names = [r["ticker"] for r in rows if r["thesis_type"] == "catalyst"]
    eligible = [r for r in rows if r["eligible"] and r["thesis_type"] != "catalyst"]
    eligible.sort(key=lambda r: (r["p"] or 0.0) * (r["mean_next"] or 0.0), reverse=True)
    top_stat = eligible[:shortlist_k]

    # catalyst legs -> the shipped Workflow-1 desk -> run_portfolio work items.
    verdicts = []
    for name in catalyst_names:
        cat = _catalyst_dict(conn, name, as_of)
        if cat is None or catalyst_context is None:
            continue  # no price/analog feed wired this phase — statistical + defensive carry the book
        verdict = await run_desk(conn, cat)
        mc = await catalyst_context(conn, name, cat, as_of)
        verdicts.append({"verdict": verdict, "catalyst": cat, **mc})

    # statistical single-leg candidates: NO hedge (Phase-5 fallback), sized target-within-survival-cap.
    extra = []
    for r in top_stat:
        cd = classify_drop(r["ticker"], as_of, store, conn, params=params).detail
        br_inputs = {"ticker": r["ticker"], "trigger": r["trigger"], "drop_class": cd["drop_class"],
                     "turnover": cd["turnover_flag"], "as_of": as_of, "params": params,
                     "window_years": None}
        size = size_for_survival(
            p_loss=1.0 - r["p"], gap=stat_gap,
            target_return=target_weekly, expected_move=r["mean_next"],
        ).value
        extra.append(Candidate(
            size_pct=size, expected_move=r["mean_next"], weight=size,
            payload={"weekly": True, "ticker": r["ticker"], "thesis_type": r["thesis_type"],
                     "trigger": r["trigger"], "p": r["p"], "mean_next": r["mean_next"],
                     "entry": _last_close(conn, r["ticker"], as_of), "exit_by_date": exit_by,
                     "base_rate_ref": tool_ref_for("weekly_base_rate", br_inputs),
                     "base_rate_inputs": br_inputs},
        ))

    defensive = build_defensive_book(params)
    for c in defensive:
        c.payload["exit_by_date"] = exit_by     # the one-week horizon (same anchor)

    book = await run_portfolio(
        conn, embed, verdicts, open_book,
        target_return=target_weekly, target_weekly=target_weekly,
        extra_candidates=extra, defensive_book=defensive,
        statistical_sleeve_cap=sleeve_cap,
    )

    # WEEK-05 seam: at the one-week exit, last week's legs have realized their return -> record them as
    # cited KB outcome claims for the Phase-10 LEARN loop. The caller supplies `closing_legs` (each with
    # its realized_ret + base_rate_inputs); nothing to close on the very first week.
    for leg in (closing_legs or []):
        record_weekly_outcome(conn, leg, embed=embed)

    return book


# --- WEEK-05: per-leg outcome record seam (cited KB claims for the Phase-10 LEARN loop) --------


def record_weekly_outcome(conn, leg, *, embed=None):
    """Persist ONE cited KB ``outcome`` claim for a realized weekly leg (WEEK-05 seam).

    The claim carries {thesis_type, trigger, p_quoted, size, realized_ret, win} and CITES the
    ``weekly_base_rate`` ToolResult that justified the leg via a ``tool:weekly_base_rate#<inputs_hash>``
    ref (Phase-4 resolved-by-construction pattern) — the ref is stored as the claim's EvidenceSource, so
    insert_claim's cite-or-drop invariant holds by construction (no uncited write). The inputs hash pins
    the exact base-rate cell, so a re-run reproduces the number.

    Build the SEAM only — the base-rate refit that CONSUMES these rows is Phase-10 (LEARN), out of scope.
    # ponytail: the eligibility / auto-demotion ledger (research §3.3) is Phase-10 — record the raw
    #           outcomes now, do NOT build the demotion machinery.
    """
    br_inputs = leg["base_rate_inputs"]
    ref = tool_ref_for("weekly_base_rate", br_inputs)          # resolved-by-construction (cite-or-drop)
    ev = kb.EvidenceSource(
        url=ref,
        retrieved_at=now_iso(),
        snippet_hash=ref.split("#", 1)[1],
        quote=f"p_up={leg['p_quoted']} thesis={leg['thesis_type']} trigger={leg['trigger']}",
    )
    node = kb.KBNode(kind="outcome", attrs={
        "kind": "weekly_leg",
        "ticker": leg["ticker"],
        "thesis_type": leg["thesis_type"],
        "trigger": leg["trigger"],
        "p_quoted": leg["p_quoted"],
        "size": leg["size"],
        "realized_ret": leg["realized_ret"],
        "win": leg["realized_ret"] > 0,
    })
    return kb.insert_claim(conn, node, [ev], embed=embed,
                           embed_text=f"weekly {leg['thesis_type']} {leg['ticker']}" if embed else None)
