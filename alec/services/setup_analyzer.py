"""Setup analyzer — assesses source coverage for a problem statement via LLM."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp
import structlog
from bs4 import BeautifulSoup

from alec.agents.llm_client import LLMClient
from alec.agents.prompts.setup_assistant import SETUP_ASSISTANT_SYSTEM_PROMPT

logger = structlog.get_logger()

_DUCKDUCKGO_URL = "https://html.duckduckgo.com/html/"
_MAX_SEARCH_QUERIES = 2
_MAX_RESULTS_PER_QUERY = 3
_HEAD_TIMEOUT = aiohttp.ClientTimeout(total=8)
_SEARCH_TIMEOUT = aiohttp.ClientTimeout(total=10)
_USER_AGENT = "ALEC/5.0 (Knowledge Discovery Bot)"

_EMPTY_ANALYSIS: dict[str, Any] = {
    "topics": [],
    "gaps": [],
    "search_queries": [],
    "suggested_sources": [],
    "overall_assessment": "Analysis could not be completed. Please review your sources manually.",
}


class SetupAnalyzer:
    """Stateless service that analyzes problem-statement-to-source coverage."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def analyze(
        self,
        problem_statement: str,
        sources: list[str],
    ) -> dict[str, Any]:
        """Run full analysis: LLM topic extraction, search, reachability."""
        user_message = self._build_user_message(problem_statement, sources)

        response = await self._llm.call(
            system=SETUP_ASSISTANT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=4096,
        )

        analysis = self._parse_analysis(response.text)

        # Find and validate additional sources for gaps
        analysis = await self._find_and_validate_sources(analysis)

        return analysis

    @staticmethod
    def _build_user_message(problem_statement: str, sources: list[str]) -> str:
        """Assemble the user message for the LLM call."""
        sections = [
            f"## Problem Statement\n{problem_statement}",
            "\n## Provided Sources",
        ]
        if sources:
            for s in sources:
                sections.append(f"- {s}")
        else:
            sections.append("(no sources provided)")
        return "\n".join(sections)

    @staticmethod
    def _parse_analysis(text: str) -> dict[str, Any]:
        """Parse LLM JSON output with bracket-finding fallback."""
        # Try direct parse first
        try:
            result: dict[str, Any] = json.loads(text)
            return result
        except json.JSONDecodeError:
            pass

        # Bracket-finding fallback (handles markdown fences, preamble text, etc.)
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                result = json.loads(text[start:end])
                return result
            except json.JSONDecodeError:
                pass

        logger.warning("setup_analyzer.parse_failed", text=text[:200])
        return dict(_EMPTY_ANALYSIS)

    async def _find_and_validate_sources(
        self,
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        """Search DuckDuckGo for gap topics, then HEAD-check all suggestions."""
        queries = analysis.get("search_queries", [])[:_MAX_SEARCH_QUERIES]

        # Search for additional sources
        found_sources: list[dict[str, Any]] = []
        for query in queries:
            results = await self._search_duckduckgo(query)
            for url, title in results[:_MAX_RESULTS_PER_QUERY]:
                found_sources.append({
                    "url": url,
                    "title": title,
                    "reason": f"Found via search: {query}",
                    "covers_topics": [],
                })

        # Merge with LLM-suggested sources
        existing = analysis.get("suggested_sources", [])
        all_sources = existing + found_sources

        # Deduplicate by URL
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for src in all_sources:
            url = src.get("url", "")
            if url and url not in seen:
                seen.add(url)
                deduped.append(src)

        # HEAD-check reachability
        urls = [s["url"] for s in deduped if s.get("url")]
        reachable_map = await self._check_reachability(urls)

        for src in deduped:
            src["reachable"] = reachable_map.get(src.get("url", ""), False)

        analysis["suggested_sources"] = deduped
        return analysis

    @staticmethod
    async def _search_duckduckgo(query: str) -> list[tuple[str, str]]:
        """Search DuckDuckGo HTML endpoint. Returns list of (url, title)."""
        results: list[tuple[str, str]] = []
        try:
            async with aiohttp.ClientSession(
                timeout=_SEARCH_TIMEOUT,
                headers={"User-Agent": _USER_AGENT},
            ) as session:
                async with session.post(
                    _DUCKDUCKGO_URL,
                    data={"q": query, "b": ""},
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "setup_analyzer.search_error",
                            status=resp.status,
                            query=query,
                        )
                        return results
                    html = await resp.text()

            soup = BeautifulSoup(html, "html.parser")
            for result in soup.select(".result__a"):
                raw_href = result.get("href", "")
                href: str = raw_href[0] if isinstance(raw_href, list) else str(raw_href or "")
                title = result.get_text(strip=True)
                # DuckDuckGo wraps URLs in a redirect — extract the actual URL
                if "uddg=" in href:
                    from urllib.parse import parse_qs, urlparse

                    parsed = urlparse(href)
                    qs = parse_qs(parsed.query)
                    actual = qs.get("uddg", [""])[0]
                    if actual:
                        href = actual
                if href and href.startswith("http"):
                    results.append((href, title))

        except Exception:
            logger.warning("setup_analyzer.search_exception", query=query, exc_info=True)

        return results

    @staticmethod
    async def _check_reachability(urls: list[str]) -> dict[str, bool]:
        """Parallel HEAD requests to check URL reachability."""
        if not urls:
            return {}

        results: dict[str, bool] = {}

        async def _check_one(session: aiohttp.ClientSession, url: str) -> None:
            try:
                async with session.head(url, allow_redirects=True) as resp:
                    if resp.status < 400:
                        results[url] = True
                        return
                    # HEAD rejected (403/405/etc) — fall back to GET with range
                    if resp.status in (403, 405, 501):
                        async with session.get(
                            url,
                            allow_redirects=True,
                            headers={"Range": "bytes=0-0"},
                        ) as get_resp:
                            results[url] = get_resp.status < 400
                            return
                    results[url] = False
            except Exception:
                results[url] = False

        async with aiohttp.ClientSession(
            timeout=_HEAD_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        ) as session:
            await asyncio.gather(*[_check_one(session, url) for url in urls])

        return results
