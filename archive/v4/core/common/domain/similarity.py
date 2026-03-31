"""Semantic similarity utilities for context-aware learning.

Provides cosine similarity computation and similarity gating for
determining when bullets should be assessed in their current context.

Phase 0.6: Context-Aware Learning
"""

from dataclasses import dataclass
from typing import List, Tuple, Union

import numpy as np


@dataclass
class SimilarityResult:
    """Result of a similarity check."""
    similarity_score: float
    is_relevant: bool
    threshold: float


def cosine_similarity(
    vec1: Union[List[float], np.ndarray],
    vec2: Union[List[float], np.ndarray]
) -> float:
    """Compute cosine similarity between two vectors.

    Cosine similarity measures the angle between vectors, returning
    1.0 for identical directions, 0.0 for orthogonal, -1.0 for opposite.

    Args:
        vec1: First embedding vector
        vec2: Second embedding vector

    Returns:
        Cosine similarity score between -1.0 and 1.0

    Raises:
        ValueError: If vectors have different dimensions or are empty
    """
    v1 = np.asarray(vec1, dtype=np.float64)
    v2 = np.asarray(vec2, dtype=np.float64)

    if v1.shape != v2.shape:
        raise ValueError(
            f"Vector dimensions must match: {v1.shape} vs {v2.shape}"
        )

    if v1.size == 0:
        raise ValueError("Vectors cannot be empty")

    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return float(np.dot(v1, v2) / (norm1 * norm2))


def should_assess_bullet(
    query_embedding: Union[List[float], np.ndarray],
    bullet_embedding: Union[List[float], np.ndarray],
    threshold: float = 0.5
) -> Tuple[bool, float]:
    """Determine if a bullet should be assessed for effectiveness.

    Similarity gating prevents context pollution: bullets that were
    not semantically relevant to the current problem should not have
    their effectiveness scores updated (either positive or negative).

    Args:
        query_embedding: Embedding of the current query/problem
        bullet_embedding: Embedding of the bullet being assessed
        threshold: Minimum similarity for relevance (default 0.5)

    Returns:
        Tuple of (is_relevant, similarity_score)
        - is_relevant: True if bullet should be assessed
        - similarity_score: The computed similarity (0.0-1.0)
    """
    similarity = cosine_similarity(query_embedding, bullet_embedding)

    # Clamp to [0, 1] for positive similarity space
    # Negative similarities indicate opposite meanings, treat as 0
    similarity = max(0.0, similarity)

    return (similarity >= threshold, similarity)


def batch_similarity(
    query_embedding: Union[List[float], np.ndarray],
    bullet_embeddings: List[Union[List[float], np.ndarray]],
    threshold: float = 0.5
) -> List[SimilarityResult]:
    """Compute similarity for multiple bullets efficiently.

    Args:
        query_embedding: Embedding of the current query/problem
        bullet_embeddings: List of bullet embeddings
        threshold: Minimum similarity for relevance

    Returns:
        List of SimilarityResult for each bullet
    """
    query = np.asarray(query_embedding, dtype=np.float64)
    query_norm = np.linalg.norm(query)

    if query_norm == 0:
        return [
            SimilarityResult(0.0, False, threshold)
            for _ in bullet_embeddings
        ]

    results = []
    for bullet_emb in bullet_embeddings:
        bullet = np.asarray(bullet_emb, dtype=np.float64)
        bullet_norm = np.linalg.norm(bullet)

        if bullet_norm == 0:
            similarity = 0.0
        else:
            similarity = float(np.dot(query, bullet) / (query_norm * bullet_norm))
            similarity = max(0.0, similarity)

        results.append(SimilarityResult(
            similarity_score=similarity,
            is_relevant=similarity >= threshold,
            threshold=threshold
        ))

    return results


def filter_relevant_bullets(
    query_embedding: Union[List[float], np.ndarray],
    bullets: List[dict],
    embedding_key: str = "embedding",
    threshold: float = 0.5
) -> List[Tuple[dict, float]]:
    """Filter bullets to only those semantically relevant to query.

    Convenience function that filters a list of bullet dictionaries
    and returns those above the similarity threshold with their scores.

    Args:
        query_embedding: Embedding of the current query/problem
        bullets: List of bullet dictionaries with embeddings
        embedding_key: Key in bullet dict containing the embedding
        threshold: Minimum similarity for relevance

    Returns:
        List of (bullet, similarity_score) tuples for relevant bullets,
        sorted by similarity descending
    """
    relevant = []

    for bullet in bullets:
        bullet_embedding = bullet.get(embedding_key)
        if bullet_embedding is None:
            continue

        is_relevant, score = should_assess_bullet(
            query_embedding, bullet_embedding, threshold
        )

        if is_relevant:
            relevant.append((bullet, score))

    # Sort by similarity descending
    relevant.sort(key=lambda x: x[1], reverse=True)
    return relevant


def compute_context_relevance_stats(
    results: List[SimilarityResult]
) -> dict:
    """Compute summary statistics for context relevance.

    Useful for monitoring and debugging similarity gating behavior.

    Args:
        results: List of SimilarityResult from batch_similarity

    Returns:
        Dictionary with relevance statistics
    """
    if not results:
        return {
            "total_bullets": 0,
            "relevant_bullets": 0,
            "irrelevant_bullets": 0,
            "relevance_rate": 0.0,
            "mean_similarity": 0.0,
            "max_similarity": 0.0,
            "min_similarity": 0.0,
        }

    scores = [r.similarity_score for r in results]
    relevant_count = sum(1 for r in results if r.is_relevant)

    return {
        "total_bullets": len(results),
        "relevant_bullets": relevant_count,
        "irrelevant_bullets": len(results) - relevant_count,
        "relevance_rate": relevant_count / len(results),
        "mean_similarity": float(np.mean(scores)),
        "max_similarity": float(np.max(scores)),
        "min_similarity": float(np.min(scores)),
    }
