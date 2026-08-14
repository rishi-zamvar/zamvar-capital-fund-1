"""Two-source verification rule, uncertainty re-derivation from real source rows,
the single tradeable gate, and the curated-PDUFA loader — all origins flow here."""

from catalyst_trader import store
from catalyst_trader.calendar import verify
from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    DatePrecision,
    DateType,
    SourceOrigin,
    SourceType,
    Status,
    Uncertainty,
)


def _source(**over):
    base = dict(
        source_name="ClinicalTrials.gov",
        source_url="https://clinicaltrials.gov/study/NCT1",
        source_type=SourceType.primary,
        reported_date="2026-11-30",
        date_type=DateType.estimated,
        agrees=True,
        retrieved_at="2026-08-14T00:00:00Z",
    )
    base.update(over)
    return CatalystSource(**base)


def _catalyst(sources, **over):
    base = dict(
        ticker="VRTX",
        catalyst_type=CatalystType.pdufa,
        event_date="2026-11-30",
        date_precision=DatePrecision.day,
        uncertainty_type=Uncertainty.soft,
        source_origin=SourceOrigin.curated_pdufa,
        sources=sources,
    )
    base.update(over)
    return Catalyst(**base)


# --- two-source rule ---------------------------------------------------------

def test_single_source_stays_unverified(db):
    cid = store.insert_catalyst(db, _catalyst([_source()]))
    assert verify.verify_catalyst(db, cid) == Status.unverified


def test_two_agreeing_sources_with_primary_becomes_verified(db):
    cid = store.insert_catalyst(
        db, _catalyst([_source(source_type=SourceType.primary), _source(source_type=SourceType.secondary)])
    )
    assert verify.verify_catalyst(db, cid) == Status.verified
    assert verify.is_tradeable(store.get_catalyst(db, cid)) is True


def test_two_sources_no_primary_not_verified(db):
    cid = store.insert_catalyst(
        db, _catalyst([_source(source_type=SourceType.secondary), _source(source_type=SourceType.secondary)])
    )
    assert verify.verify_catalyst(db, cid) != Status.verified


def test_two_sources_one_disagrees_not_verified(db):
    cid = store.insert_catalyst(
        db, _catalyst([_source(source_type=SourceType.primary), _source(source_type=SourceType.secondary, agrees=False)])
    )
    assert verify.verify_catalyst(db, cid) != Status.verified


# --- uncertainty re-derived from real source rows, never guessed -------------

def test_estimated_vs_actual_single_source_full_day(db):
    """Identical single-source full-day catalyst: source date_type drives uncertainty."""
    est = store.insert_catalyst(db, _catalyst([_source(date_type=DateType.estimated)], ticker="EST"))
    act = store.insert_catalyst(db, _catalyst([_source(date_type=DateType.actual)], ticker="ACT"))
    verify.verify_catalyst(db, est)
    verify.verify_catalyst(db, act)
    assert store.get_catalyst(db, est).uncertainty_type == Uncertainty.window
    assert store.get_catalyst(db, act).uncertainty_type == Uncertainty.soft


def test_partial_date_with_two_primaries_still_window(db):
    cid = store.insert_catalyst(
        db,
        _catalyst(
            [
                _source(source_type=SourceType.primary, reported_date="2027-04"),
                _source(source_type=SourceType.primary, reported_date="2027-04"),
            ],
            event_date="2027-04",
            date_precision=DatePrecision.month,
        ),
    )
    verify.verify_catalyst(db, cid)
    assert store.get_catalyst(db, cid).uncertainty_type == Uncertainty.window


def test_corroborated_full_day_primary_becomes_firm(db):
    cid = store.insert_catalyst(
        db, _catalyst([_source(source_type=SourceType.primary), _source(source_type=SourceType.secondary)])
    )
    verify.verify_catalyst(db, cid)
    assert store.get_catalyst(db, cid).uncertainty_type == Uncertainty.firm


def test_authoritative_source_is_primary_preferred(db):
    """A secondary 'actual' + primary 'estimated' single-source style: verify reads the
    primary row's date_type, not the first row's."""
    cid = store.insert_catalyst(
        db,
        _catalyst(
            [_source(source_type=SourceType.secondary, agrees=False, date_type=DateType.actual),
             _source(source_type=SourceType.primary, date_type=DateType.estimated)],
        ),
    )
    verify.verify_catalyst(db, cid)
    # only 1 agreeing source (primary, estimated, full-day) -> window, not soft
    assert store.get_catalyst(db, cid).uncertainty_type == Uncertainty.window


# --- single gate -------------------------------------------------------------

def test_is_tradeable_is_only_the_verified_status():
    c_ok = _catalyst([_source()], status=Status.verified)
    c_no = _catalyst([_source()], status=Status.unverified)
    assert verify.is_tradeable(c_ok) is True
    assert verify.is_tradeable(c_no) is False


# --- no date without a source, round-tripped through the store ---------------

def test_no_date_without_source(db):
    orphan = Catalyst.model_construct(**{**_catalyst([_source()]).model_dump(), "sources": []})
    import pytest
    with pytest.raises(ValueError):
        store.insert_catalyst(db, orphan)


def test_adhoc_needs_second_source(db):
    cid = store.insert_catalyst(
        db, _catalyst([_source(source_type=SourceType.secondary)], source_origin=SourceOrigin.ad_hoc_user)
    )
    assert verify.verify_catalyst(db, cid) == Status.unverified
    # a corroborating primary source arrives on the next refresh
    db.execute(
        "INSERT INTO catalyst_source (catalyst_id, source_name, source_type, reported_date, date_type, agrees, retrieved_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (cid, "FDA", "primary", "2026-11-30", "actual", 1, "2026-08-15T00:00:00Z"),
    )
    db.commit()
    assert verify.verify_catalyst(db, cid) == Status.verified


# --- curated PDUFA loader flows through the same pipeline --------------------

def test_load_curated_pdufa(db, tmp_path):
    csv_path = tmp_path / "pdufa.csv"
    csv_path.write_text(
        "ticker,catalyst_type,event_date,source_name,source_url,source_type\n"
        "VRTX,pdufa,2026-11-30,FDA,https://www.fda.gov/x,primary\n"
        "SRPT,adcom,2027-04,BiopharmaWatch,https://www.biopharmawatch.com/y,secondary\n"
    )
    ids = verify.load_curated_pdufa(db, str(csv_path))
    assert len(ids) == 2
    c0 = store.get_catalyst(db, ids[0])
    assert c0.source_origin == SourceOrigin.curated_pdufa
    assert c0.status == Status.unverified  # single source -> needs corroboration
    assert c0.sources[0].date_type == DateType.estimated  # PDUFA target, not realized
    c1 = store.get_catalyst(db, ids[1])
    assert c1.date_precision == DatePrecision.month  # partial date preserved
    assert c1.uncertainty_type == Uncertainty.window
