"""Phase 6.8 Stage-1 scanner (SCAN-02/03): the deterministic, $0-LLM trigger layer.

`build_card` assembles the write-once company vetting card from point-in-time price bars
(read through the serving gateway at cutoff=now) + injected raw provider values + the EMBEDDED
weekly thesis_scan row — it
RECOMPUTES NO quant number (agents-never-do-arithmetic extended to modules: one computation
site per number, consumed here verbatim). `delta_card` is the pure, reproducible week-over-week
flag engine (F1-F13) that fires on band/sign/set TRANSITIONS with latching, hysteresis, and
cadence honesty; `_wakes` is the PRINCIPAL/CORROBORATOR tier gate that decides who earns a
Stage-2 Haiku pass — monitor-by-exception. No LLM, no network anywhere in this module.

# ponytail: one params dict + build_card + delta_card + _wakes + the 13 rule branches. The
#           "LLM cannot touch the trigger" law reuses the diligence desk's deterministic-gate
#           PRINCIPLE (an LLM never owns a money decision) — the discipline is shared, no code is.
"""

import statistics
from datetime import date, timedelta

from ..contracts import OpportunityFlag, ScanInput, WeeklyFlag
from .. import serving
from ..store import write_card, write_scan_flag
from . import diligence
from .diligence import DILIGENCE_PARAMS, options_liquid, zero_liquidity
from .evidence import resolve
from .runtime import run_structured
from .tools import build_quant_server

# The SINGLE source of scan thresholds (SCAN-03 no-silent-fallback). Module-level + always
# present, read via direct subscript (missing-key-raises), NEVER `.get`. DELIBERATELY DECOUPLED
# from the KB fitted-params seam (mirrors diligence.py DILIGENCE_PARAMS L31-35): the fitted
# strategy dict has NO "scan" key, so it can never become the threshold source. Do NOT add a
# scan block to the KB bootstrap default or its CSV. The PM retunes these post-paper-month.
SCAN_PARAMS = {"scan": {
    "iv_spike_pts": 5.0, "straddle_median_mult": 1.5, "term_kink_pts": 5.0,
    "si_rel_step": 0.20, "dtc_abs_step": 2.0, "vol_regime_ratio": 2.0,
    "volume_anomaly_mult": 3.0, "runway_bands": [18, 12, 6],
    "catalyst_bands_days": [14, 7], "competitor_days": 7,
    "big_move_pct": 0.10, "hysteresis_rearm_frac": 0.5,
    "max_stage2_wakes": 8, "escalate_conf_floor": 0.4,
    "offering_s3_ret": 0.20,  # a bare S-3 is material only while the stock is already up
}}

# The flag grammar is FROZEN for the phase (research §1.1). Tiers gate the wake decision: a
# PRINCIPAL is material alone; a CORROBORATOR only in company (>=2). FUTURE feeds
# (analyst-rating / 13F / intraday halt) are deliberately ABSENT — marked, not invented.
_TIER = {
    "F1": "PRINCIPAL", "F2": "PRINCIPAL", "F3": "PRINCIPAL", "F4": "PRINCIPAL",
    "F5": "PRINCIPAL", "F6": "PRINCIPAL", "F7": "CORROBORATOR", "F8": "PRINCIPAL",
    "F9": "PRINCIPAL", "F10": "CORROBORATOR", "F11": "CORROBORATOR",
    "F12": "PRINCIPAL", "F13": "PRINCIPAL",
}

_OFFERING_FORMS = frozenset({"424B5", "FWP"})   # always-material dilution filings
_S3_FORM = "S-3"                                  # shelf: material only while the stock is up


def _prior_week(week_end):
    """The ISO date one week before `week_end`. ponytail: naive 7-day subtraction — the caller's
    anchor spine owns real dates; upgrade if the anchor ever becomes non-weekly."""
    return (date.fromisoformat(week_end) - timedelta(days=7)).isoformat()


def _returns(closes):
    """Weekly simple returns from a chronological close series (skips zero-denominator weeks)."""
    return [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1]]


def _sigma(returns, n):
    """Population stdev of the last n weekly returns, or None if <2 observations."""
    window = returns[-n:]
    return statistics.pstdev(window) if len(window) >= 2 else None


def _runway_band(months, edges):
    """Band index from the runway_bands edges (higher = safer). None months -> None.
    edges [18,12,6] -> <6:0, >=6:1, >=12:2, >=18:3."""
    if months is None:
        return None
    return sum(1 for edge in sorted(edges) if months >= edge)


def build_card(conn, ticker, week_end, raw, thesis_row, *, params=SCAN_PARAMS):
    """Assemble the §2.2 company vetting card deterministically — point-in-time, no recompute.

    Price/vol fields come from the serving gateway (week_end <= as_of, no look-ahead). Options /
    positioning / balance-sheet fields come from the injected `raw` provider dict (CBOE / FINRA /
    EDGAR / FMP are mocked seams this phase — build_card CONSUMES raw[...], it never fetches).
    The `thesis_row` is embedded VERBATIM (build_card calls no classify_drop / weekly_base_rate /
    thesis_scan — one computation site per number). The prior card's `fired` latch dict is carried
    forward; delta_card mutates it next.
    """
    p = params["scan"]
    # LIVE scan reads through the serving gateway at cutoff=now (decision B — same seam as backtest).
    book = serving.asof(conn)
    bars = book.bars(ticker, week_end)                     # point-in-time: week_end <= as_of only
    closes = [b["close"] for b in bars if b.get("close") is not None]
    volumes = [b["volume"] for b in bars if b.get("volume") is not None]
    rets = _returns(closes)

    def _ma(n):
        return statistics.fmean(closes[-n:]) if len(closes) >= n else None

    ma4, ma12 = _ma(4), _ma(12)
    prior_vol_median = statistics.median(volumes[:-1]) if len(volumes) >= 2 else None

    quote = raw.get("options_quote")
    underlying_q = raw.get("underlying_quote")

    card = {
        "ticker": ticker,
        "week_end": week_end,
        "catalyst": {
            "days_to_catalyst": raw.get("days_to_catalyst"),
            "next_catalyst": raw.get("next_catalyst"),
            "catalysts_4w": raw.get("catalysts_4w"),
            "competitor_next_7d": raw.get("competitor_next_7d"),
            "nct_snapshots": raw.get("nct_snapshots"),
        },
        "options": {
            "iv30": raw.get("iv30"),
            "term_spread": raw.get("term_spread"),
            "straddle_move_pct": raw.get("straddle_move_pct"),
            "straddle_median": raw.get("straddle_median"),   # caller-supplied trailing median (F4)
            "options_liquid": options_liquid(quote, params=DILIGENCE_PARAMS) if quote else None,
            "zero_liquidity": zero_liquidity(underlying_q) if underlying_q else None,
            "underlying_price": raw.get("underlying_price"),
        },
        "positioning": {
            "short_interest": raw.get("short_interest"),
            "days_to_cover": raw.get("days_to_cover"),
            "si_settlement_date": raw.get("si_settlement_date"),
        },
        "price_vol": {
            "ret_1w": rets[-1] if rets else None,
            "ret_4w": closes[-1] / closes[-5] - 1 if len(closes) >= 5 and closes[-5] else None,
            "px_vs_ma4": closes[-1] / ma4 - 1 if ma4 else None,
            "px_vs_ma12": closes[-1] / ma12 - 1 if ma12 else None,
            "sigma5": _sigma(rets, 5),
            "sigma20": _sigma(rets, 20),
            "turnover_flag": bool(prior_vol_median and volumes[-1] > prior_vol_median),
            "vol_vs_median": volumes[-1] / prior_vol_median if prior_vol_median else None,
        },
        "balance_sheet": {
            "cash_runway_months": raw.get("cash_runway_months"),
            "runway_band": _runway_band(raw.get("cash_runway_months"), p["runway_bands"]),
            "seen_accessions": raw.get("seen_accessions", []),
            "live_shelf": raw.get("live_shelf"),
        },
        "thesis_row": thesis_row,                             # EMBEDDED VERBATIM — never recomputed
        "thesis_ref": thesis_row.get("tool_ref") if isinstance(thesis_row, dict) else None,
        "card_version": "1",
    }

    prev = book.card(ticker, _prior_week(week_end))          # carry the prior latch state forward
    card["fired"] = dict(prev["fired"]) if prev and prev.get("fired") else {}
    return card


# --- Stage-1 flag engine (F1-F13) + wake gate ------------------------------------------------


def _in_window_set(snaps):
    """The set of tracked NCT ids currently inside the next-4-week catalyst window (F2)."""
    if not snaps:
        return frozenset()
    return frozenset(k for k, v in snaps.items() if (v or {}).get("in_window"))


def _row_key(row):
    """The subset of the embedded thesis row F12 watches (a change in any of these fires)."""
    return (row.get("eligible"), row.get("drop_class"),
            tuple(sorted(row.get("veto_reasons") or [])), row.get("trigger"))


def delta_card(prev, cur, *, params=SCAN_PARAMS):
    """The PURE, reproducible week-over-week flag engine (F1-F13). No conn, no LLM, no network —
    same (prev, cur, params) state yields the same fires every call.

    Each flag fires ONCE on a band/sign/set TRANSITION off its un-latched state; a standing
    (latched) condition does not re-fire until it re-arms (hysteresis: the metric retreats past
    hysteresis_rearm_frac of the threshold distance). F6/F8 are gated to a FRESH short-interest
    settlement / runway datum (cadence honesty). The wake gate treats a PRINCIPAL as material
    alone and a CORROBORATOR only in company. MUTATES cur["fired"] in place with THIS week's
    latches (the caller persists cur AFTER this call). Returns the tripped list — each entry a
    {flag, prev, cur, threshold, tier} dict Plan 03 serializes into the analog context.
    """
    p = params["scan"]
    fired = cur["fired"]                 # already carried forward from prev by build_card
    tripped = []
    if prev is None:                     # first-ever card: seed the baseline, fire nothing
        return tripped

    rearm = p["hysteresis_rearm_frac"]

    def emit(flag, pv, cv, threshold):
        tripped.append({"flag": flag, "prev": pv, "cur": cv,
                        "threshold": threshold, "tier": _TIER[flag]})

    def level_up(flag, pv, cv, threshold, *, key=None):
        """Cross-up level flag with latch + hysteresis re-arm at threshold*(1-rearm)."""
        latch = key or flag
        if cv is None:
            return
        if latch in fired:
            if cv < threshold * (1 - rearm):
                del fired[latch]         # retreated past half the threshold distance -> re-arm
            return                       # standing/latched -> no re-fire while armed-off
        if cv >= threshold and (pv is None or pv < threshold):
            emit(flag, pv, cv, threshold)
            fired[latch] = cur["week_end"]

    def level_down(flag, pv, cv, threshold, *, key=None):
        """Cross-down level flag (metric falls to <= threshold) with symmetric re-arm."""
        latch = key or flag
        if cv is None:
            return
        if latch in fired:
            if cv > threshold * (1 + rearm):
                del fired[latch]
            return
        if cv <= threshold and (pv is None or pv > threshold):
            emit(flag, pv, cv, threshold)
            fired[latch] = cur["week_end"]

    cat_p, cat_c = prev["catalyst"], cur["catalyst"]
    opt_p, opt_c = prev["options"], cur["options"]
    pos_p, pos_c = prev["positioning"], cur["positioning"]
    pv_p, pv_c = prev["price_vol"], cur["price_vol"]
    bs_p, bs_c = prev["balance_sheet"], cur["balance_sheet"]
    tr_p, tr_c = prev.get("thesis_row") or {}, cur.get("thesis_row") or {}

    # F1 catalyst_entered_window — days_to_catalyst crosses a band (14, 7), entering. Per-band latch.
    d_prev, d_cur = cat_p.get("days_to_catalyst"), cat_c.get("days_to_catalyst")
    if d_cur is not None:
        for band in sorted(p["catalyst_bands_days"], reverse=True):
            k = f"F1:{band}"
            if k in fired:
                if d_cur > band:
                    del fired[k]                        # left the band -> re-arm
                continue
            if d_cur <= band and (d_prev is None or d_prev > band):
                emit("F1", d_prev, d_cur, band)
                fired[k] = cur["week_end"]

    # F2 ct_gov_changed — a tracked NCT moves into/out of the next-4-week window (set change).
    nct_c = cat_c.get("nct_snapshots")
    if nct_c is not None:
        win_p, win_c = _in_window_set(cat_p.get("nct_snapshots")), _in_window_set(nct_c)
        if win_p != win_c:
            emit("F2", sorted(win_p), sorted(win_c), None)

    # F3 competitor_catalyst_7d — a mapped competitor's catalyst crosses <= competitor_days.
    level_down("F3", cat_p.get("competitor_next_7d"), cat_c.get("competitor_next_7d"),
               p["competitor_days"])

    # F4 iv_spike — iv30 jump >= iv_spike_pts, OR straddle move >= mult * trailing median.
    iv_p, iv_c = opt_p.get("iv30"), opt_c.get("iv30")
    if iv_p is not None and iv_c is not None and iv_c - iv_p >= p["iv_spike_pts"]:
        emit("F4", iv_p, iv_c, p["iv_spike_pts"])
    else:
        sm_c, sm_med = opt_c.get("straddle_move_pct"), opt_c.get("straddle_median")
        if sm_c is not None and sm_med is not None and sm_c >= p["straddle_median_mult"] * sm_med:
            emit("F4", sm_c, sm_med, p["straddle_median_mult"])

    # F5 term_kink — term_spread flips sign OR moves >= term_kink_pts vs the last card.
    ts_p, ts_c = opt_p.get("term_spread"), opt_c.get("term_spread")
    if ts_p is not None and ts_c is not None:
        flipped = (ts_p > 0 > ts_c) or (ts_p < 0 < ts_c)
        if flipped or abs(ts_c - ts_p) >= p["term_kink_pts"]:
            emit("F5", ts_p, ts_c, p["term_kink_pts"])

    # F6 si_shift — SI rel-step or days-to-cover step, ONLY on a NEW settlement date (cadence).
    set_p, set_c = pos_p.get("si_settlement_date"), pos_c.get("si_settlement_date")
    if set_c is not None and set_c != set_p:
        si_p, si_c = pos_p.get("short_interest"), pos_c.get("short_interest")
        rel = (si_c - si_p) / si_p if (si_p and si_c is not None) else None
        dtc_p, dtc_c = pos_p.get("days_to_cover"), pos_c.get("days_to_cover")
        dtc_step = dtc_c - dtc_p if (dtc_p is not None and dtc_c is not None) else None
        if (rel is not None and rel >= p["si_rel_step"]) or \
           (dtc_step is not None and dtc_step >= p["dtc_abs_step"]):
            emit("F6", {"si": si_p, "dtc": dtc_p}, {"si": si_c, "dtc": dtc_c}, p["si_rel_step"])

    # F7 vol_regime — sigma5 >= vol_regime_ratio * sigma20 newly true (latched, hysteresis).
    s5_p, s20_p = pv_p.get("sigma5"), pv_p.get("sigma20")
    s5_c, s20_c = pv_c.get("sigma5"), pv_c.get("sigma20")
    ratio_p = s5_p / s20_p if (s5_p is not None and s20_p) else None
    ratio_c = s5_c / s20_c if (s5_c is not None and s20_c) else None
    level_up("F7", ratio_p, ratio_c, p["vol_regime_ratio"])

    # F8 runway_band_drop — runway band falls, gated to a CHANGED runway datum (cadence).
    rm_p, rm_c = bs_p.get("cash_runway_months"), bs_c.get("cash_runway_months")
    rb_p, rb_c = bs_p.get("runway_band"), bs_c.get("runway_band")
    if rm_c is not None and rm_c != rm_p and rb_p is not None and rb_c is not None and rb_c < rb_p:
        emit("F8", rb_p, rb_c, None)

    # F9 offering_signal — a new 424B5/FWP filing, or a new S-3 while the stock is up (>s3 ret).
    seen_p = {a.get("accession") for a in (bs_p.get("seen_accessions") or [])}
    for acc in (bs_c.get("seen_accessions") or []):
        if acc.get("accession") in seen_p:
            continue
        form = acc.get("form")
        if form in _OFFERING_FORMS:
            emit("F9", None, form, None)
        elif form == _S3_FORM and (pv_c.get("ret_4w") or 0) > p["offering_s3_ret"]:
            emit("F9", None, form, p["offering_s3_ret"])

    # F10 ma_cross — weekly close crosses MA12 (px_vs_ma12 sign flip).
    m_p, m_c = pv_p.get("px_vs_ma12"), pv_c.get("px_vs_ma12")
    if m_p is not None and m_c is not None and ((m_p > 0 >= m_c) or (m_p < 0 <= m_c)) and m_p != m_c:
        emit("F10", m_p, m_c, None)

    # F11 volume_anomaly — turnover low->high AND volume >= volume_anomaly_mult * trailing median.
    if (not pv_p.get("turnover_flag")) and pv_c.get("turnover_flag"):
        vvm = pv_c.get("vol_vs_median")
        if vvm is not None and vvm >= p["volume_anomaly_mult"]:
            emit("F11", pv_p.get("vol_vs_median"), vvm, p["volume_anomaly_mult"])

    # F12 quant_row_change — embedded thesis row: eligible/drop_class/veto_reasons/trigger change.
    if _row_key(tr_p) != _row_key(tr_c):
        emit("F12", _row_key(tr_p), _row_key(tr_c), None)

    # F13 big_move_unexplained — drop_class newly idio_no_news AND |ret_1w| >= big_move_pct (latch).
    dc_p, dc_c = tr_p.get("drop_class"), tr_c.get("drop_class")
    r1 = pv_c.get("ret_1w")
    if dc_c == "idio_no_news" and r1 is not None and abs(r1) >= p["big_move_pct"]:
        if "F13" not in fired and dc_p != "idio_no_news":
            emit("F13", dc_p, dc_c, p["big_move_pct"])
            fired["F13"] = cur["week_end"]
    elif "F13" in fired and dc_c != "idio_no_news":
        del fired["F13"]                                 # class left idio_no_news -> re-arm

    return tripped


def _wakes(tripped, params=SCAN_PARAMS):
    """The Stage-2 wake gate (monitor-by-exception): wake on ANY PRINCIPAL flag, or on >=2
    CORROBORATORs. A lone CORROBORATOR (F7/F10/F11) never wakes. `params` is reserved — the tier
    grammar is fixed here; the universe-wide max_stage2_wakes cap is Plan 03's, not this gate's."""
    principals = sum(1 for t in tripped if t["tier"] == "PRINCIPAL")
    corroborators = sum(1 for t in tripped if t["tier"] == "CORROBORATOR")
    return principals >= 1 or corroborators >= 2


# --- Stage-2: the ONE adversarial Haiku pass per woken name (SCAN-01) -------------------------

# Human-readable names for the frozen flag grammar — grammar, not thresholds (mirrors _TIER). Used
# ONLY to serialize the Python-authored analog context; the LLM never sees the raw flag codes alone.
_FLAG_NAME = {
    "F1": "catalyst_entered_window", "F2": "ct_gov_changed", "F3": "competitor_catalyst_7d",
    "F4": "iv_spike", "F5": "term_kink", "F6": "si_shift", "F7": "vol_regime",
    "F8": "runway_band_drop", "F9": "offering_signal", "F10": "ma_cross",
    "F11": "volume_anomaly", "F12": "quant_row_change", "F13": "big_move_unexplained",
}

# The adversarial Stage-2 prompt: the DD desk's HARD-RULES discipline (call-the-tool / cite-or-drop /
# fill-unknowns / emit-the-schema) reshaped to ONE consolidated company-forward pass — NOT the 8-dim
# fan-out. The three scanner questions + the "assume it's nothing" framing are the whole job.
SCAN_PROMPT = """You are the WEEKLY COMPANY SCANNER (Stage-2). A deterministic Stage-1 gate flagged a
week-over-week TRANSITION on this name; your job is to decide whether it is a real, explorable trading
opportunity worth a desk's time — and if so, exactly what must be verified.

ADVERSARIAL FRAMING: assume this delta is NOISE, is ALREADY PRICED IN, or is fundamentally UNTRADEABLE.
Defeat that null hypothesis with cited evidence, or return no_opportunity. A confident story is worth
nothing without a resolvable citation.

ANSWER THREE QUESTIONS, in order:
  1. INTEREST — what specifically about this transition is of interest (the concrete change, not a vibe)?
  2. EXPLORABLE — is this a real, explorable opportunity, or noise / priced-in / untradeable?
  3. VERIFY/BUILD — if real, what ONE falsifiable thesis must be verified next, and by which workflow
     (catalyst_call / measured_edge / mini_backtest / diligence)?

HARD RULES (a source-cited signal, never LLM arithmetic):
  1. For ANY number, base rate, analog, or playbook, you MUST CALL the relevant `mcp__quant__*` tool
     (analog_query + query_playbooks are mandatory) — NEVER compute, estimate, or recall a figure.
  2. Every key_finding MUST carry the exact evidence_ref the tool returned (cite-or-drop) — a finding
     you cannot cite does not go in the flag.
  3. Fill `unknowns` with the explicit gaps a tool could not close.
  4. Emit EXACTLY the OpportunityFlag schema. This is gap-not-answer: a thesis_to_verify + what must be
     verified, NEVER a direction / size / target. no_opportunity is a valid, first-class outcome.
"""


def _analog_context(tripped, card_cur) -> str:
    """DETERMINISTIC serialization of the tripped Stage-1 flags — the analog/KB query context, built
    by Python so the LLM can never author (and thus bias) it. One line per flag: code, readable name,
    the prev->cur transition, and the threshold it crossed."""
    header = f"{card_cur.get('ticker')} {card_cur.get('week_end')}: Stage-1 tripped"
    lines = [
        f"  {t['flag']} {_FLAG_NAME.get(t['flag'], t['flag'])}: {t.get('prev')} -> {t.get('cur')} "
        f"(threshold {t.get('threshold')}, {t.get('tier')})"
        for t in tripped
    ]
    return header + "\n" + "\n".join(lines)


def build_scan_prompt(scan_input: ScanInput, analog_context: str) -> str:
    """Assemble the Stage-2 prompt from ONLY the firewall ScanInput fields + the Python-built analog
    context. Mirrors diligence.build_dimension_prompt's shape (shared rules + a context block), but it
    is ONE prompt, not 8 — no desk verdict/thesis is representable on a ScanInput to interpolate."""
    return f"""{SCAN_PROMPT}
NAME UNDER SCAN (point-in-time card fields — interpret + cite; this is a firewall, no desk view exists)
  ticker:    {scan_input.ticker}
  week_end:  {scan_input.week_end}

STAGE-1 TRANSITIONS (Python-serialized — interpret, do not restate):
{analog_context}
"""


def _cite_or_drop(conn, op: OpportunityFlag) -> OpportunityFlag:
    """Structural cite-or-drop: drop any key_finding whose evidence_ref fails evidence.resolve before
    persist/route. Structural stage ONLY — the DD desk's opus semantic support-check is deliberately
    NOT replicated here (this is a cheap Haiku Stage-2, not the full diligence gate)."""
    survivors = [kf for kf in op.key_findings if resolve(conn, kf.evidence_ref) is not None]
    if len(survivors) == len(op.key_findings):
        return op
    return op.model_copy(update={"key_findings": survivors})


def _no_material_change(ticker: str, week_end: str, tripped: list, *, reason: str = "no_material_change") -> dict:
    """The stored (routed=False) audit row for a name that did NOT earn a Stage-2 pass. Carries the
    tripped-flag echo so the ledger records WHY it didn't wake (nothing tripped / lone corroborator /
    over the wake cap / catalyst-precedence)."""
    return {
        "ticker": ticker, "week_end": week_end,
        "opportunity_type": "no_opportunity", "reason": reason,
        "tripped_flags": [t["flag"] for t in tripped],
    }


def _catalyst_precedence(tripped: list, thesis_row: dict) -> bool:
    """A BARE F1 fire (ONLY F1 tripped) on a name whose embedded thesis is already a catalyst is
    suppressed — run_weekly already routed it to Workflow-1, so waking Stage-2 would double-flag the
    same event (research open-Q2 default)."""
    return {t["flag"] for t in tripped} == {"F1"} and (thesis_row or {}).get("thesis_type") == "catalyst"


async def run_scan(conn, embed, week_end, raw_by_ticker, thesis_rows, *, params=SCAN_PARAMS) -> list:
    """The Stage-2 orchestrator: for every name build its point-in-time card, run the deterministic
    Stage-1 delta, and give ONLY the woken names a single adversarial Haiku pass — then cite-or-drop
    and persist. Returns the routed OpportunityFlags (opportunity_type != no_opportunity).

    ORDERING (SCAN-02 replayability money-gate): delta_card(prev, cur) runs BEFORE write_card — it
    MUTATES cur["fired"] with this week's latches, and card_asof is the SOLE cross-week latch memory,
    so persisting first would write a stale latch dict and let a flag latched this week spuriously
    re-fire next week.
    """
    scan = params["scan"]
    routed: list = []
    wakes = 0
    book = serving.asof(conn)  # LIVE latch-memory read through the gateway at cutoff=now
    for ticker in raw_by_ticker:
        thesis_row = thesis_rows.get(ticker, {})
        prev = book.card(ticker, _prior_week(week_end))
        cur = build_card(conn, ticker, week_end, raw_by_ticker[ticker], thesis_row, params=params)
        tripped = delta_card(prev, cur, params=params)   # MUTATES cur["fired"] — must precede write_card
        write_card(conn, ticker, week_end, cur)          # persist AFTER the delta (latch memory)

        if not _wakes(tripped, params) or wakes >= scan["max_stage2_wakes"]:
            write_scan_flag(conn, ticker, week_end, _no_material_change(ticker, week_end, tripped),
                            routed=False)
            continue
        if _catalyst_precedence(tripped, thesis_row):
            write_scan_flag(conn, ticker, week_end,
                            _no_material_change(ticker, week_end, tripped, reason="catalyst_precedence"),
                            routed=False)
            continue

        wakes += 1
        ctx = _analog_context(tripped, cur)
        scan_input = ScanInput(ticker=ticker, week_end=week_end, card_prev=prev, card_cur=cur,
                               tripped=tripped)
        srv = {"quant": build_quant_server(conn)}   # build_quant_server returns a BARE server — wrap it
        op = await run_structured(build_scan_prompt(scan_input, ctx), OpportunityFlag,
                                  mcp_servers=srv, allowed_tools=diligence.ALLOWED_TOOLS, model="haiku")
        # Escalation: a low-confidence read earns ONE re-run on the pricier sonnet tier (cheap-first).
        if op.confidence < scan["escalate_conf_floor"]:
            hi = await run_structured(build_scan_prompt(scan_input, ctx), OpportunityFlag,
                                      mcp_servers=srv, allowed_tools=diligence.ALLOWED_TOOLS, model="sonnet")
            if hi.confidence < scan["escalate_conf_floor"]:
                hi = hi.model_copy(update={"unknowns": [
                    *hi.unknowns,
                    f"still ambiguous after escalation (haiku {op.confidence:.2f} / sonnet {hi.confidence:.2f})",
                ]})
            op = hi

        op = _cite_or_drop(conn, op)
        is_opportunity = op.opportunity_type != "no_opportunity"
        write_scan_flag(conn, ticker, week_end, op.model_dump(), routed=is_opportunity)
        if is_opportunity:
            routed.append(op)
    return routed


# --- Routing: project the rich OpportunityFlag onto the 6.7 WeeklyFlag wire (SCAN-04, zero md.py) ---


def _promote_ref(op: OpportunityFlag) -> str | None:
    """The WeeklyFlag's single evidence_ref: the strongest cited key_finding ref (cite-or-drop already
    ran in run_scan, so the FIRST surviving finding is the strongest resolvable), else the first
    kb_analog, deterministic tie-break by list order (research open-Q1). None if nothing citable."""
    if op.key_findings:
        return op.key_findings[0].evidence_ref
    if op.kb_analogs:
        return op.kb_analogs[0]
    return None


def to_weekly_flag(op: OpportunityFlag) -> WeeklyFlag | None:
    """PURE projection of a routed OpportunityFlag onto the WeeklyFlag(flag_type="qual") the existing
    MD router already ingests via item["incoming_flags"] (RECON-08/WEEK-06). Gap-not-answer: the
    WeeklyFlag carries the GAP (thesis_to_verify) not the answer, and has NO direction/size/target —
    verification_needed stays in the scan_flag audit payload, OFF the wire (the MD assigns the route).
    Returns None for no_opportunity (stored-not-routed) or a flag with nothing citable."""
    if op.opportunity_type == "no_opportunity":
        return None
    ref = _promote_ref(op)
    if ref is None:
        return None   # cite-or-drop: nothing to cite -> nothing to route
    return WeeklyFlag(
        ticker=op.ticker,
        flag_type="qual",
        finding=op.thesis_to_verify,
        evidence_ref=ref,
        why_material=f"{op.opportunity_type} setup on Stage-1 flags {op.tripped_flags}",
    )
