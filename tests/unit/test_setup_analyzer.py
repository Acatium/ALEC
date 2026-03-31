"""Tests for setup analyzer service."""

from __future__ import annotations

import json

import pytest
from aioresponses import aioresponses

from alec.agents.mock_llm import MockLLMClient
from alec.services.setup_analyzer import SetupAnalyzer

# --- Fixtures ---


def _good_analysis() -> dict:
    return {
        "topics": [
            {
                "topic": "Data Platform Architecture",
                "description": "Cloud and on-prem data platform design",
                "covered_by": [],
                "coverage_level": "none",
                "importance": "critical",
            },
            {
                "topic": "Regulatory Compliance",
                "description": "Banking data regulations",
                "covered_by": ["web:https://bis.org"],
                "coverage_level": "full",
                "importance": "high",
            },
        ],
        "gaps": ["Data platform architecture is not covered by any source"],
        "search_queries": ["enterprise data platform architecture patterns"],
        "suggested_sources": [
            {
                "url": "https://cloud.google.com/architecture",
                "title": "Google Cloud Architecture",
                "reason": "Covers cloud data platform patterns",
                "covers_topics": ["Data Platform Architecture"],
            }
        ],
        "overall_assessment": (
            "Sources focus on regulatory compliance"
            " but lack technical architecture coverage."
        ),
    }


DUCKDUCKGO_HTML = """
<html><body>
<div class="result">
    <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fdata-platform&amp;rut=abc">
        Example Data Platform Guide
    </a>
</div>
<div class="result">
    <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Farchitecture&amp;rut=def">
        Architecture Best Practices
    </a>
</div>
</body></html>
"""


# --- _parse_analysis tests ---


class TestParseAnalysis:
    def test_clean_json(self) -> None:
        analysis = _good_analysis()
        text = json.dumps(analysis)
        result = SetupAnalyzer._parse_analysis(text)
        assert result["topics"][0]["topic"] == "Data Platform Architecture"
        assert len(result["gaps"]) == 1

    def test_markdown_fenced_json(self) -> None:
        analysis = _good_analysis()
        text = f"```json\n{json.dumps(analysis)}\n```"
        result = SetupAnalyzer._parse_analysis(text)
        assert result["topics"][0]["topic"] == "Data Platform Architecture"
        assert result["overall_assessment"].startswith("Sources focus on")

    def test_json_with_preamble(self) -> None:
        analysis = _good_analysis()
        text = f"Here is my analysis:\n\n{json.dumps(analysis)}\n\nHope this helps!"
        result = SetupAnalyzer._parse_analysis(text)
        assert len(result["topics"]) == 2

    def test_garbage_input(self) -> None:
        result = SetupAnalyzer._parse_analysis("This is not JSON at all. No braces here.")
        assert result["topics"] == []
        assert result["gaps"] == []
        assert "manually" in result["overall_assessment"]

    def test_invalid_json_with_braces(self) -> None:
        result = SetupAnalyzer._parse_analysis("Look at this { broken json }")
        assert result["topics"] == []


# --- analyze tests ---


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_calls_llm_with_correct_message(self) -> None:
        mock = MockLLMClient()
        analysis = _good_analysis()
        analysis["search_queries"] = []  # No search to avoid network calls
        analysis["suggested_sources"] = []
        mock.add_response(mock.make_text_response(json.dumps(analysis)))

        analyzer = SetupAnalyzer(mock)
        await analyzer.analyze(
            problem_statement="Build a data platform for banking",
            sources=["web:https://bis.org", "./docs/design"],
        )

        assert len(mock.calls) == 1
        user_msg = mock.calls[0].messages[0]["content"]
        assert "Build a data platform for banking" in user_msg
        assert "web:https://bis.org" in user_msg
        assert "./docs/design" in user_msg

    @pytest.mark.asyncio
    async def test_returns_safe_defaults_on_parse_failure(self) -> None:
        mock = MockLLMClient()
        mock.add_response(mock.make_text_response("I cannot help with that."))

        analyzer = SetupAnalyzer(mock)
        result = await analyzer.analyze(
            problem_statement="Some problem",
            sources=[],
        )

        assert result["topics"] == []
        assert result["gaps"] == []
        assert "manually" in result["overall_assessment"]

    @pytest.mark.asyncio
    async def test_no_sources_message(self) -> None:
        mock = MockLLMClient()
        analysis = _good_analysis()
        analysis["search_queries"] = []
        analysis["suggested_sources"] = []
        mock.add_response(mock.make_text_response(json.dumps(analysis)))

        analyzer = SetupAnalyzer(mock)
        await analyzer.analyze(problem_statement="Explore things", sources=[])

        user_msg = mock.calls[0].messages[0]["content"]
        assert "(no sources provided)" in user_msg


# --- DuckDuckGo parsing tests ---


class TestDuckDuckGoSearch:
    @pytest.mark.asyncio
    async def test_extracts_urls_from_html(self) -> None:
        with aioresponses() as m:
            m.post("https://html.duckduckgo.com/html/", body=DUCKDUCKGO_HTML)

            results = await SetupAnalyzer._search_duckduckgo("data platform architecture")

        assert len(results) == 2
        assert results[0][0] == "https://example.com/data-platform"
        assert results[0][1] == "Example Data Platform Guide"
        assert results[1][0] == "https://example.org/architecture"

    @pytest.mark.asyncio
    async def test_handles_search_error(self) -> None:
        with aioresponses() as m:
            m.post("https://html.duckduckgo.com/html/", status=503)

            results = await SetupAnalyzer._search_duckduckgo("test query")

        assert results == []

    @pytest.mark.asyncio
    async def test_handles_network_exception(self) -> None:
        with aioresponses() as m:
            m.post(
                "https://html.duckduckgo.com/html/",
                exception=Exception("Connection refused"),
            )

            results = await SetupAnalyzer._search_duckduckgo("test query")

        assert results == []


# --- Reachability tests ---


class TestReachability:
    @pytest.mark.asyncio
    async def test_reports_reachable_urls(self) -> None:
        with aioresponses() as m:
            m.head("https://example.com/good", status=200)
            m.head("https://example.com/bad", status=404)
            m.head("https://example.com/error", exception=Exception("timeout"))

            result = await SetupAnalyzer._check_reachability([
                "https://example.com/good",
                "https://example.com/bad",
                "https://example.com/error",
            ])

        assert result["https://example.com/good"] is True
        assert result["https://example.com/bad"] is False
        assert result["https://example.com/error"] is False

    @pytest.mark.asyncio
    async def test_falls_back_to_get_on_head_403(self) -> None:
        with aioresponses() as m:
            m.head("https://example.com/blocked", status=403)
            m.get("https://example.com/blocked", status=200)

            result = await SetupAnalyzer._check_reachability([
                "https://example.com/blocked",
            ])

        assert result["https://example.com/blocked"] is True

    @pytest.mark.asyncio
    async def test_falls_back_to_get_on_head_405(self) -> None:
        with aioresponses() as m:
            m.head("https://example.com/no-head", status=405)
            m.get("https://example.com/no-head", status=200)

            result = await SetupAnalyzer._check_reachability([
                "https://example.com/no-head",
            ])

        assert result["https://example.com/no-head"] is True

    @pytest.mark.asyncio
    async def test_empty_urls(self) -> None:
        result = await SetupAnalyzer._check_reachability([])
        assert result == {}


# --- Integration: analyze with search + reachability ---


class TestAnalyzeIntegration:
    @pytest.mark.asyncio
    async def test_full_flow(self) -> None:
        mock = MockLLMClient()
        analysis = _good_analysis()
        mock.add_response(mock.make_text_response(json.dumps(analysis)))

        with aioresponses() as m:
            m.post("https://html.duckduckgo.com/html/", body=DUCKDUCKGO_HTML)
            # HEAD checks for LLM-suggested + search-found sources
            m.head("https://cloud.google.com/architecture", status=200)
            m.head("https://example.com/data-platform", status=200)
            m.head("https://example.org/architecture", status=404)

            analyzer = SetupAnalyzer(mock)
            result = await analyzer.analyze(
                problem_statement="Build a data platform",
                sources=["web:https://bis.org"],
            )

        # LLM-suggested source + 2 search results = 3 total
        assert len(result["suggested_sources"]) == 3
        # Check reachability flags
        by_url = {s["url"]: s for s in result["suggested_sources"]}
        assert by_url["https://cloud.google.com/architecture"]["reachable"] is True
        assert by_url["https://example.com/data-platform"]["reachable"] is True
        assert by_url["https://example.org/architecture"]["reachable"] is False

    @pytest.mark.asyncio
    async def test_deduplicates_sources(self) -> None:
        mock = MockLLMClient()
        analysis = _good_analysis()
        # LLM suggests same URL that search will find
        analysis["suggested_sources"] = [
            {
                "url": "https://example.com/data-platform",
                "title": "LLM Suggested",
                "reason": "From LLM",
                "covers_topics": ["Data Platform Architecture"],
            }
        ]
        mock.add_response(mock.make_text_response(json.dumps(analysis)))

        with aioresponses() as m:
            m.post("https://html.duckduckgo.com/html/", body=DUCKDUCKGO_HTML)
            m.head("https://example.com/data-platform", status=200)
            m.head("https://example.org/architecture", status=200)

            analyzer = SetupAnalyzer(mock)
            result = await analyzer.analyze(
                problem_statement="Build a data platform",
                sources=[],
            )

        urls = [s["url"] for s in result["suggested_sources"]]
        # No duplicate — LLM's version kept, search duplicate removed
        assert urls.count("https://example.com/data-platform") == 1
        assert len(result["suggested_sources"]) == 2
