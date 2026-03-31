"""Service configuration store that loads configs from PostgreSQL."""

import logging
from typing import Optional, TypedDict

import asyncpg

logger = logging.getLogger(__name__)


class _ServiceConfigDefaults(TypedDict):
    model: str
    temperature: float
    max_tokens: int
    system_prompt: str


# Default LLM configurations for services
# v3 Architecture: REFLECTOR handles turn analysis, ADVISOR normalizes tasks
DEFAULT_CONFIGS: dict[str, _ServiceConfigDefaults] = {
    "session": {
        "model": "claude-haiku-4-5-20251001",
        "temperature": 0.7,
        "max_tokens": 8192,
        "system_prompt": "You are a helpful AI assistant.",
    },
    "advisor": {
        "model": "claude-haiku-4-5-20251001",
        "temperature": 0.1,  # Very low - want consistent normalization
        "max_tokens": 100,   # Output is just "When [X]..."
        "system_prompt": "",  # Passed inline
    },
    "reflector": {
        "model": "claude-haiku-4-5-20251001",
        "temperature": 0.2,  # Low temp for consistent analysis
        "max_tokens": 4096,
        "system_prompt": "",  # REFLECTOR passes prompts inline
    },
    "strategist": {
        "model": "claude-haiku-4-5-20251001",
        "temperature": 0.4,  # Slightly higher for creative synthesis
        "max_tokens": 2048,  # Workflow solutions are concise
        "system_prompt": "",  # Passed inline for caching
    },
}


class ServiceConfig:
    """Configuration for a service's LLM calls."""

    def __init__(
        self,
        service_name: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: str,
    ):
        self.agent_name = service_name  # Keep agent_name for backward compatibility
        self.service_name = service_name
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt


class ConfigStore:
    """Stores and manages service configurations loaded from PostgreSQL."""

    def __init__(self):
        self._configs: dict[str, ServiceConfig] = {}
        self._pool: Optional[asyncpg.Pool] = None

    async def initialize(self, database_url: str) -> None:
        """Initialize the config store with a database connection.

        Args:
            database_url: PostgreSQL connection URL.
        """
        from core.common.postgres import create_pool
        self._pool = await create_pool(dsn=database_url)
        await self.reload_configs()
        logger.info("ConfigStore initialized with database connection")

    async def close(self) -> None:
        """Close the database connection pool."""
        if self._pool:
            await self._pool.close()
            logger.info("ConfigStore database connection closed")

    async def reload_configs(self) -> None:
        """Reload all service configurations from the database."""
        if not self._pool:
            raise RuntimeError("ConfigStore not initialized")

        # Start with default configs
        self._configs = {}
        for service_name, defaults in DEFAULT_CONFIGS.items():
            self._configs[service_name] = ServiceConfig(
                service_name=service_name,
                model=defaults["model"],
                temperature=defaults["temperature"],
                max_tokens=defaults["max_tokens"],
                system_prompt=defaults["system_prompt"],
            )

        # Override with values from service_configs table if present
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT service_name, parameter_name, parameter_value
                    FROM service_configs
                    WHERE parameter_name IN ('model', 'temperature', 'max_tokens')
                    """
                )

                for row in rows:
                    service_name = row["service_name"]
                    param_name = row["parameter_name"]
                    param_value = row["parameter_value"]

                    if service_name not in self._configs:
                        # Create config with defaults for unknown service
                        self._configs[service_name] = ServiceConfig(
                            service_name=service_name,
                            model="claude-haiku-4-20250514",
                            temperature=0.5,
                            max_tokens=4096,
                            system_prompt="You are a helpful AI assistant.",
                        )

                    config = self._configs[service_name]
                    if param_name == "model":
                        config.model = param_value
                    elif param_name == "temperature":
                        config.temperature = float(param_value)
                    elif param_name == "max_tokens":
                        config.max_tokens = int(param_value)

                # Load system prompts from service_prompts table if available
                prompt_rows = await conn.fetch(
                    """
                    SELECT service_name, prompt_content
                    FROM service_prompts
                    WHERE prompt_name = 'system_prompt' AND is_active = true
                    """
                )

                for row in prompt_rows:
                    service_name = row["service_name"]
                    if service_name in self._configs:
                        self._configs[service_name].system_prompt = row["prompt_content"]

        except Exception as e:
            logger.warning(f"Could not load configs from database: {e}. Using defaults.")

        logger.info(f"Loaded {len(self._configs)} service configurations")

    def get_config(self, service_name: str) -> Optional[ServiceConfig]:
        """Get configuration for a specific service.

        Args:
            service_name: Name of the service (also accepts agent_name for compatibility).

        Returns:
            ServiceConfig if found, None otherwise.
        """
        return self._configs.get(service_name)

    def list_agents(self) -> list[str]:
        """List all configured service names.

        Returns:
            List of service names.
        """
        return list(self._configs.keys())
