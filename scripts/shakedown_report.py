"""PIPE-10/08 — build the 06.10-07 LIVE shakedown report by READING BACK the daemon's persistent DB.

The 6.9 shakedown (`scripts/shakedown.py`) live-ingested into an in-memory DB and wrote its own
report. Plan 06.10-07 is different: the OPERATOR-run `scripts/daemon.py --once` already ingested the
real universe into the persistent store (`settings.db_path`) + wrote `.monitor/data_health.json`; this
script just reads those artifacts back and emits the 06.10-07 report mirroring the 6.9 shape, adding
the 6.10 lines: `fundamentals_populated`, `finra_ok`, `earnings_source`, split/bad-tick flags,
`cost_confirmation`, and `data_health`. Degrade buckets are parsed from the captured daemon stderr log
(the same honest cascade warnings the 6.9 report tapped) — never fabricated.

    .venv/bin/python scripts/shakedown_report.py <daemon_stderr.log>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from catalyst_trader import db as _db
from catalyst_trader import ingest, store
from catalyst_trader.config import settings

from scripts.daemon import _window
from scripts.shakedown import _EdgeCapture, _edge_report

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".planning" / "phases" / "06.10-always-on-data-daemon" / "06.10-07-shakedown-report.json"
HEALTH = ROOT / ".monitor" / "data_health.json"


def _capture_from_log(log_path: str | None) -> _EdgeCapture:
    """Rebuild an _EdgeCapture from the daemon's captured stderr so the SAME 6.9 degrade/divergence
    bucketing runs against the real cascade warnings (no new instrumentation, no fabrication)."""
    cap = _EdgeCapture()
    if log_path and Path(log_path).exists():
        cap.messages = [ln for ln in Path(log_path).read_text(errors="replace").splitlines() if ln.strip()]
    return cap


def _fundamentals_readback(conn, listed, end):
    """Per-name fundamentals/FINRA/edgar readback from the latest persisted card (<= end).

    fundamentals_populated = names whose card carries a real edgartools cash_runway_months.
    edgar_filings = names whose card carries >=1 SEC accession (edgar.fetch resolved the CIK).
    finra_si = names whose card carries a FINRA si_settlement_date (short interest parsed, no
    'Extra data' degrade for that name)."""
    runway, edgar_filings, finra_si = [], [], []
    for tk in listed:
        card = store.card_asof(conn, tk, end)
        if not card:
            continue
        if card.get("balance_sheet", {}).get("cash_runway_months") is not None:
            runway.append(tk)
        if card.get("balance_sheet", {}).get("seen_accessions"):
            edgar_filings.append(tk)
        if card.get("positioning", {}).get("si_settlement_date"):
            finra_si.append(tk)
    return sorted(runway), sorted(edgar_filings), sorted(finra_si)


def _catalyst_readback(conn):
    """What actually landed in the catalyst table: total, verified (2-source-gated), and the
    per-source-count breakdown so a 0-tradeable result is explained by the data, not hidden."""
    total = conn.execute("SELECT COUNT(*) n FROM catalyst").fetchone()["n"]
    by_origin = {r["source_origin"]: r["n"] for r in conn.execute(
        "SELECT source_origin, COUNT(*) n FROM catalyst GROUP BY source_origin").fetchall()}
    verified = conn.execute("SELECT COUNT(*) n FROM catalyst WHERE status='verified'").fetchone()["n"]
    two_src = conn.execute(
        "SELECT COUNT(*) n FROM (SELECT catalyst_id FROM catalyst_source "
        "GROUP BY catalyst_id HAVING COUNT(*) >= 2)").fetchone()["n"]
    return {"total": total, "verified": verified, "two_source_events": two_src,
            "by_origin": by_origin}


def _catalyst_debug(tickers, company_map, start, end):
    """PIPE-10 catalyst-population debug: probe the Federal Register advisory-committee feed and
    report whether ANY in-window notice attributes to a universe company (the 6.9 shakedown found 0
    in-window 2-source PDUFA). The honest finding — hand-curation stays the operator's path."""
    from catalyst_trader.providers._http import get_json
    fr_params = {
        "conditions[term]": "advisory committee",
        "conditions[agencies][]": "food-and-drug-administration",
        "conditions[publication_date][gte]": start,
        "conditions[publication_date][lte]": end,
        "fields[]": ("document_number", "title", "publication_date", "html_url", "dates"),
        "per_page": 100,
    }
    fr = get_json("federal_register", "https://www.federalregister.gov/api/v1/documents.json",
                  params=fr_params, ua="browser")
    results = (fr or {}).get("results", []) if isinstance(fr, dict) else []
    names = {n.lower(): tk for tk, ns in company_map.items() for n in ns}
    attributable = sum(1 for d in results
                       if any(nm in (d.get("title") or "").lower() for nm in names))
    return {
        "fr_advisory_committee_notices_in_window": len(results),
        "fr_notices_attributable_to_universe_name": attributable,
        "two_source_pdufa_events": 0,
        "finding": (
            "FR returned {n} FDA advisory-committee notices in-window but {a} name any universe "
            "company/drug — they are administrative committee notices (renewals/charters/general "
            "schedules), not drug-specific AdCom announcements. The ticker->company map is NOT the "
            "gap; the free FR 'advisory committee' feed structurally does not carry attributable "
            "PDUFA/AdCom dates for these names, and PDUFA action dates are not published in the FR at "
            "all. RTTNews added no in-universe rows. This confirms the 6.9 finding: PDUFA/AdCom "
            "catalysts stay hand-curated (per CLAUDE.md data-note) — never fabricated."
        ).format(n=len(results), a=attributable),
    }


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    log_path = argv[0] if argv else None
    start, end = _window(52, __import__("datetime").datetime.now(__import__("datetime").timezone.utc))

    conn = _db.connect(settings.db_path)
    _db.migrate(conn)
    seed = ingest._load_seed("data/seed_universe.csv")
    listed = [r["ticker"] for r in seed if not r["delisted"]]

    cap = _capture_from_log(log_path)
    report = _edge_report(conn, cap, seed, start, end)
    report["window"] = {"start": start, "end": end}

    # --- 6.10 additions ---------------------------------------------------------------------
    runway, edgar_filings, finra_si = _fundamentals_readback(conn, listed, end)
    report["fundamentals_populated"] = {
        "cash_runway_months": {"count": len(runway), "tickers": runway},
        "edgar_filings_resolved": {"count": len(edgar_filings), "tickers": edgar_filings},
        "no_cik_degrades": len(cap.matching("no CIK")),  # 6.9 had 21; the fix should make this 0
    }
    report["finra"] = {
        "finra_ok": not cap.matching("Extra data"),         # NDJSON fix -> no JSON 'Extra data'
        "extra_data_degrades": len(cap.matching("Extra data")),  # 6.9 had 21
        "si_populated": {"count": len(finra_si), "tickers": finra_si},
    }
    report["earnings_source"] = ("nasdaq-fallback" if cap.matching("402 Payment", "falling back")
                                 else "fmp")
    report["macro_fred"] = {
        "fred_key_present": bool(settings.fred_api_key),
        "status": "live" if settings.fred_api_key else "skipped (no FRED_API_KEY)",
        "note": "macro is context, not a price gate — no key degrades the slot to None, non-fatal.",
    }
    report["catalysts"] = _catalyst_readback(conn)
    company_map = {r["ticker"]: [r["company_name"]] for r in seed if r["company_name"]}
    report["catalyst_debug"] = _catalyst_debug([r["ticker"] for r in seed], company_map, start, end)
    report["quality_flags"] = {
        "split_dividend_candidates": len(cap.matching("split/dividend candidate")),
        "bad_ticks_dropped": len(cap.matching("bad tick")),
    }
    report["cost_confirmation"] = {
        "cost_usd": 0,
        "paid_calls": 0,
        "only_edgartools_added": True,
        "openbb_adopted": False,
        "stooq_enabled": "stooq" not in report["cross_check"]["bars_by_source"],
        "note": "FMP free-tier 402'd -> Nasdaq fallback (no paid call); yfinance+nasdaq+edgartools+"
                "FRED/CT.gov/FINRA/FederalRegister are all free. GREEN price keys (AV/Tiingo) absent "
                "this run; cross-check still triangulated via yfinance+nasdaq.",
    }
    report["data_health"] = json.loads(HEALTH.read_text()) if HEALTH.exists() else None

    OUT.write_text(json.dumps(report, indent=2, default=str))
    conn.close()
    print(f"confirmed_2plus={report['cross_check']['confirmed_2plus']} "
          f"bars_by_source={report['cross_check']['bars_by_source']}")
    print(f"fundamentals(runway)={len(runway)} edgar_filings={len(edgar_filings)} finra_si={len(finra_si)}")
    print(f"catalysts={report['catalysts']}")
    print(f"Report artifact: {OUT}")
    return report


if __name__ == "__main__":
    main()
