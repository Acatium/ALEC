"""Local filesystem source connector."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from alec.errors import ToolError


class LocalFilesConnector:
    """Source connector for local filesystem directories.

    All paths are validated against base_path to prevent directory traversal.
    """

    def __init__(self, base_path: str) -> None:
        self._base_path = Path(base_path).resolve()
        if not self._base_path.is_dir():
            raise ToolError(f"Base path is not a directory: {self._base_path}")

    def source_type(self) -> str:
        return "local_files"

    def source_ref(self) -> str:
        return str(self._base_path)

    async def survey(self) -> list[dict[str, Any]]:
        """List top-level files and directories."""
        entries = []
        for item in sorted(self._base_path.iterdir()):
            if item.name.startswith("."):
                continue
            entries.append(
                {
                    "ref": str(item.relative_to(self._base_path)),
                    "type": "directory" if item.is_dir() else "file",
                    "name": item.name,
                    "size": item.stat().st_size if item.is_file() else None,
                }
            )
        return entries

    async def list_children(self, ref: str) -> list[dict[str, Any]]:
        """List children of a directory."""
        path = self._resolve_path(ref)
        if not path.is_dir():
            return [{"error": f"Not a directory: {ref}"}]

        entries = []
        for item in sorted(path.iterdir()):
            if item.name.startswith("."):
                continue
            entries.append(
                {
                    "ref": str(item.relative_to(self._base_path)),
                    "type": "directory" if item.is_dir() else "file",
                    "name": item.name,
                    "size": item.stat().st_size if item.is_file() else None,
                }
            )
        return entries

    async def read(self, ref: str) -> str:
        """Read a file's content as text."""
        path = self._resolve_path(ref)
        if not path.is_file():
            raise ToolError(f"Not a file: {ref}")

        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            raise ToolError(f"Cannot read file {ref}: {e}") from e

    async def search(self, query: str) -> list[dict[str, Any]]:
        """Search for files containing query text."""
        query_lower = query.lower()
        results = []

        for root, _dirs, files in os.walk(self._base_path):
            root_path = Path(root)
            # Skip hidden directories
            if any(part.startswith(".") for part in root_path.relative_to(self._base_path).parts):
                continue

            for fname in sorted(files):
                if fname.startswith("."):
                    continue
                fpath = root_path / fname
                try:
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                except (OSError, UnicodeDecodeError):
                    continue

                if query_lower in content.lower():
                    # Find first matching line for snippet
                    for i, line in enumerate(content.splitlines(), 1):
                        if query_lower in line.lower():
                            snippet = line.strip()[:200]
                            results.append(
                                {
                                    "ref": str(fpath.relative_to(self._base_path)),
                                    "line": i,
                                    "snippet": snippet,
                                }
                            )
                            break

                if len(results) >= 20:
                    break
            if len(results) >= 20:
                break

        return results

    def _resolve_path(self, ref: str) -> Path:
        """Resolve a reference to an absolute path, validating against base_path."""
        resolved = (self._base_path / ref).resolve()
        if not str(resolved).startswith(str(self._base_path)):
            raise ToolError(f"Path traversal detected: {ref}")
        return resolved
