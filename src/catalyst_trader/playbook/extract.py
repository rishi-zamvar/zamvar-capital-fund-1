"""ATTRIBUTION front-half: turn ONE past peer catalyst into a validated CatalystRecord (Plan 01),
from cached lake material only (research B §3).

Two seams, both offline-safe:
- build_bundle(conn, catalyst_id) assembles a CIK-filtered, event-proximate context bundle from the
  raw-snapshot lake + catalyst_move + universe_profiles. The lake join reproduces the SAME
  _safe_name(key) stem the archiver wrote (providers/_http.py) — the archiver hashes the FULL fetch
  key (url+params+json_body), and edgar_8k exhibits are fetched with NO params/body, so the stem is
  reproducible from the source_url alone: _safe_name(_key("text","edgar_8k",url,None,None)) ->
  glob "<stem>_*.txt". This disambiguates the ex99-1.htm cross-company collision that a bare
  last-segment glob cannot (two companies' ex99-1 differ by the URL hash in the stem).
- extract_record(bundle, complete_fn) turns the bundle + an INJECTED model completion into the
  strict Plan-01 contract. complete_fn is the ONLY LLM seam (Plan 04 injects the Sonnet call;
  tests inject a stub returning fixture JSON). Deterministic facts (ids, dates, the SIGNED move)
  are copied from the bundle, NEVER from the model.

# ponytail: complete_fn injection = one seam. No SDK/httpx import here -> the module imports offline
#           and the tests stay free; the one-time Plan-04 script owns the real model wiring.
"""

import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

from bs4 import BeautifulSoup

from catalyst_trader.config import settings
from catalyst_trader.playbook.schema import (
    INLINE_BAND,
    CatalystRecord,
    Citation,
    DriverClaim,
    NarrativeAfter,
    NarrativeBefore,
    compute_move_consistency,
)
from catalyst_trader.providers._http import _key, _safe_name, load_snapshot

_CIK_RE = re.compile(r"/data/(\d+)/")
_DISAGREE_PENALTY = 0.5       # move/text sign disagreement -> halve confidence (research B §3.4)
_MONTH_PRECISION_PENALTY = 0.7  # no move to corroborate against -> reduce confidence (research B §4)
_EARNINGS_INLINE_BAND = INLINE_BAND  # single source of truth (schema.INLINE_BAND); |move|<=3% => inline
_REPO_ROOT = Path(__file__).resolve().parents[3]


# ── CIK filter (research B §3.2, the biggest correctness fix) ─────────────────

def cik_filter_exhibits(urls, own_cik) -> list[str]:
    """Keep only exhibit URLs whose /data/<CIK>/ segment matches own_cik; drop cross-company
    contamination (LPCN<->Acumen style). [] when none match (cite-or-drop; never feed a wrong
    company's text to the extractor)."""
    own = str(int(own_cik))
    return [u for u in urls if (m := _CIK_RE.search(u or "")) and str(int(m.group(1))) == own]


def prune_cross_filer_sources(conn, catalyst_id, own_cik) -> list[dict]:
    """FIX C — delete cross-filer (wrong-CIK) EDGAR contamination from catalyst_source and dedupe
    exact-duplicate own-CIK EDGAR urls (keep the lowest id). ct.gov / non-EDGAR rows are left
    untouched. Reuses cik_filter_exhibits for the keep-set (no re-written CIK regex). own_cik=None ->
    no-op (no guess). Returns the dropped rows [{id, source_url, reason}] for the prune artifact."""
    if own_cik is None:
        return []
    rows = conn.execute(
        "SELECT id, source_url FROM catalyst_source "
        "WHERE catalyst_id=? AND source_url IS NOT NULL ORDER BY id",
        (catalyst_id,),
    ).fetchall()
    edgar = [r for r in rows if "sec.gov/Archives" in (r["source_url"] or "")]
    keep = set(cik_filter_exhibits([r["source_url"] for r in edgar], own_cik))

    dropped: list[dict] = []
    seen: set[str] = set()
    for r in edgar:
        url = r["source_url"]
        if url not in keep:
            reason = "cross_filer"
        elif url in seen:
            reason = "duplicate"
        else:
            seen.add(url)
            continue
        conn.execute("DELETE FROM catalyst_source WHERE id=?", (r["id"],))
        dropped.append({"id": r["id"], "source_url": url, "reason": reason})
    conn.commit()
    return dropped


# ── cached-lake retrieval join (research B §1.2) ─────────────────────────────

def _resolve_lake_file(url: str, lake_dir: str) -> Path | None:
    """The archived snapshot for `url` via the reproduced _safe_name stem. Newest on the rare tie
    (same request archived twice = identical content)."""
    stem = _safe_name(_key("text", "edgar_8k", url, None, None))
    root = Path(lake_dir) / "edgar_8k"
    if not root.exists():
        return None
    hits = sorted(root.rglob(f"{stem}_*.txt"), key=lambda p: p.stat().st_mtime)
    return hits[-1] if hits else None


def _strip_tags(raw: str) -> str:
    """Tag-strip an archived 8-K/PR exhibit to plain text (pdufa_edgar.py:143 pattern)."""
    return re.sub(r"\s+", " ", BeautifulSoup(raw, "html.parser").get_text(separator=" ")).strip()


def _closest_source(urls: list[str], reported: dict[str, str], event_date: str) -> str | None:
    """Among own-company exhibit URLs, the one whose reported_date is closest to event_date."""
    if not urls:
        return None

    def dist(u: str) -> int:
        try:
            return abs((date.fromisoformat(reported[u][:10]) - date.fromisoformat(event_date[:10])).days)
        except (ValueError, KeyError, TypeError):
            return 10**6  # unparseable (e.g. month-precision) -> deprioritize, keep order

    return min(urls, key=dist)


@lru_cache(maxsize=1)
def _load_profiles() -> tuple:
    """universe_profiles.json as an immutable tuple (lru-cached; research B §4 reconcile to the 73)."""
    path = _REPO_ROOT / "data" / "universe_profiles.json"
    if not path.exists():
        return ()
    return tuple(json.loads(path.read_text()))


def _profile_for(ticker: str, profiles) -> tuple[str, str]:
    rows = _load_profiles() if profiles is None else profiles
    for p in rows:
        if (p.get("ticker") or "").upper() == ticker.upper():
            pr = p.get("profile") or {}
            return pr.get("indication", ""), pr.get("modality", "")
    return "", ""


def _resolve_own_cik(ticker: str):
    """Cache-miss fallback ONLY (frugality): edgartools ticker->CIK (pdufa_edgar's pattern). Tests
    inject own_cik, so this network path never runs offline."""
    from catalyst_trader.providers.pdufa_edgar import _cik_map

    return next((cik for cik, t in _cik_map([ticker]).items() if t.upper() == ticker.upper()), None)


def build_bundle(conn, catalyst_id: int, *, own_cik=None, lake_dir=None, profiles=None) -> dict | None:
    """A CIK-filtered, event-proximate context bundle for one catalyst, from cached material only.

    own_cik/lake_dir/profiles are injectable so tests stay offline; live runs default to an
    edgartools CIK lookup, settings.raw_snapshot_dir, and data/universe_profiles.json.
    """
    cat = conn.execute(
        "SELECT id, ticker, company_name, catalyst_type, event_date, date_precision "
        "FROM catalyst WHERE id=?",
        (catalyst_id,),
    ).fetchone()
    if cat is None:
        return None
    ticker, event_date = cat["ticker"], cat["event_date"]
    lake_dir = lake_dir or settings.raw_snapshot_dir

    srcs = conn.execute(
        "SELECT source_url, reported_date FROM catalyst_source "
        "WHERE catalyst_id=? AND source_url IS NOT NULL",
        (catalyst_id,),
    ).fetchall()
    edgar_urls = [s["source_url"] for s in srcs if "sec.gov/Archives" in (s["source_url"] or "")]
    ctgov = next((s["source_url"] for s in srcs if "clinicaltrials.gov" in (s["source_url"] or "")), None)
    reported = {s["source_url"]: s["reported_date"] for s in srcs}

    # CIK-filter FIRST, then resolve the closest-dated own-company exhibit from the lake.
    if own_cik is None:
        own_cik = _resolve_own_cik(ticker)
    exhibit_text = None
    if own_cik is not None:
        chosen = _closest_source(cik_filter_exhibits(edgar_urls, own_cik), reported, event_date)
        if chosen:
            f = _resolve_lake_file(chosen, lake_dir)
            if f is not None:
                exhibit_text = _strip_tags(load_snapshot(f))

    mv = conn.execute(
        "SELECT realized_move, move_window, knowable_asof FROM catalyst_move "
        "WHERE catalyst_id=? ORDER BY id LIMIT 1",
        (catalyst_id,),
    ).fetchone()
    indication, modality = _profile_for(ticker, profiles)

    return {
        "catalyst_id": cat["id"],
        "ticker": ticker,
        "catalyst_type": cat["catalyst_type"],
        "indication": indication,
        "modality": modality,
        "event_date": event_date,
        "date_precision": cat["date_precision"],
        "exhibit_text": exhibit_text,
        # ponytail: ctgov corroboration = the study URL's presence (used for the skip decision);
        #           a live overallStatus parse is Plan-04's job if a richer status is ever needed.
        "ctgov": ctgov,
        "signed_move": mv["realized_move"] if mv else None,     # SIGNED; None on month-precision/absent
        "move_window": mv["move_window"] if mv else None,
        "knowable_asof": mv["knowable_asof"] if mv else None,
    }


# ── the extraction prompt (shared taxonomy cached across calls, research B §3.6) ──

_TAXONOMY = (
    "DRIVER TAXONOMY (research A). PDUFA: D2 pivotal-data strength/consistency, D3 endpoint "
    "acceptability, D4 safety signal, D5 prior-CRL reason, D6 CMC/manufacturing readiness, "
    "D9 expedited designations. READOUT: R1 prior effect size/p-value, R2 endpoint hardness, "
    "R7 therapeutic-area base rate. ADCOM: benefit-risk clarity, endpoint acceptability, safety "
    "salience, vote split. Cite EVERY driver with a verbatim quote + source_url or DROP it."
)

# Standards that make INDEPENDENT extractions converge (reproducibility): fixed label enums + rules,
# a fixed reference_class shape, stale-profile self-correction, an honesty rule, and altitude/length.
_LABEL_RUBRIC = (
    "OUTCOME_LABEL enum BY TYPE — PDUFA: approve|crl|delay (a large NEGATIVE signed move => crl even "
    "when the only exhibit is the earlier acceptance PR; large POSITIVE => approve). READOUT: "
    "hit|miss|mixed — judge by whether the PRIMARY endpoint was met AND the market verdict: a "
    "statistically-significant result that missed the approved-competitor benchmark, or whose key "
    "dose/arm failed, is a MISS (cite the effect size vs precedent), not a hit. ADCOM: favorable|unfavorable. "
    "EARNINGS: beat|miss|inline, ANCHORED TO THE SIGNED MOVE (clearly positive reaction => beat, clearly "
    "negative => miss, muted => inline); capture the two-sided detail (e.g. telegraphed milestone vs widening "
    "loss) in the narrative, not the label."
)
_STANDARDS = (
    "STANDARDS (follow exactly for reproducibility): "
    "(1) reference_class MUST name a specific precedent GROUP + a rough BASE RATE + directional tendency "
    "(e.g. 'CMC/PAI CRLs for CDMO-dependent small pharma: usually curable, high eventual-approval, 6-12mo delay'). "
    "(2) If the given INDICATION/MODALITY conflicts with the exhibit's actual lead asset (a stale profile after a "
    "pivot/acquisition), set the corrected `indication` and `modality` at the TOP LEVEL of your JSON and explain in "
    "causal_setup; otherwise omit them. "
    "(3) If the exhibit does NOT state the outcome REASON, SAY SO in why_narrative and reason from the reference "
    "class + the signed move — NEVER fabricate a specific reason. "
    "(4) Each narrative field = 2-4 specific sentences, concrete, no boilerplate. "
    "(5) lesson_rule = one reusable IF-<condition>-THEN-<implication> generalization."
)


def build_prompt(bundle: dict) -> str:
    """The extraction system+user prompt: driver taxonomy + narrative spec + strict JSON schema.
    Prompt string ONLY — no model call here (that is complete_fn, injected by the caller)."""
    return (
        "You extract ONE biotech catalyst into strict JSON matching the CatalystRecord contract:\n"
        "{outcome_label, confidence(0..1), drivers:[{factor,value,evidence_quote,source_url}], "
        "narrative_before:{thesis,causal_setup,reference_class,variant_why,what_to_watch[],"
        "what_would_change_our_mind[]}, narrative_after:{what_happened,why_narrative,"
        "surprise_vs_prior,which_disconfirmer_fired,lesson_rule,process_grade,second_order}, "
        "citations:[{url,quote,snippet_hash}]}.\n"
        + _TAXONOMY + "\n" + _LABEL_RUBRIC + "\n" + _STANDARDS + "\n\n"
        f"TICKER: {bundle.get('ticker')}  TYPE: {bundle.get('catalyst_type')}  "
        f"INDICATION: {bundle.get('indication')}  MODALITY: {bundle.get('modality')}\n"
        f"EVENT_DATE: {bundle.get('event_date')}  SIGNED_MOVE: {bundle.get('signed_move')}\n\n"
        f"OWN-COMPANY EXHIBIT (CIK-filtered):\n{bundle.get('exhibit_text') or '[none]'}\n"
    )


# ── deterministic outcome anchoring (research B §3.3-3.4, LOCKED) ─────────────

def _anchor_label(catalyst_type: str, llm_label: str, signed_move) -> str:
    """PDUFA: the SIGNED move is the primary outcome signal (the decision 8-K is usually absent from
    the lake) — large + => approve, - => CRL/delay; text is context. READOUT/ADCOM: text-primary
    (the PR is often the outcome itself), the move only cross-checks."""
    if catalyst_type == "pdufa" and signed_move is not None:
        return "approve" if signed_move > 0 else "crl"
    if catalyst_type == "earnings" and signed_move is not None:
        # move-anchored earnings label (reproducible; the two-sided detail lives in the narrative)
        if signed_move > _EARNINGS_INLINE_BAND:
            return "beat"
        if signed_move < -_EARNINGS_INLINE_BAND:
            return "miss"
        return "inline"
    return llm_label


def extract_record(bundle: dict, complete_fn) -> CatalystRecord | None:
    """Bundle + injected completion -> validated CatalystRecord, or None (skip).

    Skips (None, no LLM call) a NAKED catalyst — no own-company exhibit AND no ctgov AND no move.
    Else: parse complete_fn's JSON, DROP uncited drivers, OVERWRITE the deterministic facts
    (catalyst_id/dates/SIGNED move) from the bundle, anchor the outcome by type, and lower
    confidence on a move/text disagreement or when the move is unavailable (month-precision).
    """
    text, move, ctgov = bundle.get("exhibit_text"), bundle.get("signed_move"), bundle.get("ctgov")
    if not text and move is None and not ctgov:
        return None  # naked -> caller skips, no node (research B §4)

    data = json.loads(complete_fn(build_prompt(bundle)))

    drivers = [
        DriverClaim(**d)
        for d in data.get("drivers", [])
        if d.get("source_url") and d.get("evidence_quote")  # cite-or-drop
    ]
    label = _anchor_label(bundle["catalyst_type"], data.get("outcome_label", ""), move)

    conf = float(data.get("confidence", 0.0))
    if move is None:
        conf *= _MONTH_PRECISION_PENALTY          # corroboration unavailable
    elif compute_move_consistency(label, move):
        conf *= _DISAGREE_PENALTY                 # label vs move sign disagree
    conf = max(0.0, min(1.0, conf))

    return CatalystRecord(
        catalyst_id=bundle["catalyst_id"],        # deterministic facts: from the bundle, not the LLM
        ticker=bundle["ticker"],
        catalyst_type=bundle["catalyst_type"],
        # stale-profile self-correct: use the LLM's exhibit-derived indication/modality when it
        # overrides a stale stored profile (QNCX-style pivot), else the bundle's.
        indication=(data.get("indication") or bundle.get("indication") or ""),
        modality=(data.get("modality") or bundle.get("modality") or ""),
        event_date=bundle["event_date"],
        knowable_asof=bundle.get("knowable_asof") or bundle["event_date"],
        outcome_label=label,
        signed_move=move,
        move_window=bundle.get("move_window") or "",
        confidence=conf,
        drivers=drivers,
        narrative_before=NarrativeBefore(**data["narrative_before"]),
        narrative_after=NarrativeAfter(**data["narrative_after"]),
        citations=[Citation(**c) for c in data.get("citations", [])],
    )
