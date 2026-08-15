"""The model-fit PARAMETER SEAM (PORT-02/03).

load_params(conn, catalyst_type) is the ONE seam Phase-9's refit loop later replaces the SOURCE of:
it returns the highest-confidence fitted_params:<type> playbook's strategy dict, or a labeled
bootstrap default when none exists. A fitted param set is itself a CITED, versioned playbook claim
(higher confidence shadows lower). Every returned dict carries the estimator + sl_tp + builder groups
the quant tools + the trade builder read (no param literals live in those bodies).
"""

import pytest

from catalyst_trader.kb import (
    BOOTSTRAP_DEFAULT,
    EvidenceSource,
    insert_playbook,
    load_params,
)

EV = [EvidenceSource(url="https://ct.gov/fit", retrieved_at="2026-08-15", snippet_hash="h")]

_GROUPS = ("estimator", "sl_tp", "builder")


def _strategy(down_move: float) -> dict:
    """A fitted-params strategy dict with all three groups (down_move tags which version won)."""
    return {
        "estimator": {"method": "median", "min_analogs": 5, "implied_blend": 0.5,
                      "default_down_move": down_move},
        "sl_tp": {"sl_vol_mult": 1.0, "tp_frac": 0.8, "drift_coef": 0.0},
        "builder": {"min_tradeable_size": 0.002, "log_growth_margin": 0.0, "runup_capture_frac": 0.3},
        "fit_source": "test",
    }


def test_load_params_returns_seeded_strategy(db):
    insert_playbook(db, "fitted_params:pdufa", "pdufa fit", _strategy(0.70), 0.3, EV)
    got = load_params(db, "pdufa")
    assert all(g in got for g in _GROUPS)
    assert got["estimator"]["default_down_move"] == 0.70


def test_newer_higher_confidence_version_shadows_older(db):
    insert_playbook(db, "fitted_params:pdufa", "old fit", _strategy(0.60), 0.4, EV)
    insert_playbook(db, "fitted_params:pdufa", "new fit", _strategy(0.75), 0.7, EV)
    # versioning: the 0.7 row wins (query_playbooks is confidence-desc)
    assert load_params(db, "pdufa")["estimator"]["default_down_move"] == 0.75


def test_missing_type_returns_labeled_bootstrap_default(db):
    got = load_params(db, "never_seeded")
    assert got == BOOTSTRAP_DEFAULT
    assert all(g in got for g in _GROUPS)


def test_returned_dict_always_has_all_three_builder_groups(db):
    # cold (default) path
    assert all(g in load_params(db, "cold") for g in _GROUPS)
    # seeded path
    insert_playbook(db, "fitted_params:earnings", "earnings fit", _strategy(0.5), 0.3, EV)
    seeded = load_params(db, "earnings")
    assert all(g in seeded for g in _GROUPS)
    for k in ("min_tradeable_size", "log_growth_margin", "runup_capture_frac"):
        assert k in seeded["builder"]


def test_bootstrap_default_carries_builder_thresholds(db):
    # the builder's hold-vs-exit + tradeable-size thresholds are fitted params, never literals in
    # the builder body — they must be homed in BOOTSTRAP_DEFAULT (05-06 depends on this).
    for k in ("min_tradeable_size", "log_growth_margin", "runup_capture_frac"):
        assert k in BOOTSTRAP_DEFAULT["builder"]


def test_load_params_does_not_mutate_bootstrap_default(db):
    # load_params returns a copy on the cold path — a caller mutating the result must not poison
    # the module-level default for the next caller.
    got = load_params(db, "cold")
    got["builder"]["min_tradeable_size"] = 999
    assert BOOTSTRAP_DEFAULT["builder"]["min_tradeable_size"] != 999
