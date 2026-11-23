"""Omnichannel Verification Dispatcher: routes COD verification to Twilio, WhatsApp, or Hybrid strategy."""

from __future__ import annotations

import logging
from typing import Any
from fastapi import Request
from sqlalchemy import select

from app.api.deps import build_ws_url
from app.db.models import CallDirection, CallSession, CallStatus, ChannelChoice, OmnichannelStrategy, Order, OrderStatus, Tenant, utcnow
from app.db.session import get_session_factory
from app.schemas import OrderOut
from app.services.twilio_client import TwilioClient
from app.services.whatsapp_agent import initiate_whatsapp_verification

logger = logging.getLogger(__name__)


async def dispatch_twilio_voice_call(
    order: Order,
    tenant: Tenant,
    request: Request,
) -> dict[str, Any]:
    """Place an outbound voice verification call via Twilio."""
    async with get_session_factory()() as db:
        # Check for existing active voice session
        existing = await db.scalar(
            select(CallSession).where(
                CallSession.tenant_id == tenant.id,
                CallSession.order_id == order.id,
                CallSession.channel == "VOICE",
                CallSession.status == CallStatus.ACTIVE,
            ).order_by(CallSession.created_at.desc()).limit(1)
        )
        if existing is not None:
            session = existing
        else:
            session = CallSession(
                tenant_id=tenant.id,
                order_id=order.id,
                direction=CallDirection.OUTBOUND_VERIFY,
                channel="VOICE",
                status=CallStatus.ACTIVE,
                transcript=[],
                tool_traces=[],
            )
            db.add(session)
            await db.flush()

        # Update order status
        current_order = await db.scalar(select(Order).where(Order.id == order.id))
        if current_order:
            current_order.status = OrderStatus.CALLING
            current_order.verification_channel = "VOICE"

        # Build public host URLs for Twilio
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "127.0.0.1:8100"
        scheme = "https" if request.headers.get("x-forwarded-proto") == "https" else "http"
        twiml_url = f"{scheme}://{host}/api/v1/twilio/voice/{session.id}/twiml"
        status_url = f"{scheme}://{host}/api/v1/twilio/voice/{session.id}/status"

        # Place call using Twilio REST API
        tw_client = TwilioClient(
            account_sid=tenant.twilio_account_sid or "mock_account_sid",
            auth_token=tenant.twilio_auth_token or "mock_auth_token",
            default_from=tenant.twilio_from_number or "+15005550006",
        )
        call_res = await tw_client.initiate_voice_call(
            to_phone=order.customer_phone,
            twiml_url=twiml_url,
            status_callback_url=status_url,
            timeout_seconds=25,
        )

        session.provider_call_sid = call_res.get("call_sid")
        if current_order:
            current_order.provider_reference_id = call_res.get("call_sid")

        await db.commit()
        await db.refresh(session)

        return {
            "session_id": session.id,
            "order_id": order.id,
            "channel": "VOICE",
            "provider": "TWILIO",
            "provider_call_sid": call_res.get("call_sid"),
            "status": "CALLING",
            "ws_url": build_ws_url(request, session.id),
        }


async def dispatch_order_verification(
    order_id: str,
    tenant_id: str,
    request: Request,
    preferred_channel: str | None = None,
) -> dict[str, Any]:
    """Omnichannel dispatch: dynamically determines best verification channel."""
    async with get_session_factory()() as db:
        order = await db.scalar(select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id))
        tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
        if not order or not tenant:
            raise ValueError("Order or Tenant not found")

    channel_to_use = preferred_channel or tenant.channel_choice

    if channel_to_use == ChannelChoice.WHATSAPP:
        res = await initiate_whatsapp_verification(order_id=order.id, tenant_id=tenant.id)
        return {
            "session_id": res["session_id"],
            "order_id": order.id,
            "channel": "WHATSAPP",
            "provider": tenant.whatsapp_provider,
            "provider_reference_id": res.get("provider_reference"),
            "status": "MESSAGING",
        }

    elif channel_to_use == ChannelChoice.TWILIO:
        return await dispatch_twilio_voice_call(order=order, tenant=tenant, request=request)

    else:
        # BOTH: Check omnichannel strategy
        if tenant.omnichannel_strategy == OmnichannelStrategy.VOICE_FIRST:
            return await dispatch_twilio_voice_call(order=order, tenant=tenant, request=request)
        else:
            # WHATSAPP_FIRST (Default cost-effective strategy)
            res = await initiate_whatsapp_verification(order_id=order.id, tenant_id=tenant.id)
            return {
                "session_id": res["session_id"],
                "order_id": order.id,
                "channel": "WHATSAPP",
                "provider": tenant.whatsapp_provider,
                "provider_reference_id": res.get("provider_reference"),
                "status": "MESSAGING",
            }
