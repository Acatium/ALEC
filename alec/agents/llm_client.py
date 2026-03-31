"""LLM client protocol and Anthropic implementation with prompt caching."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import anthropic
import structlog

from alec.errors import LLMError

logger = structlog.get_logger()


@dataclass
class ToolCall:
    """A single tool call from the LLM."""

    id: str
    name: str
    input: dict[str, Any]


@dataclass
class Usage:
    """Token usage from an LLM response."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class LLMResponse:
    """Parsed LLM response."""

    content: list[dict[str, Any]]
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = ""
    usage: Usage = field(default_factory=Usage)


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM clients."""

    async def call(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Make an LLM call. Returns parsed response."""
        ...


class AnthropicLLMClient:
    """Anthropic API client with prompt caching and streaming."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001") -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def call(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Make a cached, streamed LLM call."""
        try:
            # Build system with cache control
            system_content = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

            # Build tools with cache control
            cached_tools = None
            if tools:
                cached_tools = []
                for i, tool in enumerate(tools):
                    t = dict(tool)
                    # Cache the last tool definition (Anthropic caches up to the breakpoint)
                    if i == len(tools) - 1:
                        t["cache_control"] = {"type": "ephemeral"}
                    cached_tools.append(t)

            kwargs: dict[str, Any] = {
                "model": self._model,
                "max_tokens": max_tokens,
                "system": system_content,
                "messages": messages,
            }
            if cached_tools:
                kwargs["tools"] = cached_tools

            response = await self._client.messages.create(**kwargs)

            return self._parse_response(response)

        except anthropic.APIError as e:
            logger.error("llm.api_error", error=str(e), status=getattr(e, "status_code", None))
            raise LLMError(f"Anthropic API error: {e}") from e

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse Anthropic response into our LLMResponse type."""
        content_blocks = []
        text_parts = []
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content_blocks.append({"type": "text", "text": block.text})
                text_parts.append(block.text)
            elif block.type == "tool_use":
                content_blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        input=block.input,
                    )
                )

        usage = Usage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read_input_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
            cache_creation_input_tokens=getattr(response.usage, "cache_creation_input_tokens", 0)
            or 0,
        )

        return LLMResponse(
            content=content_blocks,
            text="\n".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
            usage=usage,
        )
