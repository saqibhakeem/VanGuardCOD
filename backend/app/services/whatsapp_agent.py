"""Conversational WhatsApp Verification Agent service powered by LLaMA 3.3.

Provides full multi-turn conversational intelligence for WhatsApp:
- Outbound verification initiation
- Multi-turn customer natural language chat (English, Urdu, Roman Urdu)
- Direct tool execution:
  * confirm_cod_order
  * record_delivery_landmark
  * record_delivery_window
  * cancel_cod_order
  * request_price_or_city_modification (HITL approval gate)
- Transcripts, traces, and database state synchronization
"""

from __future__ import annotations

import logging
from typing import Any
from sqlalchemy import select

from app.agents.hitl import DatabaseApprovalGate, build_persistence_sink
from app.agents.runtime import AgentProfile, AutonomousVoiceAgent
from app.agents.tools import OUTBOUND_TOOL_NAMES, ToolContext, build_tool_registry
from app.config import get_settings
from app.db.models import CallDirection, CallSession, CallStatus, Order, OrderStatus, Tenant, utcnow
from app.db.session import get_session_factory
from app.security import normalize_phone
from app.services.twilio_client import TwilioClient
from app.services.whatsapp_client import WhatsAppClient

logger = logging.getLogger(__name__)


def _money(amount: float) -> str:
    return f"{amount:,.0f}"


def build_whatsapp_prompt(tenant: Tenant, order: Order) -> str:
    return f"""You are a professional, helpful WhatsApp customer service agent for {tenant.name}.
You are chatting on WhatsApp with {order.customer_name} regarding Cash-on-Delivery Order {order.external_order_id}.

ORDER DETAILS:
- Customer Name: {order.customer_name}
- Items: {order.items_summary}
- Payable COD Amount: PKR {_money(order.cod_amount)}
- Delivery Address: {order.raw_address}
- Verified Landmark: {order.verified_landmark or "Not provided yet"}
- Preferred Delivery Window: {order.delivery_window or "Not set"}
- RTO Risk Score: {order.rto_risk_score}/100

WHATSAPP CHAT GUIDELINES:
1. Communicate in clear, friendly WhatsApp messages with appropriate emojis (🛍️, 📦, 📍, ✅, 🚚).
2. Support English, Urdu, or Roman Urdu matching the customer's language.
3. Keep each message concise (1 to 3 short sentences). Do not send giant walls of text.
4. If customer confirms (e.g. 'haan bhejdein', 'yes confirm', 'approved'):
   - Call confirm_cod_order immediately.
   - If a landmark was provided in their message, also call record_delivery_landmark.
   - If landmark is missing, ask for a nearby landmark (e.g. Masjid, bank, chowk).
5. If customer provides a landmark (e.g. 'near Meezan Bank', 'opposite park'):
   - Call record_delivery_landmark immediately and confirm you noted it.
6. If customer specifies a delivery time (e.g. 'kal shaam 5 baje', 'tomorrow after 4pm'):
   - Call record_delivery_window.
7. If customer cancels (e.g. 'cancel kardo', 'no I changed mind', 'mistake'):
   - Call cancel_cod_order and acknowledge politely.
8. If customer wants to alter the price, order items, or change city:
   - Call request_price_or_city_modification to pause for manager review.
9. Every tool call must pass order_id as {order.id}.
"""


def build_whatsapp_greeting(tenant: Tenant, order: Order) -> str:
    first_name = order.customer_name.split()[0]
    return (
        f"Assalam-o-Alaikum {first_name}! 🛍️\n\n"
        f"This is {tenant.name} regarding your Cash-on-Delivery order *{order.external_order_id}*.\n\n"
        f"📦 *Items:* {order.items_summary}\n"
        f"💵 *Payable COD:* PKR {_money(order.cod_amount)}\n"
        f"📍 *Delivery Address:* {order.raw_address}\n\n"
        f"Could you please confirm if you would like us to dispatch this order? "
        f"If you have a nearby landmark (e.g. Masjid or market), please share that too! 🚚"
    )


async def initiate_whatsapp_verification(
    order_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """Start conversational WhatsApp verification for a COD order."""
    async with get_session_factory()() as db:
        order = await db.scalar(
            select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id)
        )
        tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
        if not order or not tenant:
            raise ValueError("Order or Tenant not found")

        # Find or create active WhatsApp call session
        session = await db.scalar(
            select(CallSession).where(
                CallSession.tenant_id == tenant.id,
                CallSession.order_id == order.id,
                CallSession.channel == "WHATSAPP",
                CallSession.status == CallStatus.ACTIVE,
            ).order_by(CallSession.created_at.desc()).limit(1)
        )
        if session is None:
            session = CallSession(
                tenant_id=tenant.id,
                order_id=order.id,
                direction=CallDirection.OUTBOUND_VERIFY,
                channel="WHATSAPP",
                status=CallStatus.ACTIVE,
                transcript=[],
                tool_traces=[],
            )
            db.add(session)
            await db.flush()

        greeting = build_whatsapp_greeting(tenant, order)

        # Append greeting to transcript
        transcript = list(session.transcript or [])
        transcript.append({
            "role": "assistant",
            "text": greeting,
            "channel": "WHATSAPP",
            "at": int(utcnow().timestamp() * 1000),
        })
        session.transcript = transcript

        order.status = OrderStatus.CALLING
        order.verification_channel = "WHATSAPP"
        order.delivery_status = "sent"

        # Dispatch outgoing message via tenant provider
        msg_result: dict[str, Any] = {}
        if tenant.whatsapp_provider == "TWILIO":
            tw = TwilioClient(
                account_sid=tenant.twilio_account_sid or "mock_sid",
                auth_token=tenant.twilio_auth_token or "mock_token",
                default_from=tenant.twilio_from_number or "+14155238886",
            )
            msg_result = await tw.send_whatsapp_message(
                to_phone=order.customer_phone,
                body=greeting,
            )
            order.provider_reference_id = msg_result.get("message_sid")
        else:
            wa = WhatsAppClient(
                phone_number_id=tenant.whatsapp_phone_number_id or "mock_phone_id",
                access_token=tenant.whatsapp_access_token or "mock_token",
                waba_id=tenant.whatsapp_waba_id,
            )
            msg_result = await wa.send_text_message(
                recipient_phone=order.customer_phone,
                text_body=greeting,
            )
            order.provider_reference_id = msg_result.get("message_id")

        await db.commit()
        await db.refresh(session)
        await db.refresh(order)

        logger.info("Outbound WhatsApp verification initiated for order %s (Session %s)", order.external_order_id, session.id)
        return {
            "session_id": session.id,
            "order_id": order.id,
            "channel": "WHATSAPP",
            "greeting": greeting,
            "provider_reference": order.provider_reference_id,
        }


async def handle_whatsapp_incoming_message(
    from_phone: str,
    message_text: str,
    provider: str = "META",
    tenant_id: str | None = None,
) -> str | None:
    """Process an incoming WhatsApp message from a customer and generate an AI response."""
    normalized_from = normalize_phone(from_phone)
    logger.info("Incoming WhatsApp message from %s: '%s'", normalized_from, message_text)

    async with get_session_factory()() as db:
        # Match order by customer_phone
        order_query = select(Order).where(Order.customer_phone == normalized_from)
        if tenant_id:
            order_query = order_query.where(Order.tenant_id == tenant_id)
        # Prefer orders that are CALLING, PENDING_CALL, or PENDING_RETRY
        order_query = order_query.order_by(Order.created_at.desc())
        orders = (await db.scalars(order_query)).all()

        if not orders:
            logger.warning("No order found matching customer phone %s", normalized_from)
            return None

        # Prioritize currently active or recently created order
        order = next(
            (o for o in orders if o.status in (OrderStatus.CALLING, OrderStatus.PENDING_CALL, OrderStatus.PENDING_RETRY)),
            orders[0],
        )

        tenant = await db.scalar(select(Tenant).where(Tenant.id == order.tenant_id))
        if not tenant:
            return None

        # Find or create CallSession
        session = await db.scalar(
            select(CallSession).where(
                CallSession.order_id == order.id,
                CallSession.tenant_id == tenant.id,
                CallSession.channel == "WHATSAPP",
                CallSession.status == CallStatus.ACTIVE,
            ).order_by(CallSession.created_at.desc()).limit(1)
        )
        if session is None:
            session = CallSession(
                tenant_id=tenant.id,
                order_id=order.id,
                direction=CallDirection.OUTBOUND_VERIFY,
                channel="WHATSAPP",
                status=CallStatus.ACTIVE,
                transcript=[],
                tool_traces=[],
            )
            db.add(session)
            await db.flush()

        # Append user message to transcript
        transcript = list(session.transcript or [])
        transcript.append({
            "role": "user",
            "text": message_text,
            "channel": "WHATSAPP",
            "at": int(utcnow().timestamp() * 1000),
        })

        # Build conversation history for LLaMA 3.3
        history: list[dict[str, str]] = []
        for entry in transcript[:-1]:
            r = str(entry.get("role") or "")
            t = str(entry.get("text") or "").strip()
            if r in ("user", "assistant") and t:
                history.append({"role": r, "content": t})

        # Initialize LLaMA 3.3 agent with WhatsApp prompt and tools
        gate = DatabaseApprovalGate(db=db, tenant=tenant, order=order, call_session=session)
        tool_ctx = ToolContext(db=db, tenant=tenant, order=order, call_session=session)
        registry = build_tool_registry(tool_ctx, tool_names=OUTBOUND_TOOL_NAMES)
        profile = AgentProfile(
            name="WhatsAppVerifierAgent",
            system_prompt=build_whatsapp_prompt(tenant, order),
            greeting="",
        )
        sink = build_persistence_sink(call_session=session)

        agent = AutonomousVoiceAgent(
            profile=profile,
            registry=registry,
            context={"tenant_id": tenant.id, "order_id": order.id, "customer_name": order.customer_name},
            approval_gate=gate,
            on_event=sink,
            history=history,
        )

        # Run multi-turn agent step
        turn = await agent.run_turn(message_text)
        reply_text = turn.text.strip() if turn.text else "Thank you for confirming your order!"

        # Append assistant response to transcript
        transcript.append({
            "role": "assistant",
            "text": reply_text,
            "channel": "WHATSAPP",
            "at": int(utcnow().timestamp() * 1000),
        })
        session.transcript = transcript

        # If order became verified, complete the session
        if order.status == OrderStatus.VERIFIED:
            session.status = CallStatus.COMPLETED

        await db.commit()
        await db.refresh(session)
        await db.refresh(order)

        # Send response back to customer on WhatsApp
        try:
            if tenant.whatsapp_provider == "TWILIO":
                tw = TwilioClient(
                    account_sid=tenant.twilio_account_sid or "mock_sid",
                    auth_token=tenant.twilio_auth_token or "mock_token",
                    default_from=tenant.twilio_from_number or "+14155238886",
                )
                await tw.send_whatsapp_message(to_phone=order.customer_phone, body=reply_text)
            else:
                wa = WhatsAppClient(
                    phone_number_id=tenant.whatsapp_phone_number_id or "mock_phone_id",
                    access_token=tenant.whatsapp_access_token or "mock_token",
                    waba_id=tenant.whatsapp_waba_id,
                )
                await wa.send_text_message(recipient_phone=order.customer_phone, text_body=reply_text)
        except Exception as send_err:
            logger.warning("Error sending WhatsApp reply: %s", send_err)

        return reply_text
