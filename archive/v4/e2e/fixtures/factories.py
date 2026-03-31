"""
Test Data Factories for E2E Tests.

These factories create valid test data for bullets, clusters, and sessions.
"""

from typing import Any, Optional

import numpy as np

# Embedding dimension used by ALEC
EMBEDDING_DIM = 384


def make_embedding(seed: Optional[int] = None) -> list[float]:
    """
    Generate a normalized random embedding vector.

    Args:
        seed: Optional random seed for reproducibility

    Returns:
        Normalized embedding as list of floats
    """
    if seed is not None:
        rng = np.random.default_rng(seed)
    else:
        rng = np.random.default_rng()

    vec = rng.standard_normal(EMBEDDING_DIM)
    normalized = vec / np.linalg.norm(vec)
    return normalized.tolist()


def make_embedding_str(seed: Optional[int] = None) -> str:
    """
    Generate embedding as PostgreSQL vector string format.

    Args:
        seed: Optional random seed for reproducibility

    Returns:
        Embedding formatted for PostgreSQL: "[0.1, 0.2, ...]"
    """
    embedding = make_embedding(seed)
    return "[" + ",".join(str(x) for x in embedding) + "]"


def make_bullet(
    domain: str,
    situation: Optional[str] = None,
    assertion: Optional[str] = None,
    **overrides: Any
) -> dict:
    """
    Create bullet test data.

    Args:
        domain: Domain for the bullet (used for cleanup)
        situation: Optional situation text
        assertion: Optional assertion text
        **overrides: Additional fields to override

    Returns:
        Dict with all bullet fields
    """
    sit = situation or f"When handling {domain} operations"
    asrt = assertion or "Always validate input before processing"
    default = {
        "situation": sit,
        "assertion": asrt,
        "content": asrt,  # content = assertion (required NOT NULL column)
        "modality": "should",
        "polarity": "do",
        "domain": domain,
        "source": "e2e-test",
        "status": "active",
        "category": "constraints",
        "situation_embedding": make_embedding(),
        "assertion_embedding": make_embedding(),
        "helpful_count": 0,
        "harmful_count": 0,
        "neutral_count": 0,
        "evidence_count": 1,
    }
    default.update(overrides)
    return default


def make_cluster(
    label: str,
    domain: str = "test",
    **overrides: Any
) -> dict:
    """
    Create cluster test data.

    Args:
        label: Cluster label (used for cleanup)
        domain: Domain for the cluster
        **overrides: Additional fields to override

    Returns:
        Dict with all cluster fields
    """
    default = {
        "label": label,
        "domain": domain,
        "centroid": make_embedding(),
        "success_count": 0,
        "failure_count": 0,
        "turn_count": 0,
        "status": "active",
    }
    default.update(overrides)
    return default


def make_session_request(domain: str, **overrides: Any) -> dict:
    """
    Create a session creation request.

    Args:
        domain: Domain for the session
        **overrides: Additional fields

    Returns:
        Dict for POST /api/v1/chat/sessions
    """
    default = {
        "domain": domain,
        "metadata": {"e2e_test": True},
    }
    default.update(overrides)
    return default


def make_message_request(content: str, **overrides: Any) -> dict:
    """
    Create a message request.

    Args:
        content: Message content
        **overrides: Additional fields

    Returns:
        Dict for POST /api/v1/chat/sessions/{id}/messages
    """
    default = {
        "content": content,
    }
    default.update(overrides)
    return default


def make_complete_request(success: bool, reason: str = "", **overrides: Any) -> dict:
    """
    Create a session completion request.

    Args:
        success: Whether session succeeded
        reason: Completion reason
        **overrides: Additional fields

    Returns:
        Dict for POST /api/v1/chat/sessions/{id}/complete
    """
    default = {
        "success": success,
        "reason": reason,
    }
    default.update(overrides)
    return default
