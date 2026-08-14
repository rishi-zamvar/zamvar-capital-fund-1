"""Ad-hoc catalyst injection + manual verify ops.

A user-injected catalyst is a *lead*, not a green light: it enters the exact same
insert_catalyst -> verify pipeline as the automated feeds, starts UNVERIFIED with
a single source, and cannot become tradeable until a second (ideally primary)
source corroborates it. There is no separate write path for user dates.

    python -m catalyst_trader.cli inject --ticker XYZ --type pdufa --date 2026-11-30 \
        --source-url https://ir.example.com/pr [--window-end 2026-12] [--source-name "user"]
    python -m catalyst_trader.cli verify --id 7
"""

import argparse
import sqlite3
from datetime import datetime, timezone

from catalyst_trader import db as _db
from catalyst_trader import store
from catalyst_trader.calendar import verify
from catalyst_trader.dates import classify, parse_precision
from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    DateType,
    SourceOrigin,
    SourceType,
    Status,
)

TYPES = [t.value for t in CatalystType]


def inject(
    conn: sqlite3.Connection,
    ticker: str,
    catalyst_type: str,
    date: str,
    source_url: str,
    window_end: str | None = None,
    source_name: str = "user",
) -> int:
    """Persist an ad-hoc user catalyst through the standard pipeline; return its id.

    date_precision is derived from the raw string (parse_precision RAISES on a
    malformed date rather than fabricating one). The single source is 'secondary'
    with the documented default date_type='estimated' (a user lead is an
    unconfirmed target, not a realized actual).
    """
    now = datetime.now(timezone.utc).isoformat()
    precision = parse_precision(date)  # raises ValueError on a bad date -> no fabrication
    source = CatalystSource(
        source_name=source_name,
        source_url=source_url,
        source_type=SourceType.secondary,
        reported_date=date,
        date_type=DateType.estimated,
        retrieved_at=now,
    )
    catalyst = Catalyst(
        ticker=ticker,
        catalyst_type=CatalystType(catalyst_type),
        event_date=date,
        event_date_end=window_end,
        date_precision=precision,
        uncertainty_type=classify(date, DateType.estimated.value, source_count=1, has_primary=False),
        status=Status.unverified,
        source_origin=SourceOrigin.ad_hoc_user,
        sources=[source],
    )
    return store.insert_catalyst(conn, catalyst)


def _open() -> sqlite3.Connection:
    conn = _db.connect()
    _db.migrate(conn)
    return conn


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="catalyst_trader.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    inj = sub.add_parser("inject", help="inject an ad-hoc catalyst (starts unverified)")
    inj.add_argument("--ticker", required=True)
    inj.add_argument("--type", dest="catalyst_type", required=True, choices=TYPES)
    inj.add_argument("--date", required=True, help="YYYY, YYYY-MM, or YYYY-MM-DD (never coerced)")
    inj.add_argument("--window-end", dest="window_end", default=None)
    inj.add_argument("--source-url", dest="source_url", required=True)
    inj.add_argument("--source-name", dest="source_name", default="user")

    ver = sub.add_parser("verify", help="re-run the two-source verify on a catalyst id")
    ver.add_argument("--id", dest="catalyst_id", type=int, required=True)

    args = parser.parse_args(argv)
    conn = _open()
    try:
        if args.command == "inject":
            cid = inject(
                conn,
                ticker=args.ticker,
                catalyst_type=args.catalyst_type,
                date=args.date,
                source_url=args.source_url,
                window_end=args.window_end,
                source_name=args.source_name,
            )
            c = store.get_catalyst(conn, cid)
            print(f"injected catalyst id={cid} status={c.status.value} (needs a 2nd source to trade)")
        elif args.command == "verify":
            status = verify.verify_catalyst(conn, args.catalyst_id)
            print(f"catalyst id={args.catalyst_id} status={status.value}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
