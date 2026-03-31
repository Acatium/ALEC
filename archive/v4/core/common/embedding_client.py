"""Gateway-based embedding client for all services.

Calls LLM Gateway's /embed endpoint instead of loading model locally.
This centralizes embedding in the gateway and keeps other services lightweight.
"""

import os
from typing import Optional

import httpx

from core.common.observability import setup_logging

logger = setup_logging("embedding-client")

# Gateway URL - can be overridden per-service
LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://llm-gateway:8000")
EMBEDDING_DIMENSION = 384


class EmbeddingClient:
    """HTTP client for LLM Gateway embedding endpoint.

    Singleton pattern for connection pooling.
    """

    _instance: Optional["EmbeddingClient"] = None
    _client: Optional[httpx.AsyncClient] = None
    _sync_client: Optional[httpx.Client] = None

    def __new__(cls) -> "EmbeddingClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls) -> "EmbeddingClient":
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def preload(cls) -> None:
        """Pre-initialize the client (no-op, kept for API compatibility)."""
        cls.get_instance()
        logger.info("Embedding client initialized (gateway mode)")

    async def start(self) -> None:
        """Start the async client."""
        if EmbeddingClient._client is None:
            EmbeddingClient._client = httpx.AsyncClient(
                base_url=LLM_GATEWAY_URL,
                timeout=30.0,
            )

    async def stop(self) -> None:
        """Stop the async client."""
        if EmbeddingClient._client is not None:
            await EmbeddingClient._client.aclose()
            EmbeddingClient._client = None

    def _ensure_sync_client(self) -> httpx.Client:
        """Ensure sync client is initialized."""
        if EmbeddingClient._sync_client is None:
            EmbeddingClient._sync_client = httpx.Client(
                base_url=LLM_GATEWAY_URL,
                timeout=30.0,
            )
        return EmbeddingClient._sync_client

    def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text (synchronous).

        Args:
            text: Input text to embed.

        Returns:
            List of 384 floats representing the embedding.
        """
        if not text or not text.strip():
            return [0.0] * EMBEDDING_DIMENSION

        client = self._ensure_sync_client()
        response = client.post(
            "/api/v1/embed",
            json={"text": text},
        )
        response.raise_for_status()
        return response.json()["embedding"]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts (synchronous).

        Args:
            texts: List of input texts to embed.

        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []

        client = self._ensure_sync_client()
        response = client.post(
            "/api/v1/embed/batch",
            json={"texts": texts},
        )
        response.raise_for_status()
        return response.json()["embeddings"]

    async def embed_async(self, text: str) -> list[float]:
        """Generate embedding for a single text (async).

        Args:
            text: Input text to embed.

        Returns:
            List of 384 floats representing the embedding.
        """
        if not text or not text.strip():
            return [0.0] * EMBEDDING_DIMENSION

        if EmbeddingClient._client is None:
            await self.start()

        response = await EmbeddingClient._client.post(
            "/api/v1/embed",
            json={"text": text},
        )
        response.raise_for_status()
        return response.json()["embedding"]

    async def embed_batch_async(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts (async).

        Args:
            texts: List of input texts to embed.

        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []

        if EmbeddingClient._client is None:
            await self.start()

        response = await EmbeddingClient._client.post(
            "/api/v1/embed/batch",
            json={"texts": texts},
        )
        response.raise_for_status()
        return response.json()["embeddings"]


# Convenience functions for backwards compatibility
def embed(text: str) -> list[float]:
    """Embed a single text (synchronous)."""
    return EmbeddingClient.get_instance().embed(text)


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts (synchronous)."""
    return EmbeddingClient.get_instance().embed_batch(texts)
