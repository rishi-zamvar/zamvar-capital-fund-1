"""FIX B — verify + correct the SIGNED T-1..T+2 realized move from CACHED bars (zero API).

PURE + offline in the tested surface: recompute_signed_move is math over a bar list; the live
network seam is the INJECTED bars_provider (find_move_divergences) — tests pass a callable over
seeded bars, live passes a get_daily_bars-backed callable (cache/free-daily only, CLAUDE.md
frugality). A wrong stored move is a silent money bug in the analog corpus; this flags + corrects it.

# ponytail: this is the CANONICAL tested (-1,+2) recompute. scripts/polish_a3_a4.py:signed_move and
#   universe/discover.py:_realized_catalyst_move embed the SAME window math — not refactoring shipped
#   money-path code under a quick task, just homing a tested copy the live application (Task 4) calls.
"""

MOVE_WINDOW = (-1, 2)


def recompute_signed_move(bars: list[dict], event_date: str, window=MOVE_WINDOW) -> float | None:
    """close[T+window[1]] / close[T+window[0]] - 1.0, SIGNED, over a DAILY bar list. None (never
    imputed) on a month-precision event_date, a missing/guarded window, or a null/zero close.

    bars use `week_end` for the daily trade date (price_bar's date column). t0 = first index whose
    date >= event_date; the window offsets are applied off t0 and bounds-guarded."""
    if len(event_date) != 10:
        return None
    bars = sorted(bars, key=lambda b: b["week_end"])
    t0 = next((i for i, b in enumerate(bars) if b["week_end"] >= event_date), None)
    if t0 is None:
        return None
    i_lo, i_hi = t0 + window[0], t0 + window[1]
    if i_lo < 0 or i_hi >= len(bars):
        return None
    c_lo, c_hi = bars[i_lo].get("close"), bars[i_hi].get("close")
    if not c_lo or not c_hi:
        return None
    return c_hi / c_lo - 1.0  # SIGNED — never abs


def find_move_divergences(conn, bars_provider, *, tol=0.02) -> list[dict]:
    """For each catalyst_move JOIN catalyst, recompute the signed move from bars_provider(ticker,
    event_date) and flag rows whose stored realized_move diverges from the recompute by more than tol.

    bars_provider is the injected offline/frugal seam. A None recompute is NEVER flagged (cite-or-drop:
    keep the stored value when there is no usable window). Returns one dict per divergence:
    {catalyst_id, ticker, event_date, stored, recomputed, delta}."""
    rows = conn.execute(
        "SELECT m.catalyst_id AS catalyst_id, m.realized_move AS stored, m.move_window AS move_window, "
        "c.ticker AS ticker, c.event_date AS event_date "
        "FROM catalyst_move m JOIN catalyst c ON c.id = m.catalyst_id"
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        bars = bars_provider(r["ticker"], r["event_date"]) or []
        recomputed = recompute_signed_move(bars, r["event_date"])
        if recomputed is None:
            continue
        stored = r["stored"]
        if abs(recomputed - stored) > tol:
            out.append({
                "catalyst_id": r["catalyst_id"],
                "ticker": r["ticker"],
                "event_date": r["event_date"],
                "stored": stored,
                "recomputed": recomputed,
                "delta": recomputed - stored,
            })
    return out


def correct_move(conn, catalyst_id, move_window, new_move) -> None:
    """Write the recomputed SIGNED value into the divergent catalyst_move row (idempotent on the
    UNIQUE(catalyst_id, move_window) key). Commits."""
    conn.execute(
        "UPDATE catalyst_move SET realized_move=? WHERE catalyst_id=? AND move_window=?",
        (new_move, catalyst_id, move_window),
    )
    conn.commit()
