"""Before/after retrieval stress harness (quick-260818-l64 Task 3). NOT a pytest test — the LIVE run
is the Task-4 operator step against the gitignored catalyst.db in the MAIN working dir.

The finding this proves out: `analog_query` used to cluster on identity (disease + ticker), not on
the SITUATIONAL SETUP that actually transfers to a fresh event. This harness runs analog_query for
held-out cids TWICE — BEFORE = type-only filter (the old behaviour), AFTER = setup-aware filter
(kb.setup_filters on the node's tagged setups) — and reports the aggregate mean setup-overlap for
each. AFTER should exceed BEFORE, and held-out cids should retrieve setup-siblings from OTHER
tickers/indications, not just same-identity matches.

The MATH is two pure helpers (_overlap / _aggregate) unit-tested offline with no DB. All DB access
(connect, analog_query) lives in main(), guarded so `--help` never touches the DB.

# ponytail: a plain argparse script, no framework. The aggregate mean-overlap is the ONE number that
#           proves setup-awareness moved retrieval; the two pure helpers are the only tested surface.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

_REPORT_DEFAULT = (
    Path(__file__).resolve().parents[1] / ".planning" / "quick"
    / "260818-l64-situational-setup-taxonomy-derive-tag-47" / "retrieval_stress.json"
)


# ── pure math (unit-tested offline, no DB) ────────────────────────────────────

def _overlap(query_setups, result_setups) -> int:
    """Count of setup tags shared between the query and one retrieved result (0 disjoint, len if
    identical). Order-free, dedup-safe."""
    return len(set(query_setups) & set(result_setups))


def _aggregate(per_cid: list[dict]) -> dict:
    """Headline before/after aggregation over already-collected per-cid records.

    Each record: {"cid", "query_setups", "before":[result...], "after":[result...]} where each result
    is a dict carrying a "setups" list. Per-cid overlap = mean overlap across that cid's results
    (0.0 when the cid returned no results); the headline is the mean of those per-cid values.
    Pure — never touches the DB.
    """
    def _cohort_mean(records: list[dict], results_key: str) -> float:
        per = []
        for rec in records:
            results = rec.get(results_key) or []
            if not results:
                per.append(0.0)
                continue
            overlaps = [_overlap(rec["query_setups"], r.get("setups") or []) for r in results]
            per.append(sum(overlaps) / len(overlaps))
        return sum(per) / len(per) if per else 0.0

    return {
        "mean_overlap_before": _cohort_mean(per_cid, "before"),
        "mean_overlap_after": _cohort_mean(per_cid, "after"),
        "n": len(per_cid),
    }


# ── live wiring (main() only — imported lazily so --help never opens a DB) ─────

def _default_cids() -> list[int]:
    """A spread of held-out cids drawn from the taxonomy's example_cids across several setups."""
    from catalyst_trader.playbook import tagger
    seen, out = set(), []
    for tag in tagger.load_taxonomy()["tags"]:
        if tag.get("group") != "ex-ante":
            continue
        for cid in (tag.get("example_cids") or [])[:2]:
            if cid not in seen:
                seen.add(cid)
                out.append(cid)
    return out


def _result_row(with_outcome: dict) -> dict:
    """Trim an analog_query result to the report shape (node_id, ticker, indication, setups)."""
    cat = with_outcome.get("catalyst") or {}
    return {
        "node_id": with_outcome.get("node_id"),
        "ticker": cat.get("ticker"),
        "indication": cat.get("indication"),
        "setups": cat.get("setups") or [],
    }


def _run_one(conn, kb, embed, cid: int, k: int) -> dict | None:
    """One held-out cid: build the builder's query context, run analog_query BEFORE (type-only) and
    AFTER (setup-aware), return the per-cid record — or None if the node is absent."""
    row = conn.execute(
        "SELECT id, attrs_json FROM kb_node WHERE kind='catalyst' AND ref_id=? ORDER BY id DESC LIMIT 1",
        (cid,),
    ).fetchone()
    if row is None:
        return None
    attrs = json.loads(row["attrs_json"]) if row["attrs_json"] else {}
    ctype = attrs.get("type")
    thesis = (attrs.get("narrative_before") or {}).get("thesis", "")
    context = f"{ctype} catalyst: {thesis}"  # the builder's query context (no ticker)
    q_setups = attrs.get("setups") or []

    before = kb.analog_query(conn, embed, context, filters={"type": ctype}, k=k)
    after = kb.analog_query(conn, embed, context, filters=kb.setup_filters(conn, ctype, q_setups), k=k)
    return {
        "cid": cid,
        "query_setups": q_setups,
        "before": [_result_row(r) for r in before],
        "after": [_result_row(r) for r in after],
    }


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description="Before/after setup-aware retrieval stress harness (LIVE).")
    ap.add_argument("--cids", help="comma-separated held-out catalyst ids (default: taxonomy example_cids)")
    ap.add_argument("--k", type=int, default=5, help="analogs per query (default 5)")
    ap.add_argument("--db", default=None, help="sqlite path (default: settings.db_path)")
    ap.add_argument("--out", default=str(_REPORT_DEFAULT), help="JSON report output path")
    args = ap.parse_args(argv)

    # DB + heavy imports are lazy so `--help` (and the offline unit tests) never open a DB.
    from catalyst_trader import db as _db
    from catalyst_trader import kb

    cids = [int(c) for c in args.cids.split(",")] if args.cids else _default_cids()
    conn = _db.connect(args.db)  # open the EXISTING live DB (no migrate)
    embed = kb.default_embedder()
    try:
        per_cid, missing = [], []
        for cid in cids:
            rec = _run_one(conn, kb, embed, cid, args.k)
            (per_cid if rec is not None else missing).append(rec if rec is not None else cid)
    finally:
        conn.close()

    report = {"aggregate": _aggregate(per_cid), "missing_cids": missing, "per_cid": per_cid}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str))
    agg = report["aggregate"]
    print(f"held-out cids: {len(per_cid)} present, {len(missing)} missing")
    print(f"mean setup-overlap  BEFORE={agg['mean_overlap_before']:.3f}  "
          f"AFTER={agg['mean_overlap_after']:.3f}  (n={agg['n']})")
    print(f"report: {out}")
    return report


if __name__ == "__main__":
    main()
