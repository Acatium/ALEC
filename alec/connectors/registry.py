"""Connector registry — maps source type strings to factory callables."""

from __future__ import annotations

from typing import Any, Callable

from alec.connectors.local_files import LocalFilesConnector
from alec.connectors.protocol import SourceConnector
from alec.errors import ConfigError


class ConnectorRegistry:
    """Maps source type names to connector factory callables."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[dict[str, Any]], SourceConnector]] = {}

    def register(
        self, source_type: str, factory: Callable[[dict[str, Any]], SourceConnector]
    ) -> None:
        """Register a factory for a source type."""
        self._factories[source_type] = factory

    def create(self, source_type: str, config: dict[str, Any]) -> SourceConnector:
        """Create a connector for the given source type and config."""
        factory = self._factories.get(source_type)
        if factory is None:
            raise ConfigError(
                f"Unknown source type: {source_type!r}. Available: {sorted(self._factories.keys())}"
            )
        return factory(config)

    @property
    def registered_types(self) -> list[str]:
        return sorted(self._factories.keys())


def default_registry() -> ConnectorRegistry:
    """Create a registry with all built-in connector types."""
    registry = ConnectorRegistry()

    registry.register(
        "local_files",
        lambda config: LocalFilesConnector(config["base_path"]),
    )

    # Web connector — lazy import to avoid hard dependency on aiohttp at module level
    def _create_web(config: dict[str, Any]) -> SourceConnector:
        from alec.connectors.web import WebConnector

        return WebConnector(seed_urls=[config["seed_url"]])

    registry.register("web", _create_web)

    return registry
