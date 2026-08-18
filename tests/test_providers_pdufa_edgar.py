"""Our own PDUFA/AdCom source from SEC 8-K filings (providers/pdufa_edgar.py) — offline.

The provider discovers PDUFA 8-Ks via EDGAR full-text search (CIK-filtered to the universe),
fetches the matched EX-99.1 exhibit (RAW HTML, as the live .htm delivers), normalizes HTML->text
(tag-strip) FIRST, then deterministically regex-extracts the date verbatim-adjacent to a
PDUFA/target-action/goal/AdCom keyword (no-LLM-dates, cite-or-drop), and emits a Catalyst with a
SINGLE source_name="SEC EDGAR" primary source that self-verifies via the DATA-03 amendment.

The offline-green/live-broken trap is closed here: fixtures are REAL-HTML-shaped 8-K exhibits with
tags interspersed AROUND and BETWEEN the keyword and the date, and _extract tag-strips before the
regex. ZERO live API — efts JSON + 8-K exhibit HTML are mocked; edgar.Company is faked.
"""

import re

from catalyst_trader.models import CatalystType


# ── Task 1: HTML->text normalize + deterministic extraction ─────────────────────────────────


def test_normalize_rejoins_tag_split_keyword_date():
    """A tag-split keyword/date (`date</span> of <span>April 28, 2027`) must NOT match the regex
    on RAW HTML but MUST match after _normalize — proving tag-strip precedes the regex (the fix
    that closes the offline-green/live-broken trap)."""
    from catalyst_trader.providers import pdufa_edgar

    raw = "PDUFA target action date</span> of <span>April 28, 2027"
    assert pdufa_edgar._PDUFA_RX.search(raw) is None  # raw HTML breaks ~40-char adjacency
    text = pdufa_edgar._normalize(raw)
    m = pdufa_edgar._PDUFA_RX.search(text)  # adjacency restored after tag-strip
    assert m is not None
    assert m.group(1) == "April 28, 2027"


def _load_htm(name):
    from pathlib import Path

    return (Path(__file__).parent / "fixtures" / name).read_text()


def test_extract_imnm_high():
    from catalyst_trader.providers import pdufa_edgar

    out = pdufa_edgar._extract(_load_htm("edgar_8k_imnm.htm"), "2026-08-11")
    pdufa = [c for c in out if c["catalyst_type"] == CatalystType.pdufa]
    assert len(pdufa) == 1  # date repeated 3x -> deduped to one candidate
    assert pdufa[0]["event_date"] == "2027-04-28"
    assert pdufa[0]["confidence"] == "HIGH"


def test_extract_capr_high():
    from catalyst_trader.providers import pdufa_edgar

    out = pdufa_edgar._extract(_load_htm("edgar_8k_capr.htm"), "2026-05-12")
    pdufa = [c for c in out if c["catalyst_type"] == CatalystType.pdufa]
    assert len(pdufa) == 1
    assert pdufa[0]["event_date"] == "2026-08-22"
    assert pdufa[0]["confidence"] == "HIGH"


def test_extract_no_keyword_no_date():
    """no-LLM-dates: a bare date with NO PDUFA/target-action/goal/AdCom keyword nearby is
    NEVER emitted."""
    from catalyst_trader.providers import pdufa_edgar

    html = "<html><body><p>The board met on April 28, 2027 to discuss strategy.</p></body></html>"
    assert pdufa_edgar._extract(html, "2026-08-11") == []


def test_extract_unparseable_date_dropped():
    """cite-or-drop: a keyword followed by a garbage date does not normalize -> dropped."""
    from catalyst_trader.providers import pdufa_edgar

    html = "<p>PDUFA target action date of Someday 99, 20XX for the drug.</p>"
    assert pdufa_edgar._extract(html, "2026-08-11") == []


def test_extract_multiple_dates_medium():
    """Two DIFFERENT candidate dates near keywords -> MEDIUM (routes to review, never auto-HIGH)."""
    from catalyst_trader.providers import pdufa_edgar

    html = (
        "<p>PDUFA target action date of April 28, 2027 in the release,</p>"
        "<p>but a PDUFA target action date of June 15, 2027 appears elsewhere.</p>"
    )
    out = pdufa_edgar._extract(html, "2026-08-11")
    dates = {c["event_date"] for c in out}
    assert dates == {"2027-04-28", "2027-06-15"}
    assert all(c["confidence"] == "MEDIUM" for c in out)


def test_extract_target_action_without_pdufa_medium():
    """'target action date of <date>' with NO 'PDUFA' token -> MEDIUM (human confirm)."""
    from catalyst_trader.providers import pdufa_edgar

    html = "<p>The FDA set a target action date of August 22, 2026 for the application.</p>"
    out = pdufa_edgar._extract(html, "2026-05-12")
    assert len(out) == 1
    assert out[0]["event_date"] == "2026-08-22"
    assert out[0]["confidence"] == "MEDIUM"


def test_extract_adcom():
    """An AdCom 'advisory committee meeting ... on <date>' -> catalyst_type adcom."""
    from catalyst_trader.providers import pdufa_edgar

    html = (
        "<p>The FDA has scheduled an advisory committee meeting to review the BLA "
        "on <span>September 10, 2026</span>.</p>"
    )
    out = pdufa_edgar._extract(html, "2026-05-12")
    adcom = [c for c in out if c["catalyst_type"] == CatalystType.adcom]
    assert len(adcom) == 1
    assert adcom[0]["event_date"] == "2026-09-10"


def test_no_network_in_extract():
    """No LLM/network call anywhere in _extract/_normalize — pure regex over tag-stripped text."""
    import inspect

    from catalyst_trader.providers import pdufa_edgar

    src = inspect.getsource(pdufa_edgar._extract) + inspect.getsource(pdufa_edgar._normalize)
    # bs4's .get_text() is local parsing, not network — guard only _http fetches + HTTP/LLM libs.
    assert not re.search(r"get_json|_http|httpx|requests|urllib|anthropic|openai", src)


# ── Task 2: efts discovery (CIK-filtered) + exhibit fetch + single-source Catalyst emit ──────

import json  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from catalyst_trader.calendar import verify  # noqa: E402
from catalyst_trader.config import settings  # noqa: E402
from catalyst_trader.models import SourceType  # noqa: E402

_CIK = {"IMNM": 1476964, "CAPR": 1133869, "TOPL": 1820875}
_IMNM_FRAG = "000119312526344577"  # accession no-dashes, in the built exhibit URL
_CAPR_FRAG = "000110465926059380"
_READOUT_FRAG = "000162828024025999"  # readout 8-K accession no-dashes


class _FakeCompany:
    def __init__(self, cik):
        self.cik = cik


def _efts_fixture():
    return json.loads((Path(__file__).parent / "fixtures" / "efts_pdufa_hits.json").read_text())


def _wire(monkeypatch, *, efts, text_map, tmp_csv):
    """Monkeypatch the whole offline surface: efts get_json, exhibit get_text (routed by URL
    fragment), edgar.Company (ticker->CIK), the SEC UA, and the review-CSV constant. NO network."""
    import edgar as edgar_lib

    from catalyst_trader.providers import pdufa_edgar

    monkeypatch.setattr(settings, "sec_user_agent", "Zamvar Capital research@zamvar.example")
    monkeypatch.setattr(edgar_lib, "set_identity", lambda ua: None)
    monkeypatch.setattr(edgar_lib, "Company", lambda t, *a, **k: _FakeCompany(_CIK[t.upper()]))
    monkeypatch.setattr(pdufa_edgar, "get_json", lambda *a, **k: efts)

    def _fake_get_text(source, url, **k):
        for frag, val in text_map.items():
            if frag in url:
                return val
        return None

    monkeypatch.setattr(pdufa_edgar, "get_text", _fake_get_text)
    monkeypatch.setattr(pdufa_edgar, "_CURATED_CSV", tmp_csv)
    return pdufa_edgar


def _by_ticker(cats, ticker):
    return next((c for c in cats if c.ticker == ticker), None)


def test_fetch_cik_filter_drops_out_of_universe(monkeypatch, tmp_path):
    pe = _wire(
        monkeypatch,
        efts=_efts_fixture(),
        text_map={_IMNM_FRAG: _load_htm("edgar_8k_imnm.htm"), _CAPR_FRAG: _load_htm("edgar_8k_capr.htm")},
        tmp_csv=tmp_path / "pdufa_curated.csv",
    )
    out = pe.fetch(["IMNM", "CAPR"], "2026-01-01", "2026-12-31")
    assert {c.ticker for c in out} == {"IMNM", "CAPR"}  # out-of-universe CIK dropped (no fuzzy title)


def test_fetch_emits_single_sec_edgar_primary(monkeypatch, tmp_path):
    pe = _wire(
        monkeypatch,
        efts=_efts_fixture(),
        text_map={_IMNM_FRAG: _load_htm("edgar_8k_imnm.htm"), _CAPR_FRAG: _load_htm("edgar_8k_capr.htm")},
        tmp_csv=tmp_path / "pdufa_curated.csv",
    )
    out = pe.fetch(["IMNM", "CAPR"], "2026-01-01", "2026-12-31")
    imnm = _by_ticker(out, "IMNM")
    assert imnm is not None
    assert imnm.event_date == "2027-04-28"
    assert len(imnm.sources) == 1
    src = imnm.sources[0]
    assert src.source_name == "SEC EDGAR"
    assert src.source_type == SourceType.primary
    assert _IMNM_FRAG in src.source_url  # authoritative accession exhibit URL
    assert src.published_date == "2026-08-11"  # point-in-time: the 8-K filing_date
    assert imnm.external_ref == "pdufa_edgar:IMNM:0001193125-26-344577"


def test_fetch_catalyst_self_verifies(monkeypatch, tmp_path):
    pe = _wire(
        monkeypatch,
        efts=_efts_fixture(),
        text_map={_IMNM_FRAG: _load_htm("edgar_8k_imnm.htm"), _CAPR_FRAG: _load_htm("edgar_8k_capr.htm")},
        tmp_csv=tmp_path / "pdufa_curated.csv",
    )
    out = pe.fetch(["IMNM", "CAPR"], "2026-01-01", "2026-12-31")
    imnm = _by_ticker(out, "IMNM")
    # the single-EDGAR-8K-self-verifies invariant, proven against the REAL verify.py (zero edit)
    assert verify._authoritative_single(imnm.sources) is True


def test_fetch_medium_routes_to_review_csv_not_emitted(monkeypatch, tmp_path):
    tmp_csv = tmp_path / "pdufa_curated.csv"
    # single IMNM hit whose exhibit is MEDIUM ("target action date" without a PDUFA token)
    efts = {"hits": {"hits": [
        {"_id": "0001193125-26-344577:d.htm",
         "_source": {"ciks": ["0001476964"], "display_names": ["Immunome, Inc. (IMNM)"], "file_date": "2026-08-11"}}
    ]}}
    medium_html = "<p>The FDA set a target action date of August 22, 2026 for the application.</p>"
    pe = _wire(monkeypatch, efts=efts, text_map={_IMNM_FRAG: medium_html}, tmp_csv=tmp_csv)

    out = pe.fetch(["IMNM"], "2026-01-01", "2026-12-31")
    assert out == []  # MEDIUM never auto-emitted as tradeable

    body = tmp_csv.read_text()
    lines = [ln for ln in body.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert lines[0].startswith("# ")  # #-commented -> verify.load_curated_pdufa SKIPS it (human gate)
    assert "SEC EDGAR" in lines[0] and "2026-08-22" in lines[0] and _IMNM_FRAG in lines[0]

    pe.fetch(["IMNM"], "2026-01-01", "2026-12-31")  # re-run
    assert len([ln for ln in tmp_csv.read_text().splitlines() if ln.strip()]) == 1  # idempotent


def test_fetch_efts_degrades(monkeypatch, tmp_path):
    pe = _wire(monkeypatch, efts=None, text_map={}, tmp_csv=tmp_path / "c.csv")
    assert pe.fetch(["IMNM", "CAPR"], "2026-01-01", "2026-12-31") == []  # no raise


def test_fetch_exhibit_degrades(monkeypatch, tmp_path):
    pe = _wire(
        monkeypatch,
        efts=_efts_fixture(),
        text_map={_IMNM_FRAG: _load_htm("edgar_8k_imnm.htm")},  # CAPR url -> None (missing)
        tmp_csv=tmp_path / "c.csv",
    )
    out = pe.fetch(["IMNM", "CAPR"], "2026-01-01", "2026-12-31")
    assert {c.ticker for c in out} == {"IMNM"}  # CAPR exhibit degraded -> skipped, IMNM still emits


# ── Task 1 (UNIV-08): trial-RESULT 8-Ks -> day-precision measurable trial_readout ────────────


def _readout_efts_fixture():
    return json.loads((Path(__file__).parent / "fixtures" / "efts_readout_hits.json").read_text())


def test_extract_readout_emits_day_precision():
    """A topline-result 8-K (no PDUFA/AdCom date) -> exactly one HIGH day-precision trial_readout
    keyed on the filing_date (the announcement day IS the event)."""
    from catalyst_trader.providers import pdufa_edgar

    out = pdufa_edgar._extract(_load_htm("edgar_8k_readout.htm"), "2024-05-31")
    assert len(out) == 1
    c = out[0]
    assert c["catalyst_type"] == CatalystType.trial_readout
    assert c["event_date"] == "2024-05-31"  # == filing_date, day precision
    assert c["filing_date"] == "2024-05-31"
    assert c["confidence"] == "HIGH"


def test_extract_readout_negative_still_captured():
    """A FAILED readout ('did not meet the primary endpoint') is a big measurable move -> MUST count."""
    from catalyst_trader.providers import pdufa_edgar

    html = (
        "<p>The Company today announced that its Phase 3 trial "
        "<b>did not meet</b> its <span>primary endpoint</span>.</p>"
    )
    out = pdufa_edgar._extract(html, "2024-05-31")
    assert len(out) == 1
    assert out[0]["catalyst_type"] == CatalystType.trial_readout


def test_extract_pdufa_precedence_no_false_readout():
    """PDUFA PRECEDENCE: an 8-K with BOTH a target-action date AND topline-result language emits the
    PDUFA candidate ONLY — never also a trial_readout (no double-count / no misclassification)."""
    from catalyst_trader.providers import pdufa_edgar

    html = (
        "<p>The FDA accepted our NDA with a PDUFA target action date of April 28, 2027.</p>"
        "<p>The submission was supported by <span>topline results</span> that "
        "<b>met the primary endpoint</b>.</p>"
    )
    out = pdufa_edgar._extract(html, "2024-05-31")
    assert [c["catalyst_type"] for c in out] == [CatalystType.pdufa]
    assert all(c["catalyst_type"] != CatalystType.trial_readout for c in out)


def test_extract_non_result_8k_not_emitted():
    """cite-or-drop: bare 'primary endpoint' in trial-DESIGN context (no completion phrase) -> []."""
    from catalyst_trader.providers import pdufa_edgar

    html = (
        "<p>The trial has been initiated; the <span>primary endpoint</span> is overall "
        "survival and enrollment is ongoing.</p>"
    )
    assert pdufa_edgar._extract(html, "2024-05-31") == []


def test_extract_readout_requires_day_precision_filing_date():
    """No day-precision filing_date -> no anchorable move -> no readout (cite-or-drop)."""
    from catalyst_trader.providers import pdufa_edgar

    html = _load_htm("edgar_8k_readout.htm")
    assert pdufa_edgar._extract(html, "2024-05") == []  # month precision
    assert pdufa_edgar._extract(html, None) == []       # missing filing_date


def test_fetch_emits_readout_single_sec_edgar_primary(monkeypatch, tmp_path):
    pe = _wire(
        monkeypatch,
        efts=_readout_efts_fixture(),
        text_map={_READOUT_FRAG: _load_htm("edgar_8k_readout.htm")},
        tmp_csv=tmp_path / "c.csv",
    )
    out = pe.fetch(["TOPL"], "2024-01-01", "2024-12-31")
    assert len(out) == 1
    c = out[0]
    assert c.catalyst_type == CatalystType.trial_readout
    assert c.event_date == "2024-05-31"  # == filing_date (a PAST day, never the FORWARD calendar)
    assert len(c.sources) == 1
    src = c.sources[0]
    assert src.source_name == "SEC EDGAR"
    assert src.source_type == SourceType.primary
    assert _READOUT_FRAG in src.source_url
    assert verify._authoritative_single(c.sources) is True  # self-verifies, zero verify.py change


def test_no_network_in_readout_extract():
    """The readout branch is pure regex (no network/LLM) and lives INSIDE _extract."""
    import inspect

    from catalyst_trader.providers import pdufa_edgar

    src = inspect.getsource(pdufa_edgar._extract)
    assert "_READOUT_RX" in src  # readout classification is in _extract (not a separate fetch)
    assert not re.search(r"get_json|_http|httpx|requests|urllib|anthropic|openai", src)
