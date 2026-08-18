"""GENERALIZE: graduate recurring per-catalyst lesson_rules into cited per-scenario playbook nodes.

A single catalyst is an anecdote; a (type, reference_class) class with a base rate and a standing
lesson is precedent (research C §2.3, research D §1d "Bridgewater machine"). This harvests the
populated catalyst corpus (playbook.store wrote it) and, for each recurring group, writes ONE cited
insert_playbook scenario node the desk's query_playbooks tool consumes.

NAMESPACE SAFETY: scenario_type is FREE-FORM f"{type}:{slug}" and MUST NEVER collide with the
reserved fitted_params:<type> namespace (kb.py load_params seam) — a collision would poison
load_params. Asserted before every write.

Pure-read + insert_playbook only: never seed_fitted_params, never a raw kb_node INSERT — so
cite-or-drop holds atomically (insert_playbook routes through insert_claim).
"""

import json
import re
import statistics
from collections import Counter

from catalyst_trader.kb import EvidenceSource, get_node, insert_playbook, query_playbooks

_RESERVED = "fitted_params:"


def _slug(reference_class: str) -> str:
    """Stable short token for the scenario_type suffix: lowercased, non-alnum -> '_', collapsed."""
    s = re.sub(r"[^a-z0-9]+", "_", reference_class.lower()).strip("_")
    return s[:40] or "unclassified"


def _member_evidence(conn, node_id: int) -> list[EvidenceSource]:
    """The EvidenceSource claims cited by `node_id` (its CITES -> evidence_source nodes)."""
    rows = conn.execute(
        "SELECT dst_id FROM kb_edge WHERE src_id=? AND rel='CITES'", (node_id,)
    ).fetchall()
    out = []
    for r in rows:
        a = get_node(conn, r["dst_id"])["attrs"]
        out.append(EvidenceSource(url=a["url"], retrieved_at=a["retrieved_at"],
                                  snippet_hash=a["snippet_hash"], quote=a.get("quote")))
    return out


def _harvest(conn) -> dict:
    """Group populated catalysts by (type, reference_class), each member carrying its lesson_rule,
    realized outcome (label + signed move), watch-list, and evidence.

    Newest node per ref_id wins (a content re-write leaves a fresh node) so a re-populated catalyst
    isn't double-counted. Catalysts missing type or reference_class are skipped (can't be classed).
    """
    rows = conn.execute(
        "SELECT id, ref_id, attrs_json FROM kb_node WHERE kind='catalyst' ORDER BY id"
    ).fetchall()
    latest = {}  # ref_id -> newest row (ref_id None keyed by its own id)
    for r in rows:
        key = r["ref_id"] if r["ref_id"] is not None else f"_{r['id']}"
        latest[key] = r  # ORDER BY id ASC -> last write wins
    groups: dict = {}
    for r in latest.values():
        a = json.loads(r["attrs_json"])
        nb, na = a.get("narrative_before") or {}, a.get("narrative_after") or {}
        ctype, ref_class = a.get("type"), nb.get("reference_class")
        if not ctype or not ref_class:
            continue
        orow = conn.execute(
            "SELECT dst_id FROM kb_edge WHERE src_id=? AND rel='RESULTED_IN' ORDER BY id LIMIT 1",
            (r["id"],),
        ).fetchone()
        outcome = get_node(conn, orow["dst_id"])["attrs"] if orow else {}
        groups.setdefault((ctype, ref_class), []).append({
            "node_id": r["id"],
            "lesson_rule": na.get("lesson_rule"),
            "label": outcome.get("label"),
            "move": outcome.get("move"),
            "what_to_watch": a.get("what_to_watch") or nb.get("what_to_watch") or [],
            "evidence": _member_evidence(conn, r["id"]),
        })
    return groups


def _dedup_evidence(members: list[dict]) -> list[EvidenceSource]:
    """Union of members' EvidenceSource, deduped on (url, snippet_hash)."""
    seen, out = set(), []
    for m in members:
        for ev in m["evidence"]:
            key = (ev.url, ev.snippet_hash)
            if key not in seen:
                seen.add(key)
                out.append(ev)
    return out


def _confidence(members: list[dict]) -> float:
    """Support x label-agreement, saturating at 5 members (the estimator's min_analogs floor).

    More members AND more agreement on the outcome label -> higher confidence, clamped to [0,1] so
    insert_playbook's invariant holds. A 2-member unanimous group scores 0.4; a 5+-member unanimous
    group scores 1.0.
    """
    labels = [m["label"] for m in members if m["label"]]
    agreement = (Counter(labels).most_common(1)[0][1] / len(labels)) if labels else 0.5
    support = min(1.0, len(members) / 5)
    return round(agreement * support, 4)


def generalize_playbooks(conn, min_support: int = 2) -> int:
    """Harvest recurring (type, reference_class) groups into cited scenario playbook nodes.

    For each group with >= min_support members: write ONE insert_playbook node whose FREE-FORM
    scenario_type is f"{type}:{slug}" (asserted to NEVER start with the reserved fitted_params:),
    carrying the representative lesson_rule (scenario) + base rate + median signed move + member ids
    + unioned watch-list (strategy), cited by the union of the members' evidence. Idempotent: an
    existing scenario_type is skipped, not duplicated. Returns the count written.
    """
    written = 0
    for (ctype, ref_class), members in _harvest(conn).items():
        if len(members) < min_support:
            continue
        scenario_type = f"{ctype}:{_slug(ref_class)}"
        assert not scenario_type.startswith(_RESERVED), (
            f"scenario_type {scenario_type!r} collides with the reserved {_RESERVED!r} namespace "
            f"(would poison load_params)"
        )
        if query_playbooks(conn, scenario_type):
            continue  # idempotent: already generalized
        evidence = _dedup_evidence(members)
        if not evidence:
            continue  # cite-or-drop: a group with no cited members can't graduate
        labels = [m["label"] for m in members if m["label"]]
        moves = [m["move"] for m in members if m["move"] is not None]
        lesson = Counter(m["lesson_rule"] for m in members if m["lesson_rule"]).most_common(1)
        strategy = {
            "base_rate": {lbl: round(c / len(labels), 4) for lbl, c in Counter(labels).items()} if labels else {},
            "median_move": round(statistics.median(moves), 4) if moves else None,
            "n": len(members),
            "member_ids": sorted(m["node_id"] for m in members),
            "what_to_watch": sorted({w for m in members for w in m["what_to_watch"]}),
            "reference_class": ref_class,
        }
        scenario = lesson[0][0] if lesson else ref_class
        insert_playbook(conn, scenario_type, scenario, strategy, _confidence(members), evidence)
        written += 1
    return written
