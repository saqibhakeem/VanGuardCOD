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
from app.db.models import (
    ApprovalRequest,
    ApprovalStatus,
    CallDirection,
    CallSession,
    CallStatus,
    Order,
    OrderStatus,
    Tenant,
    utcnow,
)
from app.db.session import get_session_factory
from app.security import normalize_phone
from app.services.twilio_client import TwilioClient
from app.services.whatsapp_client import WhatsAppClient

logger = logging.getLogger(__name__)


def _money(amount: float) -> str:
    return f"{amount:,.0f}"


def build_whatsapp_prompt(
    tenant: Tenant,
    order: Order,
    approvals: list[ApprovalRequest] | None = None,
) -> str:
    approval_section = ""
    if approvals:
        notes = []
        for app in approvals:
            if app.status == ApprovalStatus.REJECTED:
                notes.append(
                    f"- A previous request for '{app.tool_name.replace('_', ' ')}' was REJECTED by the store manager ({app.reason or 'Rejected by manager'}). "
                    f"CRITICAL: Do NOT call request_price_or_city_modification again for this request. Tell the customer the manager could not approve the change, and ask if they want to confirm the original order at PKR {_money(order.cod_amount)} or cancel."
                )
            elif app.status == ApprovalStatus.APPROVED:
                notes.append(
                    f"- A previous request for '{app.tool_name.replace('_', ' ')}' was APPROVED by the store manager. The order details reflect the approved changes."
                )
            elif app.status == ApprovalStatus.PENDING:
                notes.append(
                    f"- A request for '{app.tool_name.replace('_', ' ')}' is currently PENDING manager review. Tell the customer it is under review."
                )
        if notes:
            approval_section = "\nAPPROVAL HISTORY & MANAGER DECISIONS:\n" + "\n".join(notes) + "\n"

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
{approval_section}
WHATSAPP CHAT GUIDELINES:
1. Communicate in clear, friendly WhatsApp messages with appropriate emojis (🛍️, 📦, 📍, ✅, 🚚).
2. Support English, Urdu, or Roman Urdu matching the customer's language.
3. Keep each message concise (1 to 3 short sentences). Do not send giant walls of text.
4. If customer confirms (e.g. 'haan bhejdein', 'yes confirm', 'approved', 'theek hai original bhejdein'):
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
   - If a previous request for this alteration was REJECTED above, do NOT call request_price_or_city_modification. Remind them politely that the manager could not approve the change and ask if they want to proceed with the original order or cancel.
   - Otherwise, call request_price_or_city_modification to pause for manager review.
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


async def send_whatsapp_message(
    tenant: Tenant,
    recipient_phone: str,
    text_body: str,
) -> dict[str, Any]:
    """Dispatch an outgoing WhatsApp message to a customer via the store's configured provider."""
    if tenant.whatsapp_provider == "TWILIO":
        tw = TwilioClient(
            account_sid=tenant.twilio_account_sid or "mock_sid",
            auth_token=tenant.twilio_auth_token or "mock_token",
            default_from=tenant.twilio_from_number or "+14155238886",
        )
        return await tw.send_whatsapp_message(
            to_phone=recipient_phone,
            body=text_body,
        )
    else:
        wa = WhatsAppClient(
            phone_number_id=tenant.whatsapp_phone_number_id or "mock_phone_id",
            access_token=tenant.whatsapp_access_token or "mock_token",
            waba_id=tenant.whatsapp_waba_id,
        )
        try:
            return await wa.send_text_message(
                recipient_phone=recipient_phone,
                text_body=text_body,
            )
        except Exception as wa_err:
            logger.warning("Meta text send attempt note: %s. Attempting template fallback...", wa_err)
            try:
                return await wa.send_template_message(
                    recipient_phone=recipient_phone,
                    template_name="hello_world",
                )
            except Exception:
                raise wa_err


async def notify_customer_approval_resolution(
    approval: ApprovalRequest,
    approved: bool,
    resolution_note: str,
    db: Any,
) -> str | None:
    """Notify customer on WhatsApp when an approval request is approved or rejected by an admin."""
    order = approval.order
    session = approval.call_session
    tenant = await db.scalar(select(Tenant).where(Tenant.id == approval.tenant_id))
    if not order or not tenant:
        return None

    is_whatsapp = (
        (session and session.channel == "WHATSAPP")
        or (order.verification_channel == "WHATSAPP")
    )
    if not is_whatsapp:
        return None

    first_name = order.customer_name.split()[0] if order.customer_name else "Customer"

    if approved:
        message_text = (
            f"Assalam-o-Alaikum {first_name}! 🛍️\n\n"
            f"Great news regarding your order *{order.external_order_id}*! "
            f"Our store manager has *approved* your request ({resolution_note}). ✅\n\n"
            f"💵 *Payable COD Amount:* PKR {_money(order.cod_amount)}\n"
            f"📍 *Delivery Address:* {order.raw_address}\n\n"
            f"Your order is now updated and confirmed for dispatch! 🚚📦"
        )
    else:
        message_text = (
            f"Assalam-o-Alaikum {first_name}. 🛍️\n\n"
            f"Regarding your request for order *{order.external_order_id}*: "
            f"Our store manager reviewed your request, but unfortunately it was *not approved* ({resolution_note}). ❌\n\n"
            f"💵 *Payable COD Amount:* PKR {_money(order.cod_amount)}\n"
            f"📍 *Delivery Address:* {order.raw_address}\n\n"
            f"Would you like us to dispatch your original order, or would you prefer to cancel it?"
        )

    # Append to session transcript as assistant message so conversation history is maintained
    if session:
        transcript = list(session.transcript or [])
        transcript.append({
            "role": "assistant",
            "text": message_text,
            "channel": "WHATSAPP",
            "at": int(utcnow().timestamp() * 1000),
        })
        session.transcript = transcript
        session.status = CallStatus.ACTIVE

    try:
        await send_whatsapp_message(tenant, order.customer_phone, message_text)
        logger.info(
            "Dispatched approval resolution notice (%s) to %s for order %s",
            "APPROVED" if approved else "REJECTED",
            order.customer_phone,
            order.external_order_id,
        )
    except Exception as err:
        logger.warning("Failed to dispatch WhatsApp approval resolution notice: %s", err)

    return message_text


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
                CallSession.status.in_((CallStatus.ACTIVE, CallStatus.PAUSED_APPROVAL)),
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
        msg_result = await send_whatsapp_message(
            tenant=tenant,
            recipient_phone=order.customer_phone,
            text_body=greeting,
        )
        if tenant.whatsapp_provider == "TWILIO":
            order.provider_reference_id = msg_result.get("message_sid")
        else:
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

        # Find or create CallSession - check active or paused sessions first
        session = await db.scalar(
            select(CallSession).where(
                CallSession.order_id == order.id,
                CallSession.tenant_id == tenant.id,
                CallSession.channel == "WHATSAPP",
                CallSession.status.in_((CallStatus.ACTIVE, CallStatus.PAUSED_APPROVAL)),
            ).order_by(CallSession.created_at.desc()).limit(1)
        )
        if session is None:
            # Fallback to any recent WhatsApp session for this order
            session = await db.scalar(
                select(CallSession).where(
                    CallSession.order_id == order.id,
                    CallSession.tenant_id == tenant.id,
                    CallSession.channel == "WHATSAPP",
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
        else:
            if session.status == CallStatus.PAUSED_APPROVAL:
                session.status = CallStatus.ACTIVE

        # Check if there is an active PENDING approval for this order
        pending_approval = await db.scalar(
            select(ApprovalRequest).where(
                ApprovalRequest.order_id == order.id,
                ApprovalRequest.tenant_id == tenant.id,
                ApprovalRequest.status == ApprovalStatus.PENDING,
            ).order_by(ApprovalRequest.created_at.desc()).limit(1)
        )
        if pending_approval is not None:
            first_name = order.customer_name.split()[0] if order.customer_name else "Customer"
            hold_reply = (
                f"Assalam-o-Alaikum {first_name}! 🛍️\n\n"
                f"Your request is currently *under review* by our store manager. "
                f"We will notify you right here on WhatsApp as soon as it is approved or declined. "
                f"Thank you for your patience! ⏳"
            )
            transcript = list(session.transcript or [])
            transcript.append({
                "role": "user",
                "text": message_text,
                "channel": "WHATSAPP",
                "at": int(utcnow().timestamp() * 1000),
            })
            transcript.append({
                "role": "assistant",
                "text": hold_reply,
                "channel": "WHATSAPP",
                "at": int(utcnow().timestamp() * 1000),
            })
            session.transcript = transcript
            session.status = CallStatus.PAUSED_APPROVAL
            await db.commit()

            try:
                await send_whatsapp_message(tenant, order.customer_phone, hold_reply)
            except Exception as send_err:
                logger.warning("Error sending pending approval WhatsApp reply: %s", send_err)
            return hold_reply

        # Query recent approvals to provide context to the agent prompt
        latest_approvals = (await db.scalars(
            select(ApprovalRequest).where(
                ApprovalRequest.order_id == order.id,
                ApprovalRequest.tenant_id == tenant.id,
            ).order_by(ApprovalRequest.created_at.desc()).limit(3)
        )).all()

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
            elif r == "system" and t:
                history.append({"role": "user", "content": f"[SYSTEM UPDATE: {t}]"})

        # Initialize LLaMA 3.3 agent with WhatsApp prompt and tools
        gate = DatabaseApprovalGate(db=db, tenant=tenant, order=order, call_session=session)
        tool_ctx = ToolContext(db=db, tenant=tenant, order=order, call_session=session)
        registry = build_tool_registry(tool_ctx, tool_names=OUTBOUND_TOOL_NAMES)
        profile = AgentProfile(
            name="WhatsAppVerifierAgent",
            system_prompt=build_whatsapp_prompt(tenant, order, approvals=latest_approvals),
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
            await send_whatsapp_message(
                tenant=tenant,
                recipient_phone=order.customer_phone,
                text_body=reply_text,
            )
        except Exception as send_err:
            logger.warning("Error sending WhatsApp reply: %s", send_err)

        return reply_text
