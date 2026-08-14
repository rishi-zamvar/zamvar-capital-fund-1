"""EXHAUSTIVE date-precision + uncertainty suite (money-critical, TDD-first).

The total-loss vector this suite guards against: silently coercing a partial
source date (e.g. "2027-04") into a false-precision day ("2027-04-01") and then
treating it as a firm, tradeable date. A month- or year-only source date is
inherently a WINDOW and must NEVER classify as `firm`, regardless of how many
sources corroborate it. These tests are written before the implementation and
MUST be RED until catalyst_trader.dates exists.
"""

import pytest

from catalyst_trader.dates import classify, parse_precision
from catalyst_trader.models import DatePrecision, Uncertainty


# --- parse_precision: precision is derived from the raw string's SHAPE, never guessed ---


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2027-11-14", DatePrecision.day),
        ("2027-04", DatePrecision.month),
        ("2032-12", DatePrecision.month),
        ("2027", DatePrecision.year),
    ],
)
def test_parse_precision_maps_shape_to_precision(raw, expected):
    assert parse_precision(raw) is expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "abc", "2027-13-40", "2027-00", "2027-13", "2027-02-30", "27-04", "2027/04/01"],
)
def test_parse_precision_raises_on_malformed_never_defaults(raw):
    # Never silently default a bad string to a date/precision.
    with pytest.raises(ValueError):
        parse_precision(raw)


def test_parse_precision_returns_enum_not_datetime():
    result = parse_precision("2027-04")
    assert isinstance(result, DatePrecision)
    assert not hasattr(result, "day")  # not a datetime.date


def test_parse_precision_does_not_coerce_partial_to_day():
    # The raw month string round-trips unchanged: no day component is invented.
    raw = "2027-04"
    assert parse_precision(raw) is DatePrecision.month
    assert raw == "2027-04"  # untouched
    # And a full day stays day — the shape check does not strip precision either.
    assert parse_precision("2027-04-15") is DatePrecision.day


# --- classify: uncertainty is DERIVED from precision + corroboration, never a judgement ---


@pytest.mark.parametrize(
    "raw, date_type, source_count, has_primary, expected",
    [
        # month/year-only → ALWAYS window, corroboration is irrelevant
        ("2027-04", "ESTIMATED", 3, True, Uncertainty.window),
        ("2032-12", "ESTIMATED", 1, False, Uncertainty.window),
        ("2027", "ESTIMATED", 2, True, Uncertainty.window),
        # full day + ESTIMATED (company-guided)
        ("2027-11-14", "ESTIMATED", 1, False, Uncertainty.window),
        ("2027-11-14", "ESTIMATED", 2, True, Uncertainty.firm),
        # full day + ACTUAL
        ("2026-11-30", "ACTUAL", 2, True, Uncertainty.firm),
        ("2026-11-30", "ACTUAL", 1, False, Uncertainty.soft),
        ("2026-11-30", "ACTUAL", 2, False, Uncertainty.soft),  # no primary → not firm
        # case-insensitive date_type (persisted lowercase DB value must classify identically)
        ("2026-11-30", "actual", 2, True, Uncertainty.firm),
        ("2027-11-14", "estimated", 1, False, Uncertainty.window),
    ],
)
def test_classify_derives_uncertainty(raw, date_type, source_count, has_primary, expected):
    assert classify(raw, date_type, source_count, has_primary) is expected


@pytest.mark.parametrize("raw", ["2027-04", "2032-12", "2027"])
@pytest.mark.parametrize("date_type", ["ESTIMATED", "ACTUAL", "estimated", "actual"])
@pytest.mark.parametrize("source_count", [1, 2, 5])
@pytest.mark.parametrize("has_primary", [True, False])
def test_month_or_year_date_is_never_firm(raw, date_type, source_count, has_primary):
    # THE invariant: a partial date can never be firm, across every combination.
    result = classify(raw, date_type, source_count, has_primary)
    assert result is not Uncertainty.firm
    assert result is Uncertainty.window


def test_firm_requires_a_primary_source():
    # Two agreeing sources are not enough — at least one must be primary.
    assert classify("2026-11-30", "ACTUAL", 2, False) is Uncertainty.soft
    assert classify("2026-11-30", "ACTUAL", 2, True) is Uncertainty.firm


def test_estimated_full_day_needs_corroboration_and_primary_for_firm():
    # A guided estimate on a full day is a window until corroborated + primary.
    assert classify("2027-11-14", "ESTIMATED", 1, False) is Uncertainty.window
    assert classify("2027-11-14", "ESTIMATED", 2, False) is Uncertainty.window
    assert classify("2027-11-14", "ESTIMATED", 2, True) is Uncertainty.firm


def test_classify_rejects_malformed_date():
    # A date it cannot even parse must not be silently classified.
    with pytest.raises(ValueError):
        classify("garbage", "ACTUAL", 2, True)
