"""Clinical base-rate table loader (FRAME-03).

The anti-hallucination invariant, same as KeyFinding.evidence_ref: no number without a source.
base_rate() returns the value WITH its citation (source_name/source_url/quote) and RAISES on an
unknown key — never a silent None an agent could cite as fact. Data lives in data/base_rates.csv
(per-row source columns), matching the data/pdufa_curated.csv convention.
"""

import csv
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[3] / "data"  # repo-root/data


def load_base_rates(path: str | Path = DATA_DIR / "base_rates.csv") -> list[dict]:
    """Return the table as row dicts with `value` cast to float."""
    with Path(path).open(newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["value"] = float(r["value"])
    return rows


def base_rate(
    metric: str,
    phase: str | None = None,
    indication: str | None = None,
    path: str | Path = DATA_DIR / "base_rates.csv",
) -> dict:
    """Look up one base rate → {value, source_name, source_url, quote}. Filters by metric and,
    when supplied, phase/indication. Raises ValueError if no row matches (no silent None) or if
    the filter is ambiguous (multiple rows — the caller must narrow phase/indication)."""
    matches = [
        r
        for r in load_base_rates(path)
        if r["metric"] == metric
        and (phase is None or r["phase"] == phase)
        and (indication is None or r["indication"] == indication)
    ]
    if not matches:
        raise ValueError(f"no base rate for metric={metric!r} phase={phase!r} indication={indication!r}")
    if len(matches) > 1:
        raise ValueError(
            f"ambiguous base rate for metric={metric!r} phase={phase!r} indication={indication!r} "
            f"({len(matches)} rows) — narrow phase/indication"
        )
    r = matches[0]
    return {k: r[k] for k in ("value", "source_name", "source_url", "quote")}
