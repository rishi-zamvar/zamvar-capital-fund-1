"""BACK-01: point-in-time, survivorship-free event set + the catalyst-verification filter.

Every test seeds through tests/synth_history.py (fully offline). The money invariants:
- universe/bars read ONLY through the shipped `<= as_of` guards (no future data leaks),
- catalysts read through tradeable_catalysts THEN post-filtered on
  `last_verified_at <= effective_asof` — because tradeable_catalysts has NO date guard,
- delisted names in the cohort still appear (survivorship-free).
"""

from catalyst_trader.backtest.events import build_event_set
from catalyst_trader.store import bars_asof, upsert_bars
from catalyst_trader.universe.build import build_snapshot
from tests.synth_history import _series, seed_history, week_ends

_OPEN = {"min_catalyst_density": 0, "min_market_cap": 0, "min_adv_usd": 0}


def test_event_set_is_point_in_time(db):
    # A catalyst + bars dated in a FUTURE week must not appear in an earlier week's record.
    wk = seed_history(
        db, tickers=["AAAA"], weeks=6,
        catalysts=[{"ticker": "AAAA", "event_date": wk5, "last_verified_at": wk0}
                   for wk0, wk5 in [(week_ends(6)[0], week_ends(6)[5])]],
    )
    recs = build_event_set(db, start=wk[0], end=wk[-1])  # default hold_days=7
    by_asof = {r["as_of"]: r for r in recs}
    # earliest week: the future catalyst is out of the coming hold window -> excluded
    assert recs[0]["catalysts"] == []
    # it surfaces ONLY in its own hold-window week: as_of=wk[4] (2024-01-29), event wk[5] in (wk4, wk4+7d]
    weeks_with_it = [r["as_of"] for r in recs if any(c["event_date"] == wk[5] for c in r["catalysts"])]
    assert weeks_with_it == [wk[4]]
    assert by_asof[wk[4]]["as_of"] < wk[5]


def test_event_set_excludes_catalyst_verified_after_as_of(db):
    # The guard tradeable_catalysts does NOT provide: a catalyst becomes tradeable only
    # once its last_verified_at has passed. Excluded early, included once verification catches up.
    wk = week_ends(6)  # W0..W5 weekly from 2024-01-01
    seed_history(
        db, tickers=["AAAA"], weeks=6,
        catalysts=[{"ticker": "AAAA", "event_date": wk[4],       # 2024-01-29
                    "last_verified_at": "2024-01-20"}],          # between W2 and W3
    )
    # hold_days=60 keeps the event "upcoming" across several weeks so we can watch the flip
    recs = build_event_set(db, start=wk[0], end=wk[-1], hold_days=60)
    by_asof = {r["as_of"]: r for r in recs}

    early = by_asof[wk[1]]   # as_of 2024-01-08 < last_verified_at -> NOT knowable yet
    assert [c for c in early["catalysts"] if c["ticker"] == "AAAA"] == []

    later = by_asof[wk[3]]   # as_of 2024-01-22 >= last_verified_at -> now tradeable
    hit = [c for c in later["catalysts"] if c["ticker"] == "AAAA"]
    assert len(hit) == 1 and hit[0]["last_verified_at"] == "2024-01-20"


def test_event_set_includes_delisted(db):
    # Survivorship-free: a delisted name in the cohort still appears in the event universe.
    wk = seed_history(db, tickers=["AAAA", "DEAD"], weeks=6, delisted=["DEAD"])
    recs = build_event_set(db, start=wk[0], end=wk[-1])
    assert all("DEAD" in r["universe"] for r in recs)
    # and its (delisted) price history is still readable point-in-time
    assert recs[-1]["has_bars"]["DEAD"] is True


def test_event_set_no_future_bar(db):
    # A name whose bars only START in a future week shows has_bars=False until then, and no
    # record ever reports coverage for a bar with week_end > as_of.
    wk = week_ends(6)
    upsert_bars(db, "LIVE", _series("LIVE", wk, start_close=10.0, seed=1))
    upsert_bars(db, "LATE", _series("LATE", wk[3:], start_close=20.0, seed=2))  # bars from W3
    build_snapshot(
        db, wk[0],
        [{"ticker": "LIVE", "delisted": False}, {"ticker": "LATE", "delisted": False}],
        criteria=_OPEN,
    )
    # bitemporal bridge (07.6): backdate the fabricated historical cohort's knowable stamp to its
    # contemporaneous as_of_date so the gateway serves it at the 2024 replay cutoff (build_snapshot
    # stamps recorded_at=now, correct for LIVE but not for a hand-seeded historical cohort).
    db.execute("UPDATE universe_snapshot SET recorded_at = as_of_date")
    db.commit()
    recs = build_event_set(db, start=wk[0], end=wk[-1])
    assert recs[0]["has_bars"]["LIVE"] is True
    assert recs[0]["has_bars"]["LATE"] is False          # no future bar leaks into coverage
    for r in recs:
        for tk, present in r["has_bars"].items():
            if present:
                assert bars_asof(db, tk, r["as_of"])[-1]["week_end"] <= r["as_of"]


def test_event_set_weekly_cursor_covers_range(db):
    # ~1yr of weekly records: one per Monday across the start/end window.
    wk = seed_history(db, tickers=["AAAA"], weeks=52)
    recs = build_event_set(db, start=wk[0], end=wk[-1])
    assert len(recs) == 52
    assert [r["as_of"] for r in recs] == wk
    assert recs == sorted(recs, key=lambda r: r["as_of"])  # chronological
