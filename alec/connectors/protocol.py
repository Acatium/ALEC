"""Source connector protocol — interface for all source types."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SourceConnector(Protocol):
    """Protocol for source connectors. Implementations provide read-only
    access to a specific source type (filesystem, Confluence, GitHub, etc.)."""

    async def survey(self) -> list[dict[str, Any]]:
        """List top-level entry points. Returns list of resource refs."""
        ...

    async def list_children(self, ref: str) -> list[dict[str, Any]]:
        """List sub-resources of a specific resource."""
        ...

    async def read(self, ref: str) -> str:
        """Read the full content of a resource. Returns text."""
        ...

    async def search(self, query: str) -> list[dict[str, Any]]:
        """Search within this source. Returns matching refs with snippets."""
        ...

    def source_type(self) -> str:
        """Return the source type identifier (e.g., 'local_files')."""
        ...

    def source_ref(self) -> str:
        """Return the source reference (e.g., base path)."""
        ...
