"""Mock LLM client for testing — scriptable responses, records all calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from alec.agents.llm_client import LLMResponse, ToolCall, Usage


@dataclass
class RecordedCall:
    """A recorded LLM call for test assertions."""

    system: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None
    max_tokens: int


class MockLLMClient:
    """Scriptable mock LLM client.

    Usage:
        mock = MockLLMClient()
        mock.add_response(LLMResponse(
            content=[{"type": "text", "text": "Hello"}],
            text="Hello",
            stop_reason="end_turn",
        ))
        response = await mock.call(system="...", messages=[...])
        assert mock.calls[0].system == "..."
    """

    def __init__(self) -> None:
        self.calls: list[RecordedCall] = []
        self._responses: list[LLMResponse] = []
        self._default_response: LLMResponse | None = None

    def add_response(self, response: LLMResponse) -> None:
        """Queue a response. Responses are returned in order."""
        self._responses.append(response)

    def set_default_response(self, response: LLMResponse) -> None:
        """Set a default response used when the queue is empty."""
        self._default_response = response

    async def call(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Return the next queued response, recording the call."""
        self.calls.append(
            RecordedCall(
                system=system,
                messages=messages,
                tools=tools,
                max_tokens=max_tokens,
            )
        )

        if self._responses:
            return self._responses.pop(0)
        if self._default_response:
            return self._default_response
        return LLMResponse(
            content=[{"type": "text", "text": "No response configured"}],
            text="No response configured",
            stop_reason="end_turn",
            usage=Usage(input_tokens=100, output_tokens=10),
        )

    def make_tool_response(
        self,
        tool_calls: list[tuple[str, str, dict[str, Any]]],
        text: str = "",
    ) -> LLMResponse:
        """Helper to create a response with tool calls.

        Args:
            tool_calls: List of (id, name, input) tuples.
            text: Optional text content.
        """
        content: list[dict[str, Any]] = []
        parsed_tools: list[ToolCall] = []

        if text:
            content.append({"type": "text", "text": text})

        for tc_id, name, tc_input in tool_calls:
            content.append(
                {
                    "type": "tool_use",
                    "id": tc_id,
                    "name": name,
                    "input": tc_input,
                }
            )
            parsed_tools.append(ToolCall(id=tc_id, name=name, input=tc_input))

        return LLMResponse(
            content=content,
            text=text,
            tool_calls=parsed_tools,
            stop_reason="tool_use",
            usage=Usage(input_tokens=200, output_tokens=50),
        )

    def make_text_response(self, text: str) -> LLMResponse:
        """Helper to create a simple text response (end_turn)."""
        return LLMResponse(
            content=[{"type": "text", "text": text}],
            text=text,
            stop_reason="end_turn",
            usage=Usage(input_tokens=200, output_tokens=50),
        )
