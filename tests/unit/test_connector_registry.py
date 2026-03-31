"""Tests for ConnectorRegistry."""

from __future__ import annotations

import pytest

from alec.connectors.registry import ConnectorRegistry, default_registry
from alec.errors import ConfigError


def test_register_and_create(tmp_path):
    registry = ConnectorRegistry()

    class FakeConnector:
        def __init__(self, path: str) -> None:
            self.path = path

    registry.register("fake", lambda config: FakeConnector(config["path"]))
    connector = registry.create("fake", {"path": "/tmp"})
    assert isinstance(connector, FakeConnector)
    assert connector.path == "/tmp"


def test_unknown_type_raises():
    registry = ConnectorRegistry()
    with pytest.raises(ConfigError, match="Unknown source type"):
        registry.create("nonexistent", {})


def test_default_registry_has_local_files():
    registry = default_registry()
    assert "local_files" in registry.registered_types


def test_default_registry_has_web():
    registry = default_registry()
    assert "web" in registry.registered_types


def test_default_registry_creates_local_files(tmp_path):
    registry = default_registry()
    connector = registry.create("local_files", {"base_path": str(tmp_path)})
    assert connector.source_type() == "local_files"


def test_registered_types():
    registry = ConnectorRegistry()
    registry.register("alpha", lambda c: None)  # type: ignore[arg-type]
    registry.register("beta", lambda c: None)  # type: ignore[arg-type]
    assert registry.registered_types == ["alpha", "beta"]
