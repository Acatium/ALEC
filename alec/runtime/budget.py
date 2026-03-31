"""Budget tracker — accumulates real token counts from LLM responses."""

from __future__ import annotations

import asyncio

import structlog

from alec.errors import BudgetExhaustedError

logger = structlog.get_logger()


class BudgetTracker:
    """Tracks token usage with warn and hard-stop thresholds.

    Thread-safe via asyncio.Lock.
    """

    def __init__(self, max_tokens: int = 100_000) -> None:
        self.max_tokens = max_tokens
        self.tokens_used = 0
        self._lock = asyncio.Lock()
        self._warned = False

    @property
    def tokens_remaining(self) -> int:
        return max(0, self.max_tokens - self.tokens_used)

    @property
    def usage_percent(self) -> float:
        if self.max_tokens == 0:
            return 100.0
        return (self.tokens_used / self.max_tokens) * 100.0

    async def record(self, input_tokens: int, output_tokens: int) -> None:
        """Record token usage. Raises BudgetExhaustedError at 100%."""
        async with self._lock:
            self.tokens_used += input_tokens + output_tokens

            if not self._warned and self.usage_percent >= 80.0:
                self._warned = True
                logger.warning(
                    "budget.threshold",
                    tokens_used=self.tokens_used,
                    tokens_remaining=self.tokens_remaining,
                    threshold_percent=80,
                )

            if self.tokens_used > self.max_tokens:
                raise BudgetExhaustedError(
                    f"Token budget exhausted: {self.tokens_used}/{self.max_tokens}"
                )

    def check(self) -> bool:
        """Return True if budget has remaining capacity."""
        return self.tokens_used < self.max_tokens

    def summary(self) -> dict[str, int | float]:
        """Return budget summary dict."""
        return {
            "tokens_used": self.tokens_used,
            "max_tokens": self.max_tokens,
            "tokens_remaining": self.tokens_remaining,
            "usage_percent": round(self.usage_percent, 1),
        }
