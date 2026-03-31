"""ALEC configuration via environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All ALEC configuration. Loaded from environment variables with ALEC_ prefix."""

    model_config = {"env_prefix": "ALEC_"}

    # Required
    anthropic_api_key: str = ""
    database_url: str = "postgresql://alec:alec-dev-password@localhost:5432/alec"

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "console"

    # LLM
    default_model: str = "claude-haiku-4-5-20251001"
    max_workers: int = 5
    worker_max_tokens: int = 250_000
    worker_max_turns: int = 30
    coordinator_max_tokens: int = 4096

    # Convergence
    convergence_threshold: float = 3.0
    consecutive_cycles_required: int = 3
    convergence_novelty_decay: bool = True
    convergence_max_reinforcement_per_entity: int = 3
    convergence_expansion_deceleration_cycles: int = 4

    # Entity resolution
    entity_similarity_threshold: float = 0.80

    # Post-cycle deduplication
    dedup_enabled: bool = True
    dedup_auto_merge_threshold: float = 0.92

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dimensions: int = 384
    use_real_embeddings: bool = True

    # Database pool
    db_min_pool_size: int = 2
    db_max_pool_size: int = 10

    # API server
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_cors_origins: list[str] = ["http://localhost:5173"]


def load_settings() -> Settings:
    """Load settings from environment."""
    return Settings()
