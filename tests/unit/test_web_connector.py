"""Unit tests for WebConnector using mocked HTTP."""

from __future__ import annotations

import pytest

aioresponses_mod = pytest.importorskip("aioresponses", reason="aioresponses not installed")

from aioresponses import aioresponses  # noqa: E402

from alec.connectors.web import WebConnector, parse_html  # noqa: E402
from alec.errors import ToolError  # noqa: E402

SAMPLE_HTML = """
<html>
<head><title>Test Page</title></head>
<body>
<nav>Navigation</nav>
<h1>Main Title</h1>
<p>First paragraph with <b>bold</b> text.</p>
<h2>Section Two</h2>
<p>Second paragraph.</p>
<ul>
<li>Item one</li>
<li>Item two</li>
</ul>
<script>var x = 1;</script>
<style>.hidden { display: none; }</style>
<footer>Footer content</footer>
<a href="/page2">Link 1</a>
<a href="https://example.com/page3">Link 2</a>
<a href="https://other.com/external">External</a>
<a href="javascript:void(0)">JS Link</a>
<a href="mailto:test@example.com">Email</a>
</body>
</html>
"""


def test_parse_html_extracts_text():
    text, _ = parse_html(SAMPLE_HTML, "https://example.com")
    assert "Main Title" in text
    assert "First paragraph" in text
    assert "bold" in text
    assert "Section Two" in text
    assert "Item one" in text


def test_parse_html_strips_scripts_and_styles():
    text, _ = parse_html(SAMPLE_HTML, "https://example.com")
    assert "var x = 1" not in text
    assert ".hidden" not in text


def test_parse_html_strips_nav_and_footer():
    text, _ = parse_html(SAMPLE_HTML, "https://example.com")
    assert "Navigation" not in text
    assert "Footer content" not in text


def test_parse_html_formats_headings():
    text, _ = parse_html(SAMPLE_HTML, "https://example.com")
    assert "# Main Title" in text
    assert "## Section Two" in text


def test_parse_html_formats_list_items():
    text, _ = parse_html(SAMPLE_HTML, "https://example.com")
    assert "- Item one" in text
    assert "- Item two" in text


def test_parse_html_extracts_links():
    _, links = parse_html(SAMPLE_HTML, "https://example.com")
    assert "https://example.com/page2" in links
    assert "https://example.com/page3" in links
    assert "https://other.com/external" in links


def test_parse_html_skips_javascript_and_mailto():
    _, links = parse_html(SAMPLE_HTML, "https://example.com")
    for link in links:
        assert not link.startswith("javascript:")
        assert not link.startswith("mailto:")


@pytest.mark.asyncio
async def test_survey_returns_seeds():
    connector = WebConnector(seed_urls=["https://example.com/a", "https://example.com/b"])
    entries = await connector.survey()
    assert len(entries) == 2
    assert entries[0]["ref"] == "https://example.com/a"
    assert entries[1]["ref"] == "https://example.com/b"
    await connector.close()


@pytest.mark.asyncio
async def test_read_fetches_and_caches():
    connector = WebConnector(seed_urls=["https://example.com"], request_delay=0)
    try:
        with aioresponses() as m:
            m.get("https://example.com/page", body=SAMPLE_HTML)
            text = await connector.read("https://example.com/page")
            assert "Main Title" in text

            # Second read should use cache (no mock needed)
            text2 = await connector.read("https://example.com/page")
            assert text2 == text
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_list_children_same_domain():
    connector = WebConnector(seed_urls=["https://example.com"], request_delay=0)
    try:
        with aioresponses() as m:
            m.get("https://example.com/page", body=SAMPLE_HTML)
            children = await connector.list_children("https://example.com/page")
            refs = [c["ref"] for c in children]
            # Same-domain links should be included
            assert "https://example.com/page2" in refs or any("/page2" in r for r in refs)
            # External domain should be excluded
            assert not any("other.com" in r for r in refs)
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_search_across_cache():
    connector = WebConnector(seed_urls=["https://example.com"], request_delay=0)
    try:
        with aioresponses() as m:
            m.get("https://example.com/page1", body="<p>Alpha content here</p>")
            m.get("https://example.com/page2", body="<p>Beta content here</p>")
            await connector.read("https://example.com/page1")
            await connector.read("https://example.com/page2")

            results = await connector.search("Alpha")
            assert len(results) == 1
            assert results[0]["ref"] == "https://example.com/page1"

            results = await connector.search("content")
            assert len(results) == 2
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_http_error_raises_tool_error():
    connector = WebConnector(seed_urls=["https://example.com"], request_delay=0)
    try:
        with aioresponses() as m:
            m.get("https://example.com/missing", status=404)
            with pytest.raises(ToolError, match="HTTP 404"):
                await connector.read("https://example.com/missing")
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_source_type_and_ref():
    connector = WebConnector(seed_urls=["https://example.com/start"])
    assert connector.source_type() == "web"
    assert connector.source_ref() == "https://example.com/start"
    await connector.close()
