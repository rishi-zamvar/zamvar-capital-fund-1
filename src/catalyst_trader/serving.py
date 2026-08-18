"""The MANDATORY deny-by-default serving seam (decision B, DBOOK-03/04).

Every money-path read routes through ``serving.asof(conn, cutoff)`` -> a ``Databook`` whose
accessors inject a ``knowable <= cutoff`` transaction-time filter ON TOP of the shipped valid-time
``<= as_of`` reads. Live uses ``cutoff = now`` (default); a walk-forward week W uses ``cutoff = W``
— the SAME code, so live-vs-backtest logic drift (the subtlest leak) is impossible.

Deny-by-default: a table absent from ``STAMP_REGISTRY``, or a served row whose knowable stamp is
NULL, RAISES ``LookAheadDenied`` — never a silent ``[]`` masquerading as "no data".

``STAMP_REGISTRY`` IS the encoded per-table stamp audit (07.6-CONTEXT). Plan 02 ships the mechanism
+ the ``price_bar`` accessor; Plan 03 populates the full 9-table registry + the rest of the
accessors.
"""

from __future__ import annotations

import json
import sqlite3
from typing import NamedTuple

from catalyst_trader import store
from catalyst_trader.dates import now_iso
from catalyst_trader.models import CatalystType, Status
from catalyst_trader.store import CatalystLite
from catalyst_trader.universe import build

# Sentinel knowable_expr for catalyst: there is NO single knowable COLUMN on the catalyst row —
# the knowable event_date is resolved via the append-only catalyst_version history (recorded_at).
_VERSION = "<version>"


class LookAheadDenied(Exception):
    """Raised on any deny-by-default trip: an unregistered table or a NULL knowable stamp."""


class StampSpec(NamedTuple):
    """One served table's audited stamps.

    valid_col:     the existing valid-time column the shipped read already gates on (<= as_of).
    knowable_expr: the correct transaction/knowable column the gateway ADDS a <= cutoff gate on.
    data_class:    the fill.effective_asof ingestion-lag class (None = no lag).
    """

    valid_col: str
    knowable_expr: str
    data_class: str | None = None


# The encoded per-table stamp audit (07.6-CONTEXT). One StampSpec per served table; a table
# ABSENT here is deny-by-default (e.g. the 7.5 playbook tables, not built yet).
STAMP_REGISTRY: dict[str, StampSpec] = {
    # price_bar/company_card: knowable = week_end (+lag), NEVER retrieved_at. retrieved_at is the
    # FETCH date — a 5-yr bulk backfill stamps every historical bar with today, which would deny
    # ALL history for any past cutoff (the backfill trap). A weekly bar is public ~T+0.
    "price_bar":    StampSpec(valid_col="week_end", knowable_expr="week_end", data_class="price"),
    "company_card": StampSpec(valid_col="week_end", knowable_expr="week_end", data_class="card"),
    # scan_flag/universe_snapshot: knowable = recorded_at (added in migration 011); week_end /
    # as_of_date are valid-time only and would lie about knowability on a backdated backfill.
    "scan_flag":         StampSpec(valid_col="week_end",   knowable_expr="recorded_at", data_class="scan"),
    "universe_snapshot": StampSpec(valid_col="as_of_date", knowable_expr="recorded_at", data_class=None),
    # catalyst: THE BUG. Never gate on event_date (the scheduled PDUFA/readout date). The knowable
    # event_date is resolved from the append-only catalyst_version history (latest recorded_at<=cutoff).
    "catalyst":      StampSpec(valid_col="event_date", knowable_expr=_VERSION,       data_class="catalyst"),
    # already-correct exemplars — the accessor just injects the existing knowable column:
    "catalyst_move": StampSpec(valid_col="event_date", knowable_expr="knowable_asof", data_class=None),
    "trigger_event": StampSpec(valid_col="event_date", knowable_expr="fired_at",      data_class=None),
    "kb_node":       StampSpec(valid_col="created_at", knowable_expr="created_at",     data_class=None),
    "kb_edge":       StampSpec(valid_col="created_at", knowable_expr="created_at",     data_class=None),
}


def _guard_not_null(value, table: str):
    """Deny-by-default on a NULL knowable stamp — a served row with no transaction time is a
    silent-leak risk, so it RAISES rather than being served."""
    if value is None:
        raise LookAheadDenied(f"table {table!r} row has a NULL knowable stamp — denied")
    return value


def asof(conn: sqlite3.Connection, cutoff: str | None = None, *, latency_cfg: dict | None = None) -> "Databook":
    """Return the as-of Databook for `cutoff` (None => now_iso(), the LIVE path)."""
    return Databook(conn, cutoff if cutoff is not None else now_iso(), latency_cfg)


class Databook:
    """As-of accessor: wraps the shipped store reads + injects knowable<=cutoff. Deny-by-default."""

    def __init__(self, conn: sqlite3.Connection, cutoff: str, latency_cfg: dict | None):
        self.conn = conn
        self.cutoff = cutoff
        self.latency_cfg = latency_cfg

    def _require(self, table: str) -> StampSpec:
        spec = STAMP_REGISTRY.get(table)
        if spec is None:
            raise LookAheadDenied(f"table {table!r} not registered — deny-by-default")
        return spec

    def _effective_cutoff(self, spec: StampSpec) -> str:
        # No lag class, or no cfg supplied (explicit opt-out) => the raw cutoff. Otherwise reuse
        # the shipped effective_asof (RAISES on an unconfigured class — no silent 0-lag).
        if spec.data_class is None or self.latency_cfg is None:
            return self.cutoff
        # Lazy import avoids a hard backtest dependency at module load. effective_asof wants a
        # date; a live now-timestamp cutoff is truncated to its date part before shifting.
        from catalyst_trader.backtest.fill import effective_asof

        return effective_asof(spec.data_class, self.cutoff[:10], self.latency_cfg)

    def bars(self, ticker: str, as_of: str, *, lookback_weeks: int | None = None) -> list[dict]:
        # ponytail: for a table whose knowable_expr == valid_col (price_bar: week_end), the
        # valid-time and knowable gates collapse to a single min() — no second query needed.
        spec = self._require("price_bar")
        eff = self._effective_cutoff(spec)
        return store.bars_asof(self.conn, ticker, min(as_of, eff), lookback_weeks=lookback_weeks)

    def card(self, ticker: str, as_of: str) -> dict | None:
        # company_card knowable_expr == valid_col == week_end -> gates collapse to min() (as bars).
        spec = self._require("company_card")
        eff = self._effective_cutoff(spec)
        return store.card_asof(self.conn, ticker, min(as_of, eff))

    def catalysts(self) -> list[CatalystLite]:
        # ponytail: the bitemporal replacement for events.py's ad-hoc last_verified_at post-filter.
        # Gate is the version's recorded_at (transaction time) — NEVER the raw event_date column and
        # NEVER last_verified_at (a later re-verification stamp). A catalyst whose only version was
        # recorded after the cutoff is not yet knowable -> dropped.
        spec = self._require("catalyst")
        eff = self._effective_cutoff(spec)
        # verified = live upcoming; resolved = a historical catalyst that HAS occurred. At a past
        # cutoff a now-resolved catalyst was a real known-upcoming event, so the backward/backtest
        # walk must surface it too. Safe in live: the caller's `as_of < event_date` window filters
        # already-occurred events. Knowability stays gated by the version recorded_at below.
        rows = self.conn.execute(
            "SELECT id, ticker, catalyst_type, last_verified_at FROM catalyst "
            "WHERE status IN (?, ?) ORDER BY id",
            (Status.verified.value, Status.resolved.value),
        ).fetchall()
        out: list[CatalystLite] = []
        for r in rows:
            v = store.catalyst_version_asof(self.conn, r["id"], eff)
            if v is None:  # no version knowable by the cutoff -> not yet knowable
                continue
            out.append(CatalystLite(
                ticker=r["ticker"],
                event_date=v["event_date"],  # AS-OF-resolved, not the raw materialized row
                catalyst_type=CatalystType(r["catalyst_type"]),
                last_verified_at=r["last_verified_at"],
            ))
        return out

    def scan_flags(self, ticker: str, as_of: str) -> list[dict]:
        # Two DIFFERENT columns: valid=week_end, knowable=recorded_at. Cannot collapse to min() —
        # gate week_end<=as_of AND recorded_at<=cutoff; a served row with NULL recorded_at is denied.
        spec = self._require("scan_flag")
        eff = self._effective_cutoff(spec)
        rows = self.conn.execute(
            "SELECT payload, recorded_at FROM scan_flag WHERE ticker=? AND week_end <= ? "
            "ORDER BY week_end",
            (ticker, as_of),
        ).fetchall()
        out = []
        for r in rows:
            _guard_not_null(r["recorded_at"], "scan_flag")
            if r["recorded_at"] <= eff:
                out.append(json.loads(r["payload"]))
        return out

    def universe(self, as_of: str) -> list:
        spec = self._require("universe_snapshot")
        eff = self._effective_cutoff(spec)
        # deny if the latest valid cohort has a NULL knowable stamp (leak-signal masquerading as data)
        latest_valid = self.conn.execute(
            "SELECT MAX(as_of_date) AS d FROM universe_snapshot WHERE as_of_date <= ?", (as_of,)
        ).fetchone()["d"]
        if latest_valid is not None:
            stamp = self.conn.execute(
                "SELECT recorded_at FROM universe_snapshot WHERE as_of_date=? LIMIT 1", (latest_valid,)
            ).fetchone()["recorded_at"]
            _guard_not_null(stamp, "universe_snapshot")
        # the latest cohort both valid (<=as_of) and knowable (recorded_at<=cutoff)
        knowable = self.conn.execute(
            "SELECT MAX(as_of_date) AS d FROM universe_snapshot "
            "WHERE as_of_date <= ? AND recorded_at <= ?", (as_of, eff)
        ).fetchone()["d"]
        if knowable is None:
            return []
        return build.universe_as_of(self.conn, knowable)  # reuse the shipped read on the knowable cohort

    # ponytail: catalyst_move / trigger_event / kb needed NO stamp fix (already point-in-time
    # honest) — the accessor just injects the existing knowable column (knowable_asof / created_at).

    def catalyst_moves(self, catalyst_id: int) -> list[dict]:
        spec = self._require("catalyst_move")
        eff = self._effective_cutoff(spec)
        rows = self.conn.execute(
            "SELECT * FROM catalyst_move WHERE catalyst_id=? ORDER BY move_window, knowable_asof",
            (catalyst_id,),
        ).fetchall()
        latest: dict[str, dict] = {}
        for r in rows:
            _guard_not_null(r["knowable_asof"], "catalyst_move")
            if r["knowable_asof"] <= eff:
                latest[r["move_window"]] = dict(r)  # ascending order -> keeps the latest per window
        return list(latest.values())

    def kb_nodes(self, *, kind: str | None = None) -> list[dict]:
        return self._kb_read("kb_node", kind)

    def kb_edges(self, *, rel: str | None = None) -> list[dict]:
        return self._kb_read("kb_edge", rel, filter_col="rel")

    def _kb_read(self, table: str, filter_val, *, filter_col: str = "kind") -> list[dict]:
        spec = self._require(table)
        eff = self._effective_cutoff(spec)
        q = f"SELECT * FROM {table}"
        params: list = []
        if filter_val is not None:
            q += f" WHERE {filter_col}=?"
            params.append(filter_val)
        rows = self.conn.execute(q + " ORDER BY id", params).fetchall()
        out = []
        for r in rows:
            _guard_not_null(r["created_at"], table)
            if r["created_at"] <= eff:
                out.append(dict(r))
        return out
