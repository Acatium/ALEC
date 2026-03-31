"""Embedding service protocol and mock implementation."""

from __future__ import annotations

import hashlib
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class EmbeddingService(Protocol):
    """Protocol for embedding text into vectors."""

    @property
    def dimensions(self) -> int:
        """Return the dimensionality of the embedding vectors."""
        ...

    async def embed(self, text: str) -> list[float]:
        """Embed text into a vector."""
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts. Default: sequential calls to embed()."""
        ...


class MockEmbeddingService:
    """Deterministic hash-based embeddings for testing and initial development.

    Produces consistent unit vectors from text input.
    Same text always produces the same vector. Similar text does NOT
    produce similar vectors (no semantic meaning).
    """

    def __init__(self, dimensions: int = 384) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, text: str) -> list[float]:
        """Generate a deterministic vector from text."""
        return self._hash_to_vector(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate vectors for multiple texts."""
        return [self._hash_to_vector(t) for t in texts]

    def _hash_to_vector(self, text: str) -> list[float]:
        """Hash text to a deterministic unit vector."""
        # Use SHA-512 repeatedly to fill dimensions
        # Each SHA-512 gives 64 bytes = 64 values (1 byte each, mapped to [-1, 1])
        num_hashes = (self._dimensions + 63) // 64
        values: list[float] = []
        for i in range(num_hashes):
            h = hashlib.sha512(f"{text}:{i}".encode()).digest()
            for b in h:
                values.append((b / 127.5) - 1.0)

        # Normalize to unit vector
        arr = np.array(values[: self._dimensions], dtype=np.float64)
        norm = np.linalg.norm(arr)
        if norm > 0:
            arr = arr / norm
        result: list[float] = arr.tolist()
        return result
