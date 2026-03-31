"""Tests for SentenceTransformerEmbeddingService."""

from __future__ import annotations

import math

import pytest

st = pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed")

from alec.db.embeddings_st import SentenceTransformerEmbeddingService  # noqa: E402


@pytest.mark.asyncio
async def test_dimensions():
    svc = SentenceTransformerEmbeddingService("all-MiniLM-L6-v2")
    assert svc.dimensions == 384


@pytest.mark.asyncio
async def test_embed_output_length():
    svc = SentenceTransformerEmbeddingService("all-MiniLM-L6-v2")
    v = await svc.embed("hello world")
    assert len(v) == 384


@pytest.mark.asyncio
async def test_embed_unit_vector():
    svc = SentenceTransformerEmbeddingService("all-MiniLM-L6-v2")
    v = await svc.embed("test embedding normalization")
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 1e-4


@pytest.mark.asyncio
async def test_embed_batch():
    svc = SentenceTransformerEmbeddingService("all-MiniLM-L6-v2")
    texts = ["alpha", "beta", "gamma"]
    results = await svc.embed_batch(texts)
    assert len(results) == 3
    assert all(len(v) == 384 for v in results)


@pytest.mark.asyncio
async def test_determinism():
    svc = SentenceTransformerEmbeddingService("all-MiniLM-L6-v2")
    v1 = await svc.embed("consistency check")
    v2 = await svc.embed("consistency check")
    assert v1 == v2
