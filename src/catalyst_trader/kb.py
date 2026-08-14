"""Knowledge-base module: the default deterministic embedder (later plans add the write/query paths).

The KB stores an L2-normalized vector per node in kb_vec (vec0 float[384] cosine). The default
embedder here is offline and dependency-free so the whole KB tests with zero network / zero ML deps.
"""

import hashlib

EMBED_DIM = 384


def hash_embed(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Deterministic, offline, L2-normalized embedding of `text` (default 384-dim).

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


# ponytail: hash embedder = plumbing only, not semantic quality; swap to model2vec/MiniLM behind
#           this callable when analog quality matters (later phase).
