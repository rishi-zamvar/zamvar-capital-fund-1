"""Precision-driven date + uncertainty classification — the money-critical date path.

The source's own precision IS the fact: a "2027-04" completion date knows the
month, not the day, so it is a WINDOW, never a firm day. We derive precision by
length-checking the raw string's shape and validating it as a real calendar
value — we NEVER parse-with-defaults (dateutil fills the missing day with today,
fabricating a false-precision date, which in this domain is a total-loss vector).

# ponytail: precision-driven rules, not a model. Tune thresholds if a source
# class misclassifies.
"""

import re
from datetime import date

from catalyst_trader.models import DatePrecision, Uncertainty

_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH = re.compile(r"^\d{4}-\d{2}$")
_YEAR = re.compile(r"^\d{4}$")


def parse_precision(raw: str) -> DatePrecision:
    """Derive DatePrecision from the raw string's shape. Never coerces, never defaults.

    "2027-11-14" -> day, "2027-04" -> month, "2027" -> year.
    Raises ValueError on empty/malformed/impossible-calendar input.
    """
    s = raw.strip()
    if _DAY.match(s):
        date.fromisoformat(s)  # rejects e.g. 2027-02-30, re-raises ValueError
        return DatePrecision.day
    if _MONTH.match(s):
        month = int(s[5:7])
        if not 1 <= month <= 12:
            raise ValueError(f"invalid month in {raw!r}")
        return DatePrecision.month
    if _YEAR.match(s):
        return DatePrecision.year
    raise ValueError(f"unrecognized date shape: {raw!r}")


def classify(
    raw_date: str, date_type: str, source_count: int, has_primary: bool
) -> Uncertainty:
    """Uncertainty derived from source precision + corroboration — never a guess.

    - month/year-only precision -> window ALWAYS (before any corroboration check)
    - full-day ESTIMATED (company-guided) -> firm iff corroborated + primary, else window
    - full-day ACTUAL/confirmed -> firm iff corroborated + primary, else soft

    date_type is normalized case-insensitively so persisted lowercase DB values
    ('estimated'/'actual') and raw API values ('ESTIMATED'/'ACTUAL') classify identically.
    """
    if parse_precision(raw_date) is not DatePrecision.day:
        return Uncertainty.window  # partial date is inherently a window

    corroborated = source_count >= 2 and has_primary

    if date_type.upper() == "ESTIMATED":
        return Uncertainty.firm if corroborated else Uncertainty.window

    return Uncertainty.firm if corroborated else Uncertainty.soft
