"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alec.config.settings import Settings
from alec.db.pool import close_pool, create_pool
from alec.events.bus import EventBus

logger = structlog.get_logger()


def create_app(settings: Settings) -> FastAPI:
    """Create and configure the FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Startup
        pool = await create_pool(
            settings.database_url,
            min_size=settings.db_min_pool_size,
            max_size=settings.db_max_pool_size,
        )
        app.state.pool = pool
        app.state.settings = settings
        app.state.event_bus = EventBus()
        logger.info("api.startup", host=settings.api_host, port=settings.api_port)

        yield

        # Shutdown
        await close_pool(pool)
        logger.info("api.shutdown")

    app = FastAPI(
        title="ALEC API",
        version="5.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    from alec.api.routes.engagements import router as engagements_router
    from alec.api.routes.knowledge import router as knowledge_router
    from alec.api.routes.research import router as research_router
    from alec.api.routes.ws import router as ws_router

    app.include_router(engagements_router, prefix="/api")
    app.include_router(knowledge_router, prefix="/api")
    app.include_router(research_router, prefix="/api")
    app.include_router(ws_router, prefix="/api")

    return app
