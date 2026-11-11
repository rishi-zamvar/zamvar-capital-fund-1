"""Offline TDD for GENERALIZE (playbook.generalize, Plan 07.5-05).

Recurring per-catalyst lesson_rules graduate into cited per-scenario playbook nodes the desk's
query_playbooks tool consumes. Every test is offline + free: synthetic catalyst+outcome pairs are
written via playbook.store.insert_catalyst_record with hash_embed (no fastembed, no LLM, no network),
then generalize_playbooks harvests them. The CRITICAL guard: the free-form scenario namespace never
collides with the reserved fitted_params:<type> namespace (kb.py load_params seam).
"""

import pytest

from catalyst_trader import kb
from catalyst_trader.kb import BOOTSTRAP_DEFAULT, hash_embed, load_params, query_playbooks
from catalyst_trader.playbook.generalize import generalize_playbooks
from catalyst_trader.playbook.schema import (
    CatalystRecord,
    Citation,
    DriverClaim,
    NarrativeAfter,
    NarrativeBefore,
)
from catalyst_trader.playbook.store import insert_catalyst_record


def _record(cid, *, ctype="pdufa", reference_class="CMC-only CRL, clean-efficacy",
            lesson_rule="re-approval likely once CMC deficiency is resolved",
            move=0.05, label="approve", watch=("cmc 483",)):
    cite = Citation(url=f"https://ct.gov/{cid}", quote="q", snippet_hash=f"h{cid}")
    return CatalystRecord(
        catalyst_id=cid, ticker="KRYS", catalyst_type=ctype, indication="DEB",
        modality="gene therapy", event_date="2023-02-17", knowable_asof="2023-02-22",
        outcome_label=label, signed_move=move, move_window="(-1,2)", confidence=0.7,
        drivers=[DriverClaim(factor="designations", value="BTD",
                             evidence_quote="priority review granted", source_url=f"https://ct.gov/{cid}")],
        narrative_before=NarrativeBefore(
            thesis=f"thesis {cid}", causal_setup="expedited stack", reference_class=reference_class,
            variant_why="market underweighted designations",
            what_to_watch=list(watch), what_would_change_our_mind=["surprise adcom"]),
        narrative_after=NarrativeAfter(
            what_happened="resolved", why_narrative="held", surprise_vs_prior="low",
            which_disconfirmer_fired="none", lesson_rule=lesson_rule, process_grade="A"),
        citations=[cite],
    )


def _seed_recurring_plus_singleton(db):
    """3 pdufa members sharing (type, reference_class) + 1 pdufa singleton (must NOT graduate)."""
    insert_catalyst_record(db, _record(1, move=0.20, label="approve", watch=("cmc 483",)), embed=hash_embed)
    insert_catalyst_record(db, _record(2, move=0.15, label="approve", watch=("gmp reinspection",)), embed=hash_embed)
    insert_catalyst_record(db, _record(3, move=-0.30, label="crl", watch=("cmc 483",)), embed=hash_embed)
    # singleton: distinct reference_class -> its own group of size 1
    insert_catalyst_record(db, _record(9, reference_class="AdCom split panel",
                                       lesson_rule="panel splits are coin flips", move=0.4, label="approve"),
                           embed=hash_embed)


# ── grouping + scenario-node write ───────────────────────────────────────────

def test_given_recurring_group_when_generalize_then_one_scenario_node(db):
    _seed_recurring_plus_singleton(db)
    n = generalize_playbooks(db, min_support=2)
    assert n == 1  # only the 3-member group graduates; the singleton does not
    playbooks = db.execute("SELECT COUNT(*) AS c FROM kb_node WHERE kind='playbook'").fetchone()["c"]
    assert playbooks == 1


def test_given_recurring_group_when_generalize_then_free_form_scenario_type(db):
    _seed_recurring_plus_singleton(db)
    generalize_playbooks(db, min_support=2)
    row = db.execute(
        "SELECT json_extract(attrs_json,'$.scenario_type') AS st FROM kb_node WHERE kind='playbook'"
    ).fetchone()
    st = row["st"]
    assert st.startswith("pdufa:")
    assert not st.startswith("fitted_params:")  # NEVER the reserved namespace


def test_given_singleton_when_generalize_then_no_node(db):
    _seed_recurring_plus_singleton(db)
    generalize_playbooks(db, min_support=2)
    # the singleton's group (AdCom split panel) produced no playbook
    all_st = [r["st"] for r in db.execute(
        "SELECT json_extract(attrs_json,'$.scenario_type') AS st FROM kb_node WHERE kind='playbook'"
    ).fetchall()]
    assert not any("split_panel" in st or "adcom" in st for st in all_st)


def test_given_generalized_when_query_then_confidence_and_strategy_surface(db):
    _seed_recurring_plus_singleton(db)
    generalize_playbooks(db, min_support=2)
    st = db.execute(
        "SELECT json_extract(attrs_json,'$.scenario_type') AS st FROM kb_node WHERE kind='playbook'"
    ).fetchone()["st"]
    rows = query_playbooks(db, st)
    assert len(rows) == 1
    pb = rows[0]
    assert 0.0 < pb["confidence"] <= 1.0
    strat = pb["strategy"]
    # base rate = label shares over the group's outcomes (2 approve / 1 crl)
    assert strat["base_rate"] == {"approve": pytest.approx(2 / 3, abs=1e-3), "crl": pytest.approx(1 / 3, abs=1e-3)}
    assert strat["n"] == 3
    assert strat["median_move"] == pytest.approx(0.15, abs=1e-6)  # median of [0.20, 0.15, -0.30]
    assert len(strat["member_ids"]) == 3
    assert set(strat["what_to_watch"]) == {"cmc 483", "gmp reinspection"}  # unioned tells
    # scenario = the representative lesson_rule
    assert "re-approval" in pb["scenario"]


# ── cite-or-drop: the scenario node aggregates its members' evidence ──────────

def test_given_generalized_when_written_then_scenario_node_is_cited(db):
    _seed_recurring_plus_singleton(db)
    generalize_playbooks(db, min_support=2)
    pid = db.execute("SELECT id FROM kb_node WHERE kind='playbook'").fetchone()["id"]
    n_cites = db.execute(
        "SELECT COUNT(*) AS c FROM kb_edge WHERE src_id=? AND rel='CITES'", (pid,)
    ).fetchone()["c"]
    assert n_cites >= 1  # generalizes from its members' evidence (insert_playbook would raise on empty)


# ── CRITICAL namespace guard: never touch the reserved fitted_params seam ─────

def test_given_generalize_when_done_then_fitted_params_namespace_untouched(db):
    _seed_recurring_plus_singleton(db)
    before = load_params(db, "pdufa")
    assert query_playbooks(db, "fitted_params:pdufa") == []  # no fitted_params node exists
    generalize_playbooks(db, min_support=2)
    # generalize wrote a free-form node but NEVER a fitted_params:<type> node
    assert query_playbooks(db, "fitted_params:pdufa") == []
    after = load_params(db, "pdufa")
    assert after == before == BOOTSTRAP_DEFAULT  # load_params still the bootstrap default, not a generalization


def test_given_seeded_fitted_params_when_generalize_then_load_params_unchanged(db):
    """A pre-existing fitted_params:pdufa node must survive generalization untouched (no collision)."""
    from catalyst_trader.kb import EvidenceSource, insert_playbook
    ev = EvidenceSource(url="https://x", retrieved_at="2026-01-01", snippet_hash="fp")
    insert_playbook(db, "fitted_params:pdufa", "seed", {"estimator": {"method": "median"}}, 0.3, [ev])
    _seed_recurring_plus_singleton(db)
    before = load_params(db, "pdufa")
    generalize_playbooks(db, min_support=2)
    assert load_params(db, "pdufa") == before  # the seeded fit is the winner, untouched by generalize


# ── idempotency ──────────────────────────────────────────────────────────────

def test_given_generalize_twice_when_rerun_then_no_duplicate(db):
    _seed_recurring_plus_singleton(db)
    first = generalize_playbooks(db, min_support=2)
    second = generalize_playbooks(db, min_support=2)
    assert first == 1
    assert second == 0  # already generalized -> nothing new written
    assert db.execute("SELECT COUNT(*) AS c FROM kb_node WHERE kind='playbook'").fetchone()["c"] == 1


# ── min_support gate ─────────────────────────────────────────────────────────

def test_given_high_min_support_when_generalize_then_group_below_threshold_skipped(db):
    _seed_recurring_plus_singleton(db)
    n = generalize_playbooks(db, min_support=4)  # the 3-member group is below 4
    assert n == 0
    assert db.execute("SELECT COUNT(*) AS c FROM kb_node WHERE kind='playbook'").fetchone()["c"] == 0
