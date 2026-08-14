"""Deterministic hash embedder: dimension, determinism, distinctness, L2-normalization."""

from catalyst_trader.kb import EMBED_DIM, hash_embed


def test_dimension():
    assert len(hash_embed("x")) == EMBED_DIM == 384


def test_deterministic():
    assert hash_embed("x") == hash_embed("x")


def test_distinct_text_differs():
    assert hash_embed("x") != hash_embed("y")


def test_l2_normalized():
    v = hash_embed("x")
    assert abs(sum(c * c for c in v) - 1.0) < 1e-6


def test_embed_fixture(embed):
    assert embed("x") == hash_embed("x")
