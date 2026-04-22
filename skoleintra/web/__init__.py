from __future__ import annotations

from fastapi import FastAPI

from skoleintra.web.routes import router as web_router


def create_app() -> FastAPI:
    app = FastAPI(title="Skoleintra", version="0.1.0")
    app.include_router(web_router)
    return app

