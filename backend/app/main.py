"""FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import approvals, auth, calls, channels, config, orders, twilio_voice, webhooks, whatsapp, ws_call
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

    application.include_router(auth.router, prefix=settings.api_prefix)
    application.include_router(webhooks.router, prefix=settings.api_prefix)
    application.include_router(orders.router, prefix=settings.api_prefix)
    application.include_router(calls.router, prefix=settings.api_prefix)
    application.include_router(approvals.router, prefix=settings.api_prefix)
    application.include_router(channels.router, prefix=settings.api_prefix)
    application.include_router(twilio_voice.router, prefix=settings.api_prefix)
    application.include_router(whatsapp.router, prefix=settings.api_prefix)
    application.include_router(config.router, prefix=settings.api_prefix)
    application.include_router(ws_call.router)


    if CONSOLE_DIR.is_dir():
        application.mount(
            "/console",
            StaticFiles(directory=CONSOLE_DIR, html=True),
            name="console",
        )

    @application.get("/", response_model=None)
    async def root(request: Request) -> dict[str, str] | RedirectResponse:
        accept = request.headers.get("accept", "")
        if "text/html" in accept and CONSOLE_DIR.is_dir():
            return RedirectResponse(url="/console/")
        return {
            "app": settings.app_name,
            "version": settings.app_version,
            "status": "ok",
        }

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/webhook")
    async def meta_webhook_challenge_root(
        hub_mode: str = Query(default="", alias="hub.mode"),
        hub_challenge: str = Query(default="", alias="hub.challenge"),
        hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    ) -> Response:
        return await whatsapp.verify_meta_webhook(hub_mode, hub_challenge, hub_verify_token)

    @application.post("/webhook")
    async def meta_webhook_receive_root(request: Request) -> dict[str, str]:
        return await whatsapp.receive_meta_whatsapp_message(request)

    @application.get("/softphone", include_in_schema=False)
    async def softphone() -> FileResponse:
        return FileResponse(STATIC_DIR / "softphone.html")

    return application


app = create_app()
