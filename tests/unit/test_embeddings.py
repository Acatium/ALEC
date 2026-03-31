"""Tests for mock embedding service."""

from __future__ import annotations

import math

import pytest

from alec.db.embeddings import MockEmbeddingService


@pytest.mark.asyncio
async def test_deterministic():
    svc = MockEmbeddingService()
    v1 = await svc.embed("hello world")
    v2 = await svc.embed("hello world")
    assert v1 == v2


@pytest.mark.asyncio
async def test_dimension():
    svc = MockEmbeddingService()
    v = await svc.embed("test text")
    assert len(v) == 384


@pytest.mark.asyncio
async def test_unit_vector():
    svc = MockEmbeddingService()
    v = await svc.embed("unit test")
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 1e-6


@pytest.mark.asyncio
async def test_different_texts_different_vectors():
    svc = MockEmbeddingService()
    v1 = await svc.embed("hello")
    v2 = await svc.embed("world")
    assert v1 != v2


@pytest.mark.asyncio
async def test_embed_batch():
    svc = MockEmbeddingService()
    texts = ["alpha", "beta", "gamma"]
    results = await svc.embed_batch(texts)
    assert len(results) == 3
    assert all(len(v) == 384 for v in results)
    # Individual results should match batch results
    for text, batch_result in zip(texts, results):
        individual = await svc.embed(text)
        assert batch_result == individual


@pytest.mark.asyncio
async def test_configurable_dimensions():
    svc_256 = MockEmbeddingService(dimensions=256)
    assert svc_256.dimensions == 256
    v = await svc_256.embed("test")
    assert len(v) == 256

    svc_512 = MockEmbeddingService(dimensions=512)
    assert svc_512.dimensions == 512
    v = await svc_512.embed("test")
    assert len(v) == 512


@pytest.mark.asyncio
async def test_default_dimensions():
    svc = MockEmbeddingService()
    assert svc.dimensions == 384
