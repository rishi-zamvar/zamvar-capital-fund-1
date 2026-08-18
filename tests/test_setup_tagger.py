"""Deterministic, LLM-free setup tagger (quick-260818-l64 Task 1).

The tagger stamps a multi-label `setups` list onto a catalyst from its narrative fields via a frozen
keyword/regex rubric derived from data/setup_taxonomy.json. Money-adjacent invariants under test:
  - pure function of its inputs (same fields -> same list, taxonomy-declaration-order stable),
  - multi-label by design (a distressed microcap fires BOTH structure tags),
  - no false tag on empty / unrelated text,
  - bulk tagging writes a json LIST readable by json_each and is IDEMPOTENT (recompute, never append).
"""

from catalyst_trader import kb
from catalyst_trader.kb import EvidenceSource, KBNode, insert_claim
from catalyst_trader.playbook import tagger


def test_load_taxonomy_resolves_frozen_artifact():
    tax = tagger.load_taxonomy()
    assert tax["tags"], "taxonomy must load from <repo-root>/data/setup_taxonomy.json"
    assert any(t["name"] == "single-asset-microcap-binary" for t in tax["tags"])
    assert "tagging_rubric" in tax


def test_every_taxonomy_tag_has_a_pattern():
    # the rubric must cover every vocab tag or bulk coverage silently under-tags.
    names = {t["name"] for t in tagger.load_taxonomy()["tags"]}
    assert names == set(tagger._TAG_PATTERNS), "each vocab tag needs a regex list"


def test_distressed_microcap_is_multi_label():
    tags = tagger.tag_setups({
        "thesis": "nanocap, thin float, going-concern, imminent dilutive raise, sole remaining pivotal"
    })
    assert "single-asset-microcap-binary" in tags
    assert "financing-overhang-going-concern" in tags


def test_graveyard_indication_tag():
    tags = tagger.tag_setups({
        "thesis": "ALS readout on a functional rating scale primary; Alzheimer's cognition history is a graveyard"
    })
    assert "trial-graveyard-high-placebo-indication" in tags


def test_priced_in_derisked_readout_tag():
    tags = tagger.tag_setups({
        "thesis": "topline already disclosed; confirmatory Phase 3 re-presentation after a big run-up"
    })
    assert "priced-in-derisked-readout" in tags


def test_empty_and_unrelated_text_yields_no_tag():
    assert tagger.tag_setups({}) == []
    assert tagger.tag_setups({"thesis": "the quick brown fox jumped over the lazy dog"}) == []


def test_tag_setups_is_pure_and_order_stable():
    fields = {"thesis": "microcap single asset; going concern dilutive raise; confirmatory topline disclosed"}
    first = tagger.tag_setups(fields)
    second = tagger.tag_setups(fields)
    assert first == second
    order = [t["name"] for t in tagger.load_taxonomy()["tags"]]
    assert first == sorted(first, key=order.index), "tags must be in taxonomy declaration order"


def test_tag_setups_reads_list_valued_fields():
    # what_to_watch-style list fields are concatenated, not str()'d into noise.
    tags = tagger.tag_setups({"what_to_watch": ["microcap thin float", "single company-defining pivotal"]})
    assert "single-asset-microcap-binary" in tags


def _seed(db, attrs):
    ev = EvidenceSource(url="https://ct.gov/x", retrieved_at="2026-08-14", snippet_hash="h" + str(attrs))
    return insert_claim(db, KBNode(kind="catalyst", attrs=attrs), [ev])


def test_bulk_tag_writes_json_each_filterable_list_and_is_idempotent(db):
    _seed(db, {"type": "pdufa", "indication": "ALS",
               "narrative_before": {"thesis": "nanocap single asset; going concern; ALS graveyard readout"}})
    _seed(db, {"type": "pdufa", "indication": "psoriasis",
               "narrative_before": {"thesis": "topline already disclosed confirmatory label expansion"}})
    _seed(db, {"type": "earnings", "indication": "",
               "narrative_before": {"thesis": "the quick brown fox"}})  # no ex-ante tag

    stats = tagger.tag_all_catalyst_nodes(db)
    assert stats["total"] == 3
    assert stats["with_ex_ante"] == 2
    assert stats["coverage"] == 2 / 3

    # setups is a real json list, filterable by json_each (the retrieval axis Task 2 relies on).
    hit = db.execute(
        "SELECT COUNT(*) c FROM kb_node WHERE kind='catalyst' AND EXISTS("
        "SELECT 1 FROM json_each(attrs_json,'$.setups') WHERE value='single-asset-microcap-binary')"
    ).fetchone()["c"]
    assert hit == 1

    # idempotent: a second run reproduces identical tags, never duplicates.
    before = [r["attrs_json"] for r in db.execute(
        "SELECT attrs_json FROM kb_node WHERE kind='catalyst' ORDER BY id").fetchall()]
    tagger.tag_all_catalyst_nodes(db)
    after = [r["attrs_json"] for r in db.execute(
        "SELECT attrs_json FROM kb_node WHERE kind='catalyst' ORDER BY id").fetchall()]
    assert before == after
