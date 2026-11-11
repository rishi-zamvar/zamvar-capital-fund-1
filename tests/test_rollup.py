"""07.9 Plan 3 — the deterministic single-thesis roll-up (guideline §6) + the structured renderer.
Pure functions, offline. Every roll-up number is null when an input is null (never fabricated)."""

import pytest

from catalyst_trader.contracts import (
    ClinicalReport,
    FinancialReport,
    MarketReport,
    RegulatoryReport,
)
from catalyst_trader.desk import rollup


def _base(dim):
    return {
        "dimension": dim, "ticker": "XYZ", "catalyst_id": "c1", "thesis": "t",
        "score": 0.1, "confidence": 0.6,
        "key_findings": [{"claim": "c", "evidence_ref": "tool:x#1"}],
    }


def _lenses(pos=0.6, poa=0.7, x=30.0, z=50.0, y=12.0, clears=True, expression="hold-through"):
    return [
        ClinicalReport(**_base("clinical"), pos_estimate=pos, pos_estimate_source="tool:base_rate#p" if pos is not None else None),
        RegulatoryReport(**_base("regulatory"), poa={"point": poa, "point_source": "tool:base_rate#r" if poa is not None else None}),
        FinancialReport(**_base("financial"), runway={"clears_catalyst": clears}),
        MarketReport(**_base("market_sentiment"), implied_prob={"x": x, "z": z, "y": y},
                     asymmetry={"driver": "fundamentals", "expression": expression}),
    ]


def test_full_rollup():
    r = rollup.rollup(_lenses())
    assert r.fundamental_p_approval == pytest.approx(0.65)
    assert r.market_implied_p_approval == pytest.approx(18 / 38)
    assert r.edge == pytest.approx(0.65 - 18 / 38)
    assert r.lenses_disagree is False
    assert r.solvency_clears_catalyst is True
    assert r.expression == "hold-through" and r.driver == "fundamentals"


def test_lens_disagreement_flagged():
    r = rollup.rollup(_lenses(pos=0.3, poa=0.8))
    assert r.lenses_disagree is True  # the disagreement is itself the finding
    assert r.fundamental_p_approval == pytest.approx(0.55)


def test_one_lens_p_only_uses_it_and_disagreement_unknown():
    r = rollup.rollup(_lenses(pos=None))
    assert r.fundamental_p_approval == pytest.approx(0.7)
    assert r.lenses_disagree is None


def test_nulls_propagate_never_fabricated():
    r = rollup.rollup(_lenses(pos=None, poa=None, x=None, clears=None, expression=None))
    assert r.fundamental_p_approval is None
    assert r.market_implied_p_approval is None
    assert r.edge is None
    assert r.solvency_clears_catalyst is None and r.expression is None


@pytest.mark.parametrize("x, z, y", [(30.0, 12.0, 12.0), (60.0, 50.0, 12.0), (5.0, 50.0, 12.0)])
def test_implied_p_null_when_degenerate_or_out_of_range(x, z, y):
    r = rollup.rollup(_lenses(x=x, z=z, y=y))
    assert r.market_implied_p_approval is None and r.edge is None


def test_missing_lenses_all_null():
    r = rollup.rollup([])
    assert all(v is None for v in r.model_dump().values())


def test_headline_reads_models_and_dicts():
    clin = _lenses()[0]
    assert rollup.headline(clin) == ("pos_estimate", 0.6, "tool:base_rate#p")
    d = {"dimension": "liquidity", "tradeability": {"volume": 100.0, "volume_source": "tool:lq#1"}}
    assert rollup.headline(d) == ("tradeability.volume", 100.0, "tool:lq#1")
    assert rollup.headline({"dimension": "liquidity"}) is None  # thin raw dict -> no headline
    assert rollup.headline({"dimension": "unknown_dim"}) is None


def test_render_lists_only_non_null_leaves():
    lines = rollup.render(_lenses()[1])
    text = "\n".join(lines)
    assert "poa.point=0.7" in text
    assert "HEADLINE poa.point=0.7 (source: tool:base_rate#r)" in text
    assert "None" not in text and "adcom" not in text  # empty slots are not rendered as data


def test_render_rollup_block():
    text = rollup.render_rollup(rollup.rollup(_lenses()))
    assert "ROLL-UP" in text and "edge" in text and "fundamental_p_approval=0.65" in text
