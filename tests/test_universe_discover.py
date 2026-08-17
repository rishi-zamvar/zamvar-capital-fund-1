"""Data-driven candidate discovery (universe/discover.py) — offline (Phase 6.12 Plan 01).

Two free feeds, both the REVERSE of how the shipped providers run:
  - CT.gov reverse-sponsor: UNFILTERED near-term Ph2/Ph3 -> leadSponsor.name -> ticker via the
    inverted ticker_sponsor_map; an unmapped sponsor routes to a human-review queue (NEVER fuzzy).
  - EDGAR unfiltered efts PDUFA: no universe-CIK intersection; ticker parsed PER HIT from
    display_names ("Name (TICKER) (CIK ...)"); CIK key = int(ciks[0]).
Both merge into ONE CIK-keyed candidate dict carrying live-parity catalyst evidence.
ZERO live API — the CT.gov client, efts get_json, exhibit get_text and edgar.Company are all faked.
"""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# Fake ticker->CIK resolution (edgar.Company(t).cik) used across the suite.
_CIK = {"BCRX": 882796, "IMNM": 1476964, "CAPR": 1133869, "KURA": 1618181}


class _FakeCompany:
    def __init__(self, cik):
        self.cik = cik


class _FakeResp:
    def __init__(self, payload, *, raise_exc=None):
        self._payload = payload
        self._raise = raise_exc

    def raise_for_status(self):
        if self._raise is not None:
            raise self._raise

    def json(self):
        return self._payload


class _FakeClient:
    """Minimal httpx.Client stand-in: .get(url, params=) -> _FakeResp. No network."""

    def __init__(self, payload, *, raise_exc=None):
        self._payload = payload
        self._raise = raise_exc
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        return _FakeResp(self._payload, raise_exc=self._raise)


def _ctgov_fixture():
    return json.loads((FIXTURES / "ctgov_readouts_universe.json").read_text())


def _efts_fixture():
    return json.loads((FIXTURES / "efts_pdufa_universe.json").read_text())


def _load_htm(name):
    return (FIXTURES / name).read_text()


def _fake_identity(monkeypatch):
    import edgar as edgar_lib

    from catalyst_trader.config import settings

    monkeypatch.setattr(settings, "sec_user_agent", "Zamvar Capital research@zamvar.example")
    monkeypatch.setattr(edgar_lib, "set_identity", lambda ua: None)
    monkeypatch.setattr(edgar_lib, "Company", lambda t, *a, **k: _FakeCompany(_CIK[t.upper()]))


# ── Task 1: reverse-sponsor CT.gov discovery ──────────────────────────────────────────────


def test_reverse_map_inverts_including_multiname():
    """BBIO's two legal names both invert to 'BBIO'; casefolded keys."""
    from catalyst_trader.providers import clinicaltrials
    from catalyst_trader.universe import discover

    rev = discover._reverse_sponsor_map(clinicaltrials.load_sponsor_map())
    assert rev["qed therapeutics, a bridgebio company".casefold()] == "BBIO"
    assert rev["calcilytix therapeutics, inc., a bridgebio company".casefold()] == "BBIO"
    assert rev["biocryst pharmaceuticals"] == "BCRX"


def test_ctgov_resolves_mapped_sponsor(monkeypatch, tmp_path):
    from catalyst_trader.universe import discover

    _fake_identity(monkeypatch)
    monkeypatch.setattr(discover, "_SPONSOR_REVIEW_CSV", tmp_path / "review.csv")
    client = _FakeClient(_ctgov_fixture())
    out = discover.discover_ctgov("2026-08-17", "2027-08-17", client=client)

    assert _CIK["BCRX"] in out  # mapped lead sponsor -> CIK-keyed candidate
    cand = out[_CIK["BCRX"]]
    assert cand["ticker"] == "BCRX"
    assert cand["source_feeds"] == {"ctgov"}
    cats = cand["catalysts"]
    assert len(cats) == 1
    assert cats[0]["type"] == "trial_readout"
    assert cats[0]["event_date"] == "2026-11-30"
    assert "NCT06000001" in cats[0]["source_url"]
    assert cats[0]["fetch_ts"] and cats[0]["grade"]


def test_ctgov_unknown_sponsor_routes_to_review_not_fuzzy(monkeypatch, tmp_path):
    from catalyst_trader.universe import discover

    _fake_identity(monkeypatch)
    review = tmp_path / "review.csv"
    monkeypatch.setattr(discover, "_SPONSOR_REVIEW_CSV", review)
    client = _FakeClient(_ctgov_fixture())
    out = discover.discover_ctgov("2026-08-17", "2027-08-17", client=client)

    # Nurix is NOT in the curated map -> never fuzzy-attributed to a ticker.
    assert all(c["ticker"] != "NURIX" for c in out.values())
    assert not any("Nurix" in (c.get("company_name") or "") for c in out.values())
    body = review.read_text()
    assert "Nurix Therapeutics, Inc." in body
    assert body.lstrip().startswith("#")  # #-commented review row (human gate)

    # idempotent: a re-run does not duplicate the review row.
    discover.discover_ctgov("2026-08-17", "2027-08-17", client=_FakeClient(_ctgov_fixture()))
    lines = [ln for ln in review.read_text().splitlines() if "Nurix" in ln]
    assert len(lines) == 1


def test_ctgov_drops_non_phase23(monkeypatch, tmp_path):
    from catalyst_trader.universe import discover

    _fake_identity(monkeypatch)
    monkeypatch.setattr(discover, "_SPONSOR_REVIEW_CSV", tmp_path / "review.csv")
    out = discover.discover_ctgov("2026-08-17", "2027-08-17", client=_FakeClient(_ctgov_fixture()))
    # Kura's study is PHASE1 -> not admitted even though the sponsor IS mapped.
    assert _CIK["KURA"] not in out


def test_ctgov_degrades(monkeypatch, tmp_path):
    from catalyst_trader.universe import discover

    _fake_identity(monkeypatch)
    monkeypatch.setattr(discover, "_SPONSOR_REVIEW_CSV", tmp_path / "review.csv")
    boom = _FakeClient(None, raise_exc=RuntimeError("HTTP 500"))
    assert discover.discover_ctgov("2026-08-17", "2027-08-17", client=boom) == {}  # no raise


# ── Task 2: unfiltered efts PDUFA discovery + CIK-keyed merge ──────────────────────────────

_IMNM_FRAG = "000119312526344577"
_CAPR_FRAG = "000110465926059380"


def _wire_edgar(monkeypatch, *, efts, text_map):
    from catalyst_trader.universe import discover

    _fake_identity(monkeypatch)
    monkeypatch.setattr(discover, "get_json", lambda *a, **k: efts)

    def _fake_get_text(source, url, **k):
        for frag, val in text_map.items():
            if frag in url:
                return val
        return None

    monkeypatch.setattr(discover, "get_text", _fake_get_text)
    return discover


def test_edgar_unfiltered_discovers_new_ticker(monkeypatch):
    """A hit for a ticker NOT in today's seed universe is returned (no CIK-intersection filter)."""
    discover = _wire_edgar(
        monkeypatch,
        efts=_efts_fixture(),
        text_map={_IMNM_FRAG: _load_htm("edgar_8k_imnm.htm"),
                  _CAPR_FRAG: _load_htm("edgar_8k_capr.htm")},
    )
    out = discover.discover_edgar("2026-01-01", "2026-12-31")
    assert _CIK["IMNM"] in out  # IMNM is not in the 19-name seed universe -> proves un-filtering
    cand = out[_CIK["IMNM"]]
    assert cand["ticker"] == "IMNM"
    assert cand["source_feeds"] == {"edgar"}
    cats = cand["catalysts"]
    assert any(c["type"] == "pdufa" and c["event_date"] == "2027-04-28" for c in cats)
    assert any(_IMNM_FRAG in c["source_url"] for c in cats)


def test_edgar_ticker_per_hit_from_display_names(monkeypatch):
    """The trailing-CIK display_name trap: 'Immunome, Inc. (IMNM) (CIK 0001476964)' -> 'IMNM'
    (NOT 'CIK', NOT dropped); CIK key = int(ciks[0])."""
    from catalyst_trader.universe import discover

    assert discover._ticker_from_display("Immunome, Inc. (IMNM) (CIK 0001476964)") == "IMNM"
    assert discover._ticker_from_display("Capricor Therapeutics, Inc. (CAPR) (CIK 0001133869)") == "CAPR"

    d = _wire_edgar(
        monkeypatch,
        efts=_efts_fixture(),
        text_map={_IMNM_FRAG: _load_htm("edgar_8k_imnm.htm"),
                  _CAPR_FRAG: _load_htm("edgar_8k_capr.htm")},
    )
    out = d.discover_edgar("2026-01-01", "2026-12-31")
    assert _CIK["IMNM"] in out and _CIK["CAPR"] in out


def test_edgar_no_ticker_suffix_dropped(monkeypatch):
    """cite-or-drop: a display_name with no '(TICKER)' suffix is dropped (never keyed as 'CIK')."""
    from catalyst_trader.universe import discover

    assert discover._ticker_from_display("Private Biotech Holdings LLC (CIK 0001999999)") is None
    d = _wire_edgar(
        monkeypatch,
        efts=_efts_fixture(),
        text_map={_IMNM_FRAG: _load_htm("edgar_8k_imnm.htm"),
                  _CAPR_FRAG: _load_htm("edgar_8k_capr.htm")},
    )
    out = d.discover_edgar("2026-01-01", "2026-12-31")
    assert 1999999 not in out  # the no-suffix hit never becomes a candidate


def test_merge_by_cik_unions_catalysts(monkeypatch, tmp_path):
    """A CIK in BOTH feeds -> one candidate row with a trial_readout (CT.gov) + a pdufa (EDGAR)
    and source_feeds == {ctgov, edgar}; never a duplicate CIK."""
    from catalyst_trader.universe import discover

    _fake_identity(monkeypatch)
    monkeypatch.setattr(discover, "_SPONSOR_REVIEW_CSV", tmp_path / "review.csv")
    monkeypatch.setattr(discover, "get_json", lambda *a, **k: _efts_fixture())

    def _fake_get_text(source, url, **k):
        for frag, val in {_IMNM_FRAG: _load_htm("edgar_8k_imnm.htm"),
                          _CAPR_FRAG: _load_htm("edgar_8k_capr.htm")}.items():
            if frag in url:
                return val
        return None

    monkeypatch.setattr(discover, "get_text", _fake_get_text)

    out = discover.discover_candidates(
        "2026-08-17", "2027-08-17", client=_FakeClient(_ctgov_fixture())
    )
    imnm = out[_CIK["IMNM"]]
    types = {c["type"] for c in imnm["catalysts"]}
    assert "trial_readout" in types and "pdufa" in types
    assert imnm["source_feeds"] == {"ctgov", "edgar"}
    # No duplicate CIK rows anywhere.
    assert len(out) == len({k for k in out})


def test_merge_degrades_one_feed(monkeypatch, tmp_path):
    """efts get_json None -> the merged dict still contains the CT.gov candidates."""
    from catalyst_trader.universe import discover

    _fake_identity(monkeypatch)
    monkeypatch.setattr(discover, "_SPONSOR_REVIEW_CSV", tmp_path / "review.csv")
    monkeypatch.setattr(discover, "get_json", lambda *a, **k: None)  # efts degrades
    monkeypatch.setattr(discover, "get_text", lambda *a, **k: None)

    out = discover.discover_candidates(
        "2026-08-17", "2027-08-17", client=_FakeClient(_ctgov_fixture())
    )
    assert _CIK["BCRX"] in out  # CT.gov feed survived the EDGAR degrade


def test_only_live_parity_types(monkeypatch, tmp_path):
    """No earnings/other type ever appears in candidate evidence — only pdufa/adcom/trial_readout."""
    from catalyst_trader.universe import discover

    _fake_identity(monkeypatch)
    monkeypatch.setattr(discover, "_SPONSOR_REVIEW_CSV", tmp_path / "review.csv")
    monkeypatch.setattr(discover, "get_json", lambda *a, **k: _efts_fixture())

    def _fake_get_text(source, url, **k):
        for frag, val in {_IMNM_FRAG: _load_htm("edgar_8k_imnm.htm"),
                          _CAPR_FRAG: _load_htm("edgar_8k_capr.htm")}.items():
            if frag in url:
                return val
        return None

    monkeypatch.setattr(discover, "get_text", _fake_get_text)
    out = discover.discover_candidates(
        "2026-08-17", "2027-08-17", client=_FakeClient(_ctgov_fixture())
    )
    live_parity = {"pdufa", "adcom", "trial_readout"}
    for cand in out.values():
        for c in cand["catalysts"]:
            assert c["type"] in live_parity
