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

import sqlite3
from typing import NamedTuple

from catalyst_trader import store
from catalyst_trader.dates import now_iso


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


# The encoded audit. Plan 02 seeds ONLY price_bar (the wired exemplar); Plan 03 adds the rest.
# price_bar's knowable stamp is week_end (NOT retrieved_at — the backfill trap: a bulk backfill
# stamps every historical bar with today's retrieved_at, which would deny ALL history).
STAMP_REGISTRY: dict[str, StampSpec] = {
    "price_bar": StampSpec(valid_col="week_end", knowable_expr="week_end", data_class="price"),
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
