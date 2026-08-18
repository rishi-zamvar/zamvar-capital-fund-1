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
    seed_fitted_params,
)

_SEED_TYPES = ("pdufa", "ph3_readout", "conference", "earnings")

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


# --- Task 2: cited bootstrap seeding ---------------------------------------------------------


def test_seed_writes_one_cited_row_per_catalyst_type(db):
    n = seed_fitted_params(db)
    assert n == len(_SEED_TYPES)
    for t in _SEED_TYPES:
        rows = db.execute(
            "SELECT id FROM kb_node WHERE kind='playbook' "
            "AND json_extract(attrs_json,'$.scenario_type')=?",
            (f"fitted_params:{t}",),
        ).fetchall()
        assert len(rows) == 1, f"expected exactly one bootstrap row for {t}"


def test_each_seeded_row_carries_a_cites_edge(db):
    seed_fitted_params(db)
    rows = db.execute("SELECT id FROM kb_node WHERE kind='playbook'").fetchall()
    assert rows
    for r in rows:
        cites = db.execute(
            "SELECT count(*) FROM kb_edge WHERE src_id=? AND rel='CITES'", (r["id"],)
        ).fetchone()[0]
        assert cites >= 1, "a fitted param set is a CITED claim — provenance is mandatory"


def test_seeded_params_have_all_groups_and_fit_source(db):
    seed_fitted_params(db)
    for t in _SEED_TYPES:
        strat = load_params(db, t)
        for g in _GROUPS:
            assert g in strat
        assert "fit_source" in strat
        for k in ("min_tradeable_size", "log_growth_margin", "runup_capture_frac"):
            assert k in strat["builder"]


def test_load_params_returns_seeded_not_default_after_seeding(db):
    before = load_params(db, "pdufa")
    seed_fitted_params(db)
    after = load_params(db, "pdufa")
    assert after != before, "post-seed load_params must return the cited seed, not the bootstrap default"
    assert after["fit_source"] != BOOTSTRAP_DEFAULT["fit_source"]


def test_seed_confidence_is_shadowable_by_a_future_fit(db):
    # bootstrap rows are seeded at low confidence so any later, better fit shadows them (versioning)
    seed_fitted_params(db)
    insert_playbook(db, "fitted_params:pdufa", "refit", _strategy(0.99), 0.9, EV)
    assert load_params(db, "pdufa")["estimator"]["default_down_move"] == 0.99


def test_seed_raises_on_uncited_row(db, tmp_path):
    # cite-or-drop for the seeder: a row missing its evidence URL must raise, never seed an
    # uncited param set.
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text(
        "catalyst_type,method,min_analogs,implied_blend,default_down_move,sl_vol_mult,tp_frac,"
        "drift_coef,min_tradeable_size,log_growth_margin,runup_capture_frac,fit_source,"
        "evidence_url,evidence_snippet\n"
        "pdufa,median,5,0.5,0.5,1.0,0.8,0.0,0.002,0.0,0.3,no source,,\n"
    )
    with pytest.raises(ValueError):
        seed_fitted_params(db, csv_path=str(csv_path))
    assert db.execute("SELECT count(*) FROM kb_node WHERE kind='playbook'").fetchone()[0] == 0


# --- Task 3: "weekly" params group (WEEK-02) -------------------------------------------------
# The weekly thesis engine reads every threshold from params['weekly'] — NEVER a literal in a tool
# body. Homed in BOOTSTRAP_DEFAULT (not the catalyst-shaped fitted_params CSV). load_params(conn,
# "weekly") finds no fitted_params:weekly playbook -> returns the deep-copied bootstrap default.

_WEEKLY_KEYS = (
    "anchor", "beta_window_weeks", "sector_frac_cut", "turnover_lookback", "window_years",
    "min_effective_n", "shrink_prior_weight", "edge_min_pts", "cost_mult", "roundtrip_cost",
    "hard_veto_drop", "shortlist_k", "defensive_instruments", "defensive_max_frac",
    "statistical_sleeve_cap",
)


def test_weekly_group_exposes_every_documented_threshold(db):
    weekly = load_params(db, "weekly")["weekly"]
    for k in _WEEKLY_KEYS:
        assert k in weekly, f"weekly params must expose {k} (no literal fallback in tool bodies)"


def test_statistical_sleeve_cap_is_present(db):
    # research §4.5 knob #4 — the statistical-sleeve cap must live in params, not a literal.
    assert load_params(db, "weekly")["weekly"]["statistical_sleeve_cap"] == 0.5


def test_missing_weekly_key_raises_keyerror(db):
    # missing-key-raises: plain dict indexing, no numeric fallback hides in the tools.
    weekly = load_params(db, "weekly")["weekly"]
    with pytest.raises(KeyError):
        _ = weekly["not_a_real_weekly_threshold"]


def test_weekly_params_are_a_deep_copy(db):
    # mutating the returned weekly dict must not poison BOOTSTRAP_DEFAULT for the next caller.
    got = load_params(db, "weekly")
    got["weekly"]["shortlist_k"] = 999
    assert BOOTSTRAP_DEFAULT["weekly"]["shortlist_k"] != 999


# --- 07.7-02: "field" params group (FF-06) ----------------------------------------------------
# The football-field aggregator / builder / DD / cross_check read their thresholds+weights from
# params["field"] — never a literal. Homed in the KB fitted-params seam (BOOTSTRAP_DEFAULT + the
# cited bootstrap CSV), DELIBERATELY DECOUPLED from diligence.DILIGENCE_PARAMS (PITFALL #6).

_FIELD_SCALARS = ("min_methods", "trim_frac", "dispersion_wide", "move_discrepancy_tol")
_FIELD_WEIGHT_KEYS = (
    "analog_cold", "analog_warm", "implied_liquid", "base_rate_thin",
    "base_rate_ample", "rnpv_scenario", "analyst_pt",
)


def test_given_no_seed_when_load_params_then_field_group_present(db):
    field = load_params(db, "pdufa")["field"]
    for k in (*_FIELD_SCALARS, "weights"):
        assert k in field, f"field group must expose {k} (no literal fallback in consumers)"
    assert isinstance(field["min_methods"], int)
    for k in ("trim_frac", "dispersion_wide", "move_discrepancy_tol"):
        assert isinstance(field[k], float)
    assert isinstance(field["weights"], dict) and field["weights"], "weights must be a non-empty dict"
    for wk in _FIELD_WEIGHT_KEYS:
        assert wk in field["weights"], f"weight table must carry {wk}"
        assert isinstance(field["weights"][wk], float)


def test_given_seeded_csv_when_load_params_then_field_group_round_trips(db):
    import csv as _csv
    import json as _json
    from pathlib import Path as _Path

    from catalyst_trader import kb as _kb

    row = next(
        r for r in _csv.DictReader(_kb._BOOTSTRAP_CSV.open(newline=""))
        if r["catalyst_type"] == "pdufa"
    )
    seed_fitted_params(db)
    field = load_params(db, "pdufa")["field"]
    assert field["move_discrepancy_tol"] == float(row["move_discrepancy_tol"])
    assert field["min_methods"] == int(row["min_methods"])
    assert field["weights"] == _json.loads(row["field_weights_json"])
    _ = _Path  # silence unused-import guard if any


def test_field_group_absent_from_diligence_params(db):
    # the decoupling invariant (PITFALL #6): field knobs must NOT leak into the DD threshold source.
    from catalyst_trader.desk import diligence

    assert "field" not in diligence.DILIGENCE_PARAMS["diligence"]
