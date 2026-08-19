"""Idempotent daily refresh — the single entrypoint launchd runs (DATA-01/03/05).

One call re-fetches every provider, merges the curated PDUFA table, re-runs the
two-source verify across all active catalysts (restamping ``last_verified_at`` on
those that stay verified), excludes anything that goes stale near its event, and
fires the T-2 trigger seam. Running it twice produces the same state — providers
dedup by ``external_ref`` and the curated loader carries a deterministic ref.

Graceful degrade: CT.gov and the curated table always run; FMP is skipped (with a
warning) when its key is absent or the call fails, so a missing key never crashes
the daily job. Run it with ``python -m catalyst_trader.calendar.refresh``.
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from catalyst_trader import db as _db
from catalyst_trader import store
from catalyst_trader.calendar import triggers, verify
from catalyst_trader.config import settings
from catalyst_trader.models import Status
from catalyst_trader.providers import clinicaltrials, fmp

logger = logging.getLogger(__name__)

# How far forward to pull catalysts each run. Holds are one week and the trigger
# window is 1-2 days, so a ~6-month horizon comfortably covers the rolling calendar.
REFRESH_HORIZON_DAYS = 180

_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
_ACTIVE = (Status.unverified.value, Status.verified.value)


def refresh(
    conn,
    tickers,
    now=None,
    *,
    fmp_enabled=None,
    pdufa_csv=None,
    ct_fetch=clinicaltrials.fetch_trial_readouts,
    fmp_fetch=fmp.fetch_earnings,
    client=None,
):
    """Run the full daily pipeline once. Returns a summary dict of counts.

    Providers default to the real clients but are injectable for tests. ``now`` is
    a datetime (defaults to UTC now); all downstream time logic derives from it.
    """
    now = now or datetime.now(timezone.utc)
    today = now.date()
    date_from = today.isoformat()
    date_to = (today + timedelta(days=REFRESH_HORIZON_DAYS)).isoformat()

    # (1) ClinicalTrials.gov — always. (2) FMP — only with a key, degrade otherwise.
    fetched = list(ct_fetch(tickers, date_from, date_to, client=client))

    if fmp_enabled is None:
        fmp_enabled = settings.fmp_api_key is not None
    if fmp_enabled:
        try:
            fetched += fmp_fetch(tickers, date_from, date_to, client=client)
        except Exception as exc:  # any single provider slot degrades-to-empty, never crashes the cycle
            logger.warning("FMP unavailable (%s) — continuing with CT.gov + curated", exc)
    else:
        logger.warning("FMP key absent — continuing with CT.gov + curated")

    # (4) upsert fetched catalysts (dedup by external_ref makes re-runs idempotent)
    for catalyst in fetched:
        store.insert_catalyst(conn, catalyst)

    # (3) curated PDUFA/AdCom table — same write-path, deterministic dedup ref
    if pdufa_csv:
        verify.load_curated_pdufa(conn, pdufa_csv)

    # (5) re-verify all active catalysts; restamp last_verified_at on the verified ones
    active = conn.execute(
        "SELECT id FROM catalyst WHERE status IN (?, ?)", _ACTIVE
    ).fetchall()
    verified = 0
    for row in active:
        if verify.verify_catalyst(conn, row["id"], now=now.isoformat()) is Status.verified:
            conn.execute(
                "UPDATE catalyst SET last_verified_at=? WHERE id=?",
                (now.isoformat(), row["id"]),
            )
            verified += 1
    conn.commit()

    # (6) exclude stale near-event dates, then (7) fire the T-2 seam
    excluded = triggers.exclude_stale(conn, now)
    fired = triggers.detect_and_fire(conn, now)

    return {
        "fetched": len(fetched),
        "verified": verified,
        "excluded": len(excluded),
        "fired": len(fired),
    }


def _load_tickers(conn):
    """Latest included universe snapshot if one exists, else the curated sponsor map."""
    rows = conn.execute(
        "SELECT DISTINCT ticker FROM universe_snapshot "
        "WHERE included=1 AND as_of_date=(SELECT max(as_of_date) FROM universe_snapshot)"
    ).fetchall()
    if rows:
        return [r["ticker"] for r in rows]
    return sorted(clinicaltrials.load_sponsor_map().keys())


def main():
    """launchd entrypoint: open+migrate the DB, load tickers, run one refresh."""
    logging.basicConfig(level=logging.INFO)
    conn = _db.connect()
    _db.migrate(conn)
    # Register the real T-2 launcher ONCE (after migrate, before any detect_and_fire): a fired T-2
    # catalyst now ENQUEUES a desk-run request for a later CC-gated desk pass. refresh() itself stays
    # pure (no register) so existing suites that call it directly are unaffected. No LLM here.
    from catalyst_trader.desk import desk_queue
    desk_queue.register(conn)
    try:
        tickers = _load_tickers(conn)
        pdufa_csv = str(_DATA_DIR / "pdufa_curated.csv")
        summary = refresh(conn, tickers, now=datetime.now(timezone.utc), pdufa_csv=pdufa_csv)
        logger.info("refresh complete: %s", summary)
        return summary
    finally:
        conn.close()


if __name__ == "__main__":
    main()
