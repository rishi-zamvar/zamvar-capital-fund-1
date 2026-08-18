"""Knowledge-base write-path + default deterministic embedder.

The KB stores an L2-normalized vector per node in kb_vec (vec0 float[1024] cosine). Production uses
a real open-source semantic embedder (BAAI/bge-large-en-v1.5, 1024-dim, local via fastembed/ONNX —
no API, no rate limits, private). The default deterministic hash embedder is offline and
dependency-free so the whole KB still tests with zero network / zero ML deps.

Provenance invariant (KB-02): a claim node may not be committed without at least one
:CITES -> EvidenceSource edge. Enforced in ONE transaction, exactly like store.insert_catalyst
rejects a source-less catalyst — reject before write, roll back completely on any failure.

# ponytail: one write-path; all KB writes route through insert_claim, like Phase-1 routes through
#           store.py. No agent writes a claim via raw SQL — that would sidestep the invariant.
"""

import copy
import hashlib
import json
import sqlite3
from pathlib import Path

from pydantic import BaseModel, field_validator
from sqlite_vec import serialize_float32

from catalyst_trader.dates import now_iso

EMBED_DIM = 1024
_DATA_DIR = Path(__file__).resolve().parents[2] / "data"  # repo-root/data (mirrors quant/base_rates.py)

# The kind/rel enums are the DB CHECK constraints (migration 003) — kept here so a bad value is
# rejected at the pydantic boundary too, not only at the SQLite backstop.
_NODE_KINDS = frozenset(
    {
        "company", "drug", "indication", "trial", "catalyst", "outcome",
        "trade", "playbook", "evidence_source", "prediction", "hedge_peer",
    }
)




class EvidenceSource(BaseModel):
    """A citation: where a claim's fact came from. Deduped on (url, snippet_hash)."""

    url: str
    retrieved_at: str
    snippet_hash: str
    quote: str | None = None


class KBNode(BaseModel):
    """A graph node. `attrs` is the kind-specific payload, serialized to attrs_json on write."""

    kind: str
    ref_id: int | None = None  # optional link to a Phase-1 row (e.g. catalyst.id) — don't copy data
    attrs: dict = {}
    confidence: float | None = None

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, v: str) -> str:
        if v not in _NODE_KINDS:
            raise ValueError(f"unknown kb_node kind {v!r} (not in migration-003 enum)")
        return v

    @property
    def attrs_json(self) -> str:
        return json.dumps(self.attrs)


def _upsert_evidence(conn: sqlite3.Connection, ev: EvidenceSource) -> int:
    """Return the id of the evidence_source node for `ev`, inserting it if absent.

    Dedup on (snippet_hash, url) via json_extract so re-citing the same source reuses one node.
    """
    row = conn.execute(
        "SELECT id FROM kb_node WHERE kind='evidence_source' "
        "AND json_extract(attrs_json,'$.snippet_hash')=? "
        "AND json_extract(attrs_json,'$.url')=?",
        (ev.snippet_hash, ev.url),
    ).fetchone()
    if row is not None:
        return row["id"]
    attrs = json.dumps(
        {"url": ev.url, "retrieved_at": ev.retrieved_at, "snippet_hash": ev.snippet_hash, "quote": ev.quote}
    )
    return conn.execute(
        "INSERT INTO kb_node (kind, ref_id, attrs_json, confidence, created_at) "
        "VALUES ('evidence_source', NULL, ?, NULL, ?)",
        (attrs, now_iso()),
    ).lastrowid


def add_edge(conn, src_id, rel, dst_id, weight=None, attrs=None) -> int:
    """Insert one kb_edge (no commit — runs inside the caller's transaction). Used by insert_claim
    for CITES and by Plan 02-04 for HEDGE_PEER etc."""
    return conn.execute(
        "INSERT INTO kb_edge (src_id, rel, dst_id, weight, attrs_json, created_at) VALUES (?,?,?,?,?,?)",
        (src_id, rel, dst_id, weight, json.dumps(attrs) if attrs is not None else None, now_iso()),
    ).lastrowid


def insert_claim(conn, node: KBNode, evidence: list[EvidenceSource], embed=None, embed_text=None) -> int:
    """Persist a claim node + its CITES->EvidenceSource edges (+ optional vector) atomically.

    Shape lifted verbatim from store.insert_catalyst: reject before any write if there is no
    evidence, then node insert -> per-evidence upsert + CITES edge -> optional kb_vec row, all in
    one transaction that rolls back completely on any failure (no orphan node/edge/vec survives).
    """
    if not evidence:
        raise ValueError("cannot store a claim without a CITES->EvidenceSource edge")
    try:
        nid = conn.execute(
            "INSERT INTO kb_node (kind, ref_id, attrs_json, confidence, created_at) VALUES (?,?,?,?,?)",
            (node.kind, node.ref_id, node.attrs_json, node.confidence, now_iso()),
        ).lastrowid
        for ev in evidence:
            eid = _upsert_evidence(conn, ev)
            add_edge(conn, nid, "CITES", eid)
        if embed is not None and embed_text is not None:
            conn.execute(
                "INSERT INTO kb_vec (node_id, embedding) VALUES (?, ?)",
                (nid, serialize_float32(embed(embed_text))),
            )
        conn.commit()
        return nid
    except Exception:
        conn.rollback()
        raise


def get_node(conn, node_id: int) -> dict | None:
    """Return a node as a dict with `attrs` parsed from attrs_json, or None if absent."""
    row = conn.execute("SELECT * FROM kb_node WHERE id=?", (node_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["attrs"] = json.loads(d["attrs_json"]) if d["attrs_json"] else {}
    return d


def _structural_filter(conn, filters: dict, as_of: str | None = None) -> set[int]:
    """Candidate catalyst node ids whose attrs match every key in `filters` (deterministic SQL).

    A scenario failing the structural filter never reaches the semantic rank, even if
    embedding-close. Empty filters -> every catalyst is a candidate.

    `as_of` is the NO-LOOK-AHEAD gate (research C §5.3): when set, only catalysts with
    knowable_asof <= as_of survive. ISO YYYY-MM-DD strings compare lexicographically, so <= is a
    correct date compare. Fail-safe: a node MISSING knowable_asof has json_extract -> NULL, and
    `NULL <= date` is NULL (falsy) in SQLite, so an undated node is EXCLUDED under any set as_of.
    Default None = no gate = today's behavior (every existing caller/test is untouched).
    """
    sql = "SELECT id FROM kb_node WHERE kind='catalyst'"
    params: list = []
    for key, val in filters.items():
        # GENERIC list-membership (no fork): a LIST value matches any candidate whose $.key (scalar
        # OR json array) overlaps it; a SCALAR value keeps the exact match AND allows list-membership
        # so a scalar query can still match a list attr. json_each over a MISSING path yields no rows
        # (EXISTS false), over a scalar yields that scalar — so scalar filters stay correct.
        if isinstance(val, (list, tuple)):
            if not val:
                continue  # empty list = no constraint on this key (never emit `IN ()`)
            marks = ",".join("?" for _ in val)
            sql += (f" AND (json_extract(attrs_json,'$.{key}') IN ({marks})"
                    f" OR EXISTS(SELECT 1 FROM json_each(attrs_json,'$.{key}') WHERE value IN ({marks})))")
            params.extend(val)
            params.extend(val)
        else:
            sql += (f" AND (json_extract(attrs_json,'$.{key}')=?"
                    f" OR EXISTS(SELECT 1 FROM json_each(attrs_json,'$.{key}') WHERE value=?))")
            params.append(val)
            params.append(val)
    if as_of is not None:
        sql += " AND json_extract(attrs_json,'$.knowable_asof') <= ?"
        params.append(as_of)
    return {r["id"] for r in conn.execute(sql, params).fetchall()}


def conditional_filters(conn, ctype: str, indication: str | None = None, min_analogs: int = 5) -> dict:
    """Structural filter dict that adds `indication` to the type filter ONLY when the type+indication
    cohort still yields >= min_analogs — else falls back to type-only so the KNN is never starved
    below the estimator's min_analogs. Base is always {"type": ctype}."""
    filters = {"type": ctype}
    if indication is None:
        return filters
    n = conn.execute(
        "SELECT COUNT(*) AS c FROM kb_node WHERE kind='catalyst' "
        "AND json_extract(attrs_json,'$.type')=? AND json_extract(attrs_json,'$.indication')=?",
        (ctype, indication),
    ).fetchone()["c"]
    if n >= min_analogs:
        filters["indication"] = indication
    return filters


def setup_filters(conn, ctype: str, setups, min_analogs: int = 5) -> dict:
    """Structural filter dict that adds a `setups` LIST-membership axis to the type filter ONLY when
    the type+setups cohort yields >= min_analogs members — else falls back to type-only so the KNN is
    never starved (mirrors conditional_filters, but counts a LIST cohort via json_each, a genuinely
    different axis than the scalar indication gate). None/empty setups -> type-only.
    """
    filters = {"type": ctype}
    if not setups:
        return filters
    marks = ",".join("?" for _ in setups)
    n = conn.execute(
        f"SELECT COUNT(*) AS c FROM kb_node WHERE kind='catalyst' "
        f"AND json_extract(attrs_json,'$.type')=? "
        f"AND EXISTS(SELECT 1 FROM json_each(attrs_json,'$.setups') WHERE value IN ({marks}))",
        (ctype, *setups),
    ).fetchone()["c"]
    if n >= min_analogs:
        filters["setups"] = list(setups)
    return filters


def _with_outcome(conn, node_id: int, distance: float) -> dict:
    """Attach the catalyst's realized Outcome (via RESULTED_IN edge) so callers cite base rates."""
    cat = get_node(conn, node_id)
    row = conn.execute(
        "SELECT dst_id FROM kb_edge WHERE src_id=? AND rel='RESULTED_IN' ORDER BY id LIMIT 1",
        (node_id,),
    ).fetchone()
    outcome = get_node(conn, row["dst_id"]) if row is not None else None
    return {
        "node_id": node_id,
        "distance": distance,
        "catalyst": cat["attrs"] if cat else None,
        "outcome": outcome["attrs"] if outcome else None,
    }


def analog_query(conn, embed, context: str, filters: dict, k: int = 5, as_of: str | None = None) -> list[dict]:
    """Nearest past scenarios matching `filters`, ranked by semantic similarity to `context`,
    each with its realized Outcome. Structural SQL filter first, then KNN rank (KB-03).

    `as_of` is the NO-LOOK-AHEAD gate (default None = unchanged): it filters candidates to
    knowable_asof <= as_of. Because knowable_asof is the T+2 date, gating the catalyst also gates
    its realized move — one gate covers existence AND outcome (research C §5.3).

    # ponytail: SQL-filter + python-set intersect avoids sqlite-vec's alpha metadata-filter API;
    #           brute-force KNN over hundreds of vecs is sub-ms. Over-fetch k*4 then intersect.
    """
    cand = _structural_filter(conn, filters, as_of=as_of)
    if not cand:
        return []
    q = serialize_float32(embed(context))
    # REACHABILITY: with a LIST filter active, a setup-matched-but-disease-distant precedent can fall
    # outside the global top k*4 KNN — deepen the over-fetch to the whole vec set so it is rankable.
    # Brute-force KNN over hundreds of vecs is sub-ms, so ranking all is free at this scale.
    if any(isinstance(v, (list, tuple)) for v in filters.values()):
        overfetch = conn.execute("SELECT COUNT(*) AS c FROM kb_vec").fetchone()["c"]
    else:
        overfetch = k * 4
    rows = conn.execute(
        "SELECT node_id, distance FROM kb_vec WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
        (q, overfetch or k * 4),
    ).fetchall()
    ranked = [r for r in rows if r["node_id"] in cand][:k]
    return [_with_outcome(conn, r["node_id"], r["distance"]) for r in ranked]


def _get_or_create_company(conn, ticker: str) -> int:
    """Company nodes are reference nodes (not claims) so they need no citation. Get-or-create by ticker."""
    row = conn.execute(
        "SELECT id FROM kb_node WHERE kind='company' AND json_extract(attrs_json,'$.ticker')=?",
        (ticker,),
    ).fetchone()
    if row is not None:
        return row["id"]
    return conn.execute(
        "INSERT INTO kb_node (kind, ref_id, attrs_json, confidence, created_at) "
        "VALUES ('company', NULL, ?, NULL, ?)",
        (json.dumps({"ticker": ticker}), now_iso()),
    ).lastrowid


def insert_hedge_peer(conn, name, peer, mechanism, payoff_direction, weight, evidence) -> int:
    """Store a hedge relationship for `name` as a CITED hedge_peer claim (KB-04).

    A hedge relationship is a claim, so it MUST carry a citation — routed through insert_claim so
    the provenance invariant is enforced atomically. Also writes a HEDGE_PEER edge between the two
    company nodes for graph traversal. `payoff_direction` sign is explicit: +1 correlated co-move,
    -1 inverse-payoff (PROJECT.md vs ARCHITECTURE.md readings) — store the sign, don't hard-code polarity.
    """
    if payoff_direction not in (-1, 1):
        raise ValueError(f"payoff_direction must be +1 or -1, got {payoff_direction!r}")
    if not evidence:
        raise ValueError("cannot store a hedge peer without a CITES->EvidenceSource edge")
    name_id = _get_or_create_company(conn, name)
    peer_id = _get_or_create_company(conn, peer)
    attrs = {"name": name, "peer": peer, "mechanism": mechanism,
             "payoff_direction": payoff_direction, "weight": weight}
    # insert_claim commits (companies included); then add the traversal edge and commit it.
    hp_id = insert_claim(conn, KBNode(kind="hedge_peer", attrs=attrs), evidence)
    add_edge(conn, name_id, "HEDGE_PEER", peer_id, weight=weight,
             attrs={"mechanism": mechanism, "payoff_direction": payoff_direction})
    conn.commit()
    return hp_id


def hedge_peers(conn, name: str) -> list[dict]:
    """Every hedge_peer claim for `name` with its mechanism, payoff_direction, weight, and citations."""
    rows = conn.execute(
        "SELECT id, attrs_json FROM kb_node WHERE kind='hedge_peer' "
        "AND json_extract(attrs_json,'$.name')=?",
        (name,),
    ).fetchall()
    out = []
    for r in rows:
        a = json.loads(r["attrs_json"])
        cites = conn.execute(
            "SELECT dst_id FROM kb_edge WHERE src_id=? AND rel='CITES'", (r["id"],)
        ).fetchall()
        evidence = [get_node(conn, c["dst_id"])["attrs"] for c in cites]
        out.append({
            "peer": a["peer"], "mechanism": a["mechanism"],
            "payoff_direction": a["payoff_direction"], "weight": a["weight"],
            "evidence": evidence,
        })
    return out


def insert_playbook(conn, scenario_type, scenario, strategy, confidence, evidence) -> int:
    """Store a playbook as a derived, cited claim (KB-05).

    Routed through insert_claim so the citation invariant holds — playbooks cite the outcomes they
    generalize from. `confidence` is a first-class kb_node column (surfaced by every query).
    """
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be in [0,1], got {confidence!r}")
    node = KBNode(
        kind="playbook",
        confidence=confidence,
        attrs={"scenario_type": scenario_type, "scenario": scenario, "strategy": strategy},
    )
    return insert_claim(conn, node, evidence)


_BOOTSTRAP_CSV = _DATA_DIR / "fitted_params_bootstrap.csv"
_SEED_CONFIDENCE = 0.3  # low so any later, better fit shadows the bootstrap (versioning)


def seed_fitted_params(conn, csv_path: str | None = None) -> int:
    """Seed one CITED fitted_params:<type> playbook per row of the bootstrap CSV so the estimator /
    SL-TP tools AND the trade builder are parameterized from trade #1. Each row becomes a strategy
    dict {estimator, sl_tp, builder, fit_source} inserted via insert_playbook WITH its EvidenceSource
    (cite-or-drop — a row missing its evidence URL raises). Seeded at a low confidence so the Phase-9
    refit loop's higher-confidence fits shadow it automatically. Returns the count seeded.
    """
    import csv as _csv

    path = Path(csv_path) if csv_path else _BOOTSTRAP_CSV
    with path.open(newline="") as f:
        rows = list(_csv.DictReader(f))
    seeded = 0
    for r in rows:
        ctype = r["catalyst_type"]
        if not r.get("evidence_url", "").strip():
            raise ValueError(f"fitted_params bootstrap row {ctype!r} has no evidence URL (cite-or-drop)")
        strategy = {
            "estimator": {
                "method": r["method"],
                "min_analogs": int(r["min_analogs"]),
                "implied_blend": float(r["implied_blend"]),
                "default_down_move": float(r["default_down_move"]),
            },
            "sl_tp": {
                "sl_vol_mult": float(r["sl_vol_mult"]),
                "tp_frac": float(r["tp_frac"]),
                "drift_coef": float(r["drift_coef"]),
            },
            "builder": {
                "min_tradeable_size": float(r["min_tradeable_size"]),
                "log_growth_margin": float(r["log_growth_margin"]),
                "runup_capture_frac": float(r["runup_capture_frac"]),
            },
            # FF-06 field knobs seeded uncalibrated (refit Phase 9). Direct subscript so a missing
            # column raises, same cite-or-drop discipline as evidence_url.
            "field": {
                "min_methods": int(r["min_methods"]),
                "trim_frac": float(r["trim_frac"]),
                "dispersion_wide": float(r["dispersion_wide"]),
                "move_discrepancy_tol": float(r["move_discrepancy_tol"]),
                "weights": json.loads(r["field_weights_json"]),
            },
            "fit_source": r["fit_source"],
        }
        ev = EvidenceSource(
            url=r["evidence_url"],
            retrieved_at=now_iso(),
            snippet_hash=hashlib.sha256(r["evidence_snippet"].encode()).hexdigest(),
            quote=r["evidence_snippet"] or None,
        )
        insert_playbook(
            conn, f"fitted_params:{ctype}", f"{ctype} bootstrap params",
            strategy, _SEED_CONFIDENCE, [ev],
        )
        seeded += 1
    return seeded


def query_playbooks(conn, scenario_type: str) -> list[dict]:
    """Playbooks for `scenario_type`, confidence-desc, each surfacing its first-class confidence."""
    rows = conn.execute(
        "SELECT id, confidence, attrs_json FROM kb_node "
        "WHERE kind='playbook' AND json_extract(attrs_json,'$.scenario_type')=? "
        "ORDER BY confidence DESC",
        (scenario_type,),
    ).fetchall()
    out = []
    for r in rows:
        a = json.loads(r["attrs_json"])
        out.append({
            "id": r["id"], "confidence": r["confidence"],
            "scenario_type": a["scenario_type"], "scenario": a["scenario"], "strategy": a["strategy"],
        })
    return out


# The ONLY literal fitted-param set allowed anywhere (WARNING fix): the cold-start default so
# load_params never returns None and the estimator / SL-TP tools + the trade builder are
# parameterized from trade #1. Every OTHER param set is a cited, versioned fitted_params:<type>
# playbook (seed_fitted_params + the Phase-9 refit loop). The builder group's hold-vs-exit +
# tradeable-size thresholds live HERE (and in the cited CSV), never as literals in the builder body.
BOOTSTRAP_DEFAULT = {
    "estimator": {"method": "median", "min_analogs": 5, "implied_blend": 0.5, "default_down_move": 0.70},
    "sl_tp": {"sl_vol_mult": 1.0, "tp_frac": 0.8, "drift_coef": 0.0},
    "builder": {"min_tradeable_size": 0.002, "log_growth_margin": 0.0, "runup_capture_frac": 0.3},
    # WEEK-02: the weekly thesis engine reads EVERY threshold from here (never a literal in a tool
    # body). Not in the fitted_params CSV — that schema is catalyst-shaped; weekly base rates are
    # bar-computed at query time. Phase-10 LEARN refits the SOURCE, not these consumers.
    "weekly": {
        "anchor": "MON_OPEN",          # measurement window == execution window (the trap)
        "beta_window_weeks": 104,      # rolling beta vs XBI
        "sector_frac_cut": 0.5,        # |idio| < cut*|ret| -> sector_beta drop
        "turnover_lookback": 52,       # Medhat-Schmeling turnover switch
        "window_years": 10,            # base-rate rolling window
        "min_effective_n": 30,         # tradeability bar: n >= 30
        "shrink_prior_weight": 30,     # beta-binomial prior pseudo-obs (research 20-50)
        "edge_min_pts": 0.02,          # tradeability bar: shrunk P(up) - cohort baseline >= 2pts
        "cost_mult": 2,                # tradeability bar: mean_next > cost_mult * roundtrip_cost
        "roundtrip_cost": 0.005,       # est. spread+slippage round-trip (~50bp small-biotech)
        "hard_veto_drop": -0.15,       # -15% falling-knife: NEVER bounce-eligible
        "shortlist_k": 4,              # desk weekend pass shortlist size
        "defensive_instruments": ["SGOV", "BIL", "XBI"],
        "defensive_max_frac": 1.0,     # defensive book may be the whole book
        "statistical_sleeve_cap": 0.5, # max fraction of the weekly risk budget in statistical legs when catalyst legs exist (research §4.5 knob #4)
    },
    # FF-06: the football-field aggregator / builder / DD / cross_check read EVERY threshold + method
    # weight from here (never a literal in a consumer body). ALL UNCALIBRATED — labeled for Phase-9
    # refit (RESEARCH §6 + Open Questions). Deliberately DECOUPLED from diligence.DILIGENCE_PARAMS.
    "field": {
        "min_methods": 2,             # a one-method "field" raises (no false precision)
        "trim_frac": 0.0,             # pure weighted median default; trim only when n is large (Open Q3)
        "dispersion_wide": 0.5,       # CV threshold for "wide" cross-method disagreement (uncalibrated)
        "move_discrepancy_tol": 0.35, # builder-vs-DD relative gap tolerance (uncalibrated, Open Q2)
        "weights": {                  # structural reliability -> ordinal weight (Open Q1, uncalibrated)
            "analog_cold": 0.5, "analog_warm": 1.0,
            "implied_liquid": 1.0, "base_rate_thin": 0.5, "base_rate_ample": 1.0,
            "rnpv_scenario": 1.0, "analyst_pt": 0.75,
        },
    },
    "fit_source": "bootstrap default (uncalibrated) — refit from realized outcomes in Phase 9",
}


def load_params(conn, catalyst_type: str) -> dict:
    """Top (highest-confidence) fitted_params:<type> playbook's strategy dict, or the bootstrap
    default when none exists. The ONE seam Phase-9's refit loop replaces the SOURCE of — signature
    frozen. Only the source of params changes over time; the quant tools + builder stay pure (they
    take the dict IN). The DB read lives here, not in the tools.
    """
    rows = query_playbooks(conn, f"fitted_params:{catalyst_type}")
    if rows:
        return rows[0]["strategy"]        # query_playbooks is confidence-desc → [0] is the winning version
    return copy.deepcopy(BOOTSTRAP_DEFAULT)  # cold-start default (labeled); copy so callers can't poison it


def hash_embed(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Deterministic, offline, L2-normalized embedding of `text` (default 1024-dim).

    Same text -> same vector, no network, no ML dep. Not semantically meaningful — plumbing only.
    """
    out: list[float] = []
    i = 0
    while len(out) < dim:
        h = hashlib.sha256(f"{text}#{i}".encode()).digest()
        out += [b / 255.0 - 0.5 for b in h]
        i += 1
    v = out[:dim]
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]  # L2-normalized for cosine


# ponytail: hash embedder = plumbing only, not semantic quality. The real semantic embedder below
#           is a drop-in behind the same callable; tests keep using hash_embed (offline).

_LOCAL_MODEL = None
_LOCAL_MODEL_NAME = "BAAI/bge-large-en-v1.5"  # open-source, 1024-dim, local ONNX via fastembed


def _local_model():
    global _LOCAL_MODEL
    if _LOCAL_MODEL is None:
        from fastembed import TextEmbedding  # lazy: only imported/loaded when actually embedding
        _LOCAL_MODEL = TextEmbedding(_LOCAL_MODEL_NAME)
    return _LOCAL_MODEL


def local_embed(text: str) -> list[float]:
    """Real semantic 1024-dim embedding via a local open-source model (no API, private).

    Meaning-based similarity (unlike hash_embed's lexical vectors). Model loads lazily on first call
    and is cached for the process. Requires the `fastembed` optional dependency.
    """
    vec = next(iter(_local_model().embed([text])))
    return [float(x) for x in vec]


def default_embedder():
    """Pick the production embedder: local semantic model if available, else the offline hash.

    Force the offline embedder with env CT_EMBEDDER=hash (used to keep any headless run network-free).
    Tests never call this — they inject hash_embed via the `embed` fixture — so the suite stays offline.
    """
    import importlib.util
    import os

    if os.environ.get("CT_EMBEDDER", "").lower() == "hash":
        return hash_embed
    if importlib.util.find_spec("fastembed") is not None:
        return local_embed
    return hash_embed
