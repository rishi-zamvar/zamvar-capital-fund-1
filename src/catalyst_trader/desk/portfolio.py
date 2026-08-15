"""desk/portfolio.py (PORT-01/04/05 + HEDGE-05 + OPS-01/02): the book selector, the PM
promote/kill pass, and the position memo + pre-mortem authored SEPARATELY from approval.

Two responsibilities, both deterministic where money is involved:
  - `select_book` aggregates the week's survivable legs toward ~1% by SELECTION ONLY — it may
    drop/reorder legs under the weekly budget + concentration heat cap, but it can NEVER resize
    a leg above its `size_for_survival` output. 1% is a book-level SELECTION outcome, never a leg
    sizing input; a zero-trade week (empty promote) is a valid success, not an error (PORT-01/04).
  - `author_memo` + `author_pre_mortem` are their OWN run_structured calls, produced BEFORE and
    SEPARATELY from `pm_decide` (author != approver, OPS-01/02). `pm_decide` (opus) reads the memo
    + pre-mortem + risk + context and emits the StrategyDossier, with residual net-long + which
    risk is covered set DETERMINISTICALLY from the RECONCILED proposal.hedge (HEDGE-05).

# ponytail: `select_book` is the ONE genuinely new bit of portfolio math — it composes the
#           existing quant.concentration/exposure constraint tools; the PM/memo/pre-mortem seam
#           mirrors builder.py (narrow LLM schema, deterministic assembly), no base classes.
"""

from dataclasses import dataclass

from ..quant.portfolio import concentration


@dataclass
class Candidate:
    """A survivable leg offered to `select_book`. `size_pct` is the RECONCILED survival size
    (never resized upward); `expected_move` is the estimator EV used only for aggregation/ranking;
    `weight` is the signed book weight for the heat-cap math (defaults to +size_pct, a long);
    `payload` carries the caller's own object (e.g. the (proposal, risk) pair) through selection."""

    size_pct: float
    expected_move: float
    weight: float | None = None
    payload: object = None

    def book_weight(self) -> float:
        return self.size_pct if self.weight is None else self.weight


def select_book(candidates, open_book, weekly_budget, heat_cap, target_weekly=0.01):
    """Greedily include survivable legs (best expected_move/size first) toward ~`target_weekly`
    aggregate expected return, subject to the weekly budget + a concentration heat cap over the
    COMBINED (promoted + open) book.

    NEVER resizes a leg: legs are only included or dropped. If survivable legs cannot reach the
    target, the book stays below it (no forced upsizing); if none clear the constraints, the
    promoted set is empty — a zero-trade week is a valid success (PORT-01/04).

    Returns (promoted_subset, aggregate_expected_return) where aggregate = Σ(size_pct·expected_move).
    """
    open_weights = [ob["weight"] for ob in open_book]
    ranked = sorted(
        candidates,
        key=lambda c: (c.expected_move / c.size_pct) if c.size_pct else 0.0,
        reverse=True,
    )

    promoted: list[Candidate] = []
    aggregate = 0.0
    budget_used = 0.0
    for c in ranked:
        if aggregate >= target_weekly:
            break  # the book already clears ~1% by selection — never over-trade to a quota
        if budget_used + c.size_pct > weekly_budget:
            continue  # would breach the weekly budget — drop, don't shrink
        combined = open_weights + [x.book_weight() for x in promoted] + [c.book_weight()]
        if concentration(combined).value > heat_cap:
            continue  # too concentrated over the combined book — drop this leg
        promoted.append(c)
        budget_used += c.size_pct
        aggregate += c.size_pct * c.expected_move

    return promoted, aggregate
