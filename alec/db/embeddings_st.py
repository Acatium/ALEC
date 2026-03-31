"""Sentence-transformers embedding service for real semantic embeddings."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any


class SentenceTransformerEmbeddingService:
    """Wraps sentence-transformers for async embedding generation.

    Lazy-loads the model on first use. Uses run_in_executor() to avoid
    blocking the event loop during synchronous model inference.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model: Any = None

    def _load_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    @property
    def dimensions(self) -> int:
        model = self._load_model()
        dim: int = model.get_sentence_embedding_dimension()
        return dim

    async def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, partial(self._embed_sync, text))
        return result

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in a single batch."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, partial(self._embed_batch_sync, texts))
        return result

    def _embed_sync(self, text: str) -> list[float]:
        model = self._load_model()
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.tolist()  # type: ignore[no-any-return]

    def _embed_batch_sync(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        embeddings = model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()  # type: ignore[no-any-return]
