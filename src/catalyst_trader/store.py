"""Atomic persistence write-path for catalysts.

The invariant this module enforces: a catalyst row and its source row(s) are
written in ONE transaction, or not at all. There is no code path that writes a
date without provenance — an empty-sources catalyst is rejected before any row
is written, and a mid-insert source failure rolls the whole thing back.
"""

import sqlite3
from datetime import datetime, timezone
from enum import Enum

from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    Status,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _v(x):
    """Coerce enums to their string value; pass through everything else.

    Defensive at the DB trust boundary — accepts both enum instances and the
    plain strings a model_construct bypass might carry, so a bad value reaches
    the SQLite CHECK constraint rather than silently corrupting a money-path row.
    """
    return x.value if isinstance(x, Enum) else x


_CAT_COLS = (
    "ticker",
    "company_name",
    "catalyst_type",
    "event_date",
    "event_date_end",
    "date_precision",
    "uncertainty_type",
    "status",
    "source_origin",
    "last_verified_at",
    "external_ref",
)


def _insert_sources(conn: sqlite3.Connection, catalyst_id: int, sources: list[CatalystSource]) -> None:
    for s in sources:
        conn.execute(
            "INSERT INTO catalyst_source "
            "(catalyst_id, source_name, source_url, source_type, reported_date, "
            " date_type, agrees, retrieved_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                catalyst_id,
                _v(s.source_name),
                _v(s.source_url),
                _v(s.source_type),
                _v(s.reported_date),
                _v(s.date_type),
                1 if s.agrees else 0,
                _v(s.retrieved_at),
            ),
        )


def insert_catalyst(conn: sqlite3.Connection, catalyst: Catalyst) -> int:
    """Insert a catalyst + its source rows atomically; return the catalyst id.

    Rejects a catalyst with zero sources (no date without provenance). If a row
    with the same (ticker, external_ref) already exists, updates it in place and
    replaces its source rows (idempotent re-fetch) rather than duplicating.
    """
    if not catalyst.sources:
        raise ValueError("cannot persist a catalyst without a source row (no LLM-sourced dates)")

    now = _now()
    try:
        existing = None
        if catalyst.external_ref:
            existing = conn.execute(
                "SELECT id FROM catalyst WHERE ticker=? AND external_ref=?",
                (catalyst.ticker, catalyst.external_ref),
            ).fetchone()

        if existing is not None:
            cid = existing["id"]
            conn.execute(
                "UPDATE catalyst SET "
                "company_name=?, catalyst_type=?, event_date=?, event_date_end=?, "
                "date_precision=?, uncertainty_type=?, status=?, source_origin=?, "
                "last_verified_at=?, updated_at=? WHERE id=?",
                (
                    _v(catalyst.company_name),
                    _v(catalyst.catalyst_type),
                    _v(catalyst.event_date),
                    _v(catalyst.event_date_end),
                    _v(catalyst.date_precision),
                    _v(catalyst.uncertainty_type),
                    _v(catalyst.status),
                    _v(catalyst.source_origin),
                    _v(catalyst.last_verified_at),
                    now,
                    cid,
                ),
            )
            # ponytail: replace sources on re-fetch; corroborating sources are added
            # via a separate path (Plan 05 refresh), not by re-inserting the same ref.
            conn.execute("DELETE FROM catalyst_source WHERE catalyst_id=?", (cid,))
            _insert_sources(conn, cid, catalyst.sources)
        else:
            cur = conn.execute(
                f"INSERT INTO catalyst ({', '.join(_CAT_COLS)}, created_at, updated_at) "
                f"VALUES ({', '.join('?' * len(_CAT_COLS))}, ?, ?)",
                tuple(_v(getattr(catalyst, c)) for c in _CAT_COLS) + (now, now),
            )
            cid = cur.lastrowid
            _insert_sources(conn, cid, catalyst.sources)

        conn.commit()
        return cid
    except Exception:
        conn.rollback()
        raise


def _hydrate(conn: sqlite3.Connection, row: sqlite3.Row) -> Catalyst:
    src_rows = conn.execute(
        "SELECT * FROM catalyst_source WHERE catalyst_id=? ORDER BY id", (row["id"],)
    ).fetchall()
    sources = [
        CatalystSource(
            source_name=s["source_name"],
            source_url=s["source_url"],
            source_type=s["source_type"],
            reported_date=s["reported_date"],
            date_type=s["date_type"],
            agrees=bool(s["agrees"]),
            retrieved_at=s["retrieved_at"],
        )
        for s in src_rows
    ]
    return Catalyst(
        ticker=row["ticker"],
        company_name=row["company_name"],
        catalyst_type=row["catalyst_type"],
        event_date=row["event_date"],
        event_date_end=row["event_date_end"],
        date_precision=row["date_precision"],
        uncertainty_type=row["uncertainty_type"],
        status=row["status"],
        source_origin=row["source_origin"],
        last_verified_at=row["last_verified_at"],
        external_ref=row["external_ref"],
        sources=sources,
    )


def get_catalyst(conn: sqlite3.Connection, catalyst_id: int) -> Catalyst | None:
    row = conn.execute("SELECT * FROM catalyst WHERE id=?", (catalyst_id,)).fetchone()
    return _hydrate(conn, row) if row is not None else None


def tradeable_catalysts(conn: sqlite3.Connection) -> list[Catalyst]:
    """The ONLY tradeable gate at the query layer: status='verified'."""
    rows = conn.execute(
        "SELECT * FROM catalyst WHERE status=? ORDER BY id", (Status.verified.value,)
    ).fetchall()
    return [_hydrate(conn, r) for r in rows]


# --- price bars (WEEK-02) --------------------------------------------------------------------
# The GATING weekly-OHLCV substrate. Survivorship-free (delisted names + XBI retained) and read
# point-in-time via bars_asof. Storage only — no money math, no literals leak into base rates.


def upsert_bars(
    conn: sqlite3.Connection,
    ticker: str,
    bars: list[dict],
    *,
    delisted: bool = False,
    source: str = "fixture",
) -> int:
    """UPSERT weekly OHLCV bars for one ticker; return the count written.

    Each dict = {"week_end","open","high","low","close","volume"}. Idempotent on
    (ticker, week_end): an existing week is UPDATED in place, never duplicated (mirrors
    insert_catalyst). Atomic — the whole batch commits or rolls back. XBI is just another
    ticker; delisted names are retained (survivorship-free).
    """
    now = _now()
    d = 1 if delisted else 0
    try:
        for b in bars:
            existing = conn.execute(
                "SELECT id FROM price_bar WHERE ticker=? AND week_end=?",
                (ticker, b["week_end"]),
            ).fetchone()
            if existing is not None:
                conn.execute(
                    "UPDATE price_bar SET open=?, high=?, low=?, close=?, volume=?, "
                    "delisted=?, source=?, retrieved_at=? WHERE id=?",
                    (b.get("open"), b.get("high"), b.get("low"), b["close"],
                     b.get("volume"), d, source, now, existing["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO price_bar "
                    "(ticker, week_end, open, high, low, close, volume, delisted, source, retrieved_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (ticker, b["week_end"], b.get("open"), b.get("high"), b.get("low"),
                     b["close"], b.get("volume"), d, source, now),
                )
        conn.commit()
        return len(bars)
    except Exception:
        conn.rollback()
        raise


def bars_asof(
    conn: sqlite3.Connection,
    ticker: str,
    as_of: str,
    *,
    lookback_weeks: int | None = None,
) -> list[dict]:
    """Point-in-time weekly OHLCV read: bars for `ticker` with week_end <= `as_of`, chronological.

    The `week_end <= as_of` guard is the money-critical no-look-ahead invariant — mirrors
    universe.build.universe_as_of's "never a future cohort". A base rate must never see a bar
    that hadn't happened yet at decision time. `lookback_weeks` keeps only the most recent N
    bars at/<= as_of. Delisted history is retained (survivorship-free).
    """
    rows = conn.execute(
        "SELECT week_end, open, high, low, close, volume, delisted FROM price_bar "
        "WHERE ticker=? AND week_end <= ? ORDER BY week_end",
        (ticker, as_of),
    ).fetchall()
    out = [
        {"week_end": r["week_end"], "open": r["open"], "high": r["high"], "low": r["low"],
         "close": r["close"], "volume": r["volume"], "delisted": bool(r["delisted"])}
        for r in rows
    ]
    if lookback_weeks is not None:
        out = out[-lookback_weeks:]
    return out
