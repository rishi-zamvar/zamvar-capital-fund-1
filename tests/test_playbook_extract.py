"""Offline TDD for the ATTRIBUTION front-half (playbook.extract, Plan 07.5-03).

Every test is offline and free:
- build_bundle resolves cached lake material by the SAME _safe_name stem the archiver wrote
  (providers/_http.py), so the URL -> file join is reproduced deterministically. Two tests point
  at REAL files in data/raw/edgar_8k to prove the stem->file join actually resolves (and that the
  CIK-filter disambiguates the ex99-1.htm cross-company collision).
- extract_record takes an INJECTED complete_fn (a lambda returning fixture JSON) — never a live LLM.
"""

import json
from pathlib import Path

import pytest

from catalyst_trader.providers._http import _key, _safe_name

FIXTURES = Path(__file__).parent / "fixtures" / "playbook"
REAL_LAKE = Path(__file__).resolve().parents[1] / "data" / "raw"

# Real peer catalysts (verified in catalyst.db). Own CIK is the /data/<CIK>/ segment.
KRYS_URL = "https://www.sec.gov/Archives/edgar/data/1711279/000171127922000052/fdaacceptskrystalbiotech.htm"
KRYS_CIK = 1711279
LPCN_OWN_URL = "https://www.sec.gov/Archives/edgar/data/1535955/000149315222003057/ex99-1.htm"
LPCN_CROSS_URL = "https://www.sec.gov/Archives/edgar/data/1576885/000157688525000102/acumen_ncxcorporatexdeck.htm"
LPCN_CIK = 1535955


# ── seeding helpers ──────────────────────────────────────────────────────────

def _seed_catalyst(conn, *, ticker="KRYS", ctype="pdufa", event_date="2023-02-17",
                   precision="day", company="Krystal Biotech, Inc."):
    cur = conn.execute(
        "INSERT INTO catalyst (ticker, company_name, catalyst_type, event_date, date_precision, "
        "uncertainty_type, status, source_origin, created_at, updated_at) "
        "VALUES (?,?,?,?,?, 'firm','resolved','curated_pdufa','2026-01-01','2026-01-01')",
        (ticker, company, ctype, event_date, precision),
    )
    conn.commit()
    return cur.lastrowid


def _seed_source(conn, cid, url, *, name="edgar", reported_date="2023-02-17"):
    conn.execute(
        "INSERT INTO catalyst_source (catalyst_id, source_name, source_url, source_type, "
        "reported_date, retrieved_at) VALUES (?,?,?, 'primary', ?, '2026-01-01')",
        (cid, name, url, reported_date),
    )
    conn.commit()


def _seed_move(conn, cid, move, *, window="(-1,2)", knowable="2023-02-22"):
    conn.execute(
        "INSERT INTO catalyst_move (catalyst_id, realized_move, move_window, knowable_asof, "
        "computed_at) VALUES (?,?,?,?, '2026-01-01')",
        (cid, move, window, knowable),
    )
    conn.commit()


def _write_lake_file(lake_root: Path, url: str, text: str, *, ts="20230217T120000000000"):
    """Archive `text` at the EXACT stem the _http archiver would write for `url`, so build_bundle's
    stem-join resolves it — the offline mirror of the real-lake resolution the NIT flagged."""
    stem = _safe_name(_key("text", "edgar_8k", url, None, None))
    d = lake_root / "edgar_8k" / "2023" / "02"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}_{ts}.txt").write_text(text)


def _bundle(**over):
    """A minimal event-proximate bundle (the contract build_bundle returns), for extract unit tests."""
    b = dict(
        catalyst_id=271, ticker="KRYS", catalyst_type="pdufa",
        indication="DEB", modality="gene therapy", event_date="2023-02-17",
        exhibit_text="FDA Accepts Krystal Biotech ... PDUFA target action date is February 17, 2023.",
        ctgov=None, signed_move=0.052, move_window="(-1,2)", knowable_asof="2023-02-22",
        date_precision="day",
    )
    b.update(over)
    return b


def _completion(**over):
    data = json.loads((FIXTURES / "extract_krys_271.json").read_text())
    data.update(over)
    return json.dumps(data)


# ── cik_filter_exhibits ──────────────────────────────────────────────────────

def test_given_mixed_ciks_when_cik_filter_then_keeps_only_own_company():
    from catalyst_trader.playbook.extract import cik_filter_exhibits
    kept = cik_filter_exhibits([LPCN_OWN_URL, LPCN_CROSS_URL], LPCN_CIK)
    assert kept == [LPCN_OWN_URL]  # the Acumen (1576885) deck is dropped


def test_given_no_own_cik_url_when_cik_filter_then_empty():
    from catalyst_trader.playbook.extract import cik_filter_exhibits
    assert cik_filter_exhibits([LPCN_CROSS_URL], LPCN_CIK) == []


# ── build_bundle (offline tmp lake) ──────────────────────────────────────────

def test_given_seeded_catalyst_when_build_bundle_then_cik_filtered_exhibit_text(db, tmp_path):
    from catalyst_trader.playbook.extract import build_bundle
    cid = _seed_catalyst(db)
    _seed_source(db, cid, KRYS_URL)
    _seed_source(db, cid, LPCN_CROSS_URL)  # cross-company contamination
    _seed_move(db, cid, 0.052)
    lake = tmp_path / "raw"
    _write_lake_file(lake, KRYS_URL, (FIXTURES / "krys_271_8k.txt").read_text())

    bundle = build_bundle(db, cid, own_cik=KRYS_CIK, lake_dir=str(lake),
                          profiles=[{"ticker": "KRYS", "profile": {
                              "indication": "DEB", "modality": "gene therapy"}}])
    assert "Krystal Biotech" in bundle["exhibit_text"]
    assert "Acumen" not in (bundle["exhibit_text"] or "")  # cross-company dropped
    assert bundle["signed_move"] == pytest.approx(0.052)
    assert bundle["indication"] == "DEB"
    assert bundle["catalyst_type"] == "pdufa"


def test_given_month_precision_when_build_bundle_then_signed_move_none(db, tmp_path):
    from catalyst_trader.playbook.extract import build_bundle
    cid = _seed_catalyst(db, event_date="2023-02", precision="month")
    _seed_source(db, cid, KRYS_URL)
    lake = tmp_path / "raw"
    _write_lake_file(lake, KRYS_URL, "some PR text")
    bundle = build_bundle(db, cid, own_cik=KRYS_CIK, lake_dir=str(lake), profiles=[])
    assert bundle["signed_move"] is None  # no catalyst_move row => corroboration unavailable
    assert bundle["date_precision"] == "month"


# ── build_bundle against the REAL lake (the NIT's mandated join proof) ────────

@pytest.mark.skipif(
    not list(REAL_LAKE.glob("edgar_8k/**/fdaacceptskrystalbiotech.htm_*.txt")),
    reason="real KRYS lake file absent",
)
def test_given_real_lake_krys_when_build_bundle_then_resolves_real_file(db):
    from catalyst_trader.playbook.extract import build_bundle
    cid = _seed_catalyst(db)
    _seed_source(db, cid, KRYS_URL)
    _seed_move(db, cid, 0.052)
    bundle = build_bundle(db, cid, own_cik=KRYS_CIK, lake_dir=str(REAL_LAKE), profiles=[])
    # proves the URL -> _safe_name stem -> real archived file join actually resolves
    assert bundle["exhibit_text"] and "Krystal Biotech" in bundle["exhibit_text"]


@pytest.mark.skipif(
    not list(REAL_LAKE.glob("edgar_8k/**/ex99-1.htm_*.txt")),
    reason="real LPCN lake file absent",
)
def test_given_real_lake_lpcn_when_build_bundle_then_disambiguates_ex99(db):
    """ex99-1.htm is a cross-company collision in the lake; the CIK-filter + exact-stem join must
    resolve to LPCN's own ex99-1, NOT some other company's ex99-1 or the Acumen deck."""
    from catalyst_trader.playbook.extract import build_bundle
    cid = _seed_catalyst(db, ticker="LPCN", ctype="pdufa", event_date="2022-03-28",
                         company="Lipocine Inc.")
    _seed_source(db, cid, LPCN_CROSS_URL, reported_date="2025-11-12")
    _seed_source(db, cid, LPCN_OWN_URL, reported_date="2022-03-28")
    _seed_move(db, cid, -0.281, knowable="2022-03-30")
    bundle = build_bundle(db, cid, own_cik=LPCN_CIK, lake_dir=str(REAL_LAKE), profiles=[])
    assert bundle["exhibit_text"] and "LIPOCINE" in bundle["exhibit_text"].upper()
    assert "ACUMEN" not in bundle["exhibit_text"].upper()
    assert bundle["signed_move"] == pytest.approx(-0.281)


# ── extract_record: deterministic facts, anchoring, consistency, cite-or-drop ─

def test_given_bundle_when_extract_then_deterministic_facts_come_from_bundle():
    from catalyst_trader.playbook.extract import extract_record
    b = _bundle(catalyst_id=271, knowable_asof="2023-02-22", move_window="(-1,2)", signed_move=0.052)
    # completion carries DIFFERENT ids/dates the extractor must ignore for deterministic facts
    rec = extract_record(b, lambda _p: _completion(event_date="1999-01-01"))
    assert rec.catalyst_id == 271
    assert rec.knowable_asof == "2023-02-22"
    assert rec.move_window == "(-1,2)"
    assert rec.signed_move == pytest.approx(0.052)  # from bundle, not the LLM
    assert rec.ticker == "KRYS"
    assert rec.citations  # non-empty (cite-or-drop contract)


def test_given_pdufa_when_extract_then_outcome_follows_move_sign():
    from catalyst_trader.playbook.extract import extract_record
    # LLM says CRL, but the SIGNED move is positive -> pdufa is move-primary -> approve
    b = _bundle(catalyst_type="pdufa", signed_move=0.052)
    rec = extract_record(b, lambda _p: _completion(outcome_label="crl"))
    assert rec.outcome_label == "approve"
    assert rec.move_consistency_flag is False


def test_given_readout_when_extract_then_text_label_is_kept():
    from catalyst_trader.playbook.extract import extract_record
    # readout is text-primary: the LLM's 'hit' is kept even though move only corroborates
    b = _bundle(catalyst_type="trial_readout", signed_move=0.18)
    rec = extract_record(b, lambda _p: _completion(outcome_label="hit"))
    assert rec.outcome_label == "hit"
    assert rec.move_consistency_flag is False


def test_given_label_move_disagreement_when_extract_then_flag_and_lower_confidence():
    from catalyst_trader.playbook.extract import extract_record
    agree = extract_record(_bundle(catalyst_type="trial_readout", signed_move=0.18),
                           lambda _p: _completion(outcome_label="hit", confidence=0.6))
    disagree = extract_record(_bundle(catalyst_type="trial_readout", signed_move=-0.18),
                              lambda _p: _completion(outcome_label="hit", confidence=0.6))
    assert disagree.move_consistency_flag is True
    assert agree.move_consistency_flag is False
    assert disagree.confidence < agree.confidence


def test_given_uncited_driver_when_extract_then_dropped_not_invented():
    from catalyst_trader.playbook.extract import extract_record
    bad = {"factor": "cmc_risk", "value": "unknown", "evidence_quote": "n/a", "source_url": ""}
    base = json.loads((FIXTURES / "extract_krys_271.json").read_text())
    n_cited = len(base["drivers"])
    base["drivers"].append(bad)
    rec = extract_record(_bundle(), lambda _p: json.dumps(base))
    assert len(rec.drivers) == n_cited  # the uncited driver was dropped
    assert all(d.source_url for d in rec.drivers)


def test_given_month_precision_when_extract_then_reduced_confidence():
    from catalyst_trader.playbook.extract import extract_record
    full = extract_record(_bundle(signed_move=0.052),
                          lambda _p: _completion(confidence=0.7))
    monthp = extract_record(_bundle(signed_move=None, knowable_asof=None, move_window=None),
                            lambda _p: _completion(confidence=0.7))
    assert monthp.signed_move is None
    assert monthp.move_consistency_flag is False  # no move -> not a disagreement
    assert monthp.confidence < full.confidence  # corroboration unavailable -> reduced


def test_given_naked_catalyst_when_extract_then_none():
    from catalyst_trader.playbook.extract import extract_record
    naked = _bundle(exhibit_text=None, ctgov=None, signed_move=None,
                    knowable_asof=None, move_window=None)
    called = []
    assert extract_record(naked, lambda _p: called.append(1) or "{}") is None
    assert not called  # never even calls the LLM on a naked catalyst


# ── the offline invariant: no live-LLM / network import in the module ────────

def test_extract_module_imports_no_llm_sdk():
    src = (Path(__file__).resolve().parents[1] / "src" / "catalyst_trader" / "playbook"
           / "extract.py").read_text()
    assert "claude_agent_sdk" not in src
    assert "import httpx" not in src  # complete_fn is the only model seam; no network here


# format-hardening for reproducibility (locked spec)

def test_prompt_carries_label_rubric_and_standards():
    from catalyst_trader.playbook.extract import build_prompt
    p = build_prompt({"ticker": "X", "catalyst_type": "pdufa", "indication": "i", "modality": "m",
                      "event_date": "2025-01-01", "signed_move": -0.4, "exhibit_text": "t"})
    assert "OUTCOME_LABEL enum" in p and "reference_class MUST name" in p
    assert "stale profile" in p.lower() and "NEVER fabricate" in p


def test_extract_uses_llm_indication_override_when_stale_profile():
    from catalyst_trader.playbook.extract import extract_record
    bundle = {"catalyst_id": 1, "ticker": "QNCX", "catalyst_type": "trial_readout",
              "indication": "Ataxia-Telangiectasia", "modality": "RBC encapsulation",  # STALE
              "event_date": "2026-07-30", "knowable_asof": "2026-07-30", "signed_move": 0.13,
              "move_window": "T-1..T+2", "exhibit_text": "LAM-001 inhaled rapamycin PH-ILD positive",
              "ctgov": None}
    nb = {"thesis": "t", "causal_setup": "post-pivot to LAM-001", "reference_class": "r",
          "variant_why": "v", "what_to_watch": ["a"], "what_would_change_our_mind": ["b"]}
    na = {"what_happened": "w", "why_narrative": "y", "surprise_vs_prior": "s",
          "which_disconfirmer_fired": "d", "lesson_rule": "l", "process_grade": "B", "second_order": None}
    import json
    payload = json.dumps({"outcome_label": "hit", "confidence": 0.6, "drivers": [],
                          "indication": "PH-ILD", "modality": "inhaled rapamycin",  # OVERRIDE
                          "narrative_before": nb, "narrative_after": na,
                          "citations": [{"url": "http://x", "quote": "LAM-001", "snippet_hash": "h"}]})
    rec = extract_record(bundle, lambda _p: payload)
    assert rec.indication == "PH-ILD" and rec.modality == "inhaled rapamycin"  # corrected, not stale
