"""Atomic persistence write-path for catalysts.

The invariant this module enforces: a catalyst row and its source row(s) are
written in ONE transaction, or not at all. There is no code path that writes a
date without provenance — an empty-sources catalyst is rejected before any row
is written, and a mid-insert source failure rolls the whole thing back.
"""

import json
import sqlite3
from enum import Enum
from typing import NamedTuple

from catalyst_trader.dates import now_iso
from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    Status,
)


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


def _latest_version(conn: sqlite3.Connection, catalyst_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT event_date, event_date_end FROM catalyst_version WHERE catalyst_id=? "
        "ORDER BY recorded_at DESC, id DESC LIMIT 1",
        (catalyst_id,),
    ).fetchone()


def _append_version(conn: sqlite3.Connection, catalyst_id: int, catalyst: Catalyst, now: str) -> None:
    # The version's KNOWABLE time (transaction-time the gateway gates on) is when the date became
    # available to us = its verification/announcement stamp (last_verified_at), NOT the ingest
    # wall-clock. This is critical for HISTORICAL backfill: a 2026-01 catalyst ingested today must
    # be knowable from its 2026-01 announcement, not from `now`. Falls back to now when unstamped
    # (a live discovery with no explicit verification date). Makes the bitemporal gate equivalent
    # to the shipped last_verified_at<=cutoff filter — behaviour-preserving across every path.
    knowable = _v(catalyst.last_verified_at) or now
    conn.execute(
        "INSERT INTO catalyst_version (catalyst_id, event_date, event_date_end, recorded_at) "
        "VALUES (?,?,?,?)",
        (catalyst_id, _v(catalyst.event_date), _v(catalyst.event_date_end), knowable),
    )


def catalyst_version_asof(conn: sqlite3.Connection, catalyst_id: int, cutoff: str) -> dict | None:
    """The event_date/event_date_end knowable at `cutoff`: the LATEST catalyst_version row with
    recorded_at <= cutoff, or None if no version was recorded yet at that cutoff.

    Append-never-overwrite as-of: a replay before an amendment returns the OLD date, after the
    amendment returns the NEW one. The gateway (serving.py) reads this instead of the raw
    event_date column so an amended PDUFA date never leaks into a pre-amendment backtest week.
    """
    row = conn.execute(
        "SELECT event_date, event_date_end, recorded_at FROM catalyst_version "
        "WHERE catalyst_id=? AND recorded_at <= ? ORDER BY recorded_at DESC, id DESC LIMIT 1",
        (catalyst_id, cutoff),
    ).fetchone()
    return dict(row) if row is not None else None


def insert_catalyst(conn: sqlite3.Connection, catalyst: Catalyst) -> int:
    """Insert a catalyst + its source rows atomically; return the catalyst id.

    Rejects a catalyst with zero sources (no date without provenance). If a row with the same
    (ticker, external_ref) already exists, updates the materialized row in place and replaces its
    source rows (idempotent re-fetch). An amended event_date/event_date_end additionally APPENDS a
    catalyst_version row (append-never-overwrite); an unchanged re-fetch appends no version.

    # ponytail: the main catalyst row is the LATEST-version live-view cache (existing readers
    # unaffected); catalyst_version is the append-only replay source of truth for the gateway.
    """
    if not catalyst.sources:
        raise ValueError("cannot persist a catalyst without a source row (no LLM-sourced dates)")

    now = now_iso()
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
            # append-never-overwrite: only a CHANGED (event_date, event_date_end) appends a
            # version (idempotent on an unchanged re-fetch — the main-row refresh still runs).
            prev = _latest_version(conn, cid)
            changed = prev is None or (
                prev["event_date"] != _v(catalyst.event_date)
                or prev["event_date_end"] != _v(catalyst.event_date_end)
            )
            if changed:
                _append_version(conn, cid, catalyst, now)
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
            _append_version(conn, cid, catalyst, now)  # version-1 for a brand-new catalyst
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


class CatalystLite(NamedTuple):
    """The subset of a verified catalyst the news/hold-window/event-set callers read — no sources."""

    ticker: str
    event_date: str
    catalyst_type: CatalystType
    last_verified_at: str | None


def tradeable_catalysts_light(conn: sqlite3.Connection) -> list[CatalystLite]:
    """Same status='verified' gate as ``tradeable_catalysts`` but WITHOUT hydrating each row's
    provenance sources — for callers that only need (ticker, event_date, catalyst_type,
    last_verified_at). Avoids the per-row catalyst_source subquery (the N+1)."""
    rows = conn.execute(
        "SELECT ticker, event_date, catalyst_type, last_verified_at "
        "FROM catalyst WHERE status=? ORDER BY id",
        (Status.verified.value,),
    ).fetchall()
    return [
        CatalystLite(
            ticker=r["ticker"],
            event_date=r["event_date"],
            catalyst_type=CatalystType(r["catalyst_type"]),
            last_verified_at=r["last_verified_at"],
        )
        for r in rows
    ]


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
    source_grade: str | None = None,
    agreeing_sources: str | None = None,
) -> int:
    """UPSERT weekly OHLCV bars for one ticker; return the count written.

    Each dict = {"week_end","open","high","low","close","volume"}. Idempotent on
    (ticker, week_end): an existing week is UPDATED in place, never duplicated (mirrors
    insert_catalyst). Atomic — the whole batch commits or rolls back. XBI is just another
    ticker; delisted names are retained (survivorship-free).

    `source_grade` ('green'|'yellow') + `agreeing_sources` (comma-joined cross-check set) are
    OPTIONAL columnar provenance from the multi-source cascade (INGEST-01/04). Both default None
    so every existing source='fixture' caller keeps working; the natural key is unchanged.
    """
    now = now_iso()
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
                    "delisted=?, source=?, retrieved_at=?, source_grade=?, agreeing_sources=? "
                    "WHERE id=?",
                    (b.get("open"), b.get("high"), b.get("low"), b["close"],
                     b.get("volume"), d, source, now, source_grade, agreeing_sources,
                     existing["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO price_bar "
                    "(ticker, week_end, open, high, low, close, volume, delisted, source, "
                    "retrieved_at, source_grade, agreeing_sources) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (ticker, b["week_end"], b.get("open"), b.get("high"), b.get("low"),
                     b["close"], b.get("volume"), d, source, now, source_grade,
                     agreeing_sources),
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


# --- company cards + scan-flag ledger (SCAN-01/02) ------------------------------------------
# The per-company weekly vetting card substrate + the scan-flag audit ledger. Mirrors the
# price-bar store verbatim: write-once per (ticker, week_end), read point-in-time via card_asof
# / scan_flags_asof with the week_end <= as_of no-look-ahead guard. card/payload are single JSON
# TEXT columns (ponytail: no per-metric columns until a query needs them).


def write_card(
    conn: sqlite3.Connection,
    ticker: str,
    week_end: str,
    card: dict,
    *,
    source: str = "fixture",
) -> int:
    """UPSERT one company card; return its row id. Idempotent on (ticker, week_end): an
    existing week is UPDATED in place, never duplicated (mirrors upsert_bars). The card dict is
    json.dumps'd into the single `card` TEXT column and round-trips losslessly."""
    now = now_iso()
    payload = json.dumps(card)
    try:
        existing = conn.execute(
            "SELECT id FROM company_card WHERE ticker=? AND week_end=?",
            (ticker, week_end),
        ).fetchone()
        if existing is not None:
            conn.execute(
                "UPDATE company_card SET card=?, source=?, retrieved_at=? WHERE id=?",
                (payload, source, now, existing["id"]),
            )
            row_id = existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO company_card (ticker, week_end, card, source, retrieved_at) "
                "VALUES (?,?,?,?,?)",
                (ticker, week_end, payload, source, now),
            )
            row_id = cur.lastrowid
        conn.commit()
        return row_id
    except Exception:
        conn.rollback()
        raise


def card_asof(conn: sqlite3.Connection, ticker: str, as_of: str) -> dict | None:
    """Point-in-time company-card read: the SINGLE latest card for `ticker` with
    week_end <= `as_of`, or None. The `week_end <= as_of` guard is the money-critical
    no-look-ahead invariant (mirrors bars_asof) — the scanner must never read a card that
    hadn't been built yet at decision time."""
    row = conn.execute(
        "SELECT card FROM company_card WHERE ticker=? AND week_end <= ? "
        "ORDER BY week_end DESC LIMIT 1",
        (ticker, as_of),
    ).fetchone()
    return json.loads(row["card"]) if row is not None else None


def write_scan_flag(
    conn: sqlite3.Connection,
    ticker: str,
    week_end: str,
    payload: dict,
    *,
    routed: bool = False,
) -> int:
    """UPSERT one scan-flag payload (an OpportunityFlag dump or a no-opportunity row); return
    its row id. Idempotent on (ticker, week_end) (mirrors write_card). `routed` is stored 1/0."""
    blob = json.dumps(payload)
    r = 1 if routed else 0
    now = now_iso()  # transaction-time stamp the gateway gates on (scan_flag knowable=recorded_at)
    try:
        existing = conn.execute(
            "SELECT id FROM scan_flag WHERE ticker=? AND week_end=?",
            (ticker, week_end),
        ).fetchone()
        if existing is not None:
            conn.execute(
                "UPDATE scan_flag SET payload=?, routed=?, recorded_at=? WHERE id=?",
                (blob, r, now, existing["id"]),
            )
            row_id = existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO scan_flag (ticker, week_end, payload, routed, recorded_at) "
                "VALUES (?,?,?,?,?)",
                (ticker, week_end, blob, r, now),
            )
            row_id = cur.lastrowid
        conn.commit()
        return row_id
    except Exception:
        conn.rollback()
        raise


def scan_flags_asof(conn: sqlite3.Connection, ticker: str, as_of: str) -> list[dict]:
    """Point-in-time scan-flag ledger read: stored payloads for `ticker` with
    week_end <= `as_of`, chronological. The `week_end <= as_of` guard is the same
    no-look-ahead invariant as card_asof/bars_asof."""
    rows = conn.execute(
        "SELECT payload FROM scan_flag WHERE ticker=? AND week_end <= ? ORDER BY week_end",
        (ticker, as_of),
    ).fetchall()
    return [json.loads(r["payload"]) for r in rows]
