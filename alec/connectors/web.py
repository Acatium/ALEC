"""Web source connector — fetches and parses web pages."""

from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup, Tag

from alec.errors import ToolError


class WebConnector:
    """Source connector for web pages.

    Fetches HTML, extracts readable text, caches results in memory,
    and rate-limits requests per domain.
    """

    def __init__(
        self,
        seed_urls: list[str],
        request_delay: float = 1.0,
        timeout: float = 30,
        cache_ttl: int = 3600,
    ) -> None:
        self._seed_urls = seed_urls
        self._request_delay = request_delay
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._cache_ttl = cache_ttl
        self._session: aiohttp.ClientSession | None = None
        self._cache: dict[str, str] = {}
        self._links_cache: dict[str, list[str]] = {}
        self._domain_locks: dict[str, asyncio.Lock] = {}
        self._domain_last_request: dict[str, float] = {}

    def source_type(self) -> str:
        return "web"

    def source_ref(self) -> str:
        return self._seed_urls[0] if self._seed_urls else ""

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                headers={"User-Agent": "ALEC/5.0 (Knowledge Discovery Bot)"},
            )
        return self._session

    async def _rate_limit(self, url: str) -> None:
        """Enforce per-domain rate limiting."""
        domain = urlparse(url).netloc
        if domain not in self._domain_locks:
            self._domain_locks[domain] = asyncio.Lock()

        async with self._domain_locks[domain]:
            now = asyncio.get_event_loop().time()
            last = self._domain_last_request.get(domain, 0.0)
            wait = self._request_delay - (now - last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._domain_last_request[domain] = asyncio.get_event_loop().time()

    async def _fetch(self, url: str) -> str:
        """Fetch a URL and return raw HTML."""
        await self._rate_limit(url)
        session = await self._get_session()
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    raise ToolError(f"HTTP {response.status} fetching {url}: {response.reason}")
                return await response.text(errors="replace")
        except aiohttp.ClientError as e:
            raise ToolError(f"Network error fetching {url}: {e}") from e

    async def survey(self) -> list[dict[str, Any]]:
        """Return seed URLs as entry points."""
        return [
            {"ref": url, "type": "page", "name": urlparse(url).path.split("/")[-1] or url}
            for url in self._seed_urls
        ]

    async def read(self, ref: str) -> str:
        """Fetch a page, parse HTML to readable text, and cache the result."""
        if ref in self._cache:
            return self._cache[ref]

        html = await self._fetch(ref)
        text, links = parse_html(html, ref)
        self._cache[ref] = text
        self._links_cache[ref] = links
        return text

    async def list_children(self, ref: str) -> list[dict[str, Any]]:
        """Extract same-domain links from a cached page."""
        # Ensure the page is fetched and parsed
        if ref not in self._links_cache:
            await self.read(ref)

        links = self._links_cache.get(ref, [])
        base_domain = urlparse(ref).netloc

        children = []
        seen: set[str] = set()
        for link in links:
            parsed = urlparse(link)
            if parsed.netloc and parsed.netloc != base_domain:
                continue
            normalized = link.split("#")[0].rstrip("/")
            if normalized in seen or normalized == ref.rstrip("/"):
                continue
            seen.add(normalized)
            children.append(
                {
                    "ref": link,
                    "type": "page",
                    "name": parsed.path.split("/")[-1] or link,
                }
            )

        return children

    async def search(self, query: str) -> list[dict[str, Any]]:
        """Search across all cached pages for the query text."""
        query_lower = query.lower()
        results = []

        for url, text in self._cache.items():
            if query_lower in text.lower():
                # Find first matching line for snippet
                for i, line in enumerate(text.splitlines(), 1):
                    if query_lower in line.lower():
                        results.append(
                            {
                                "ref": url,
                                "line": i,
                                "snippet": line.strip()[:200],
                            }
                        )
                        break

            if len(results) >= 20:
                break

        return results

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None


def parse_html(html: str, base_url: str) -> tuple[str, list[str]]:
    """Parse HTML into readable text and extract links.

    Returns (text, links) where text is markdown-ish readable content
    and links are absolute URLs found in <a href> tags.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    # Extract links before converting to text
    links: list[str] = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if isinstance(href, list):
            href = href[0]
        if href.startswith(("javascript:", "mailto:", "#")):
            continue
        absolute = urljoin(base_url, href)
        links.append(absolute)

    # Convert to readable text
    lines: list[str] = []

    for element in soup.find_all(
        ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th", "blockquote", "pre"]
    ):
        text = element.get_text(separator=" ", strip=True)
        if not text:
            continue

        if isinstance(element, Tag):
            tag_name = element.name
            if tag_name in ("h1",):
                lines.append(f"\n# {text}\n")
            elif tag_name in ("h2",):
                lines.append(f"\n## {text}\n")
            elif tag_name in ("h3",):
                lines.append(f"\n### {text}\n")
            elif tag_name in ("h4", "h5", "h6"):
                lines.append(f"\n#### {text}\n")
            elif tag_name == "li":
                lines.append(f"- {text}")
            elif tag_name == "blockquote":
                lines.append(f"> {text}")
            elif tag_name == "pre":
                lines.append(f"```\n{text}\n```")
            else:
                lines.append(text)

    result = "\n".join(lines)
    # Collapse excessive blank lines
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip(), links
