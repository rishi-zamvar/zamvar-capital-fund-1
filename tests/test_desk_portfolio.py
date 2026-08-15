"""Portfolio layer (PORT-01/04/05 + HEDGE-05 + OPS-01/02): the book selector, the PM
promote/kill pass (memo + pre-mortem authored SEPARATELY from approval), and the
run_portfolio composition that reconciles the Risk Committee's authoritative outputs onto
each proposal BEFORE selection (BLOCKER-1).

Money-critical invariants under test:
  - select_book aggregates toward ~1% by SELECTION ONLY — it drops/reorders legs but NEVER
    resizes a leg above its size_for_survival output (1% is book-level, never a leg input);
    a zero-trade week (empty promote) is a valid success, not an error.
  - the position memo + pre-mortem are authored in run_structured calls SEPARATE from and
    BEFORE the PM decision call (author != approver, OPS-01/02).
  - the dossier states residual net-long (gross >= |net|) and which risk is covered, derived
    from the RECONCILED proposal.hedge (an unvalidated/None hedge can never report idiosyncratic).
  - run_portfolio reconciles risk.recommended_size_pct + risk.hedge onto the proposal BEFORE
    select_book — the builder's preliminary size/hedge are never what gets promoted (BLOCKER-1).

Quant + KB run FOR REAL (deterministic); run_structured is monkeypatched -> fully offline.
"""

import pytest

from catalyst_trader.desk import portfolio
from catalyst_trader.desk.portfolio import Candidate, select_book
from catalyst_trader.quant.portfolio import concentration


# ---------------------------------------------------------------------------
# Task 1 — select_book (aggregate to ~1% by selection; never resize above survival)
# ---------------------------------------------------------------------------


def _cand(size_pct, expected_move, weight=None):
    return Candidate(size_pct=size_pct, expected_move=expected_move, weight=weight,
                     payload=(size_pct, expected_move))


def test_select_book_aggregates_toward_one_pct():
    # three efficient legs; the selector adds them until the ~1% aggregate is reached.
    cands = [_cand(0.03, 0.25), _cand(0.03, 0.25), _cand(0.03, 0.25)]
    promoted, agg = select_book(cands, open_book=[], weekly_budget=1.0, heat_cap=1.0)
    assert agg >= 0.01                       # reached the ~1% book target by selection
    assert 0 < len(promoted) <= len(cands)   # picked a subset, did not need all/none
    assert agg == pytest.approx(sum(c.size_pct * c.expected_move for c in promoted))


def test_select_book_never_resizes_above_survival_size():
    # STRUCTURAL: every promoted leg's size_pct is EXACTLY its input survival size — never larger.
    cands = [_cand(0.03, 0.40), _cand(0.02, 0.30)]
    inputs = {id(c): c.size_pct for c in cands}
    promoted, _ = select_book(cands, open_book=[], weekly_budget=1.0, heat_cap=1.0)
    for c in promoted:
        assert c.size_pct == inputs[id(c)]   # unchanged — selection only, no upsizing


def test_select_book_ranks_by_efficiency_first():
    lo = _cand(0.03, 0.05)   # low expected_move / size
    hi = _cand(0.03, 0.60)   # high expected_move / size
    promoted, _ = select_book([lo, hi], open_book=[], weekly_budget=1.0, heat_cap=1.0)
    assert promoted[0] is hi   # the most efficient leg is selected first


def test_select_book_respects_weekly_budget():
    cands = [_cand(0.03, 0.05), _cand(0.03, 0.05)]  # inefficient so target never short-circuits
    promoted, _ = select_book(cands, open_book=[], weekly_budget=0.03, heat_cap=1.0)
    assert sum(c.size_pct for c in promoted) <= 0.03  # budget cap honored -> only one fits


def test_select_book_heat_cap_drops_a_leg():
    # two big single-name weights; the heat cap (Herfindahl) refuses the second.
    cands = [_cand(0.5, 0.30), _cand(0.5, 0.30)]
    promoted, _ = select_book(cands, open_book=[], weekly_budget=1.0, heat_cap=0.3)
    assert len(promoted) == 1                        # [0.5] Herfindahl 0.25 ok; [0.5,0.5] 0.5 > cap
    assert concentration([c.book_weight() for c in promoted]).value <= 0.3


def test_select_book_zero_trade_when_nothing_clears_budget():
    cands = [_cand(0.03, 0.20)]
    promoted, agg = select_book(cands, open_book=[], weekly_budget=0.0, heat_cap=1.0)
    assert promoted == []       # no leg fits the (zero) budget -> zero-trade week, not an error
    assert agg == 0.0


def test_select_book_empty_candidates_is_zero_trade():
    promoted, agg = select_book([], open_book=[], weekly_budget=1.0, heat_cap=1.0)
    assert promoted == [] and agg == 0.0


def test_select_book_heat_cap_uses_combined_book_with_open_positions():
    # an already-heavy open book pushes the combined Herfindahl over the cap -> nothing new fits.
    cands = [_cand(0.5, 0.30)]
    promoted, _ = select_book(cands, open_book=[{"ticker": "OPEN", "weight": 0.9, "catalyst_id": "c0"}],
                              weekly_budget=1.0, heat_cap=0.5)
    assert promoted == []   # [0.9, 0.5] Herfindahl 1.06 > 0.5 -> the candidate is dropped
