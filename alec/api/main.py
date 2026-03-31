"""ALEC API server entry point."""

from __future__ import annotations

from alec.api.app import create_app
from alec.config.settings import load_settings

app = create_app(load_settings())

if __name__ == "__main__":
    import uvicorn

    settings = load_settings()
    uvicorn.run(
        "alec.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
