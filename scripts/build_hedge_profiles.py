"""Populate + recompute hedge profiles for the universe (HEDGE-CORR-1d).

For every real universe ticker (DISTINCT from catalyst kb_nodes), compute its explicit hedge_profile
via quant.correlations.compute_hedge_profile and stamp it onto the company node via
kb.stamp_hedge_profile. The desk calls this to (re)build profiles on demand.

Frugality (CLAUDE.md): the ONLY external call is a SINGLE Friday-anchored XBI re-pull
(providers.prices.get_weekly_bars('XBI', ...)) — needed because XBI in price_bar is Monday-anchored
(mixed rows) and would mis-align against the Friday universe. Everything else reads cached price_bar.

  --dry-run   print the ticker universe + the compute/stamp plan and EXPLICITLY name that one XBI
              network call. Reads the DB to enumerate; writes NOTHING and touches NO network.
  --self-check  offline assert against an in-memory seeded DB (no network) — the ponytail one-check.

DO NOT run without --dry-run unless you intend the live XBI pull + profile writes (operator step).
"""

import argparse
import sys
from datetime import date

from catalyst_trader import db as _db
from catalyst_trader import kb, store
from catalyst_trader.quant import correlations

# Synthetic fixture tickers (+ XBI itself) are NOT the real universe — excluded from the populate.
_EXCLUDE = {"XBI", "AAA", "BBB", "CCC", "DDD", "EEE", "XYZ", "ABC", "NAME", "PEER", "ACME", "RIVAL", "COMOV"}
_XBI_START = "2020-01-01"


def _xbi_end() -> str:
    return date.today().isoformat()


def universe_tickers(conn) -> list[str]:
    """Real universe tickers from catalyst kb_nodes (DISTINCT ticker), synthetic fixtures excluded."""
    rows = conn.execute(
        "SELECT DISTINCT json_extract(attrs_json,'$.ticker') FROM kb_node "
        "WHERE kind='catalyst' AND json_extract(attrs_json,'$.ticker') IS NOT NULL"
    ).fetchall()
    return sorted(t for (t,) in rows if t and t not in _EXCLUDE)


def print_plan(conn) -> list[str]:
    """Print the compute/stamp plan naming the single XBI network call. Reads only; writes nothing."""
    tickers = universe_tickers(conn)
    call = f"get_weekly_bars('XBI', '{_XBI_START}', '{_xbi_end()}')"
    print("=== build_hedge_profiles DRY RUN ===")
    print(f"universe: {len(tickers)} real tickers (synthetic fixtures excluded)")
    print("  " + ", ".join(tickers) if tickers else "  (none)")
    print("\nplan:")
    print(f"  1. ONE network call — Friday-anchored XBI re-pull: {call}")
    print("     (clean-overwrite XBI's Monday-anchored price_bar rows; the ONLY external call)")
    print("  2. for each ticker above: correlations.compute_hedge_profile(conn, ticker)  [cached price_bar only]")
    print("  3.                        kb.stamp_hedge_profile(conn, ticker, profile)      [company-node UPDATE]")
    print("\nno network touched, no DB writes made (dry run).")
    return tickers


def repull_xbi(conn) -> int:
    """THE ONE external call: re-pull XBI Friday-anchored, clean-overwrite the Monday-anchored rows."""
    from catalyst_trader.providers.prices import get_weekly_bars  # imported lazily so --dry-run is network-free

    bars = get_weekly_bars("XBI", _XBI_START, _xbi_end())
    if not bars:
        raise SystemExit("XBI re-pull returned no bars — aborting (won't stamp against a stale mixed series)")
    conn.execute("DELETE FROM price_bar WHERE ticker='XBI'")  # clean overwrite of the mixed Monday rows
    store.upsert_bars(conn, "XBI", bars, source="get_weekly_bars")
    conn.commit()
    return len(bars)


def run(conn) -> tuple[int, int]:
    """Live populate: one XBI re-pull, then compute+stamp each ticker off cached price_bar."""
    n_xbi = repull_xbi(conn)
    print(f"XBI re-pulled Friday-anchored: {n_xbi} bars (mixed rows overwritten)")
    as_of = _xbi_end()
    stamped = skipped = 0
    for tk in universe_tickers(conn):
        try:
            profile = correlations.compute_hedge_profile(conn, tk, as_of=as_of)
        except ValueError as exc:  # insufficient aligned obs -> abstain, don't stamp a bad profile
            skipped += 1
            print(f"  {tk}: SKIP ({exc})")
            continue
        kb.stamp_hedge_profile(conn, tk, profile)
        stamped += 1
        print(f"  {tk}: stamped (xbi {profile['xbi']['full']['verdict']}, {len(profile['peers'])} peers)")
    print(f"\ndone: {stamped} stamped, {skipped} skipped")
    return stamped, skipped


def _self_check() -> None:
    """Offline assert: seed an in-memory DB, verify universe filtering + compute+stamp round-trip.
    No live network (never calls repull_xbi)."""
    import json

    from catalyst_trader.dates import now_iso

    conn = _db.connect(":memory:")
    _db.migrate(conn)

    from datetime import timedelta
    d0 = date.fromisoformat("2025-01-03")  # a Friday

    def seed_series(tk, closes):
        bars = [{"week_end": (d0 + timedelta(weeks=i)).isoformat(), "close": c} for i, c in enumerate(closes)]
        store.upsert_bars(conn, tk, bars)

    def seed_cat(tk, disease=None):
        attrs = {"type": "pdufa", "ticker": tk}
        if disease:
            attrs["disease_area"] = disease
        conn.execute("INSERT INTO kb_node (kind, ref_id, attrs_json, confidence, created_at) "
                     "VALUES ('catalyst', NULL, ?, NULL, ?)", (json.dumps(attrs), now_iso()))
        conn.commit()

    closes = [100.0 + 0.7 * i + (i % 3) for i in range(30)]
    seed_series("REAL", closes)
    seed_series("XBI", [50.0 + 0.3 * i + (i % 2) for i in range(30)])
    seed_series("AAA", closes)  # synthetic — must be filtered out of the universe
    seed_cat("REAL", disease="oncology")
    seed_cat("AAA", disease="oncology")

    assert universe_tickers(conn) == ["REAL"], universe_tickers(conn)  # synthetic AAA excluded

    prof = correlations.compute_hedge_profile(conn, "REAL", as_of="2025-08-01")
    kb.stamp_hedge_profile(conn, "REAL", prof)
    assert kb.hedge_profile(conn, "REAL") == prof  # round-trips byte-identical

    # dry-run prints the XBI call and writes nothing
    before = conn.execute("SELECT count(*) FROM kb_node WHERE kind='company'").fetchone()[0]
    print_plan(conn)
    after = conn.execute("SELECT count(*) FROM kb_node WHERE kind='company'").fetchone()[0]
    assert before == after, "dry-run must not write"
    conn.close()
    print("SELF-CHECK OK")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Populate/recompute universe hedge profiles (HEDGE-CORR-1d).")
    ap.add_argument("--dry-run", action="store_true", help="print the plan; no network, no writes")
    ap.add_argument("--self-check", action="store_true", help="offline in-memory assert (no network)")
    args = ap.parse_args(argv)

    if args.self_check:
        _self_check()
        return
    conn = _db.connect()
    try:
        if args.dry_run:
            print_plan(conn)
        else:
            run(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
