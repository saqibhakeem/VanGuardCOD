"""Strict Pydantic tool schemas and handlers for outbound and inbound agents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.runtime import RegisteredTool, ToolExecutionError, ToolRegistry
from app.db.models import (
    CallSession,
    Order,
    OrderStatus,
    Tenant,
)
from app.db.session import append_transcript
from app.security import normalize_phone

OUTBOUND_TOOL_NAMES = (
    "confirm_cod_order",
    "cancel_cod_order",
    "request_price_or_city_modification",
)
INBOUND_TOOL_NAMES = (
    "lookup_order_by_phone_or_ref",
    "log_rider_delivery_attempt",
    "reschedule_delivery_window",
    "request_address_reroute",
)

_STRICT = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConfirmCodOrderArgs(BaseModel):
    model_config = _STRICT

    order_id: str = Field(min_length=1, max_length=36, description="Internal order UUID assigned to the linked call order. Never the external reference.")
    verified_landmark: str = Field(min_length=2, max_length=500)
    delivery_window: str = Field(min_length=2, max_length=64)


class CancelCodOrderArgs(BaseModel):
    model_config = _STRICT

    order_id: str = Field(min_length=1, max_length=36, description="Internal order UUID assigned to the linked call order. Never the external reference.")
    cancellation_reason: str = Field(min_length=2, max_length=500)


class RequestPriceOrCityModificationArgs(BaseModel):
    model_config = _STRICT

    order_id: str = Field(min_length=1, max_length=36, description="Internal order UUID assigned to the linked call order. Never the external reference.")
    new_address: str | None = Field(default=None, max_length=500, description="New delivery address if customer wants to change destination.")
    requested_cod_amount: float | None = Field(default=None, ge=0.0, description="New payable COD amount if customer requested a price alteration or discount.")
    reason: str = Field(default="Customer requested modification", min_length=2, max_length=500, description="Customer stated reason for alteration.")


class LookupOrderArgs(BaseModel):
    model_config = _STRICT

    query: str = Field(min_length=2, max_length=64)


class LogRiderDeliveryAttemptArgs(BaseModel):
    model_config = _STRICT

    order_id: str = Field(min_length=1, max_length=36, description="Internal order UUID assigned to the linked call order. Never the external reference.")
    rider_issue: str = Field(min_length=2, max_length=500)
    gps_note: str = Field(min_length=2, max_length=500)


class RescheduleDeliveryWindowArgs(BaseModel):
    model_config = _STRICT

    order_id: str = Field(min_length=1, max_length=36, description="Internal order UUID assigned to the linked call order. Never the external reference.")
    new_window: str = Field(min_length=2, max_length=64)
    updated_landmark: str = Field(min_length=2, max_length=500)


class RequestAddressRerouteArgs(BaseModel):
    model_config = _STRICT

    order_id: str = Field(min_length=1, max_length=36, description="Internal order UUID assigned to the linked call order. Never the external reference.")
    proposed_address: str = Field(min_length=5, max_length=500)
    caller_role: Literal["customer", "rider"]


@dataclass(slots=True)
class ToolContext:
    db: AsyncSession
    tenant: Tenant
    order: Order | None = None
    call_session: CallSession | None = None


def _order_snapshot(order: Order) -> dict[str, Any]:
    return {
        "order_id": order.id,
        "external_order_id": order.external_order_id,
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "raw_address": order.raw_address,
        "verified_landmark": order.verified_landmark,
        "delivery_window": order.delivery_window,
        "cod_amount": order.cod_amount,
        "status": order.status,
        "rto_risk_score": order.rto_risk_score,
    }


def _normalize_reference(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


async def _resolve_order(ctx: ToolContext, order_id: str) -> Order:
    if ctx.order is not None:
        reference = _normalize_reference(order_id)
        if ctx.order.id == order_id or reference in {
            _normalize_reference(ctx.order.id),
            _normalize_reference(ctx.order.external_order_id),
        }:
            return ctx.order
    order = await ctx.db.scalar(
        select(Order).where(Order.id == order_id, Order.tenant_id == ctx.tenant.id)
    )
    if order is None:
        raise ToolExecutionError("order_not_found")
    ctx.order = order
    return order


def _record(ctx: ToolContext, text: str) -> None:
    if ctx.call_session is not None:
        append_transcript(ctx.call_session, "system", text)


async def _confirm_approval_reason(
    ctx: ToolContext, args: ConfirmCodOrderArgs
) -> str | None:
    order = await _resolve_order(ctx, args.order_id)
    if order.cod_amount > ctx.tenant.max_auto_approve_cod:
        return (
            f"COD amount PKR {order.cod_amount:,.0f} exceeds the tenant auto-approve "
            f"limit of PKR {ctx.tenant.max_auto_approve_cod:,.0f}."
        )
    return None


async def _handle_confirm(ctx: ToolContext, args: ConfirmCodOrderArgs) -> dict[str, Any]:
    order = await _resolve_order(ctx, args.order_id)
    if order.status == OrderStatus.CANCELLED:
        raise ToolExecutionError("order_already_cancelled")
    order.verified_landmark = args.verified_landmark
    order.delivery_window = args.delivery_window
    order.status = OrderStatus.VERIFIED
    await ctx.db.flush()
    _record(
        ctx,
        f"Order {order.external_order_id} confirmed. Landmark: {args.verified_landmark}. "
        f"Window: {args.delivery_window}.",
    )
    return {
        "order_id": order.id,
        "external_order_id": order.external_order_id,
        "status": order.status,
        "verified_landmark": order.verified_landmark,
        "delivery_window": order.delivery_window,
        "message": "Order confirmed for dispatch.",
    }


async def _handle_cancel(ctx: ToolContext, args: CancelCodOrderArgs) -> dict[str, Any]:
    order = await _resolve_order(ctx, args.order_id)
    order.status = OrderStatus.CANCELLED
    await ctx.db.flush()
    _record(
        ctx,
        f"Order {order.external_order_id} cancelled. Reason: {args.cancellation_reason}.",
    )
    return {
        "order_id": order.id,
        "external_order_id": order.external_order_id,
        "status": order.status,
        "message": "Order cancelled.",
    }


async def _handle_price_or_city(
    ctx: ToolContext, args: RequestPriceOrCityModificationArgs
) -> dict[str, Any]:
    order = await _resolve_order(ctx, args.order_id)
    previous_address = order.raw_address
    previous_cod = order.cod_amount
    if args.new_address:
        order.raw_address = args.new_address
    if args.requested_cod_amount is not None:
        order.cod_amount = args.requested_cod_amount
    order.status = OrderStatus.PENDING_CALL
    await ctx.db.flush()
    _record(
        ctx,
        f"Approved modification for {order.external_order_id}: "
        f"address {previous_address} -> {order.raw_address}, "
        f"COD {previous_cod:,.0f} -> {order.cod_amount:,.0f}.",
    )
    return {
        "order_id": order.id,
        "external_order_id": order.external_order_id,
        "status": order.status,
        "raw_address": order.raw_address,
        "cod_amount": order.cod_amount,
        "message": "Approved modification applied; reconfirm delivery details with the customer.",
    }


async def _handle_lookup(ctx: ToolContext, args: LookupOrderArgs) -> dict[str, Any]:
    query = args.query.strip()
    normalized_phone = normalize_phone(query)
    statement = (
        select(Order)
        .where(
            Order.tenant_id == ctx.tenant.id,
            or_(
                Order.external_order_id.ilike(f"%{query}%"),
                Order.customer_phone == normalized_phone,
            ),
        )
        .order_by(Order.created_at.desc())
        .limit(5)
    )
    orders = (await ctx.db.scalars(statement)).all()
    if not orders:
        return {
            "found": False,
            "count": 0,
            "orders": [],
            "message": "No order matched that number or phone in this store.",
        }
    if len(orders) == 1:
        ctx.order = orders[0]
    return {
        "found": True,
        "count": len(orders),
        "orders": [_order_snapshot(order) for order in orders],
    }


async def _handle_rider_attempt(
    ctx: ToolContext, args: LogRiderDeliveryAttemptArgs
) -> dict[str, Any]:
    order = await _resolve_order(ctx, args.order_id)
    _record(
        ctx,
        f"Rider delivery attempt for {order.external_order_id}: {args.rider_issue}. "
        f"GPS note: {args.gps_note}.",
    )
    await ctx.db.flush()
    return {
        "order_id": order.id,
        "external_order_id": order.external_order_id,
        "status": order.status,
        "verified_landmark": order.verified_landmark,
        "delivery_window": order.delivery_window,
        "message": "Delivery attempt logged for operations follow-up.",
    }


async def _handle_reschedule(
    ctx: ToolContext, args: RescheduleDeliveryWindowArgs
) -> dict[str, Any]:
    order = await _resolve_order(ctx, args.order_id)
    order.delivery_window = args.new_window
    order.verified_landmark = args.updated_landmark
    order.status = OrderStatus.RESCHEDULED
    await ctx.db.flush()
    _record(
        ctx,
        f"Order {order.external_order_id} rescheduled to {args.new_window}. "
        f"Landmark: {args.updated_landmark}.",
    )
    return {
        "order_id": order.id,
        "external_order_id": order.external_order_id,
        "status": order.status,
        "delivery_window": order.delivery_window,
        "verified_landmark": order.verified_landmark,
        "message": "Delivery window rescheduled.",
    }


async def _handle_reroute(
    ctx: ToolContext, args: RequestAddressRerouteArgs
) -> dict[str, Any]:
    order = await _resolve_order(ctx, args.order_id)
    previous_address = order.raw_address
    order.raw_address = args.proposed_address
    order.status = OrderStatus.PENDING_CALL
    await ctx.db.flush()
    _record(
        ctx,
        f"Approved reroute for {order.external_order_id}: "
        f"{previous_address} -> {args.proposed_address} (caller role: {args.caller_role}).",
    )
    return {
        "order_id": order.id,
        "external_order_id": order.external_order_id,
        "status": order.status,
        "raw_address": order.raw_address,
        "message": "Approved reroute applied; confirm the new address with the caller.",
    }


def build_tool_registry(
    ctx: ToolContext,
    *,
    tool_names: Sequence[str] | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()

    candidates: dict[str, RegisteredTool] = {
        "confirm_cod_order": RegisteredTool(
            name="confirm_cod_order",
            description=(
                "Confirm the COD order for dispatch after the customer agrees and provides a "
                "delivery landmark and time window. High-value COD orders pause for approval."
            ),
            args_model=ConfirmCodOrderArgs,
            handler=lambda args: _handle_confirm(ctx, args),
            dynamic_approval_reason=lambda args: _confirm_approval_reason(ctx, args),
        ),
        "cancel_cod_order": RegisteredTool(
            name="cancel_cod_order",
            description="Cancel the COD order when the customer declines the delivery.",
            args_model=CancelCodOrderArgs,
            handler=lambda args: _handle_cancel(ctx, args),
        ),
        "request_price_or_city_modification": RegisteredTool(
            name="request_price_or_city_modification",
            description=(
                "Request a delivery address, city, sector, or COD price change. This always "
                "pauses for human operator approval before any database mutation."
            ),
            args_model=RequestPriceOrCityModificationArgs,
            handler=lambda args: _handle_price_or_city(ctx, args),
            requires_approval=True,
            approval_reason=(
                "Customer requested a delivery address or COD amount change that requires "
                "human operator review."
            ),
        ),
        "lookup_order_by_phone_or_ref": RegisteredTool(
            name="lookup_order_by_phone_or_ref",
            description="Find an order in this store by order reference or customer phone number.",
            args_model=LookupOrderArgs,
            handler=lambda args: _handle_lookup(ctx, args),
        ),
        "log_rider_delivery_attempt": RegisteredTool(
            name="log_rider_delivery_attempt",
            description=(
                "Log a rider's on-site delivery attempt issue such as a locked gate, wrong pin, "
                "or unreachable customer."
            ),
            args_model=LogRiderDeliveryAttemptArgs,
            handler=lambda args: _handle_rider_attempt(ctx, args),
        ),
        "reschedule_delivery_window": RegisteredTool(
            name="reschedule_delivery_window",
            description="Reschedule the delivery window and optionally refresh the landmark note.",
            args_model=RescheduleDeliveryWindowArgs,
            handler=lambda args: _handle_reschedule(ctx, args),
        ),
        "request_address_reroute": RegisteredTool(
            name="request_address_reroute",
            description=(
                "Request rerouting the shipment to a new address. This always pauses for human "
                "operator approval before any database mutation."
            ),
            args_model=RequestAddressRerouteArgs,
            handler=lambda args: _handle_reroute(ctx, args),
            requires_approval=True,
            approval_reason=(
                "Caller requested a shipment reroute to a different address, which requires "
                "human operator review."
            ),
        ),
    }

    selected = tuple(tool_names) if tool_names is not None else tuple(candidates)
    for name in selected:
        try:
            registry.register(candidates[name])
        except KeyError as exc:
            raise ValueError(f"unknown tool requested: {name}") from exc
    return registry
