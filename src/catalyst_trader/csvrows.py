"""One tiny shared seed-CSV reader.

The seed/curated CSVs (universe seed, sponsor map, curated PDUFA table) all carry `#`-comment
template headers and blank spacer lines. The "skip blanks + `#` comments -> csv.DictReader" idiom
was copy-pasted across ingest, universe.build, and calendar.verify; this is the single source.
"""

import csv
from pathlib import Path


def read_csv_rows(path: str | Path) -> list[dict]:
    """Rows of a seed CSV as plain dicts, skipping blank lines and `#`-comment lines."""
    lines = [
        ln
        for ln in Path(path).read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    return [dict(r) for r in csv.DictReader(lines)]
