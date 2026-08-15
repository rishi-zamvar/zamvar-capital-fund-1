"""desk/md.py — the MD/GP integration desk (the one point that sees all three workflows).

`cross_check` is a PURE, deterministic diff across the catalyst verdict / portfolio dossier /
diligence dossier plus two threaded values. NO LLM, NO conn/kb, NO arithmetic-by-agent: it
pre-computes exactly the inter-workflow inconsistencies the MD would otherwise hunt for, so
the MD call is a pure JUDGMENT call (agents interpret, the desk computes) and Plan 04's bounded
loop gets a deterministic `clean` boolean for convergence (the loop control is Python, never
an LLM decision).
"""

from catalyst_trader.contracts import DebateVerdict, DiligenceDossier, StrategyDossier


def _answered(item: str, coverage: list[str]) -> bool:
    """True iff some coverage string MENTIONS `item` (case/space-normalized substring).
    A red_flag/residual is 'answered' only when a kill criterion / priced residual / hedge
    mechanism actually names it — deterministic, the MD interprets the unanswered remainder."""
    n = " ".join(item.lower().split())
    return any(n in " ".join(c.lower().split()) for c in coverage if c)


def cross_check(
    verdict: DebateVerdict,
    dossier: StrategyDossier,
    dd: DiligenceDossier,
    *,
    catalyst_id: str,
    min_tradeable_size: float,
) -> dict:
    """Deterministic consistency diff across WF-1/2/3. No LLM, no arithmetic-by-agent, no conn/kb.

    catalyst_id: the authoritative catalyst id, threaded from reconcile's item catalyst — DebateVerdict
      carries NO catalyst id, so it MUST be passed explicitly (do NOT read it off the verdict).
    min_tradeable_size: the builder size floor, threaded from reconcile (kb.load_params) so the
      net-long-held-through check has a real data source with NO magic number and cross_check stays
      a pure function (no conn/kb inside).
    Returns structured booleans + the offending items; the MD interprets the flags.
    """
    # --- catalyst_id consistency: the verdict has none, so the threaded id is authoritative;
    #     compare it against the trade id and each DD per-dimension id (§4.1 escalation-worthy). ---
    trade_id = dossier.trade.catalyst_id
    dd_ids = sorted({d["catalyst_id"] for d in dd.per_dimension if d.get("catalyst_id")})
    catalyst_id_consistent = len({catalyst_id, trade_id, *dd_ids}) <= 1

    # --- DD no_go while the portfolio promotes: the core reconciliation tension ---
    dd_vs_portfolio = dd.verdict == "no_go" and dossier.decision == "promote"

    # --- direction drift between the debate verdict and the built trade (regression guard) ---
    direction_consistent = verdict.direction == dossier.trade.direction

    # --- uncovered DD red_flags: not answered by any kill criterion / priced residual (dissent_log)
    #     / hedge mechanism coverage (RECON-04). ---
    coverage = [*dossier.kill_criteria, *dossier.dissent_log]
    if dossier.trade.hedge is not None:
        coverage.append(dossier.trade.hedge.mechanism)
    uncovered_red_flags = [f for f in dd.red_flags if not _answered(f, coverage)]

    # --- DD residuals absent from the dossier's residual accounting (dissent_log surface) ---
    dd_vs_risk_residuals = [
        r for r in dd.residual_risks if not _answered(r, dossier.dissent_log)
    ]

    # --- net-long uncovered exposure held THROUGH the binary: the coverage/net-long/hold-through
    #     TRIPLE (RiskAssessment.ruin_at_size is NOT on the dossier). The 'tiny' floor is the
    #     threaded min_tradeable_size param — no magic number, no conn/kb inside. ---
    sizing_vs_survival = (
        dossier.which_risk_covered == "none"
        and dossier.trade.size_pct > min_tradeable_size
        and dossier.trade.holds_through_catalyst
    )

    clean = (
        catalyst_id_consistent
        and direction_consistent
        and not dd_vs_portfolio
        and not uncovered_red_flags
        and not dd_vs_risk_residuals
        and not sizing_vs_survival
    )

    return {
        "clean": clean,
        "catalyst_id_consistent": catalyst_id_consistent,
        "catalyst_ids": {"threaded": catalyst_id, "trade": trade_id, "diligence": dd_ids},
        "dd_vs_portfolio": dd_vs_portfolio,
        "direction_consistent": direction_consistent,
        "directions": {"verdict": verdict.direction, "trade": dossier.trade.direction},
        "uncovered_red_flags": uncovered_red_flags,
        "dd_vs_risk_residuals": dd_vs_risk_residuals,
        "sizing_vs_survival": sizing_vs_survival,
    }
