"""SESSION service FastAPI entry point (v3).

Uvicorn entry point with FastAPI lifespan management.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.session.api.evaluation_routes import router as evaluation_router
from core.session.api.library_routes import router as library_router
from core.session.api.routes import router as chat_router
from core.session.api.system_routes import router as system_router
from core.session.service import SessionService

# CORS configuration from environment
# Default to localhost origins for development
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001"
).split(",")

# Global service instance
service = SessionService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage service lifecycle."""
    await service.start()
    yield
    await service.stop()


# FastAPI application
app = FastAPI(
    title="ALEC Session Service",
    description="Pure orchestration: bullets -> LLM -> events",
    version="3.0.0",
    lifespan=lifespan,
)

# CORS middleware - restricted to configured origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)

# Include routers
app.include_router(chat_router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(library_router, prefix="/api/v1/library", tags=["library"])
app.include_router(evaluation_router, prefix="/api/v1/evaluation", tags=["evaluation"])
app.include_router(system_router, prefix="/api/v1/system", tags=["system"])


@app.get("/health")
async def health():
    """Health check endpoint."""
    return await service.health_check()


@app.get("/")
async def root():
    """Root endpoint."""
    return {"service": "session", "version": "3.0.0"}


def get_service() -> SessionService:
    """Get the global service instance (for dependency injection)."""
    return service


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8008"))
    uvicorn.run(app, host="0.0.0.0", port=port)
