"""Tests for configuration loading."""

from __future__ import annotations

from alec.config.settings import Settings, load_settings


def test_default_settings():
    s = Settings()
    assert s.database_url == "postgresql://alec:alec-dev-password@localhost:5432/alec"
    assert s.log_level == "INFO"
    assert s.log_format == "json"
    assert s.max_workers == 5
    assert s.worker_max_tokens == 250_000
    assert s.convergence_threshold == 3.0
    assert s.consecutive_cycles_required == 3


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("ALEC_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("ALEC_MAX_WORKERS", "10")
    monkeypatch.setenv("ALEC_WORKER_MAX_TOKENS", "200000")
    s = Settings()
    assert s.log_level == "DEBUG"
    assert s.max_workers == 10
    assert s.worker_max_tokens == 200_000


def test_load_settings():
    s = load_settings()
    assert isinstance(s, Settings)
