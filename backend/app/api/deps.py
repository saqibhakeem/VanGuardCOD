"""Shared FastAPI dependencies and URL helpers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Tenant
from app.db.session import get_db
from app.security import hash_api_key

DbDep = Annotated[AsyncSession, Depends(get_db)]


async def get_current_tenant(
    db: DbDep,
    x_tenant_api_key: Annotated[str | None, Header(alias="X-Tenant-API-Key")] = None,
) -> Tenant:
    settings = get_settings()
    api_key = x_tenant_api_key or (
        settings.default_tenant_api_key if settings.allow_anonymous_tenant else None
    )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Tenant-API-Key header is required",
        )

    tenant = await db.scalar(
        select(Tenant).where(Tenant.api_key_hash == hash_api_key(api_key))
    )
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid tenant API key",
        )
    return tenant


TenantDep = Annotated[Tenant, Depends(get_current_tenant)]


async def get_optional_tenant(
    db: DbDep,
    x_tenant_api_key: Annotated[str | None, Header(alias="X-Tenant-API-Key")] = None,
) -> Tenant | None:
    settings = get_settings()
    api_key = x_tenant_api_key or (
        settings.default_tenant_api_key if settings.allow_anonymous_tenant else None
    )
    if not api_key:
        return None
    return await db.scalar(
        select(Tenant).where(Tenant.api_key_hash == hash_api_key(api_key))
    )


OptionalTenantDep = Annotated[Tenant | None, Depends(get_optional_tenant)]


def build_ws_url(request: Request, session_id: str) -> str:
    base = str(request.base_url).rstrip("/")
    if base.startswith("https://"):
        base = f"wss://{base[len('https://') :]}"
    elif base.startswith("http://"):
        base = f"ws://{base[len('http://') :]}"
    return f"{base}/ws/call/{session_id}"
