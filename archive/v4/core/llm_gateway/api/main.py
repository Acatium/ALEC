"""FastAPI application for the LLM Gateway service."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from core.llm_gateway.api import endpoints
from core.llm_gateway.infrastructure.anthropic_client import AnthropicClient
from core.llm_gateway.infrastructure.config_store import ConfigStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    # Startup
    database_url = os.getenv("DATABASE_URL")
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        raise RuntimeError("ANTHROPIC_API_KEY is required")

    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        raise RuntimeError("DATABASE_URL is required")

    # Initialize config store
    config_store = ConfigStore()
    await config_store.initialize(database_url)

    # Initialize Anthropic client
    anthropic_client = AnthropicClient(api_key)

    # Initialize embedding model in thread to not block startup
    import asyncio
    logger.info("Initializing embedding model...")
    await asyncio.to_thread(endpoints.init_embedding_model)

    # Set on endpoints module
    endpoints.config_store = config_store
    endpoints.anthropic_client = anthropic_client

    logger.info("LLM Gateway service started")

    yield

    # Shutdown
    await config_store.close()
    logger.info("LLM Gateway service stopped")


app = FastAPI(
    title="LLM Gateway",
    description="Centralized LLM (Anthropic) calls for ALEC services",
    version="1.0.0",
    lifespan=lifespan,
)

# Include API router
app.include_router(endpoints.router)


@app.get("/health")
async def health_check() -> JSONResponse:
    """Health check endpoint.

    Returns:
        JSON response with service status.
    """
    return JSONResponse(
        content={
            "status": "healthy",
            "service": "llm-gateway",
        }
    )
