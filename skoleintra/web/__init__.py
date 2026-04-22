from __future__ import annotations

from fastapi import FastAPI

from skoleintra.settings import Settings, get_settings
from skoleintra.web.routes import router as web_router


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Skoleintra", version="0.1.0")
    app.state.settings = settings or get_settings()
    app.include_router(web_router)
    return app

