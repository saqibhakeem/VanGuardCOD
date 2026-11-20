"""Inbound delivery rescue agent: prompt, greeting, and runtime wiring."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.hitl import DatabaseApprovalGate, build_persistence_sink
from app.agents.runtime import AgentProfile, AutonomousVoiceAgent, EventSink
from app.agents.tools import INBOUND_TOOL_NAMES, ToolContext, build_tool_registry
from app.db.models import CallSession, Order, Tenant

INBOUND_AGENT_NAME = "InboundRescueAgent"


def _money(amount: float) -> str:
    return f"{amount:,.0f}"


def build_system_prompt(tenant: Tenant, order: Order | None, caller_role: str) -> str:
    if order is not None:
        order_block = f"""LINKED ORDER CONTEXT:
- Reference: {order.external_order_id}
- Customer: {order.customer_name}
- Items: {order.items_summary}
- COD Amount: PKR {_money(order.cod_amount)}
- Address: {order.raw_address}
- Verified Landmark: {order.verified_landmark or "not captured yet"}
- Delivery Window: {order.delivery_window or "not captured yet"}
- Order Status: {order.status}"""
    else:
        order_block = """LINKED ORDER CONTEXT:
- No order loaded yet. Ask for the order number or phone number first."""

    return f"""You are the automated Delivery Rescue Voice Desk for {tenant.name}.
Incoming callers are either:
1. A Delivery Rider or Courier standing on the street needing landmark instructions or reporting a failed delivery attempt (locked gate, customer unreachable, wrong pin).
2. A Buyer calling to check order status, update their delivery time window, or modify their address.

{order_block}
Caller role for this session: {caller_role}.

STRICT VOICE CONVERSATION RULES:
1. Speak in ONE short sentence only (maximum 15 words). No markdown, lists, or rambling.
2. If no order is loaded yet, ask: "Could you please share your order number or phone number?" and call lookup_order_by_phone_or_ref.
3. For Delivery Riders: state the verified landmark clearly or call log_rider_delivery_attempt.
4. For Buyers: call reschedule_delivery_window or request_address_reroute.
5. After the linked order is known, every tool call must pass order_id as {order.id if order is not None else "the order_id returned by lookup_order_by_phone_or_ref"}. Never speak this identifier aloud.
"""


def build_greeting(tenant: Tenant) -> str:
    return (
        f"Thank you for calling {tenant.name} Delivery Rescue. "
        "Are you the customer or the delivery rider?"
    )


def build_profile(
    tenant: Tenant, order: Order | None, caller_role: str = "customer"
) -> AgentProfile:
    return AgentProfile(
        name=INBOUND_AGENT_NAME,
        system_prompt=build_system_prompt(tenant, order, caller_role),
        greeting=build_greeting(tenant),
    )


def build_context(
    tenant: Tenant,
    order: Order | None,
    call_session: CallSession,
    caller_role: str,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "tenant_id": tenant.id,
        "merchant_name": tenant.name,
        "call_session_id": call_session.id,
        "direction": call_session.direction,
        "caller_role": caller_role,
    }
    if order is not None:
        context.update(
            {
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
        )
    return context


def build_inbound_agent(
    db: AsyncSession,
    tenant: Tenant,
    order: Order | None,
    call_session: CallSession,
    *,
    caller_role: str = "customer",
    client: Any | None = None,
    on_event: EventSink | None = None,
    history: Sequence[dict[str, Any]] | None = None,
) -> AutonomousVoiceAgent:
    context = build_context(tenant, order, call_session, caller_role)
    registry = build_tool_registry(
        ToolContext(db=db, tenant=tenant, order=order, call_session=call_session),
        tool_names=INBOUND_TOOL_NAMES,
    )
    return AutonomousVoiceAgent(
        profile=build_profile(tenant, order, caller_role),
        registry=registry,
        context=context,
        client=client,
        history=history,
        approval_gate=DatabaseApprovalGate(db, tenant, order, call_session),
        on_event=build_persistence_sink(call_session, on_event),
    )
