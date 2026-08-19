"""Options-IV data adapter (FF-05) — the ABSTAINING seam that feeds the football-field
implied-move method, plus the options_snapshot cache read/write helpers.

This is a THIN adapter, a mirror of playbook/verify_moves.py's injected-provider seam: it does
NOT reimplement implied-move math (that is quant.options.implied_move). `implied_move_from_provider`
turns a provider's raw straddle/IV dict into a ToolResult, and — critically — ABSTAINS (returns
None) whenever the provider yields no data or an incomplete method, so the desk never fabricates a
move from thin air. The provider is injected: tests pass a fake lambda, the backtest/engine passes
`options_snapshot_provider(conn)`, and the live interactive desk passes an RH-backed closure.

The two REAL provider impls are authored + run in the INTERACTIVE plan Task 4 (RH option MCP tools
exist only in an interactive/agent session — never call them from here or the headless engine):

  LIVE (interactive desk, RH MCP via providers/robinhood mcp_call):
    get_option_chains(symbol) -> pick the nearest expiry AFTER event_date -> ATM strike ~ underlying
    -> get_option_quotes(call_id, put_id) gives mark_price (= call_mid / put_mid) + implied_volatility
    (= iv) directly; underlying from get_equity_quotes. Degrade to None when mcp_call is absent.

  HISTORICAL (backfill, RH):
    get_option_instruments(symbol, state='expired') -> ATM call+put of the expiry JUST AFTER the
    past event -> get_option_historicals as-of T-1 -> straddle mids -> write_options_snapshot(...).

# ponytail: the table is provisioned by migration 012 (db.migrate) — this module ASSUMES the DB is
#           migrated and NEVER creates schema (no inline CREATE TABLE / ensure_ helper).
"""

from ..quant.options import implied_move
from ..quant.result import ToolResult

_SNAPSHOT_COLS = ("underlying_price", "call_mid", "put_mid", "iv", "days_to_event")


def implied_move_from_provider(ticker: str, event_date: str, options_provider) -> ToolResult | None:
    """ToolResult from the provider's straddle/IV dict, or None (ABSTAIN) — never fabricates a move.

    options_provider(ticker, event_date) returns {underlying_price, call_mid, put_mid, iv,
    days_to_event} (any subset) or None. None/empty -> abstain. A dict with no complete method
    (neither a full straddle nor iv+days_to_event) or a degraded snapshot -> abstain, NEVER raise
    into the desk (the field just omits this method and forms on the survivors)."""
    data = options_provider(ticker, event_date)
    if not data:                       # None / empty -> ABSTAIN
        return None
    try:
        return implied_move(
            underlying_price=data["underlying_price"],
            call_mid=data.get("call_mid"), put_mid=data.get("put_mid"),
            iv=data.get("iv"), days_to_event=data.get("days_to_event"),
        )
    except (KeyError, ValueError):
        return None                    # incomplete / degraded snapshot -> ABSTAIN, never crash the desk


def write_options_snapshot(
    conn, ticker: str, event_date: str, *, underlying_price: float,
    call_mid: float | None = None, put_mid: float | None = None,
    iv: float | None = None, days_to_event: int | None = None, source: str,
) -> None:
    """Upsert one cached options snapshot (INSERT OR REPLACE on the (ticker, event_date) PK) + commit.

    The write half of the HISTORICAL/backtest read seam (RH MCP is unavailable headless). No DDL —
    the table is created by migration 012. `fetched_at` records the wall-clock fetch time."""
    from ..dates import now_iso  # lazy: keep the module import surface thin

    conn.execute(
        "INSERT OR REPLACE INTO options_snapshot "
        "(ticker, event_date, underlying_price, call_mid, put_mid, iv, days_to_event, source, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ticker, event_date, underlying_price, call_mid, put_mid, iv, days_to_event, source, now_iso()),
    )
    conn.commit()


def options_snapshot_provider(conn):
    """Return callable(ticker, event_date) -> {underlying_price, call_mid, put_mid, iv, days_to_event}
    | None reading one cached row (None entries dropped). The provider the builder/engine INJECT in
    the headless/backtest path; a missing (ticker, event_date) -> None (the adapter then abstains)."""

    def _provider(ticker: str, event_date: str) -> dict | None:
        row = conn.execute(
            "SELECT underlying_price, call_mid, put_mid, iv, days_to_event "
            "FROM options_snapshot WHERE ticker=? AND event_date=?",
            (ticker, event_date),
        ).fetchone()
        if row is None:
            return None
        return {c: row[c] for c in _SNAPSHOT_COLS if row[c] is not None}

    return _provider
