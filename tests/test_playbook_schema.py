"""TDD contract suite for the warm-playbook record schema (Plan 07.5-01).

Pure, DB-free, LLM-free. Locks the MONEY-PATH invariants:
- the outcome attr key is literally "move" and SIGNED (builder.py:69 _split_moves consumes it);
- structural-filter keys (type, ticker, indication, modality, knowable_asof, event_date) are
  TOP-LEVEL in the catalyst attrs (json_extract reads top-level only, kb.py:150-152);
- compose_card == thesis + causal_setup + reference_class + why_narrative (the embed_text) and
  nothing else;
- move_consistency_flag cross-checks outcome_label direction against the signed move.
"""

import pytest
from pydantic import ValidationError

from catalyst_trader.playbook.schema import (
    Citation,
    CatalystRecord,
    DriverClaim,
    NarrativeAfter,
    NarrativeBefore,
    compose_card,
    compute_move_consistency,
    to_catalyst_attrs,
    to_outcome_attrs,
)

# Distinctive marker strings so the card-composition assertions are unambiguous.
_THESIS = "THESIS_MARKER approval likely on strong pivotal data"
_CAUSAL = "CAUSAL_MARKER two positive phase-3 trials, consistent effect"
_REFCLASS = "REFCLASS_MARKER CNS small-molecule PDUFAs with positive adcom"
_VARIANT = "VARIANT_MARKER market underprices the adcom signal"
_WATCH = "WATCH_MARKER CRL risk on CMC"
_WHY_AFTER = "WHYAFTER_MARKER pivotal effect consistency drove approval"


def _before(**over):
    base = dict(
        thesis=_THESIS,
        causal_setup=_CAUSAL,
        reference_class=_REFCLASS,
        variant_why=_VARIANT,
        what_to_watch=[_WATCH, "label breadth"],
        what_would_change_our_mind=["safety signal at adcom"],
    )
    base.update(over)
    return NarrativeBefore(**base)


def _after(**over):
    base = dict(
        what_happened="FDA approved on the PDUFA date.",
        why_narrative=_WHY_AFTER,
        surprise_vs_prior="in line with base rate",
        which_disconfirmer_fired="none",
        lesson_rule="positive adcom + consistent pivotals -> high approval odds",
        process_grade="A",
    )
    base.update(over)
    return NarrativeAfter(**base)


def _pdufa(**over):
    base = dict(
        catalyst_id=1,
        ticker="ABCD",
        catalyst_type="pdufa",
        indication="major depressive disorder",
        modality="small molecule",
        event_date="2026-09-15",
        knowable_asof="2026-09-14",
        outcome_label="approve",
        signed_move=0.32,
        move_window="event_day",
        confidence=0.8,
        drivers=[
            DriverClaim(
                factor="adcom_vote",
                value="12-1 favorable",
                evidence_quote="The advisory committee voted 12 to 1 in favor.",
                source_url="https://fda.gov/adcom",
            )
        ],
        narrative_before=_before(),
        narrative_after=_after(),
        citations=[Citation(url="https://fda.gov/x", quote="approved", snippet_hash="abc123")],
    )
    base.update(over)
    return CatalystRecord(**base)


def _readout(**over):
    base = dict(
        catalyst_id=2,
        ticker="WXYZ",
        catalyst_type="trial_readout",
        indication="ulcerative colitis",
        modality="monoclonal antibody",
        event_date="2026-10-01",
        knowable_asof="2026-09-30",
        outcome_label="hit",
        signed_move=0.45,
        move_window="event_day",
        confidence=0.7,
        drivers=[
            DriverClaim(
                factor="phase",
                value="3",
                evidence_quote="This is a pivotal Phase 3 readout.",
                source_url="https://clinicaltrials.gov/x",
            )
        ],
        narrative_before=_before(),
        narrative_after=_after(what_happened="Primary endpoint met with p<0.001."),
        citations=[Citation(url="https://ct.gov/x", quote="met", snippet_hash="def456")],
    )
    base.update(over)
    return CatalystRecord(**base)


# --- DriverClaim cite-or-drop at the field level -------------------------------------------------


def test_given_driver_claim_missing_evidence_quote_when_built_then_raises():
    with pytest.raises(ValidationError):
        DriverClaim(factor="adcom_vote", value="12-1", source_url="https://fda.gov/x")


def test_given_driver_claim_missing_source_url_when_built_then_raises():
    with pytest.raises(ValidationError):
        DriverClaim(factor="adcom_vote", value="12-1", evidence_quote="voted 12-1")


# --- CatalystRecord validation -------------------------------------------------------------------


def test_given_full_pdufa_case_when_built_then_validates():
    rec = _pdufa()
    assert rec.catalyst_type == "pdufa"
    assert rec.signed_move == 0.32
    assert len(rec.drivers) == 1
    assert len(rec.citations) == 1


def test_given_full_trial_readout_case_when_built_then_validates():
    rec = _readout()
    assert rec.catalyst_type == "trial_readout"
    assert rec.drivers[0].factor == "phase"


def test_given_signed_move_none_when_built_then_validates_with_flag_false():
    rec = _pdufa(signed_move=None, confidence=0.4)
    assert rec.signed_move is None
    # None move is unavailable, not a disagreement.
    assert rec.move_consistency_flag is False


def test_given_empty_citations_when_built_then_raises():
    with pytest.raises(ValidationError):
        _pdufa(citations=[])


def test_given_confidence_out_of_range_when_built_then_raises():
    with pytest.raises(ValidationError):
        _pdufa(confidence=1.5)


# --- compose_card: the four-field embed text -----------------------------------------------------


def test_given_record_when_compose_card_then_has_the_four_narrative_fields():
    card = compose_card(_pdufa())
    assert _THESIS in card
    assert _CAUSAL in card
    assert _REFCLASS in card
    assert _WHY_AFTER in card


def test_given_record_when_compose_card_then_excludes_variant_and_watch():
    card = compose_card(_pdufa())
    assert _VARIANT not in card
    assert _WATCH not in card


# --- to_catalyst_attrs: top-level filter keys ----------------------------------------------------


def test_given_record_when_to_catalyst_attrs_then_filter_keys_top_level():
    attrs = to_catalyst_attrs(_pdufa())
    # json_extract-style TOP-LEVEL access (dict[key], not nested).
    assert attrs["type"] == "pdufa"
    assert attrs["ticker"] == "ABCD"
    assert attrs["indication"] == "major depressive disorder"
    assert attrs["modality"] == "small molecule"
    assert attrs["knowable_asof"] == "2026-09-14"
    assert attrs["event_date"] == "2026-09-15"


def test_given_record_when_to_catalyst_attrs_then_drivers_and_narrative_are_nested():
    attrs = to_catalyst_attrs(_pdufa())
    assert isinstance(attrs["drivers"], dict)
    assert attrs["drivers"]["adcom_vote"] == "12-1 favorable"
    assert isinstance(attrs["narrative_before"], dict)
    assert isinstance(attrs["narrative_after"], dict)


def test_given_record_when_to_catalyst_attrs_then_retrieval_text_is_the_card():
    rec = _pdufa()
    attrs = to_catalyst_attrs(rec)
    assert attrs["retrieval_text"] == compose_card(rec)


# --- to_outcome_attrs: the SIGNED "move" key (builder contract) ----------------------------------


def test_given_record_when_to_outcome_attrs_then_move_key_is_signed_decimal():
    rec = _pdufa(signed_move=-0.18, outcome_label="CRL")
    attrs = to_outcome_attrs(rec)
    assert "move" in attrs
    assert attrs["move"] == -0.18  # SIGNED, not abs, not renamed


def test_given_record_when_to_outcome_attrs_then_carries_label_window_confidence_readonly():
    attrs = to_outcome_attrs(_pdufa())
    assert attrs["label"] == "approve"
    assert attrs["move_window"] == "event_day"
    assert attrs["confidence"] == 0.8
    assert attrs["read_only"] is True


# --- move_consistency cross-check ----------------------------------------------------------------


def test_given_approve_label_with_negative_move_when_built_then_flag_true():
    assert _pdufa(outcome_label="approve", signed_move=-0.1).move_consistency_flag is True


def test_given_crl_label_with_positive_move_when_built_then_flag_true():
    assert _pdufa(outcome_label="CRL", signed_move=0.1).move_consistency_flag is True


def test_given_hit_label_with_negative_move_when_built_then_flag_true():
    assert _readout(outcome_label="hit", signed_move=-0.2).move_consistency_flag is True


def test_given_agreeing_direction_when_built_then_flag_false():
    assert _pdufa(outcome_label="approve", signed_move=0.3).move_consistency_flag is False
    assert _pdufa(outcome_label="CRL", signed_move=-0.3).move_consistency_flag is False


@pytest.mark.parametrize(
    "label,move,expected",
    [
        ("approve", 0.2, False),
        ("approve", -0.2, True),
        ("CRL", -0.2, False),
        ("CRL", 0.2, True),
        ("hit", 0.2, False),
        ("hit", -0.2, True),
        ("miss", -0.2, False),
        ("miss", 0.2, True),
        ("approve", None, False),
        ("unknown_label", 0.2, False),
    ],
)
def test_compute_move_consistency_truth_table(label, move, expected):
    assert compute_move_consistency(label, move) is expected
