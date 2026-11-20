"""FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import approvals, calls, config, orders, webhooks, ws_call
from app.config import get_settings
from app.db.session import dispose_database, init_db

STATIC_DIR = Path(__file__).resolve().parent / "static"
CONSOLE_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    await init_db(seed=settings.seed_on_startup)
    try:
        yield
    finally:
        await ws_call.cancel_pending_finalizers()
        await dispose_database()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Autonomous COD order verification and delivery rescue backend.",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(webhooks.router, prefix=settings.api_prefix)
    application.include_router(orders.router, prefix=settings.api_prefix)
    application.include_router(calls.router, prefix=settings.api_prefix)
    application.include_router(approvals.router, prefix=settings.api_prefix)
    application.include_router(config.router, prefix=settings.api_prefix)
    application.include_router(ws_call.router)

    if CONSOLE_DIR.is_dir():
        application.mount(
            "/console",
            StaticFiles(directory=CONSOLE_DIR, html=True),
            name="console",
        )

    @application.get("/")
    async def root() -> dict[str, str]:
        return {
            "app": settings.app_name,
            "version": settings.app_version,
            "status": "ok",
        }

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/softphone", include_in_schema=False)
    async def softphone() -> FileResponse:
        return FileResponse(STATIC_DIR / "softphone.html")

    return application


app = create_app()
