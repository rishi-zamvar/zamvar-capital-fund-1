"""SEC EDGAR provider (edgar.py), edgartools-backed — offline.

edgar.fetch resolves the CIK INTERNALLY via edgartools (Company(ticker)) and returns ONLY what
desk/company_scan.build_card consumes — seen_accessions (list of {accession, form, filing_date})
+ live_shelf (bool) + provenance. edgar.fundamentals adds the float/runway gap-filler
(shares_outstanding + cash_runway_months) from XBRL facts.

Money-path guards: a declared SEC UA is required (settings.sec_user_agent; unset -> RuntimeError,
never an empty UA — Pitfall 3); any edgartools error / unknown ticker / missing facts degrades to
None (never raise into the pipeline, never fabricate a runway). ZERO live API here — edgartools
(edgar.Company / edgar.set_identity) is mocked against the REAL introspected typed-object surface
(edgartools 5.49.0): Company.cik / Company.get_filings(form=[...]) -> iterable of EntityFiling
(.accession_no/.form/.filing_date as datetime.date); Company.get_facts() -> EntityFacts.get_concept
(name, return_metadata=True) -> {value, period, period_end, filing_date, ...}. This pins the mock to
the introspected names so offline-green survives Plan 07's live run (anti yfinance-MultiIndex guard).
"""

from datetime import date

import edgar as edgar_lib
import pytest

from catalyst_trader.config import settings
from catalyst_trader.providers import edgar


# --- fakes pinned to the introspected edgartools surface -------------------------------------


class _FakeFiling:
    """Mirrors edgar.entity.filings.EntityFiling: .accession_no (str), .form (str),
    .filing_date (datetime.date)."""

    def __init__(self, accession_no, form, filing_date):
        self.accession_no = accession_no
        self.form = form
        self.filing_date = date.fromisoformat(filing_date)


class _FakeFacts:
    """Mirrors edgar.entity.entity_facts.EntityFacts.get_concept(name, return_metadata=True)."""

    def __init__(self, concepts):
        self._c = concepts  # {standardized_name: metadata_dict}

    def get_concept(self, concept_name, period=None, unit=None, return_metadata=False):
        d = self._c.get(concept_name)
        if d is None:
            return None
        return dict(d) if return_metadata else d["value"]


class _FakeCompany:
    """Mirrors edgar.Company: .cik (int), .get_filings(form=[...]) (edgartools prefix-matches
    the form list), .get_facts()."""

    def __init__(self, cik, filings, facts):
        self.cik = cik
        self._filings = filings
        self._facts = facts

    def get_filings(self, form=None, **kw):
        if not form:
            return list(self._filings)
        return [f for f in self._filings if any(f.form.startswith(x) for x in form)]

    def get_facts(self):
        return self._facts


def _company_from_fixture(data):
    filings = [_FakeFiling(**f) for f in data["filings"]]
    return _FakeCompany(data["cik"], filings, _FakeFacts(data.get("facts", {})))


# --- fixtures --------------------------------------------------------------------------------


@pytest.fixture
def _sec_ua(monkeypatch):
    monkeypatch.setattr(settings, "sec_user_agent", "Zamvar Capital research@zamvar.example")
    return settings.sec_user_agent


@pytest.fixture
def _patch_edgar(monkeypatch, load_fixture):
    """Patch edgartools so Company(ticker) resolves internally to the fixture-backed fake and
    set_identity is a no-op recorder. NEVER hits the network."""
    data = load_fixture("edgar_facts")
    calls = {"set_identity": [], "companies": []}

    def _fake_company(ticker, *a, **kw):
        calls["companies"].append(ticker)
        return _company_from_fixture(data)

    monkeypatch.setattr(edgar_lib, "set_identity", lambda ua: calls["set_identity"].append(ua))
    monkeypatch.setattr(edgar_lib, "Company", _fake_company)
    return calls


# --- Task 1: fetch() — CIK-internal, seen_accessions/live_shelf contract preserved ------------


def test_edgar_fetch_resolves_cik_internally(_sec_ua, _patch_edgar):
    # NO cik arg — edgartools Company(ticker) resolves it internally (the shakedown gap fix).
    out = edgar.fetch("KURA")
    assert _patch_edgar["companies"] == ["KURA"]  # ticker went straight to edgartools
    assert out["seen_accessions"] and out["live_shelf"] is True


def test_edgar_fetch_keeps_contract_keys(_sec_ua, _patch_edgar):
    out = edgar.fetch("KURA")
    # EXACT build_card contract: seen_accessions (rows of accession/form/filing_date) + live_shelf.
    assert set(out) == {"seen_accessions", "live_shelf", "provenance"}
    assert isinstance(out["live_shelf"], bool)
    row = out["seen_accessions"][0]
    assert set(row) == {"accession", "form", "filing_date"}
    assert isinstance(row["accession"], str) and isinstance(row["filing_date"], str)
    accessions = {a["accession"] for a in out["seen_accessions"]}
    assert "0001193125-26-000123" in accessions
    assert out["provenance"]["grade"] == "green"
    assert out["provenance"]["source_url"] and out["provenance"]["fetch_ts"]


def test_edgar_fetch_filters_to_offering_forms(_sec_ua, _patch_edgar):
    # get_filings is scoped to the forms build_card reads (424B5/FWP/S-3/S-3ASR); the fixture's
    # 8-K is filtered out so seen_accessions stays the offering-signal surface.
    out = edgar.fetch("KURA")
    forms = {a["form"] for a in out["seen_accessions"]}
    assert "8-K" not in forms
    assert {"S-3ASR", "424B5", "S-3", "FWP"} == forms


def test_edgar_live_shelf_detects_s3(_sec_ua, monkeypatch, load_fixture):
    data = load_fixture("edgar_facts")
    # strip every shelf form -> live_shelf False; a 424B5 still present so rows are non-empty.
    data["filings"] = [f for f in data["filings"] if f["form"] not in {"S-3", "S-3ASR"}]
    monkeypatch.setattr(edgar_lib, "set_identity", lambda ua: None)
    monkeypatch.setattr(edgar_lib, "Company", lambda t, *a, **k: _company_from_fixture(data))
    out = edgar.fetch("KURA")
    assert out["live_shelf"] is False
    assert out["seen_accessions"]  # 424B5/FWP remain


def test_edgar_unknown_ticker_degrades(_sec_ua, monkeypatch):
    def _raise(ticker, *a, **k):
        raise edgar_lib.CompanyNotFoundError(f"Company not found: {ticker!r}")

    monkeypatch.setattr(edgar_lib, "set_identity", lambda ua: None)
    monkeypatch.setattr(edgar_lib, "Company", _raise)
    assert edgar.fetch("ZZZZNOTREAL") is None  # degrade, no exception


def test_edgar_missing_identity_raises(monkeypatch):
    monkeypatch.setattr(settings, "sec_user_agent", None)
    with pytest.raises(RuntimeError):  # config error, not a degrade (never send an empty UA)
        edgar.fetch("KURA")
