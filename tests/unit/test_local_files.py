"""Tests for LocalFilesConnector."""

from __future__ import annotations

import os
import tempfile

import pytest

from alec.connectors.local_files import LocalFilesConnector
from alec.errors import ToolError


@pytest.fixture
def test_dir():
    with tempfile.TemporaryDirectory() as d:
        # Create test structure
        os.makedirs(os.path.join(d, "subdir"))
        with open(os.path.join(d, "readme.md"), "w") as f:
            f.write("# Test\nThis is a test file.\nKeyword: discovery")
        with open(os.path.join(d, "data.txt"), "w") as f:
            f.write("Some data\nMore data\n")
        with open(os.path.join(d, "subdir", "nested.txt"), "w") as f:
            f.write("Nested content with keyword: discovery")
        # Hidden file
        with open(os.path.join(d, ".hidden"), "w") as f:
            f.write("hidden")
        yield d


@pytest.mark.asyncio
async def test_survey(test_dir):
    c = LocalFilesConnector(test_dir)
    entries = await c.survey()
    names = {e["name"] for e in entries}
    assert "readme.md" in names
    assert "data.txt" in names
    assert "subdir" in names
    # Hidden files excluded
    assert ".hidden" not in names


@pytest.mark.asyncio
async def test_list_children(test_dir):
    c = LocalFilesConnector(test_dir)
    children = await c.list_children("subdir")
    assert len(children) == 1
    assert children[0]["name"] == "nested.txt"


@pytest.mark.asyncio
async def test_read(test_dir):
    c = LocalFilesConnector(test_dir)
    content = await c.read("readme.md")
    assert "# Test" in content
    assert "discovery" in content


@pytest.mark.asyncio
async def test_read_nonexistent(test_dir):
    c = LocalFilesConnector(test_dir)
    with pytest.raises(ToolError, match="Not a file"):
        await c.read("nonexistent.txt")


@pytest.mark.asyncio
async def test_search(test_dir):
    c = LocalFilesConnector(test_dir)
    results = await c.search("discovery")
    assert len(results) == 2
    refs = {r["ref"] for r in results}
    assert "readme.md" in refs
    assert os.path.join("subdir", "nested.txt") in refs


@pytest.mark.asyncio
async def test_path_traversal(test_dir):
    c = LocalFilesConnector(test_dir)
    with pytest.raises(ToolError, match="Path traversal"):
        await c.read("../../../etc/passwd")


@pytest.mark.asyncio
async def test_source_type_and_ref(test_dir):
    c = LocalFilesConnector(test_dir)
    assert c.source_type() == "local_files"
    assert test_dir in c.source_ref()


def test_invalid_base_path():
    with pytest.raises(ToolError, match="not a directory"):
        LocalFilesConnector("/nonexistent/path")
