"""Valuation-assumptions adapter (FF-05) — the cache read/write helpers + pre-event context packer
that feed the football-field rnpv / sum-of-parts / analyst-PT valuation methods.

A THIN mirror of desk/options_adapter.py: NO DDL (the table is migration 013), NO valuation math
(quant.valuation owns rnpv/pipeline_value/analyst_pt_move). The builder already consumes
`assumptions_provider(ticker, catalyst, as_of) -> dict` and feeds those tools into the field — this
module PROVIDES the cache + provider + validating write helper + the pre-event context an estimator
agent reads (plan Task 4).

Two no-look-ahead halves:
  - the PROVIDER abstains ({}) when a cached row's stored `as_of` is AFTER the requested as_of;
  - the CONTEXT PACKER assembles ONLY as_of-gated pre-event facts (price/card via serving.asof,
    prior readouts via kb._structural_filter(as_of=as_of) — never post-event / this catalyst's outcome).

`write_assumptions_snapshot` REJECTS a bad-shape dict (reject-not-fabricate): PoS/prob_reach in
[0,1], shares_out > 0, non-empty cashflows/segments/price_targets, and at least one of
{rnpv, sop, analyst_pt}. A malformed agent estimate never lands in the cache.

# ponytail: the table is provisioned by migration 013 (db.migrate) — this module ASSUMES the DB is
#           migrated and NEVER creates schema. ABSTAIN is {} (never None) because the builder
#           membership-tests `"rnpv" in a`.
"""

import json
import math

from .analysts import _get


def _finite_prob(p, name: str) -> None:
    if not isinstance(p, (int, float)) or isinstance(p, bool) or not math.isfinite(p) or not 0.0 <= p <= 1.0:
        raise ValueError(f"{name} must be a finite number in [0,1] (got {p!r})")


def _finite(x, name: str) -> None:
    if not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x):
        raise ValueError(f"{name} must be finite (got {x!r})")


def _validate_cashflows(cashflows, ctx: str) -> None:
    if not cashflows:
        raise ValueError(f"{ctx}: cashflows must be non-empty")
    for cf in cashflows:  # (year, cashflow_usd, cumulative_pos)
        _, cash, pos = cf
        _finite(cash, f"{ctx}: cashflow")
        _finite_prob(pos, f"{ctx}: cumulative_pos")


def _validate_costs(costs, ctx: str) -> None:
    for c in costs or []:  # (year, cost, prob_reach)
        _, cost, prob = c
        _finite(cost, f"{ctx}: cost")
        _finite_prob(prob, f"{ctx}: prob_reach")


def _validate_shares(shares_out, ctx: str) -> None:
    if not isinstance(shares_out, (int, float)) or isinstance(shares_out, bool) \
            or not math.isfinite(shares_out) or shares_out <= 0:
        raise ValueError(f"{ctx}: shares_out must be > 0 (got {shares_out!r})")


def _validate_assumptions(a: dict) -> None:
    """Reject-not-fabricate gate: raise ValueError on any bad shape/bound so a bad row never reaches
    the cache. Validates SHAPE only — the domain rules quant.valuation already enforces (PoS ∈ [0,1],
    positive shares_out, non-empty cashflows) — it does NOT re-implement rnpv math."""
    if not isinstance(a, dict) or not ({"rnpv", "sop", "analyst_pt"} & a.keys()):
        raise ValueError("assumptions must carry at least one of {rnpv, sop, analyst_pt}")
    if "rnpv" in a:
        r = a["rnpv"]
        _validate_cashflows(r.get("cashflows"), "rnpv")
        _validate_costs(r.get("costs"), "rnpv")
        _validate_shares(r.get("shares_out"), "rnpv")
    if "sop" in a:
        s = a["sop"]
        _validate_shares(s.get("shares_out"), "sop")
        segs = s.get("segments")
        if not segs:
            raise ValueError("sop: segments must be non-empty")
        for i, seg in enumerate(segs):
            _validate_cashflows(seg.get("cashflows"), f"sop.segment[{i}]")
            _validate_costs(seg.get("costs"), f"sop.segment[{i}]")
    if "analyst_pt" in a:
        pts = a["analyst_pt"].get("price_targets")
        if not pts:
            raise ValueError("analyst_pt: price_targets must be non-empty")
        for pt in pts:
            _finite(pt, "analyst_pt: price_target")


def write_assumptions_snapshot(conn, ticker: str, event_date: str, assumptions: dict, *,
                               as_of: str | None, source: str) -> None:
    """Validate FIRST, then upsert one cached assumptions dict (INSERT OR REPLACE on the
    (ticker, event_date) PK) + commit. A malformed estimate raises before the INSERT so nothing
    lands (mirror write_options_snapshot). `as_of` is the knowable-as-of stamp; `fetched_at` the
    wall-clock fetch time."""
    from ..dates import now_iso  # lazy: keep the module import surface thin

    _validate_assumptions(assumptions)
    conn.execute(
        "INSERT OR REPLACE INTO assumptions_snapshot "
        "(ticker, event_date, assumptions_json, as_of, source, fetched_at) VALUES (?, ?, ?, ?, ?, ?)",
        (ticker, event_date, json.dumps(assumptions), as_of, source, now_iso()),
    )
    conn.commit()


def assumptions_snapshot_provider(conn):
    """Return callable(ticker, catalyst, as_of) -> dict reading one cached row. The provider the
    builder injects (default) in the headless/backtest path. ABSTAIN = {} (never None): an absent
    (ticker, event_date) row, OR a stored as_of that is AFTER the requested as_of (NO-LOOK-AHEAD).
    A live (None) requested as_of is ungated."""

    def _provider(ticker: str, catalyst, as_of: str | None = None) -> dict:
        event_date = _get(catalyst, "event_date")
        row = conn.execute(
            "SELECT assumptions_json, as_of FROM assumptions_snapshot WHERE ticker=? AND event_date=?",
            (ticker, event_date),
        ).fetchone()
        if row is None:
            return {}
        if row["as_of"] is not None and as_of is not None and row["as_of"] > as_of:
            return {}  # NO-LOOK-AHEAD abstain: the estimate was not knowable at the decision as_of
        return json.loads(row["assumptions_json"])

    return _provider


def assumptions_context(conn, ticker: str, catalyst, as_of: str) -> dict:
    """Assemble ONLY as_of-gated pre-event facts an estimator agent (plan Task 4) reads to estimate
    peak-sales / PoS / discount / shares_out / price_targets. Deterministic (same seeded rows ->
    same dict); no agent call, no network — the estimation itself is Task 4, not here.

    NO-LOOK-AHEAD is the whole point: price/card route through serving.asof(cutoff=as_of); prior
    readouts are gated via kb._structural_filter(as_of=as_of) (knowable_asof <= as_of) AND
    event_date < as_of — so a post-as_of readout and THIS catalyst's own outcome are provably absent.
    """
    from .. import kb, serving

    def g(key):
        v = _get(catalyst, key, None)
        return v if v not in ("", None) else None

    ct = g("catalyst_type")
    out: dict = {
        "ticker": ticker,
        "as_of": as_of,
        "catalyst_type": getattr(ct, "value", ct),
        "drug": g("drug"),
        "indication": g("indication"),
        "modality": g("modality"),
        "stage": g("stage"),
    }

    # disease_area / mechanism_class / drivers: off the catalyst object, else the kb catalyst node.
    node_attrs: dict = {}
    ref = _get(catalyst, "catalyst_id", None)
    if ref is not None:
        r = conn.execute(
            "SELECT attrs_json FROM kb_node WHERE kind='catalyst' AND ref_id=? ORDER BY id DESC LIMIT 1",
            (ref,),
        ).fetchone()
        if r is not None and r["attrs_json"]:
            node_attrs = json.loads(r["attrs_json"])
    for key in ("disease_area", "mechanism_class", "drivers"):
        out[key] = g(key) or node_attrs.get(key)

    # prior_readouts: this ticker's PAST realized outcomes, gated so only rows knowable by as_of
    # appear — reuse the kb as_of-gated structural filter + outcome traverse (no new SQL).
    prior: list[dict] = []
    for nid in sorted(kb._structural_filter(conn, {"ticker": ticker}, as_of=as_of)):
        wo = kb._with_outcome(conn, nid, 0.0)
        cat = wo.get("catalyst") or {}
        ev = cat.get("event_date")
        if ev is None or ev >= as_of:  # only PAST readouts (excludes this future catalyst)
            continue
        if ref is not None and cat.get("catalyst_id") == ref:  # never this catalyst's own outcome
            continue
        outcome = wo.get("outcome")
        if not outcome or "move" not in outcome:
            continue
        prior.append({"event_date": ev, "catalyst_type": cat.get("type"),
                      "indication": cat.get("indication"), "move": outcome["move"]})
    out["prior_readouts"] = prior

    # cash / runway / float + current price: as_of-gated via the serving gateway (None-safe).
    book = serving.asof(conn, as_of)
    card = book.card(ticker, as_of)
    if card:
        for k in ("cash_runway_months", "float", "shares_outstanding"):
            if card.get(k) is not None:
                out[k] = card[k]
    bars = book.bars(ticker, as_of)
    if bars:
        out["current_price"] = bars[-1]["close"]

    return out
