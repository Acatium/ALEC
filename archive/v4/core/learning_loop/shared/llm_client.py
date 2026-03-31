"""Async LLM client that routes calls through llm-gateway.

This replaces direct synchronous Anthropic calls with async HTTP requests
to the centralized llm-gateway service, preventing event loop blocking.
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://llm-gateway:8000")


@dataclass
class LLMResponse:
    """Response from LLM gateway."""

    content: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


class LLMClient:
    """Async client for LLM gateway.

    All calls are non-blocking and yield to the event loop during HTTP requests.
    This prevents GENERATOR from blocking ADVISOR during LLM calls.
    """

    def __init__(self, agent_name: str = "reflector"):
        """Initialize the LLM client.

        Args:
            agent_name: Agent name for config lookup in llm-gateway.
        """
        self.agent_name = agent_name
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        """Start the client (initialize HTTP client)."""
        await self._ensure_client()

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is initialized."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=10.0)  # 2 min for LLM calls
            )
        return self._client

    async def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Send chat request to llm-gateway.

        Args:
            messages: List of {"role": "user/assistant/system", "content": "..."}
            system_prompt: System prompt for the LLM (alternative to system message)
            temperature: Optional temperature override
            max_tokens: Optional max tokens override

        Returns:
            String content from LLM response.

        Raises:
            Exception: If the API call fails.
        """
        client = await self._ensure_client()

        # Extract system message if present in messages
        system_content = system_prompt
        filtered_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")
            else:
                filtered_messages.append(msg)

        # Build request payload
        payload = {
            "agent_name": self.agent_name,
            "messages": filtered_messages,
        }

        # Add system prompt if we have one
        if system_content:
            payload["system_prompt_override"] = system_content

        try:
            response = await client.post(
                f"{LLM_GATEWAY_URL}/api/v1/llm/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            content: str = data["content"]
            return content

        except httpx.HTTPStatusError as e:
            logger.error(
                f"LLM gateway HTTP error: {e.response.status_code} - {e.response.text}"
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"LLM gateway request error: {e}")
            raise
        except Exception as e:
            logger.error(f"LLM gateway unexpected error: {e}")
            raise

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
