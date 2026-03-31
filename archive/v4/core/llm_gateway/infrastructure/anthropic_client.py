"""Async wrapper for Anthropic API calls."""

import logging
from dataclasses import dataclass, field
from typing import Any

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

# Beta header required for prompt caching
PROMPT_CACHING_BETA = "prompt-caching-2024-07-31"


@dataclass
class ToolCall:
    """A tool call from the LLM."""

    id: str
    name: str
    input: dict[str, Any]


@dataclass
class LLMResponse:
    """Response from an LLM call."""

    content: str | None  # None if stop_reason is tool_use
    model: str
    usage: dict[str, int]
    stop_reason: str = "end_turn"
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_content: list[Any] = field(default_factory=list)


class AnthropicClient:
    """Async client wrapper for Anthropic API."""

    def __init__(self, api_key: str):
        """Initialize the Anthropic client.

        Args:
            api_key: Anthropic API key.
        """
        self._client = AsyncAnthropic(
            api_key=api_key,
            default_headers={"anthropic-beta": PROMPT_CACHING_BETA}
        )

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        system_prompt: str,
        temperature: float = 1.0,
        max_tokens: int = 4096,
        agent_name: str = "unknown",
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """Send a chat request to the Anthropic API.

        Args:
            model: Model name (e.g., claude-haiku-4-5-20251001).
            messages: List of message dicts with role and content.
            system_prompt: System prompt for the conversation.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            agent_name: Name of the calling agent (for logging).
            tools: Optional list of tool definitions for tool use.

        Returns:
            LLMResponse with content, tool_calls if any, and usage stats.

        Raises:
            Exception: If the API call fails.
        """
        try:
            # Use structured system format with cache_control for prompt caching
            # This caches the system prompt for ~5 minutes
            # Skip cache_control for empty system prompts (Anthropic API rejects them)
            if system_prompt:
                system_with_cache = [
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"}
                    }
                ]
            else:
                system_with_cache = []

            # Cache the first user message (contains AppWorld task description)
            # This is where most tokens are - caching saves 90% on subsequent turns
            # Find the first user message regardless of position (may have assistant messages before it)
            messages_with_cache = []
            first_user_cached = False
            for msg in messages:
                if not first_user_cached and msg.get("role") == "user":
                    # Cache the first user message
                    messages_with_cache.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": msg["content"],
                                "cache_control": {"type": "ephemeral"}
                            }
                        ]
                    })
                    first_user_cached = True
                else:
                    messages_with_cache.append(msg)  # type: ignore[arg-type]

            # Build API call kwargs
            api_kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system_with_cache,
                "messages": messages_with_cache,
            }
            if tools:
                api_kwargs["tools"] = tools

            response = await self._client.messages.create(**api_kwargs)

            # Extract text content and tool calls from response
            content = ""
            tool_calls: list[ToolCall] = []
            raw_content: list[Any] = []

            for block in response.content:
                raw_content.append(block)
                if hasattr(block, "text"):
                    content += block.text
                elif hasattr(block, "type") and block.type == "tool_use":
                    tool_calls.append(ToolCall(
                        id=block.id,
                        name=block.name,
                        input=block.input,
                    ))

            # Content is None if only tool calls were returned
            final_content = content if content else None

            # Extract usage including cache metrics
            cache_create = getattr(response.usage, "cache_creation_input_tokens", 0)
            cache_read = getattr(response.usage, "cache_read_input_tokens", 0)

            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "cache_creation_input_tokens": cache_create,
                "cache_read_input_tokens": cache_read,
            }

            # Log raw cache values (INFO level for debugging)
            logger.info(f"Cache metrics for '{agent_name}': create={cache_create}, read={cache_read}")

            # Log with cache info for cost analysis
            cache_info = ""
            if usage["cache_creation_input_tokens"]:
                cache_info = f", cache_created={usage['cache_creation_input_tokens']}"
            elif usage["cache_read_input_tokens"]:
                cache_info = f", cache_read={usage['cache_read_input_tokens']}"

            logger.info(
                f"LLM call completed for agent '{agent_name}': "
                f"input_tokens={usage['input_tokens']}, "
                f"output_tokens={usage['output_tokens']}{cache_info}"
            )

            return LLMResponse(
                content=final_content,
                model=model,
                usage=usage,
                stop_reason=response.stop_reason,
                tool_calls=tool_calls,
                raw_content=raw_content,
            )

        except Exception as e:
            logger.error(f"LLM call failed for agent '{agent_name}': {e}")
            raise
