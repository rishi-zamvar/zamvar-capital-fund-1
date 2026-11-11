"""Phase 10 LEARN-01 OPT-IN live judge smoke test. Skipped unless LEARN_LIVE_JUDGE=1 (needs a Claude
Code session / Max auth). Never part of the default offline suite."""

import os

import pytest

from catalyst_trader.learn import judge as jd

pytestmark = pytest.mark.skipif(os.environ.get("LEARN_LIVE_JUDGE") != "1",
                                reason="live LLM judge: set LEARN_LIVE_JUDGE=1 inside a CC session")


def test_given_live_judge_when_scoring_a_seed_case_then_a_valid_verdict_returns():
    lab = jd.load_labels()[0]
    v = jd.score_case(lab.case, jd.make_live_judge())
    assert 1 <= v.grade <= 5 and v.rationale
