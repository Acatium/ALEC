"""Integration tests for WebConnector using a local test server."""

from __future__ import annotations

import pytest
from aiohttp import web

from alec.connectors.web import WebConnector

PAGES = {
    "/": "<html><body><h1>Home</h1><p>Welcome to the test site.</p>"
    '<a href="/about">About</a> <a href="/data">Data</a></body></html>',
    "/about": "<html><body><h1>About</h1><p>This is about ALEC testing.</p>"
    '<a href="/">Home</a></body></html>',
    "/data": "<html><body><h1>Data Page</h1>"
    "<ul><li>Revenue: $100B</li><li>Employees: 50000</li></ul>"
    '<a href="/">Home</a></body></html>',
}


async def handler(request: web.Request) -> web.Response:
    path = request.path
    if path in PAGES:
        return web.Response(text=PAGES[path], content_type="text/html")
    return web.Response(status=404, text="Not Found")


@pytest.fixture
async def test_server():
    """Start a local aiohttp web server for testing."""
    app = web.Application()
    app.router.add_get("/{path:.*}", handler)
    app.router.add_get("/", handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    # Get the actual port
    sockets = site._server.sockets  # type: ignore[union-attr]
    port = sockets[0].getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"

    yield base_url

    await runner.cleanup()


@pytest.mark.asyncio
async def test_fetch_and_parse(test_server: str):
    connector = WebConnector(seed_urls=[test_server], request_delay=0)
    try:
        text = await connector.read(f"{test_server}/")
        assert "Home" in text
        assert "Welcome to the test site" in text
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_list_children(test_server: str):
    connector = WebConnector(seed_urls=[test_server], request_delay=0)
    try:
        children = await connector.list_children(f"{test_server}/")
        refs = [c["ref"] for c in children]
        assert any("/about" in r for r in refs)
        assert any("/data" in r for r in refs)
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_search_across_pages(test_server: str):
    connector = WebConnector(seed_urls=[test_server], request_delay=0)
    try:
        # Fetch multiple pages
        await connector.read(f"{test_server}/")
        await connector.read(f"{test_server}/about")
        await connector.read(f"{test_server}/data")

        # Search for content
        results = await connector.search("ALEC")
        assert len(results) == 1
        assert "/about" in results[0]["ref"]

        results = await connector.search("Revenue")
        assert len(results) == 1
        assert "/data" in results[0]["ref"]
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_survey_returns_seed(test_server: str):
    connector = WebConnector(seed_urls=[test_server], request_delay=0)
    try:
        entries = await connector.survey()
        assert len(entries) == 1
        assert entries[0]["ref"] == test_server
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_404_raises_tool_error(test_server: str):
    from alec.errors import ToolError

    connector = WebConnector(seed_urls=[test_server], request_delay=0)
    try:
        with pytest.raises(ToolError, match="HTTP 404"):
            await connector.read(f"{test_server}/nonexistent")
    finally:
        await connector.close()
