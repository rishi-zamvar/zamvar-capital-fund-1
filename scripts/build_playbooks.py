"""ONE-TIME populate: turn the resolved PEER corpus into cited, leak-safe analog nodes so
analog_query goes warm (research C §2). Per catalyst: build_bundle (Plan 03, cache-first from the
lake — no re-fetch) -> extract_record (the ONLY live-LLM seam, a Sonnet complete_fn) ->
insert_catalyst_record (Plan 04, cite-or-drop + idempotent).

FRUGALITY / SAFETY:
- The live model call is gated behind --run. Default is DRY-RUN: it counts the corpus by tier and
  prints the plan + token estimate WITHOUT building a bundle, hitting the network, or spending a cent.
- The corpus is two DISTINCT tiers, kept separate so retrieval can tier them (they carry their `type`
  top-level, so no extra tag is needed): BINARY CORE (pdufa + trial_readout) is the primary pass;
  EARNINGS is a separate tier (research B §2).
- Idempotent: a re-run skips catalysts already populated (unchanged content_sha), so a crashed run
  resumes cheaply and the ~$7 Sonnet spend is never doubled.
- Embedder consistency (plan-check NIT 2): populate with kb.default_embedder() (local_embed when
  fastembed is present; CT_EMBEDDER unset). insert_catalyst_record refuses to mix embedders, and the
  Plan-05 warm path calls store.assert_embedder_consistency before querying.

# ponytail: dry-run is pure SQL (offline). Bundle resolution + naked-skip counting happen only under
#   --run, because build_bundle's CIK-cache-miss fallback can touch the network — a dry-run must not.
"""

import argparse
import sqlite3

from catalyst_trader import kb
from catalyst_trader.playbook.extract import build_bundle, extract_record
from catalyst_trader.playbook.generalize import generalize_playbooks
from catalyst_trader.playbook.store import insert_catalyst_record

DB = "catalyst.db"
_CORE_TYPES = ("pdufa", "trial_readout")  # binary core
# research B §3.6: ~1.6M input + ~0.17M output tokens over ~336 catalysts, Sonnet ≈ $7 one-time.
_EST_INPUT_PER = 4800
_EST_OUTPUT_PER = 500


def _candidates(conn) -> list[sqlite3.Row]:
    """Resolved catalysts that CAN yield an analog: they have a realized move AND a source URL.
    Ordered core-first (the primary pass), then earnings (the distinct tier)."""
    return conn.execute(
        "SELECT DISTINCT c.id, c.ticker, c.catalyst_type FROM catalyst c "
        "JOIN catalyst_move m ON m.catalyst_id = c.id "
        "JOIN catalyst_source s ON s.catalyst_id = c.id AND s.source_url IS NOT NULL "
        "WHERE c.status = 'resolved' "
        "ORDER BY CASE WHEN c.catalyst_type IN ('pdufa','trial_readout') THEN 0 ELSE 1 END, c.id"
    ).fetchall()


def _tier(ctype: str) -> str:
    return "core" if ctype in _CORE_TYPES else ctype


def _sonnet_complete(prompt: str) -> str:
    """The live Sonnet seam (only reached under --run, never in tests/dry-run). Returns the raw JSON
    text extract_record parses. Follows desk/runtime.py's single-SDK-seam pattern."""
    import asyncio

    from claude_agent_sdk import ClaudeAgentOptions, query

    async def _go() -> str:
        opts = ClaudeAgentOptions(model="sonnet", allowed_tools=[])
        result = None
        async for message in query(prompt=prompt, options=opts):
            if getattr(message, "result", None) is not None:
                result = message.result
        if result is None:
            raise ValueError("build_playbooks: Sonnet produced no result message")
        return result

    return asyncio.run(_go())


def _dry_run(conn) -> dict:
    cands = _candidates(conn)
    counts: dict[str, int] = {}
    for r in cands:
        counts[_tier(r["catalyst_type"])] = counts.get(_tier(r["catalyst_type"]), 0) + 1
    n = len(cands)
    core = counts.get("core", 0)
    earnings = counts.get("earnings", 0)
    est_in = n * _EST_INPUT_PER
    est_out = n * _EST_OUTPUT_PER
    print("=== build_playbooks DRY-RUN (no LLM, no network, no spend) ===", flush=True)
    print(f"would process {n} peer catalysts: {core} binary CORE (pdufa+trial_readout) + "
          f"{earnings} EARNINGS tier", flush=True)
    for tier, c in sorted(counts.items(), key=lambda kv: (-kv[1])):
        print(f"  tier {tier}: {c}", flush=True)
    print(f"est. Sonnet tokens: ~{est_in:,} in + ~{est_out:,} out  (~$7 one-time, cached taxonomy)",
          flush=True)
    print("re-run with --run to populate (idempotent; safe to resume).", flush=True)
    return {"total": n, "core": core, "earnings": earnings}


def _live_run(conn, complete_fn) -> dict:
    embed = kb.default_embedder()  # local_embed when fastembed present; CT_EMBEDDER unset
    cands = _candidates(conn)
    processed = skipped = flagged = 0
    reasons: dict[str, int] = {}
    for i, r in enumerate(cands, 1):
        cid = r["id"]
        bundle = build_bundle(conn, cid)
        if bundle is None:
            skipped += 1
            reasons["no_bundle"] = reasons.get("no_bundle", 0) + 1
            continue
        record = extract_record(bundle, complete_fn)
        if record is None:  # naked: no exhibit AND no ctgov AND no move
            skipped += 1
            reasons["naked"] = reasons.get("naked", 0) + 1
            continue
        insert_catalyst_record(conn, record, embed)
        processed += 1
        if record.move_consistency_flag:
            flagged += 1
        if i % 25 == 0:
            print(f"[{i}/{len(cands)}] processed={processed} skipped={skipped} flagged={flagged}",
                  flush=True)
    # Closing step (Plan 05): graduate recurring per-catalyst lesson_rules into cited per-scenario
    # playbook nodes — the desk's query_playbooks heuristics. Runs after populate, same --run pass.
    n_scenarios = generalize_playbooks(conn)
    by_type: dict[str, int] = {}
    for row in conn.execute(
        "SELECT json_extract(attrs_json,'$.scenario_type') AS st FROM kb_node WHERE kind='playbook' "
        "AND json_extract(attrs_json,'$.scenario_type') NOT LIKE 'fitted_params:%'"
    ).fetchall():
        t = (row["st"] or "").split(":", 1)[0]
        by_type[t] = by_type.get(t, 0) + 1
    print("=== build_playbooks RUN DONE ===", flush=True)
    print(f"processed={processed}  skipped={skipped} {reasons}  move_consistency_flagged={flagged}",
          flush=True)
    print(f"generalized {n_scenarios} scenario playbooks this run  (by type: {by_type})", flush=True)
    return {"processed": processed, "skipped": skipped, "reasons": reasons, "flagged": flagged,
            "scenarios": n_scenarios}


def main(argv=None, *, complete_fn=None, conn=None) -> dict:
    ap = argparse.ArgumentParser(description="One-time warm-playbook populate (dry-run by default).")
    ap.add_argument("--run", action="store_true",
                    help="Do the LIVE Sonnet populate (spends ~$7). Omit for an offline dry-run.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Explicit offline dry-run (the default; accepted for clarity).")
    ap.add_argument("--db", default=DB)
    args = ap.parse_args(argv)

    own = conn is None
    if conn is None:
        conn = sqlite3.connect(args.db)
        conn.row_factory = sqlite3.Row
    try:
        if not args.run:
            return _dry_run(conn)
        return _live_run(conn, complete_fn or _sonnet_complete)
    finally:
        if own:
            conn.close()


if __name__ == "__main__":
    main()
