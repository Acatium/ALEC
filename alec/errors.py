"""ALEC exception hierarchy."""


class AlecError(Exception):
    """Base exception for all ALEC errors."""


class ConfigError(AlecError):
    """Bad configuration or missing environment variables."""


class DatabaseError(AlecError):
    """Connection or query failures."""


class LLMError(AlecError):
    """API failures, rate limits, unexpected responses."""


class BudgetExhaustedError(AlecError):
    """Token or cost budget limit hit."""


class ToolError(AlecError):
    """Tool execution failure. Returned to LLM as error result so it can retry/adapt."""


class EntityResolutionError(AlecError):
    """GraphWriter entity deduplication failure."""


class ConsolidationError(AlecError):
    """Consolidation process failure."""
