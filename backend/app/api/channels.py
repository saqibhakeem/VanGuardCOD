"""Store communication channels configuration and credential validation endpoints.

Allows merchants to:
- Select verification channel: Twilio Voice, WhatsApp, or Both
- Configure BYOK API keys (Twilio Account SID/Auth Token, WhatsApp Phone Number ID/Access Token)
- Test credentials live against Twilio and Meta Graph APIs
- Set omnichannel escalation strategy (WhatsApp First or Voice First)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbDep, OptionalTenantDep, TenantDep
from app.db.models import Tenant
from app.schemas import (
    ChannelConfigOut,
    ChannelConfigRequest,
    TestTwilioRequest,
    TestTwilioResponse,
    TestWhatsAppRequest,
    TestWhatsAppResponse,
)
from app.services.twilio_client import TwilioClient
from app.services.whatsapp_client import WhatsAppClient

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("/config", response_model=ChannelConfigOut)
async def get_channel_config(tenant: TenantDep) -> ChannelConfigOut:
    """Retrieve current store communication channels configuration."""
    return ChannelConfigOut(
        channel_choice=tenant.channel_choice,
        twilio_account_sid=tenant.twilio_account_sid,
        twilio_from_number=tenant.twilio_from_number,
        has_twilio_auth_token=bool(tenant.twilio_auth_token),
        is_twilio_verified=tenant.is_twilio_verified,
        whatsapp_provider=tenant.whatsapp_provider,
        whatsapp_phone_number_id=tenant.whatsapp_phone_number_id,
        whatsapp_waba_id=tenant.whatsapp_waba_id,
        has_whatsapp_access_token=bool(tenant.whatsapp_access_token),
        is_whatsapp_verified=tenant.is_whatsapp_verified,
        omnichannel_strategy=tenant.omnichannel_strategy,
    )


@router.put("/config", response_model=ChannelConfigOut)
async def update_channel_config(
    payload: ChannelConfigRequest,
    db: DbDep,
    tenant: TenantDep,
) -> ChannelConfigOut:
    """Update store communication channels and BYOK provider credentials."""
    tenant.channel_choice = payload.channel_choice
    tenant.omnichannel_strategy = payload.omnichannel_strategy

    # Twilio fields
    if payload.twilio_account_sid is not None:
        tenant.twilio_account_sid = payload.twilio_account_sid.strip() or None
    if payload.twilio_auth_token is not None:
        tenant.twilio_auth_token = payload.twilio_auth_token.strip() or None
    if payload.twilio_from_number is not None:
        tenant.twilio_from_number = payload.twilio_from_number.strip() or None

    # WhatsApp fields
    tenant.whatsapp_provider = payload.whatsapp_provider
    if payload.whatsapp_phone_number_id is not None:
        tenant.whatsapp_phone_number_id = payload.whatsapp_phone_number_id.strip() or None
    if payload.whatsapp_access_token is not None:
        tenant.whatsapp_access_token = payload.whatsapp_access_token.strip() or None
    if payload.whatsapp_waba_id is not None:
        tenant.whatsapp_waba_id = payload.whatsapp_waba_id.strip() or None
    if payload.whatsapp_verify_token is not None:
        tenant.whatsapp_verify_token = payload.whatsapp_verify_token.strip() or None

    await db.commit()
    await db.refresh(tenant)

    return ChannelConfigOut(
        channel_choice=tenant.channel_choice,
        twilio_account_sid=tenant.twilio_account_sid,
        twilio_from_number=tenant.twilio_from_number,
        has_twilio_auth_token=bool(tenant.twilio_auth_token),
        is_twilio_verified=tenant.is_twilio_verified,
        whatsapp_provider=tenant.whatsapp_provider,
        whatsapp_phone_number_id=tenant.whatsapp_phone_number_id,
        whatsapp_waba_id=tenant.whatsapp_waba_id,
        has_whatsapp_access_token=bool(tenant.whatsapp_access_token),
        is_whatsapp_verified=tenant.is_whatsapp_verified,
        omnichannel_strategy=tenant.omnichannel_strategy,
    )


@router.post("/test-twilio", response_model=TestTwilioResponse)
async def test_twilio_connection(
    payload: TestTwilioRequest,
    db: DbDep,
    tenant: OptionalTenantDep = None,
) -> TestTwilioResponse:
    """Validate Twilio Account SID and Auth Token against Twilio Accounts API."""
    client = TwilioClient(
        account_sid=payload.account_sid,
        auth_token=payload.auth_token,
        default_from=payload.from_number,
    )
    result = await client.validate_credentials()
    if result.get("ok"):
        if tenant is not None:
            tenant.is_twilio_verified = True
            await db.commit()
        return TestTwilioResponse(
            ok=True,
            friendly_name=result.get("friendly_name"),
            account_status=result.get("account_status"),
        )
    return TestTwilioResponse(ok=False, error=result.get("error") or "Twilio authentication failed")


@router.post("/test-whatsapp", response_model=TestWhatsAppResponse)
async def test_whatsapp_connection(
    payload: TestWhatsAppRequest,
    db: DbDep,
    tenant: OptionalTenantDep = None,
) -> TestWhatsAppResponse:
    """Validate WhatsApp Cloud API or Twilio WhatsApp credentials."""
    if payload.provider == "TWILIO":
        sid = payload.twilio_account_sid or (tenant.twilio_account_sid if tenant else None)
        token = payload.twilio_auth_token or (tenant.twilio_auth_token if tenant else None)
        from_num = payload.twilio_whatsapp_from or payload.twilio_from_number or (tenant.twilio_from_number if tenant else None)
        if not sid or not token:
            return TestWhatsAppResponse(
                ok=False,
                error="Twilio Account SID and Auth Token are required for Twilio WhatsApp.",
            )
        tw_client = TwilioClient(account_sid=sid, auth_token=token, default_from=from_num)
        tw_res = await tw_client.validate_credentials()
        if tw_res.get("ok"):
            if tenant is not None:
                tenant.is_whatsapp_verified = True
                await db.commit()
            return TestWhatsAppResponse(
                ok=True,
                display_phone_number=from_num or "Twilio WhatsApp Sender",
                verified_name=tw_res.get("friendly_name"),
                quality_rating="CONNECTED",
            )
        return TestWhatsAppResponse(ok=False, error=tw_res.get("error") or "Twilio credentials invalid.")

    # Meta WhatsApp Cloud API
    phone_id = payload.phone_number_id or (tenant.whatsapp_phone_number_id if tenant else None)
    token = payload.access_token or (tenant.whatsapp_access_token if tenant else None)
    waba_id = payload.waba_id or (tenant.whatsapp_waba_id if tenant else None)
    if not phone_id or not token:
        return TestWhatsAppResponse(
            ok=False,
            error="Meta WhatsApp Phone Number ID and Access Token are required.",
        )

    wa_client = WhatsAppClient(
        phone_number_id=phone_id,
        access_token=token,
        waba_id=waba_id,
    )
    result = await wa_client.validate_credentials()
    if result.get("ok"):
        if tenant is not None:
            tenant.is_whatsapp_verified = True
            await db.commit()
        return TestWhatsAppResponse(
            ok=True,
            display_phone_number=result.get("display_phone_number"),
            verified_name=result.get("verified_name"),
            quality_rating=result.get("quality_rating"),
        )
    return TestWhatsAppResponse(ok=False, error=result.get("error") or "Meta WhatsApp verification failed.")
