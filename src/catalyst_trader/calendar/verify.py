"""Two-source verification rule + uncertainty re-derivation + curated PDUFA loader.

The tradeable gate lives here as ONE predicate. A catalyst is verified (and thus
tradeable) iff it has >=2 agreeing source rows with at least one primary source.
Uncertainty is never a judgement call: verify re-derives it via ``classify()``
from the most-authoritative (primary-preferred) source row's persisted
``date_type`` — it reads the source's own ESTIMATED/ACTUAL precision, never guesses.

Freshness / near-event exclusion (the 48h re-verify) is layered on in Plan 05;
this module leaves a documented ``now`` hook but does not implement that logic.
"""

import csv
import sqlite3
from datetime import datetime, timezone

from catalyst_trader import store
from catalyst_trader.dates import classify, parse_precision
from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    DateType,
    SourceOrigin,
    SourceType,
    Status,
    Uncertainty,
)


def is_tradeable(catalyst: Catalyst) -> bool:
    """The single tradeable gate — do not scatter this check across callers."""
    return catalyst.status == Status.verified


def verify_catalyst(conn: sqlite3.Connection, catalyst_id: int, now: str | None = None) -> Status:
    """Re-apply the two-source rule + re-derive uncertainty; persist and return status.

    ``now`` is a documented hook for Plan 05's freshness / near-event exclusion —
    unused here (near-event staleness logic belongs to the daily refresh).
    """
    catalyst = store.get_catalyst(conn, catalyst_id)
    if catalyst is None:
        raise ValueError(f"no catalyst with id {catalyst_id}")

    agreeing = [s for s in catalyst.sources if s.agrees]
    has_primary = any(s.source_type == SourceType.primary for s in agreeing)

    # Most-authoritative source: prefer a primary agreeing row, else the first agreeing row.
    # We read ITS persisted date_type — never guess ESTIMATED vs ACTUAL.
    authoritative = next(
        (s for s in agreeing if s.source_type == SourceType.primary),
        agreeing[0] if agreeing else None,
    )
    date_type = authoritative.date_type.value if authoritative else DateType.estimated.value

    uncertainty = classify(
        catalyst.event_date, date_type, source_count=len(agreeing), has_primary=has_primary
    )

    verified = len(agreeing) >= 2 and has_primary
    if verified:
        new_status = Status.verified
    elif catalyst.status in (Status.unverified, Status.verified):
        new_status = Status.unverified  # downgrade a formerly-verified catalyst that lost corroboration
    else:
        new_status = catalyst.status  # never resurrect an excluded/resolved catalyst

    conn.execute(
        "UPDATE catalyst SET status=?, uncertainty_type=?, updated_at=? WHERE id=?",
        (new_status.value, uncertainty.value, now or datetime.now(timezone.utc).isoformat(), catalyst_id),
    )
    conn.commit()
    return new_status


def load_curated_pdufa(conn: sqlite3.Connection, csv_path: str) -> list[int]:
    """Load the hand-curated PDUFA/AdCom CSV into the catalyst table via the same
    atomic write-path. Each row -> one catalyst (source_origin='curated_pdufa') with
    ONE source, starting unverified — a hand-typed date needs a 2nd source to trade.

    CSV columns: ticker,catalyst_type,event_date,source_name,source_url,source_type
    Blank lines and '#'-comment lines are ignored (template placeholders).
    """
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        ln
        for ln in open(csv_path, encoding="utf-8").read().splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    ids: list[int] = []
    for row in csv.DictReader(lines):
        event_date = row["event_date"].strip()
        source_type = SourceType(row["source_type"].strip())
        # DATA-04 documented default: a PDUFA/AdCom date is an announced target, not a
        # realized event, so the source's date_type is 'estimated' ('actual' is reserved
        # for confirmed-realized sources).
        source = CatalystSource(
            source_name=row["source_name"].strip(),
            source_url=row["source_url"].strip() or None,
            source_type=source_type,
            reported_date=event_date,
            date_type=DateType.estimated,
            retrieved_at=now,
        )
        catalyst = Catalyst(
            ticker=row["ticker"].strip(),
            catalyst_type=CatalystType(row["catalyst_type"].strip()),
            event_date=event_date,
            date_precision=parse_precision(event_date),
            uncertainty_type=classify(
                event_date, DateType.estimated.value, source_count=1,
                has_primary=(source_type == SourceType.primary),
            ),
            source_origin=SourceOrigin.curated_pdufa,
            status=Status.unverified,
            sources=[source],
        )
        ids.append(store.insert_catalyst(conn, catalyst))
    return ids
