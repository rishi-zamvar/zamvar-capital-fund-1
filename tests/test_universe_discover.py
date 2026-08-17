"""Data-driven candidate discovery (universe/discover.py) — offline (Phase 6.12 Plan 01).

Two free feeds, both the REVERSE of how the shipped providers run:
  - CT.gov reverse-sponsor: UNFILTERED near-term Ph2/Ph3 -> leadSponsor.name -> ticker via the
    inverted ticker_sponsor_map; an unmapped sponsor routes to a human-review queue (NEVER fuzzy).
  - EDGAR unfiltered efts PDUFA: no universe-CIK intersection; ticker parsed PER HIT from
    display_names ("Name (TICKER) (CIK ...)"); CIK key = int(ciks[0]).
Both merge into ONE CIK-keyed candidate dict carrying live-parity catalyst evidence.
ZERO live API — both feeds' get_json (branched on source), exhibit get_text and edgar.Company faked.
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


def _ctgov_fixture():
    return json.loads((FIXTURES / "ctgov_readouts_universe.json").read_text())


def _efts_fixture():
    return json.loads((FIXTURES / "efts_pdufa_universe.json").read_text())


def _fake_get_json(*, ctgov=None, efts=None):
    """Stand-in for discover.get_json: both feeds now use get_json, so branch on the `source` arg
    ("ctgov_discover" vs "edgar_efts"). A None payload models that feed degrading."""
    def _fn(source, *a, **k):
        return ctgov if source == "ctgov_discover" else efts
    return _fn


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
    monkeypatch.setattr(discover, "get_json", _fake_get_json(ctgov=_ctgov_fixture()))
    out = discover.discover_ctgov("2026-08-17", "2027-08-17")

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
    monkeypatch.setattr(discover, "get_json", _fake_get_json(ctgov=_ctgov_fixture()))
    out = discover.discover_ctgov("2026-08-17", "2027-08-17")

    # Nurix is NOT in the curated map -> never fuzzy-attributed to a ticker.
    assert all(c["ticker"] != "NURIX" for c in out.values())
    assert not any("Nurix" in (c.get("company_name") or "") for c in out.values())
    body = review.read_text()
    assert "Nurix Therapeutics, Inc." in body
    assert body.lstrip().startswith("#")  # #-commented review row (human gate)

    # idempotent: a re-run does not duplicate the review row.
    discover.discover_ctgov("2026-08-17", "2027-08-17")
    lines = [ln for ln in review.read_text().splitlines() if "Nurix" in ln]
    assert len(lines) == 1


def test_ctgov_drops_non_phase23(monkeypatch, tmp_path):
    from catalyst_trader.universe import discover

    _fake_identity(monkeypatch)
    monkeypatch.setattr(discover, "_SPONSOR_REVIEW_CSV", tmp_path / "review.csv")
    monkeypatch.setattr(discover, "get_json", _fake_get_json(ctgov=_ctgov_fixture()))
    out = discover.discover_ctgov("2026-08-17", "2027-08-17")
    # Kura's study is PHASE1 -> not admitted even though the sponsor IS mapped.
    assert _CIK["KURA"] not in out


def test_ctgov_degrades(monkeypatch, tmp_path):
    from catalyst_trader.universe import discover

    _fake_identity(monkeypatch)
    monkeypatch.setattr(discover, "_SPONSOR_REVIEW_CSV", tmp_path / "review.csv")
    monkeypatch.setattr(discover, "get_json", lambda *a, **k: None)  # every page degrades
    assert discover.discover_ctgov("2026-08-17", "2027-08-17") == {}  # no raise, nothing fetched


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
    monkeypatch.setattr(discover, "get_json", _fake_get_json(ctgov=_ctgov_fixture(), efts=_efts_fixture()))

    def _fake_get_text(source, url, **k):
        for frag, val in {_IMNM_FRAG: _load_htm("edgar_8k_imnm.htm"),
                          _CAPR_FRAG: _load_htm("edgar_8k_capr.htm")}.items():
            if frag in url:
                return val
        return None

    monkeypatch.setattr(discover, "get_text", _fake_get_text)

    out = discover.discover_candidates("2026-08-17", "2027-08-17")
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
    monkeypatch.setattr(discover, "get_json", _fake_get_json(ctgov=_ctgov_fixture(), efts=None))  # efts degrades
    monkeypatch.setattr(discover, "get_text", lambda *a, **k: None)

    out = discover.discover_candidates("2026-08-17", "2027-08-17")
    assert _CIK["BCRX"] in out  # CT.gov feed survived the EDGAR degrade


def test_only_live_parity_types(monkeypatch, tmp_path):
    """No earnings/other type ever appears in candidate evidence — only pdufa/adcom/trial_readout."""
    from catalyst_trader.universe import discover

    _fake_identity(monkeypatch)
    monkeypatch.setattr(discover, "_SPONSOR_REVIEW_CSV", tmp_path / "review.csv")
    monkeypatch.setattr(discover, "get_json", _fake_get_json(ctgov=_ctgov_fixture(), efts=_efts_fixture()))

    def _fake_get_text(source, url, **k):
        for frag, val in {_IMNM_FRAG: _load_htm("edgar_8k_imnm.htm"),
                          _CAPR_FRAG: _load_htm("edgar_8k_capr.htm")}.items():
            if frag in url:
                return val
        return None

    monkeypatch.setattr(discover, "get_text", _fake_get_text)
    out = discover.discover_candidates("2026-08-17", "2027-08-17")
    live_parity = {"pdufa", "adcom", "trial_readout"}
    for cand in out.values():
        for c in cand["catalysts"]:
            assert c["type"] in live_parity


# ── Plan 05 Task 1: multi-year efts window (breadth + warm-start backfill) ──────────────────

_MY_FRAGS = {  # accession (dash-stripped) -> exhibit fixture
    "000119312525100001": "edgar_8k_imnm.htm",       # IMNM 2025-03-10 -> PDUFA 2027-04-28
    "000119312522200002": "edgar_8k_imnm_2022.htm",  # IMNM 2022-06-15 -> PDUFA 2023-03-15
    "000110465924300003": "edgar_8k_capr.htm",       # CAPR 2024-05-12 -> PDUFA 2026-08-22
    "000095017021400004": "edgar_8k_kura.htm",       # KURA 2021-07-01 -> PDUFA 2022-01-20
}


def _multiyear_efts():
    return json.loads((FIXTURES / "efts_pdufa_multiyear.json").read_text())


def _my_text():
    def _fn(source, url, **k):
        for frag, name in _MY_FRAGS.items():
            if frag in url:
                return _load_htm(name)
        return None
    return _fn


def _wire_multiyear(monkeypatch, *, hits_for_window, count=None):
    """Wire discover for a multi-year run: ctgov degrades (None), efts returns per-window hits.

    `hits_for_window(startdt, enddt) -> list[hit]` models the real efts API slicing a filing-date
    window. `count` (a list) accumulates edgar_efts call params so a test can assert loop vs override.
    """
    from catalyst_trader.universe import discover

    _fake_identity(monkeypatch)
    monkeypatch.setattr(discover, "_SEC_MAP", {})  # hermetic: no SEC bundled-parquet load
    monkeypatch.setattr(discover, "_SPONSOR_REVIEW_CSV", FIXTURES / "_unused_review.csv")

    def _fn(source, url=None, *, params=None, ua=None, **k):
        if source == "ctgov_discover":
            return None  # ctgov degrades -> isolate the edgar feed
        if count is not None:
            count.append((params["startdt"], params["enddt"]))
        sel = hits_for_window(params["startdt"], params["enddt"])
        return {"hits": {"total": {"value": len(sel)}, "hits": sel}}

    monkeypatch.setattr(discover, "get_json", _fn)
    monkeypatch.setattr(discover, "get_text", _my_text())
    return discover


def test_multiyear_efts_accumulates_history_by_cik(monkeypatch):
    """A CIK with a 2022 AND a 2025 PDUFA -> ONE candidate, TWO catalysts, source_feeds {edgar}
    (the warm-start backfill accumulates each name's full multi-year catalyst history per CIK)."""
    hits = _multiyear_efts()["hits"]["hits"]

    def _win(startdt, enddt):
        return [h for h in hits if startdt <= h["_source"]["file_date"] <= enddt]

    discover = _wire_multiyear(monkeypatch, hits_for_window=_win)
    out = discover.discover_candidates("2026-01-01", "2027-01-01", edgar_years=5)

    imnm = out[_CIK["IMNM"]]
    dates = sorted(c["event_date"] for c in imnm["catalysts"])
    assert dates == ["2023-03-15", "2027-04-28"]  # both years accumulated under one CIK
    assert imnm["source_feeds"] == {"edgar"}
    assert all(c["type"] == "pdufa" for c in imnm["catalysts"])


def test_multiyear_breadth(monkeypatch):
    """Distinct CIKs across 5 years all surface (breadth reaches many names, not just year 0)."""
    hits = _multiyear_efts()["hits"]["hits"]

    def _win(startdt, enddt):
        return [h for h in hits if startdt <= h["_source"]["file_date"] <= enddt]

    discover = _wire_multiyear(monkeypatch, hits_for_window=_win)
    out = discover.discover_candidates("2026-01-01", "2027-01-01", edgar_years=5)
    assert {_CIK["IMNM"], _CIK["CAPR"], _CIK["KURA"]} <= set(out)


def test_accession_dedup_across_years(monkeypatch):
    """The same accession returned in overlapping windows counts ONCE (shared seen_accessions)."""
    hits = _multiyear_efts()["hits"]["hits"]
    one = [h for h in hits if h["_id"].startswith("0001193125-25-100001")]  # IMNM 2025

    discover = _wire_multiyear(monkeypatch, hits_for_window=lambda s, e: one)  # same hit every window
    out = discover.discover_candidates("2026-01-01", "2027-01-01", edgar_years=5)
    assert len(out[_CIK["IMNM"]]["catalysts"]) == 1  # not 5


def test_year_degrade_keeps_others(monkeypatch):
    """One year's efts window degrading keeps the OTHER years' candidates (never raises)."""
    hits = _multiyear_efts()["hits"]["hits"]

    def _win(startdt, enddt):
        if startdt <= "2024-05-12" <= enddt:
            return None and []  # noqa — signal degrade for the CAPR window
        return [h for h in hits if startdt <= h["_source"]["file_date"] <= enddt]

    from catalyst_trader.universe import discover

    _fake_identity(monkeypatch)
    monkeypatch.setattr(discover, "_SEC_MAP", {})
    monkeypatch.setattr(discover, "_SPONSOR_REVIEW_CSV", FIXTURES / "_unused_review.csv")

    def _fn(source, url=None, *, params=None, ua=None, **k):
        if source == "ctgov_discover":
            return None
        if params["startdt"] <= "2024-05-12" <= params["enddt"]:
            return None  # this year's page degraded
        sel = [h for h in hits if params["startdt"] <= h["_source"]["file_date"] <= params["enddt"]]
        return {"hits": {"total": {"value": len(sel)}, "hits": sel}}

    monkeypatch.setattr(discover, "get_json", _fn)
    monkeypatch.setattr(discover, "get_text", _my_text())

    out = discover.discover_candidates("2026-01-01", "2027-01-01", edgar_years=5)
    assert _CIK["CAPR"] not in out  # the degraded window's candidate dropped
    assert _CIK["IMNM"] in out and _CIK["KURA"] in out  # every other year survived


def test_edgar_window_override_still_works(monkeypatch):
    """An explicit edgar_window bypasses the multi-year loop (offline single-window path intact)."""
    hits = _multiyear_efts()["hits"]["hits"]
    calls: list = []

    discover = _wire_multiyear(monkeypatch, hits_for_window=lambda s, e: hits, count=calls)
    out = discover.discover_candidates(
        "2026-01-01", "2027-01-01", edgar_window=("2020-01-01", "2030-12-31")
    )
    # single window -> exactly one call per efts phrase (no 5x loop)
    from catalyst_trader.providers.pdufa_edgar import _EFTS_QUERIES

    assert len(calls) == len(_EFTS_QUERIES)
    assert {_CIK["IMNM"], _CIK["CAPR"], _CIK["KURA"]} <= set(out)
