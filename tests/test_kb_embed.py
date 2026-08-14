"""Embedder tests: offline deterministic (always) + real semantic (skipped if fastembed absent)."""
import importlib.util

import pytest

from catalyst_trader import kb


def _cos(x, y):
    d = sum(a * b for a, b in zip(x, y))
    nx = sum(a * a for a in x) ** 0.5
    ny = sum(b * b for b in y) ** 0.5
    return d / (nx * ny)


def test_hash_embed_is_1024_and_normalized():
    v = kb.hash_embed("some catalyst text")
    assert kb.EMBED_DIM == 1024
    assert len(v) == 1024
    assert abs(sum(c * c for c in v) ** 0.5 - 1.0) < 1e-6


def test_default_embedder_can_be_forced_offline(monkeypatch):
    monkeypatch.setenv("CT_EMBEDDER", "hash")
    assert kb.default_embedder() is kb.hash_embed


@pytest.mark.skipif(
    importlib.util.find_spec("fastembed") is None, reason="fastembed (optional) not installed"
)
def test_local_embed_is_1024_and_semantic():
    a = kb.local_embed("Phase 3 oncology PDUFA decision after a prior CRL")
    b = kb.local_embed("late-stage cancer therapy resubmitted following an FDA rejection")
    c = kb.local_embed("quarterly earnings beat for a consumer software company")
    assert len(a) == 1024
    # meaning-based: the paraphrase must be closer than the unrelated sentence
    assert _cos(a, b) > _cos(a, c)
