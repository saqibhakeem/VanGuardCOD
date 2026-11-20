"""Call session bootstrap endpoints for outbound verification and inbound rescue."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select

from app.api.deps import DbDep, TenantDep, build_ws_url
from app.db.models import (
    CallDirection,
    CallSession,
    CallStatus,
    Order,
    OrderStatus,
)
from app.schemas import (
    CallDeclineResponse,
    CallSessionSummaryOut,
    CallTriggerResponse,
    InboundStartRequest,
    OrderOut,
)

router = APIRouter(prefix="/calls", tags=["calls"])


def _trigger_payload(request: Request, session: CallSession, order: Order) -> CallTriggerResponse:
    return CallTriggerResponse(
        session_id=session.id,
        ws_url=build_ws_url(request, session.id),
        direction=session.direction,
        status=session.status,
        order=OrderOut.from_order(order),
    )


@router.post(
    "/trigger-outbound/{order_id}",
    response_model=CallTriggerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def trigger_outbound_call(
    order_id: str,
    request: Request,
    db: DbDep,
    tenant: TenantDep,
) -> CallTriggerResponse:
    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.tenant_id == tenant.id)
    )
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="order not found"
        )

    existing = await db.scalar(
        select(CallSession)
        .where(
            CallSession.tenant_id == tenant.id,
            CallSession.order_id == order.id,
            CallSession.direction == CallDirection.OUTBOUND_VERIFY,
            CallSession.status == CallStatus.ACTIVE,
        )
        .order_by(CallSession.created_at.desc())
        .limit(1)
    )
    if existing is not None:
        return _trigger_payload(request, existing, order)

    session = CallSession(
        tenant_id=tenant.id,
        order_id=order.id,
        direction=CallDirection.OUTBOUND_VERIFY,
        status=CallStatus.ACTIVE,
        transcript=[],
        tool_traces=[],
    )
    db.add(session)
    if order.status == OrderStatus.PENDING_CALL:
        order.status = OrderStatus.CALLING
    await db.commit()
    await db.refresh(session)
    await db.refresh(order)
    return _trigger_payload(request, session, order)


@router.get("/sessions", response_model=list[CallSessionSummaryOut])
async def list_call_sessions(
    db: DbDep,
    tenant: TenantDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[CallSessionSummaryOut]:
    rows = (
        await db.execute(
            select(CallSession, Order)
            .join(Order, Order.id == CallSession.order_id)
            .where(CallSession.tenant_id == tenant.id)
            .order_by(CallSession.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        CallSessionSummaryOut(
            id=session.id,
            order_id=session.order_id,
            external_order_id=order.external_order_id,
            customer_name=order.customer_name,
            direction=session.direction,
            status=session.status,
            avg_turn_latency_ms=session.avg_turn_latency_ms,
            turn_count=sum(
                1
                for entry in session.transcript
                if entry.get("role") in {"user", "assistant"}
            ),
            created_at=session.created_at,
        )
        for session, order in rows
    ]


@router.get("/pending-outbound", response_model=list[CallTriggerResponse])
async def list_pending_outbound_calls(
    request: Request,
    db: DbDep,
    tenant: TenantDep,
) -> list[CallTriggerResponse]:
    sessions = (
        await db.scalars(
            select(CallSession)
            .where(
                CallSession.tenant_id == tenant.id,
                CallSession.direction == CallDirection.OUTBOUND_VERIFY,
                CallSession.status == CallStatus.ACTIVE,
            )
            .order_by(CallSession.created_at.desc())
            .limit(20)
        )
    ).all()
    pending = [session for session in sessions if not session.transcript]
    if not pending:
        return []

    order_ids = {session.order_id for session in pending}
    orders = {
        order.id: order
        for order in (
            await db.scalars(
                select(Order).where(
                    Order.tenant_id == tenant.id,
                    Order.id.in_(order_ids),
                )
            )
        ).all()
    }
    return [
        _trigger_payload(request, session, orders[session.order_id])
        for session in pending
        if session.order_id in orders
    ]


@router.post("/{session_id}/decline", response_model=CallDeclineResponse)
async def decline_call(
    session_id: str,
    db: DbDep,
    tenant: TenantDep,
) -> CallDeclineResponse:
    session = await db.scalar(
        select(CallSession).where(
            CallSession.id == session_id,
            CallSession.tenant_id == tenant.id,
        )
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="call session not found"
        )
    if session.status == CallStatus.ACTIVE:
        session.status = CallStatus.COMPLETED
        order = await db.scalar(
            select(Order).where(
                Order.id == session.order_id,
                Order.tenant_id == tenant.id,
            )
        )
        if order is not None and order.status == OrderStatus.CALLING:
            order.status = OrderStatus.PENDING_CALL
        await db.commit()
    return CallDeclineResponse(session_id=session.id, status=session.status)


@router.post(
    "/start-inbound",
    response_model=CallTriggerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_inbound_call(
    payload: InboundStartRequest,
    request: Request,
    db: DbDep,
    tenant: TenantDep,
) -> CallTriggerResponse:
    order: Order | None = None
    if payload.order_id is not None:
        order = await db.scalar(
            select(Order).where(Order.id == payload.order_id, Order.tenant_id == tenant.id)
        )
    elif payload.caller_phone is not None:
        order = await db.scalar(
            select(Order)
            .where(
                Order.tenant_id == tenant.id,
                Order.customer_phone == payload.caller_phone,
            )
            .order_by(Order.created_at.desc())
            .limit(1)
        )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no order found for this caller; provide order_id or a known phone number",
        )

    session = CallSession(
        tenant_id=tenant.id,
        order_id=order.id,
        direction=CallDirection.INBOUND_RESCUE,
        status=CallStatus.ACTIVE,
        transcript=[
            {
                "role": "system",
                "text": f"inbound caller role: {payload.caller_role}",
                "timestamp_ms": 0,
            }
        ],
        tool_traces=[],
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return _trigger_payload(request, session, order)
