"""Tests for mock LLM client."""

from __future__ import annotations

import pytest

from alec.agents.mock_llm import MockLLMClient


@pytest.mark.asyncio
async def test_records_calls():
    mock = MockLLMClient()
    mock.set_default_response(mock.make_text_response("ok"))

    await mock.call(system="sys", messages=[{"role": "user", "content": "hi"}])

    assert len(mock.calls) == 1
    assert mock.calls[0].system == "sys"
    assert mock.calls[0].messages[0]["content"] == "hi"


@pytest.mark.asyncio
async def test_queued_responses():
    mock = MockLLMClient()
    mock.add_response(mock.make_text_response("first"))
    mock.add_response(mock.make_text_response("second"))

    r1 = await mock.call(system="", messages=[])
    r2 = await mock.call(system="", messages=[])

    assert r1.text == "first"
    assert r2.text == "second"


@pytest.mark.asyncio
async def test_default_response():
    mock = MockLLMClient()
    mock.set_default_response(mock.make_text_response("default"))

    r = await mock.call(system="", messages=[])
    assert r.text == "default"


@pytest.mark.asyncio
async def test_tool_response():
    mock = MockLLMClient()
    resp = mock.make_tool_response(
        [
            ("tc1", "add_entity", {"name": "TestSvc", "entity_type": "service"}),
        ]
    )
    mock.add_response(resp)

    r = await mock.call(system="", messages=[])
    assert r.stop_reason == "tool_use"
    assert len(r.tool_calls) == 1
    assert r.tool_calls[0].name == "add_entity"
    assert r.tool_calls[0].input["name"] == "TestSvc"


@pytest.mark.asyncio
async def test_no_response_configured():
    mock = MockLLMClient()
    r = await mock.call(system="", messages=[])
    assert "No response configured" in r.text
    assert r.stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_usage_tracking():
    mock = MockLLMClient()
    resp = mock.make_text_response("hello")
    mock.add_response(resp)

    r = await mock.call(system="", messages=[])
    assert r.usage.input_tokens == 200
    assert r.usage.output_tokens == 50
    assert r.usage.total_tokens == 250
