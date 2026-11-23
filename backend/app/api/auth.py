"""Authentication and authorization endpoints for the VanguardCOD SaaS merchant platform."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbDep, get_current_tenant
from app.config import get_settings
from app.db.models import Tenant
from app.schemas import (
    LoginRequest,
    LoginResponse,
    RegisterStoreRequest,
    RegisterStoreResponse,
    TenantOut,
    UserOut,
)
from app.security import hash_api_key

router = APIRouter(prefix="/auth", tags=["auth"])


USERS: dict[str, dict] = {
    "operator": {
        "id": "usr-vcod-op-101",
        "name": "Farhan Ahmed",
        "password": "operator123",
        "role": "VERIFICATION_OFFICER",
        "role_label": "COD Verification Specialist",
        "permissions": [
            "orders.view",
            "calls.trigger",
            "calls.verify",
            "sheets.view",
            "phone.dial",
        ],
    },
    "manager": {
        "id": "usr-vcod-mgr-201",
        "name": "Sarah Mansoor",
        "password": "manager123",
        "role": "LOGISTICS_MANAGER",
        "role_label": "Logistics & Risk Manager",
        "permissions": [
            "orders.view",
            "calls.trigger",
            "calls.verify",
            "approvals.resolve",
            "sheets.view",
            "analytics.view",
            "phone.dial",
        ],
    },
    "admin": {
        "id": "usr-vcod-adm-001",
        "name": "Tariq Malik",
        "password": "admin123",
        "role": "SYSTEM_ADMIN",
        "role_label": "Store Owner & Administrator",
        "permissions": [
            "orders.view",
            "calls.trigger",
            "calls.verify",
            "approvals.resolve",
            "sheets.view",
            "analytics.view",
            "config.manage",
            "webhooks.manage",
            "phone.dial",
        ],
    },
}


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, db: DbDep) -> LoginResponse:
    username = payload.username.strip().lower()
    user_info = USERS.get(username)
    if not user_info or payload.password != user_info["password"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password. Available demo users: operator, manager, admin",
        )

    if user_info.get("tenant_id"):
        tenant_id = user_info["tenant_id"]
        tenant_name = user_info["tenant_name"]
    else:
        settings = get_settings()
        tenant_key = payload.tenant_key or settings.default_tenant_api_key
        tenant = await db.scalar(
            select(Tenant).where(Tenant.api_key_hash == hash_api_key(tenant_key))
        )
        if tenant is None:
            tenant = await db.scalar(select(Tenant).limit(1))

        tenant_id = tenant.id if tenant else "tenant-default"
        tenant_name = tenant.name if tenant else "Karachi Threads & Textiles"

    token = f"vcod_jwt_{secrets.token_hex(16)}"
    return LoginResponse(
        token=token,
        user=UserOut(
            id=user_info["id"],
            username=username,
            name=user_info["name"],
            role=user_info["role"],
            role_label=user_info["role_label"],
            permissions=user_info["permissions"],
            tenant_id=tenant_id,
            tenant_name=tenant_name,
        ),
    )


@router.post("/register", response_model=RegisterStoreResponse)
async def register_store(
    payload: RegisterStoreRequest, db: DbDep, request: Request
) -> RegisterStoreResponse:
    store_name = payload.store_name.strip()
    username = payload.admin_username.strip().lower()

    if username in USERS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{username}' is already registered.",
        )

    existing_tenant = await db.scalar(
        select(Tenant).where(Tenant.name == store_name)
    )
    if existing_tenant:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Store '{store_name}' is already registered.",
        )

    raw_api_key = f"vcod_{secrets.token_urlsafe(24)}"
    api_key_hash = hash_api_key(raw_api_key)

    tenant = Tenant(
        name=store_name,
        api_key_hash=api_key_hash,
        default_language=payload.default_language,
        voice_persona=payload.voice_persona,
        max_auto_approve_cod=payload.max_auto_approve_cod,
        channel_choice=payload.channel_choice,
        twilio_account_sid=payload.twilio_account_sid,
        twilio_auth_token=payload.twilio_auth_token,
        twilio_from_number=payload.twilio_from_number,
        whatsapp_provider=payload.whatsapp_provider,
        whatsapp_phone_number_id=payload.whatsapp_phone_number_id,
        whatsapp_access_token=payload.whatsapp_access_token,
        whatsapp_waba_id=payload.whatsapp_waba_id,
        omnichannel_strategy=payload.omnichannel_strategy,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)

    user_id = f"usr-vcod-{secrets.token_hex(4)}"
    USERS[username] = {
        "id": user_id,
        "name": f"{store_name} Admin",
        "password": payload.password,
        "role": "SYSTEM_ADMIN",
        "role_label": f"Store Administrator ({store_name})",
        "permissions": [
            "orders.view",
            "calls.trigger",
            "calls.verify",
            "approvals.resolve",
            "sheets.view",
            "analytics.view",
            "config.manage",
            "webhooks.manage",
            "phone.dial",
        ],
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
    }

    base = str(request.base_url).rstrip("/")
    webhook_url = f"{base}/api/v1/webhooks/orders"
    token = f"vcod_jwt_{secrets.token_hex(16)}"

    return RegisterStoreResponse(
        token=token,
        api_key=raw_api_key,
        tenant=TenantOut.model_validate(tenant),
        user=UserOut(
            id=user_id,
            username=username,
            name=f"{store_name} Admin",
            role="SYSTEM_ADMIN",
            role_label=f"Store Administrator ({store_name})",
            permissions=USERS[username]["permissions"],
            tenant_id=tenant.id,
            tenant_name=tenant.name,
        ),
        webhook_url=webhook_url,
    )


@router.get("/me", response_model=UserOut)
async def get_me(
    db: DbDep,
    tenant: Tenant = Depends(get_current_tenant),
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
    x_sap_role: Annotated[str | None, Header(alias="X-SAP-Role")] = None,
) -> UserOut:
    role_key = (x_user_role or x_sap_role or "operator").strip().lower()
    user_info = USERS.get(role_key, USERS["operator"])

    return UserOut(
        id=user_info["id"],
        username=role_key if role_key in USERS else "operator",
        name=user_info["name"],
        role=user_info["role"],
        role_label=user_info["role_label"],
        permissions=user_info["permissions"],
        tenant_id=tenant.id,
        tenant_name=tenant.name,
    )
