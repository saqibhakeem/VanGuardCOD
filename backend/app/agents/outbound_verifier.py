"""Outbound COD verification agent: prompt, greeting, and runtime wiring."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.hitl import DatabaseApprovalGate, build_persistence_sink
from app.agents.runtime import AgentProfile, AutonomousVoiceAgent, EventSink
from app.agents.tools import OUTBOUND_TOOL_NAMES, ToolContext, build_tool_registry
from app.db.models import CallSession, Order, Tenant

OUTBOUND_AGENT_NAME = "OutboundVerifierAgent"


def _money(amount: float) -> str:
    return f"{amount:,.0f}"


def build_system_prompt(tenant: Tenant, order: Order) -> str:
    return f"""You are an automated phone verification specialist calling on behalf of {tenant.name}.
You are speaking on a live phone call with {order.customer_name} regarding Cash-on-Delivery Order {order.external_order_id}.

ORDER CONTEXT:
- Items: {order.items_summary}
- COD Amount Payable on Delivery: PKR {_money(order.cod_amount)}
- Raw Checkout Address: {order.raw_address}
- Current Verified Landmark: {order.verified_landmark or "not captured yet"}
- Preferred Delivery Window: {order.delivery_window or "not captured yet"}
- RTO Risk Score: {order.rto_risk_score}/100

STRICT VOICE CONVERSATION RULES:
1. Speak in ONE short, punchy sentence only (maximum 15 words). Never ramble, lecture, or speak multiple sentences.
2. Confirm if {order.customer_name} placed order {order.external_order_id} for PKR {_money(order.cod_amount)}.
3. When confirmed, immediately call confirm_cod_order and say: "Great, your order is confirmed for delivery!"
4. If a landmark is needed, ask in one brief question: "Could you share a nearby landmark for the rider?"
5. If the customer cancels, call cancel_cod_order and say: "Understood, your order has been cancelled."
6. If the customer wants to modify price or city, call request_price_or_city_modification and say: "I forwarded your request for review."
7. Never repeat details already confirmed. Every tool call must pass order_id as {order.id}.
"""


def build_greeting(tenant: Tenant, order: Order) -> str:
    first_name = order.customer_name.split()[0]
    return (
        f"Assalam o Alaikum {first_name}, calling from {tenant.name} for order "
        f"{order.external_order_id} of PKR {_money(order.cod_amount)}. Should we dispatch it?"
    )


def build_profile(tenant: Tenant, order: Order) -> AgentProfile:
    return AgentProfile(
        name=OUTBOUND_AGENT_NAME,
        system_prompt=build_system_prompt(tenant, order),
        greeting=build_greeting(tenant, order),
    )


def build_context(
    tenant: Tenant, order: Order, call_session: CallSession
) -> dict[str, Any]:
    return {
        "tenant_id": tenant.id,
        "merchant_name": tenant.name,
        "call_session_id": call_session.id,
        "direction": call_session.direction,
        "order_id": order.id,
        "external_order_id": order.external_order_id,
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "cod_amount": order.cod_amount,
        "raw_address": order.raw_address,
        "verified_landmark": order.verified_landmark,
        "delivery_window": order.delivery_window,
        "rto_risk_score": order.rto_risk_score,
    }


def build_outbound_agent(
    db: AsyncSession,
    tenant: Tenant,
    order: Order,
    call_session: CallSession,
    *,
    client: Any | None = None,
    on_event: EventSink | None = None,
    history: Sequence[dict[str, Any]] | None = None,
) -> AutonomousVoiceAgent:
    context = build_context(tenant, order, call_session)
    registry = build_tool_registry(
        ToolContext(db=db, tenant=tenant, order=order, call_session=call_session),
        tool_names=OUTBOUND_TOOL_NAMES,
    )
    return AutonomousVoiceAgent(
        profile=build_profile(tenant, order),
        registry=registry,
        context=context,
        client=client,
        history=history,
        approval_gate=DatabaseApprovalGate(db, tenant, order, call_session),
        on_event=build_persistence_sink(call_session, on_event),
    )
