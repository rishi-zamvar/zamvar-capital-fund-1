"""Correlation engine (HEDGE-CORR-1a): DB-aware per-name XBI corr/beta/R2 + same-group peer
pairwise corr, full-window AND ex-event-week, each with an explicit verdict + direction.

Money-safety invariants under test (all offline, :memory: + seeded price_bar/catalyst):
  - the numpy math REUSES quant.pairs.correlation_beta (R2 == corr**2) and quant.weekly._weekly_returns
    (no hand-rolled returns).
  - WEEK ALIGNMENT (the XBI trap): a Monday-anchored XBI series paired with a Friday name series is
    intersected on common week_end BEFORE returns — few/zero common weeks RAISES insufficient obs
    rather than silently mis-correlating a length-padded pair.
  - ex-event-week (C1): the RETURN-observation whose destination week_end falls in the ticker's OWN
    event set is dropped (post-computation), not the raw bar; a name with no catalyst -> ex == full.
  - verdict bands + ex-event window live in module PARAMS; a missing band key RAISES (no magic literal).
  - the verdict is on |corr|; a SIGNED value is stored and direction ("co-move"/"inverse") is explicit
    (C3) — a strong negative is an inverse relationship, never "none".
"""

import json
import math

import pytest

from catalyst_trader import store
from catalyst_trader.dates import now_iso
from catalyst_trader.quant import correlations as corr
from catalyst_trader.quant.pairs import correlation_beta
from catalyst_trader.quant.weekly import _weekly_returns


# --- seeding helpers -------------------------------------------------------

def _fridays(n, start="2025-01-03"):
    """n consecutive Friday-anchored week_end strings from `start` (a Friday)."""
    from datetime import date, timedelta

    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(weeks=i)).isoformat() for i in range(n)]


def _mondays(n, start="2025-01-06"):
    """n consecutive Monday-anchored week_end strings (the XBI trap anchor)."""
    from datetime import date, timedelta

    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(weeks=i)).isoformat() for i in range(n)]


def _seed_series(db, ticker, week_ends, closes):
    bars = [{"week_end": w, "close": c} for w, c in zip(week_ends, closes)]
    store.upsert_bars(db, ticker, bars)


def _seed_catalyst(db, ticker, *, event_date=None, disease_area=None, mechanism_class=None):
    attrs = {"type": "pdufa", "ticker": ticker}
    if event_date:
        attrs["event_date"] = event_date
    if disease_area:
        attrs["disease_area"] = disease_area
    if mechanism_class:
        attrs["mechanism_class"] = mechanism_class
    db.execute(
        "INSERT INTO kb_node (kind, ref_id, attrs_json, confidence, created_at) "
        "VALUES ('catalyst', NULL, ?, NULL, ?)",
        (json.dumps(attrs), now_iso()),
    )
    db.commit()


# a reproducible non-trivial pair of 30-week close paths
_NAME_CLOSES = [100.0 + 3.0 * math.sin(i / 2.0) + 0.7 * i for i in range(30)]
_XBI_CLOSES = [50.0 + 1.4 * math.sin(i / 2.0 + 0.3) + 0.25 * i for i in range(30)]


# --- alignment + math reuse ------------------------------------------------

def test_givenAlignedFridaySeries_whenComputeXbiStats_thenMatchesCorrelationBetaAndR2IsCorrSquared(db):
    weeks = _fridays(30)
    _seed_series(db, "NAME", weeks, _NAME_CLOSES)
    _seed_series(db, "XBI", weeks, _XBI_CLOSES)

    got = corr.compute_xbi_stats(db, "NAME")

    ra = _weekly_returns([{"close": c} for c in _NAME_CLOSES])
    rb = _weekly_returns([{"close": c} for c in _XBI_CLOSES])
    ref = correlation_beta(ra, rb)
    assert got["corr"] == pytest.approx(ref.value)
    assert got["beta"] == pytest.approx(ref.detail["beta"])
    assert got["r2"] == pytest.approx(ref.value ** 2)


def test_givenMondayXbiAndFridayName_whenComputeXbiStats_thenRaisesInsteadOfMisCorrelating(db):
    # the XBI trap: Monday-anchored XBI shares ~zero common week_end with the Friday name.
    _seed_series(db, "NAME", _fridays(30), _NAME_CLOSES)
    _seed_series(db, "XBI", _mondays(30), _XBI_CLOSES)
    with pytest.raises(ValueError):
        corr.compute_xbi_stats(db, "NAME")


def test_givenMisalignedButUnequalLengths_whenAlignedReturns_thenAlignedNotLengthPadded(db):
    # even with different series lengths, alignment intersects on week_end (never zip-pads).
    _seed_series(db, "NAME", _fridays(30), _NAME_CLOSES)
    _seed_series(db, "XBI", _fridays(20), _XBI_CLOSES[:20])
    ra, rb = corr._aligned_returns(db, "NAME", "XBI")
    assert len(ra) == len(rb) == 19  # 20 common weeks -> 19 returns


# --- ex-event-week (C1) ----------------------------------------------------

def test_givenNameWithOwnEvent_whenExEventVariant_thenDiffersFromFullWindow(db):
    weeks = _fridays(30)
    _seed_series(db, "NAME", weeks, _NAME_CLOSES)
    _seed_series(db, "XBI", weeks, _XBI_CLOSES)
    _seed_catalyst(db, "NAME", event_date=weeks[15])

    full = corr.compute_xbi_stats(db, "NAME", ex_event=False)
    ex = corr.compute_xbi_stats(db, "NAME", ex_event=True)
    assert ex["corr"] != pytest.approx(full["corr"])


def test_givenNameWithNoCatalyst_whenExEventVariant_thenEqualsFullWindow(db):
    weeks = _fridays(30)
    _seed_series(db, "NAME", weeks, _NAME_CLOSES)
    _seed_series(db, "XBI", weeks, _XBI_CLOSES)

    full = corr.compute_xbi_stats(db, "NAME", ex_event=False)
    ex = corr.compute_xbi_stats(db, "NAME", ex_event=True)
    assert ex["corr"] == pytest.approx(full["corr"])


def test_givenExEvent_whenStripping_thenDropsReturnObservationNotRawBar(db):
    # C1 proof: stripping the destination-week return keeps the count = full_returns - (#stripped),
    # NOT the multi-week return that dropping a bar would create.
    weeks = _fridays(30)
    _seed_series(db, "NAME", weeks, _NAME_CLOSES)
    _seed_series(db, "XBI", weeks, _XBI_CLOSES)
    _seed_catalyst(db, "NAME", event_date=weeks[15])

    full_a, _ = corr._aligned_returns(db, "NAME", "XBI")
    ex_ends = corr._ex_event_week_ends(db, "NAME", corr.PARAMS["ex_event_window_weeks"])
    ex_a, ex_b = corr._aligned_returns(db, "NAME", "XBI", ex_event_ends=ex_ends)
    assert len(ex_a) == len(ex_b) == len(full_a) - len(ex_ends)


# --- verdict banding + direction (C3) --------------------------------------

def test_givenCorrsAcrossBands_whenVerdict_thenBandsMapCorrectly(db):
    bands = corr.PARAMS["verdict_bands"]
    assert corr._verdict(0.75, bands) == "strong"
    assert corr._verdict(0.50, bands) == "moderate"
    assert corr._verdict(0.30, bands) == "weak"
    assert corr._verdict(0.05, bands) == "none"
    # verdict is on |corr| — a strong NEGATIVE is still "strong" (an inverse relationship)
    assert corr._verdict(-0.75, bands) == "strong"


def test_givenMissingBandKey_whenVerdict_thenRaises(db):
    with pytest.raises(KeyError):
        corr._verdict(0.5, {"moderate": 0.4, "weak": 0.2})  # no "strong" key


def test_givenSignedCorr_whenDirection_thenCoMoveVsInverseExplicit(db):
    assert corr._direction(0.6) == "co-move"
    assert corr._direction(-0.6) == "inverse"


# --- full profile blob -----------------------------------------------------

def test_givenNameAndPeers_whenComputeHedgeProfile_thenExplicitBlobShape(db):
    weeks = _fridays(30)
    _seed_series(db, "NAME", weeks, _NAME_CLOSES)
    _seed_series(db, "XBI", weeks, _XBI_CLOSES)
    _seed_series(db, "PEER", weeks, [c * 1.1 + 2.0 for c in _NAME_CLOSES])
    _seed_catalyst(db, "NAME", event_date=weeks[15], disease_area="oncology")
    _seed_catalyst(db, "PEER", disease_area="oncology")

    prof = corr.compute_hedge_profile(db, "NAME", as_of=weeks[-1])

    assert prof["as_of"] == weeks[-1]
    # xbi block carries full + ex_event, each with corr/beta/r2/verdict/direction/window
    for w in ("full", "ex_event"):
        x = prof["xbi"][w]
        assert set(("corr", "beta", "r2", "verdict", "direction", "window")) <= set(x)
        assert x["r2"] == pytest.approx(x["corr"] ** 2)
    # systematic/idiosyncratic split from R2
    assert prof["systematic_frac"] == pytest.approx(prof["xbi"]["full"]["r2"])
    assert prof["idiosyncratic_frac"] == pytest.approx(1 - prof["xbi"]["full"]["r2"])
    # PEER is a same-disease peer -> present with full + ex_event corr + verdict + direction
    peers = {p["peer"]: p for p in prof["peers"]}
    assert "PEER" in peers
    p = peers["PEER"]
    assert set(("peer", "disease_or_mech", "corr_full", "corr_ex_event", "verdict", "direction")) <= set(p)


def test_givenXbiVerdictStrong_whenSuggestedHedge_thenXbiOverlayElseSizingOnly(db):
    weeks = _fridays(30)
    # near-perfectly correlated name+XBI -> strong verdict -> xbi_overlay
    _seed_series(db, "NAME", weeks, _NAME_CLOSES)
    _seed_series(db, "XBI", weeks, [c * 0.5 + 1.0 for c in _NAME_CLOSES])
    prof = corr.compute_hedge_profile(db, "NAME")
    assert prof["xbi"]["full"]["verdict"] in ("strong", "moderate")
    assert prof["suggested_hedge"].startswith("xbi_overlay@beta ")


def test_givenPeerPairInsufficientObs_whenComputeHedgeProfile_thenPeerOmittedNotNaN(db):
    weeks = _fridays(30)
    _seed_series(db, "NAME", weeks, _NAME_CLOSES)
    _seed_series(db, "XBI", weeks, _XBI_CLOSES)
    # PEER shares disease but only 3 common weeks -> below min_obs -> abstain (omitted)
    _seed_series(db, "PEER", weeks[:3], _NAME_CLOSES[:3])
    _seed_catalyst(db, "NAME", disease_area="oncology")
    _seed_catalyst(db, "PEER", disease_area="oncology")

    prof = corr.compute_hedge_profile(db, "NAME")
    assert all(p["peer"] != "PEER" for p in prof["peers"])  # no misleading number emitted
