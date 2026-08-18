"""ATTRIBUTION back-half: persist ONE validated CatalystRecord (Plan 01) into the KB through the
existing cite-or-drop write path (kb.insert_claim / kb.add_edge). One catalyst node + one outcome
node + a RESULTED_IN edge + CITES on both + one kb_vec row embedding the composed card.

SCOPE (PLAY-06): the writer lives here, not in kb.py, so kb.py stays owned by the leak-gate plan
("populate, don't rebuild the scaffold"). It re-uses insert_claim's invariant verbatim — every node
routes through insert_claim (no raw node SQL), so cite-or-drop holds atomically.

MONEY / LEAK invariants:
- knowable_asof/type/ticker/indication/modality are TOP-LEVEL on the catalyst attrs (to_catalyst_attrs)
  so kb._structural_filter's json_extract('$.<key>') and the no-look-ahead gate work.
- the outcome key is literally "move" and SIGNED (to_outcome_attrs) — the desk/builder.py contract.
- EMBEDDER CONSISTENCY (plan-check NIT 2): the embedder identity is stamped on every catalyst node at
  populate time; assert_embedder_consistency lets the warm-retrieval path (Plan 05) refuse to query a
  corpus with a different embedder, and insert_catalyst_record refuses to grow a corpus with a second
  embedder — mixing hash-populate with fastembed-query is silent garbage KNN.

# ponytail: the denormalized knowable_asof on the catalyst attr IS the leak stamp; if catalyst_move is
#   recomputed on a different window the card/facts change -> content_sha changes -> idempotency
#   re-writes a fresh node on the next populate. Re-run populate after any move-window recompute.
"""

import hashlib

from catalyst_trader import kb
from catalyst_trader.dates import now_iso
from catalyst_trader.kb import EvidenceSource, KBNode, add_edge, insert_claim
from catalyst_trader.playbook.schema import (
    CatalystRecord,
    compose_card,
    to_catalyst_attrs,
    to_outcome_attrs,
)


def _content_sha(record: CatalystRecord) -> str:
    """sha256 over the record's canonical JSON — the change-detector for idempotent re-writes."""
    return hashlib.sha256(record.model_dump_json().encode()).hexdigest()


def _embedder_name(embed) -> str:
    """Stable identity for an embedder callable (kb.hash_embed -> 'hash_embed', local_embed ->
    'local_embed'). __name__ survives the kb.default_embedder() indirection since it returns the
    real function object, not a wrapper."""
    return getattr(embed, "__name__", repr(embed))


def _existing(conn, catalyst_id: int):
    """(node_id, content_sha) of the already-populated catalyst node for `catalyst_id`, or None.

    Newest wins on the rare content-hash re-write tie (a re-populate leaves the fresh node last).
    """
    row = conn.execute(
        "SELECT id, json_extract(attrs_json,'$.content_sha') AS sha FROM kb_node "
        "WHERE kind='catalyst' AND ref_id=? ORDER BY id DESC LIMIT 1",
        (catalyst_id,),
    ).fetchone()
    return (row["id"], row["sha"]) if row is not None else None


def assert_embedder_consistency(conn, embed) -> None:
    """Raise if `embed` differs from the embedder the catalyst corpus was populated with.

    The warm-retrieval path (Plan 05) calls this before an analog_query so a query embedder that
    doesn't match the populate embedder can't silently return garbage KNN. No-op on an empty corpus.
    """
    name = _embedder_name(embed)
    rows = conn.execute(
        "SELECT DISTINCT json_extract(attrs_json,'$.embedder') AS e FROM kb_node "
        "WHERE kind='catalyst' AND json_extract(attrs_json,'$.embedder') IS NOT NULL"
    ).fetchall()
    populated = {r["e"] for r in rows}
    if populated and name not in populated:
        raise ValueError(
            f"embedder mismatch: querying/writing with {name!r} but the catalyst corpus was "
            f"populated with {populated} — cross-embedder KNN is garbage. Re-populate or match."
        )


def insert_catalyst_record(conn, record: CatalystRecord, embed) -> int:
    """Persist one CatalystRecord as a cited catalyst node + outcome node + RESULTED_IN, idempotently.

    Returns the catalyst node id. Idempotent on (ref_id, content_sha): an unchanged record is a
    no-op that returns the existing id; a content change writes a fresh node. Every node routes
    through insert_claim (cite-or-drop) — no raw kb_node INSERT.
    """
    assert_embedder_consistency(conn, embed)  # refuse to grow the corpus with a 2nd embedder (NIT 2)

    sha = _content_sha(record)
    prev = _existing(conn, record.catalyst_id)
    if prev is not None and prev[1] == sha:
        return prev[0]  # unchanged -> skip (idempotent re-run)

    evidence = [
        EvidenceSource(url=c.url, retrieved_at=now_iso(),
                       snippet_hash=c.snippet_hash, quote=c.quote)
        for c in record.citations
    ]

    cat_attrs = to_catalyst_attrs(record) | {"content_sha": sha, "embedder": _embedder_name(embed)}
    cat_node = KBNode(kind="catalyst", ref_id=record.catalyst_id,
                      attrs=cat_attrs, confidence=record.confidence)
    cat_id = insert_claim(conn, cat_node, evidence, embed=embed, embed_text=compose_card(record))

    out_node = KBNode(kind="outcome", attrs=to_outcome_attrs(record), confidence=record.confidence)
    out_id = insert_claim(conn, out_node, evidence)  # cited, NO vector on the outcome node

    add_edge(conn, cat_id, "RESULTED_IN", out_id)
    conn.commit()
    return cat_id
